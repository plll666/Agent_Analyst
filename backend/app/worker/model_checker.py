"""Запуск TLC как чёрного ящика: SANY, перебор, таймаут, лимит состояний.

Адаптер, а не домен: здесь всё, что ходит во внешний мир. Компиляция
``BehavioralModel`` в TLA+ лежит в ``app.domain.tla``, разбор вывода — в
``app.domain.tlc_output``, и оба проверяются без Java и без сети.

Сбой проверки здесь — значение, а не исключение: ``MODEL_INVALID``,
``TIMEOUT``, ``STATE_LIMIT_REACHED`` и ``ENGINE_ERROR`` возвращаются результатом,
потому что записать их должен фон, а не упавшая корутина.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
import signal
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.domain.behavioral_model import BehavioralModel, Property
from app.domain.expressions import Scalar
from app.domain.tla import MODULE_NAME, CompiledSpec, compile_model
from app.domain.tlc_output import parse_statistics, parse_trace
from app.domain.verification import (
    Counterexample,
    CounterexampleStep,
    Statistics,
    VerificationResult,
    VerificationStatus,
)

ENGINE_NAME = "TLC"
_SANY = "tla2sany.SANY"
_TLC = "tlc2.TLC"
_DEFAULT_JAR = "/opt/tla/tla2tools.jar"

_VERSION_LINE = re.compile(r"^TLC2? Version (?P<version>\S+)")
_INVARIANT_VIOLATION = re.compile(r"^Error: Invariant (?P<property>\w+) is violated", re.MULTILINE)
_TEMPORAL_VIOLATION = re.compile(
    r"^Error: Temporal property (?P<property>\w+) was violated\.", re.MULTILINE
)
_INITIAL_VIOLATION = re.compile(r"^Error: Invariant (?P<property>\w+) is violated", re.MULTILINE)
_PARSE_FAILED = "Could not parse module"
_DEADLOCK = "Deadlock reached"
_PROGRESS = re.compile(r"(?P<value>[\d,]+) states generated")
_POSIX = hasattr(os, "killpg")


@dataclass(frozen=True, slots=True)
class EngineSettings:
    """Параметры движка. Читаются из окружения один раз при создании адаптера."""

    jar: Path
    timeout_seconds: float
    state_limit: int
    workers: str
    work_dir: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> EngineSettings:
        """Собрать настройки из переменных окружения.

        Путь к jar по умолчанию — тот, что собирает Dockerfile в образе воркера.
        Локальный запуск задаёт ``TLA_TOOLS_JAR`` явно: путь из Dockerfile внутри
        контейнера на машине разработчика не существует.

        Args:
            env: Источник переменных; по умолчанию — окружение процесса.

        Returns:
            Настройки движка.
        """
        source = os.environ if env is None else env
        return cls(
            jar=Path(source.get("TLA_TOOLS_JAR", _DEFAULT_JAR)),
            timeout_seconds=float(source.get("CHECK_TIMEOUT_SECONDS", "120")),
            state_limit=int(source.get("STATE_LIMIT", "1000000")),
            workers=source.get("TLC_WORKERS", "auto"),
            work_dir=Path(source.get("TLA_WORK_DIR", tempfile.gettempdir())),
        )


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """Результат прогона, тексты, ушедшие на вход движку, и его вывод."""

    result: VerificationResult
    spec: CompiledSpec
    output: str


@dataclass(frozen=True, slots=True)
class _Execution:
    """Итог одного запуска внешнего процесса."""

    returncode: int | None
    output: str
    duration_ms: float
    timed_out: bool
    states_limit: int | None


@dataclass(frozen=True, slots=True)
class _SpecFiles:
    """Пути к записанным ``.tla`` и ``.cfg`` внутри рабочего каталога прогона."""

    tla: Path
    cfg: Path


class ModelChecker:
    """Прогон ``BehavioralModel`` через TLC.

    Один вызов ``check`` проверяет ровно одно свойство: у ``VerificationResult``
    одно поле ``property_id``, и по пачке свойств нельзя честно сказать, какое
    именно сработало.
    """

    def __init__(self, settings: EngineSettings) -> None:
        self._settings = settings

    @property
    def settings(self) -> EngineSettings:
        return self._settings

    async def check(self, model: BehavioralModel, prop: Property) -> CheckOutcome:
        """Скомпилировать модель и прогнать TLC по одному свойству.

        Args:
            model: Доменная модель прогона.
            prop: Проверяемое свойство.

        Returns:
            Результат проверки вместе со спецификацией, конфигурацией и выводом
            движка: по ним прогон воспроизводится вручную. Ни один сбой не
            поднимается наружу — он отражён в статусе результата.
        """
        spec = compile_model(model, prop)
        work_dir = Path(tempfile.mkdtemp(prefix="tlc-", dir=self._settings.work_dir))
        try:
            files = _materialize(spec, work_dir)
            invalid = await self._check_syntax(files.tla, prop)
            if invalid is not None:
                return CheckOutcome(result=invalid, spec=spec, output="")
            result, output = await self._explore(files, model, prop, spec)
            return CheckOutcome(result=result, spec=spec, output=output)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    async def _check_syntax(self, tla: Path, prop: Property) -> VerificationResult | None:
        """Разобрать спецификацию до прогона перебора.

        Нужен, чтобы отделить «модель не компилируется в TLA+» от «движок упал»:
        это разные статусы, и ``MODEL_INVALID`` не должен выдаваться за
        ``ENGINE_ERROR``.

        Args:
            tla: Записанный файл спецификации.
            prop: Проверяемое свойство.

        Returns:
            ``MODEL_INVALID`` либо ``ENGINE_ERROR`` при недоступном jar, иначе
            ``None`` — можно перебирать.
        """
        if not self._settings.jar.is_file():
            return self._engine_error(prop, f"tla2tools.jar не найден: {self._settings.jar}")
        run = await self._execute(self._java(_SANY) + [str(tla)])
        if run.returncode == 0:
            return None
        return VerificationResult(
            status=VerificationStatus.MODEL_INVALID,
            property_id=prop.id,
            engine=ENGINE_NAME,
            engine_version=_engine_version(run.output),
            duration_ms=0,
            error_detail=_tail(run.output),
        )

    async def _explore(
        self, files: _SpecFiles, model: BehavioralModel, prop: Property, spec: CompiledSpec
    ) -> tuple[VerificationResult, str]:
        """Перебрать состояния и превратить вывод TLC в результат проверки."""
        run = await self._execute(self._tlc_command(files))
        return self._classify(run, model, prop, spec), run.output

    def _classify(
        self, run: _Execution, model: BehavioralModel, prop: Property, spec: CompiledSpec
    ) -> VerificationResult:
        """Отнести вывод TLC к одному из шести статусов контракта.

        Нарушение свойства читается раньше ошибок движка: при нарушении TLC
        дописывает в вывод строки, похожие на сообщения об ошибке, и порядок
        проверок решает, не выдаст ли сломанная модель ``ENGINE_ERROR``.

        Полярность применяется последней: у ``reachable`` сгенерированный
        инвариант несёт отрицание, поэтому «нарушен» для движка означает
        «требование выполнено».

        Args:
            run: Итог запуска TLC.
            model: Модель прогона; её начальное состояние нужно там, где пути в
                контрпримере нет.
            prop: Проверяемое свойство.
            spec: Спецификация, по которой шёл прогон.

        Returns:
            Результат проверки по контракту.
        """
        version = _engine_version(run.output)
        statistics = parse_statistics(run.output)
        duration_ms = int(run.duration_ms)
        negated = spec.polarity == "negated"

        if run.states_limit is not None:
            return self._result(
                VerificationStatus.STATE_LIMIT_REACHED,
                prop,
                version,
                duration_ms,
                statistics,
                error_detail=f"перебор дорос до {run.states_limit} состояний "
                f"при лимите {self._settings.state_limit}",
            )
        if run.timed_out:
            return self._result(
                VerificationStatus.TIMEOUT,
                prop,
                version,
                duration_ms,
                statistics,
                error_detail=f"перебор не завершился за {self._settings.timeout_seconds:g} с",
            )

        violated = _violated_property(run.output)
        if violated is not None or _DEADLOCK in run.output:
            counterexample = parse_trace(run.output)
            if counterexample is None:
                return self._engine_error(
                    prop,
                    "TLC сообщил о нарушении, но трасса не разобрана, а PROPERTY_VIOLATED "
                    "без контрпримера — это ложь:\n" + _tail(run.output),
                    version,
                    duration_ms,
                )
            if negated:
                return self._result(
                    VerificationStatus.PROPERTY_HOLDS, prop, version, duration_ms, statistics
                )
            return self._result(
                VerificationStatus.PROPERTY_VIOLATED,
                prop,
                version,
                duration_ms,
                statistics,
                counterexample=counterexample,
                violated_property=violated,
            )

        if run.returncode == 0 and negated:
            return self._result(
                VerificationStatus.PROPERTY_VIOLATED,
                prop,
                version,
                duration_ms,
                statistics,
                counterexample=_unreachable_counterexample(model.initial),
                error_detail=(
                    "Состояние не достижимо: перебор исследовал пространство состояний целиком "
                    f"({statistics.states_generated if statistics else '?'} состояний) и ни "
                    "одно не удовлетворяет требованию. Пути к такому состоянию не существует, "
                    "поэтому контрпример ограничен начальным состоянием."
                ),
            )
        if run.returncode == 0:
            return self._result(
                VerificationStatus.PROPERTY_HOLDS, prop, version, duration_ms, statistics
            )
        if _PARSE_FAILED in run.output:
            return VerificationResult(
                status=VerificationStatus.MODEL_INVALID,
                property_id=prop.id,
                engine=ENGINE_NAME,
                engine_version=version,
                statistics=statistics,
                duration_ms=duration_ms,
                error_detail=_tail(run.output),
            )
        return self._result(
            VerificationStatus.ENGINE_ERROR,
            prop,
            version,
            duration_ms,
            statistics,
            error_detail=f"TLC завершился с кодом {run.returncode}:\n{_tail(run.output)}",
        )

    def _result(
        self,
        status: VerificationStatus,
        prop: Property,
        version: str | None,
        duration_ms: int,
        statistics: Statistics | None,
        *,
        counterexample: Counterexample | None = None,
        violated_property: str | None = None,
        error_detail: str | None = None,
    ) -> VerificationResult:
        return VerificationResult(
            status=status,
            property_id=violated_property or prop.id,
            engine=ENGINE_NAME,
            engine_version=version,
            statistics=statistics,
            counterexample=counterexample,
            duration_ms=duration_ms,
            error_detail=error_detail,
        )

    def _engine_error(
        self,
        prop: Property,
        detail: str,
        version: str | None = None,
        duration_ms: int = 0,
    ) -> VerificationResult:
        return VerificationResult(
            status=VerificationStatus.ENGINE_ERROR,
            property_id=prop.id,
            engine=ENGINE_NAME,
            engine_version=version,
            duration_ms=duration_ms,
            error_detail=detail,
        )

    def _java(self, entry: str) -> list[str]:
        """Префикс запуска движка: исполняемый файл, jar и точка входа."""
        return [os.getenv("JAVA_BIN", "java"), "-cp", str(self._settings.jar), entry]

    def _tlc_command(self, files: _SpecFiles) -> list[str]:
        """Команда перебора состояний.

        ``-deadlock`` подавляет собственный дедлок-отчёт TLC: свойство
        ``deadlock_free`` проверяется тем же механизмом инвариантов, и два
        независимых источника одного и того же вывода разойдутся. Лимит состояний
        не передаётся движку — у TLC нет такого ключа, а ``-maxSetSize`` относится
        к множествам симметрии; предел держит сам адаптер по строкам прогресса.

        ``-coverage 1`` заставляет TLC печатать прогресс перебора хотя бы раз в
        минуту: по этим строкам адаптер следит за лимитом состояний, и без них
        предел не срабатывал бы никогда.

        Args:
            files: Записанные ``.tla`` и ``.cfg``.

        Returns:
            Аргументы командной строки TLC.
        """
        return self._java(_TLC) + [
            "-deadlock",
            "-workers",
            self._settings.workers,
            "-coverage",
            "1",
            "-config",
            str(files.cfg),
            str(files.tla),
        ]

    async def _execute(self, command: list[str]) -> _Execution:
        """Запустить процесс под таймаутом и следить за ростом перебора.

        Процесс запускается в отдельной сессии и снимается целиком: ``kill`` только
        родителя оставил бы перебор работать в фоне.

        Args:
            command: Команда запуска внешнего процесса.

        Returns:
            Код возврата, объединённый вывод и признаки срабатывания ограничений.
        """
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=_POSIX,
        )
        started = asyncio.get_running_loop().time()
        collected: list[str] = []
        timed_out = False
        states_limit: int | None = None
        try:
            async with asyncio.timeout(self._settings.timeout_seconds):
                stdout = process.stdout
                if stdout is None:
                    raise RuntimeError("stdout процесса не перенаправлен")
                while chunk := await stdout.readline():
                    text = chunk.decode(errors="replace")
                    collected.append(text)
                    grown = _states_generated(text)
                    if grown is not None and grown > self._settings.state_limit:
                        states_limit = grown
                        break
        except TimeoutError:
            timed_out = True
        finally:
            await _terminate(process)
        duration_ms = (asyncio.get_running_loop().time() - started) * 1000
        return _Execution(
            returncode=process.returncode,
            output="".join(collected),
            duration_ms=duration_ms,
            timed_out=timed_out,
            states_limit=states_limit,
        )


def _materialize(spec: CompiledSpec, work_dir: Path) -> _SpecFiles:
    """Записать спецификацию и конфигурацию на диск.

    Имя файла обязано совпадать с именем модуля, иначе SANY отказывается разбирать
    файл.

    Args:
        spec: Собранная спецификация.
        work_dir: Каталог прогона.

    Returns:
        Пути к записанным файлам.
    """
    tla = work_dir / f"{MODULE_NAME}.tla"
    cfg = work_dir / f"{MODULE_NAME}.cfg"
    tla.write_text(spec.tla, encoding="utf-8")
    cfg.write_text(spec.cfg, encoding="utf-8")
    return _SpecFiles(tla=tla, cfg=cfg)


async def _terminate(process: asyncio.subprocess.Process) -> None:
    """Снять процесс и его группу, не оставив перебора работать в фоне.

    Args:
        process: Запущенный внешний процесс.
    """
    if process.returncode is None:
        if _POSIX:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            process.kill()
    with contextlib.suppress(ProcessLookupError):
        await process.wait()


def _states_generated(line: str) -> int | None:
    """Счётчик порождённых состояний из строки прогресса TLC.

    Args:
        line: Строка вывода TLC.

    Returns:
        Число состояний либо ``None``, если строка не про перебор.
    """
    found = _PROGRESS.search(line)
    return int(found.group("value").replace(",", "")) if found else None


def _violated_property(output: str) -> str | None:
    """Имя свойства, о нарушении которого сообщил TLC.

    Инвариант и темпоральное свойство TLC называет по-разному, а в результате у
    нас одно поле ``property_id``: имя должно достаться из вывода движка, а не
    подставляться молча.

    Args:
        output: Объединённый вывод TLC.

    Returns:
        Имя свойства либо ``None``.
    """
    for pattern in (_INVARIANT_VIOLATION, _TEMPORAL_VIOLATION, _INITIAL_VIOLATION):
        found = pattern.search(output)
        if found is not None:
            return found.group("property")
    return None


def _unreachable_counterexample(initial: Mapping[str, Scalar]) -> Counterexample:
    """Контрпример для недостижимого состояния.

    Пути к недостижимому состоянию не существует, и трассу печатать нечем: в
    контрпримере остаётся начальное состояние, из которого состояние не достигается.
    Оно берётся из самой модели, а не собирается на глаз, и сопровождается
    ``error_detail``, где сказано, что пространство состояний исследовано целиком.
    Без контрпримера статус ``PROPERTY_VIOLATED`` домен не принимает, а отчёт о
    находке был бы потерян.

    Args:
        initial: Начальные значения переменных из модели.

    Returns:
        Контрпример из одного начального состояния.
    """
    return Counterexample(
        steps=(CounterexampleStep(number=0, transition=None, state=dict(initial)),)
    )


def _engine_version(output: str) -> str | None:
    """Версия движка из его же вывода.

    Отдельный запрос версии у TLC невозможен: опции ``tlc2.TLC -version`` не
    существует, и вызов завершается ошибкой. Строка ``TLC2 Version ...`` есть в
    начале каждого прогона, поэтому версия читается оттуда и всегда соответствует
    тому, что реально запустилось.

    Args:
        output: Объединённый вывод TLC.

    Returns:
        Версия либо ``None``.
    """
    for line in output.splitlines():
        found = _VERSION_LINE.match(line.strip())
        if found is not None:
            return found.group("version")
    return None


def _tail(output: str, limit: int = 2000) -> str:
    """Хвост вывода для ``error_detail``: в текст ошибки попадает не всё.

    Args:
        output: Объединённый вывод TLC.
        limit: Сколько последних символов оставить.

    Returns:
        Хвост вывода.
    """
    return output[-limit:]
