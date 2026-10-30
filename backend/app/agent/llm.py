"""Клиент LLM: официальный SDK OpenAI и Instructor для структурного ответа.

Почему именно эти две библиотеки:

- **SDK OpenAI** — стандартный клиент для любого OpenAI-совместимого шлюза
  (у нас LiteLLM). Он отвечает за транспорт: соединения, таймауты, разбор
  конверта ``chat/completions`` и ошибки провайдера.
- **Instructor** — библиотека «Pydantic-модель из любой модели». Она добавляет
  схему ответа в запрос, проверяет ответ этой моделью и, если проверка не
  прошла, переспрашивает с текстом ошибки. Поэтому своего цикла «повторить с
  замечаниями» здесь нет.

Строгий режим structured output (``response_format: json_schema``) есть не у
всех провайдеров: в API DeepSeek у ``response_format.type`` допустимы только
``text`` и ``json_object``. Поэтому по умолчанию работает ``Mode.JSON`` —
``json_object`` плюс схема в запросе. Режим можно сменить переменной
``LLM_STRUCTURED_MODE``: ``json`` (по умолчанию), ``tools`` или ``json_schema``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

import httpx
import openai
from instructor import Mode, from_openai
from instructor.core.client import AsyncInstructor
from instructor.core.exceptions import InstructorRetryException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

_STRUCTURED_MODES: dict[str, Mode] = {
    "json": Mode.JSON,
    "tools": Mode.TOOLS,
    "json_schema": Mode.JSON_SCHEMA,
}


class LLMError(RuntimeError):
    """LLM не ответила или ответила так, что использовать его нельзя."""


class LLMConfigurationError(LLMError):
    """Провайдер не задан: не хватает адреса, модели, ключа или режима."""


class LLMResponseError(LLMError):
    """Модель ответила, но после всех попыток ответ не прошёл проверку."""

    def __init__(self, message: str, problems: list[str]) -> None:
        super().__init__(message)
        self.problems = problems


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """Параметры провайдера, прочитанные из окружения один раз на процесс."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    max_attempts: int
    structured_mode: str = "json"
    transport_retries: int = 2
    transport_backoff_seconds: float = 0.5
    reasoning_effort: str = "high"
    reasoning_supported: str = "auto"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMSettings:
        """Собрать настройки из переменных окружения.

        Args:
            env: Источник переменных; по умолчанию — окружение процесса.

        Returns:
            Настройки провайдера.
        """
        source = os.environ if env is None else env
        return cls(
            base_url=_api_root(source.get("LLM_BASE_URL", "")),
            api_key=source.get("LLM_API_KEY", "").strip(),
            model=source.get("LLM_MODEL", "").strip(),
            timeout_seconds=float(source.get("LLM_TIMEOUT_SECONDS", "180")),
            max_attempts=max(1, int(source.get("LLM_MAX_ATTEMPTS", "3"))),
            structured_mode=source.get("LLM_STRUCTURED_MODE", "json").strip().lower(),
            transport_retries=max(0, int(source.get("LLM_TRANSPORT_RETRIES", "2"))),
            transport_backoff_seconds=max(
                0.0, float(source.get("LLM_TRANSPORT_BACKOFF_SECONDS", "0.5"))
            ),
            reasoning_effort=source.get("LLM_REASONING_EFFORT", "high").strip() or "high",
            reasoning_supported=source.get("LLM_REASONING_SUPPORTED", "auto").strip().lower(),
        )

    @property
    def is_configured(self) -> bool:
        """Заданы ли все три обязательных значения."""
        return bool(self.base_url and self.api_key and self.model)

    def missing(self) -> list[str]:
        """Перечислить незаданные переменные — для понятного текста ошибки."""
        names = (
            ("LLM_BASE_URL", self.base_url),
            ("LLM_API_KEY", self.api_key),
            ("LLM_MODEL", self.model),
        )
        return [name for name, value in names if not value]


class LLMClient(Protocol):
    """Запрос к модели с ответом, проверенным Pydantic-моделью."""

    async def parse(
        self,
        response_model: type[ModelT],
        *,
        system: str,
        user: str,
        prompt_version: str,
        attempts: int,
        context: Mapping[str, Any] | None = None,
        reasoning: bool | None = None,
    ) -> ModelT:
        """Получить ответ модели в виде заполненной Pydantic-модели.

        Args:
            response_model: Модель ответа; она же становится схемой запроса.
            system: Системная инструкция.
            user: Пользовательское сообщение с данными задачи.
            prompt_version: Версия промпта — попадает в лог вместе с числом токенов.
            attempts: Сколько всего попыток сделать, включая первую.
            context: Контекст проверки для валидаторов модели ответа.
            reasoning: Рассуждать ли модели до ответа; ``None`` — оставить
                поведение провайдера по умолчанию.

        Returns:
            Проверенный ответ модели.
        """
        ...

    async def aclose(self) -> None:
        """Освободить соединения клиента."""
        ...


LLMFactory = Callable[[], LLMClient]
"""Фабрика клиента: зависимость API, чтобы права проверялись до сети."""


class OpenAILLMClient:
    """Клиент на официальном SDK OpenAI, структура ответа — через Instructor."""

    def __init__(self, settings: LLMSettings, http_client: httpx.AsyncClient | None = None) -> None:
        mode = _STRUCTURED_MODES.get(settings.structured_mode)
        if mode is None:
            raise LLMConfigurationError(
                f"LLM_STRUCTURED_MODE={settings.structured_mode!r}: допустимы "
                + ", ".join(sorted(_STRUCTURED_MODES))
            )
        self._settings = settings
        # Повторы разделены: временные отказы провайдера (сеть, таймаут, 429,
        # 5xx) повторяет сам клиент с паузой (``transport_retries``), Instructor
        # — негодный ответ модели, до ``attempts`` попыток. Встроенные повторы
        # SDK выключены: иначе один и тот же отказ умножался бы на два счётчика.
        self._api = openai.AsyncOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout_seconds,
            max_retries=0,
            http_client=http_client,
        )
        self._client: AsyncInstructor = from_openai(self._api, mode=mode)

    async def aclose(self) -> None:
        """Закрыть соединения SDK."""
        await self._api.close()

    async def parse(
        self,
        response_model: type[ModelT],
        *,
        system: str,
        user: str,
        prompt_version: str,
        attempts: int,
        context: Mapping[str, Any] | None = None,
        reasoning: bool | None = None,
    ) -> ModelT:
        """Запросить ответ и вернуть его проверенной моделью.

        Args:
            response_model: Модель ответа; она же становится схемой запроса.
            system: Системная инструкция.
            user: Пользовательское сообщение с данными задачи.
            prompt_version: Версия промпта — попадает в лог вместе с числом токенов.
            attempts: Сколько всего попыток сделать, включая первую.
            context: Контекст проверки для валидаторов модели ответа.
            reasoning: Рассуждать ли модели до ответа; ``None`` — оставить
                поведение провайдера по умолчанию.

        Returns:
            Проверенный ответ модели.

        Raises:
            LLMResponseError: за отведённые попытки пригодный ответ не получился.
            LLMError: провайдер недоступен или отказал в запросе.
        """
        started = time.monotonic()
        extra_body = _reasoning_body(self._settings, reasoning)
        transport_attempt = 0
        while True:
            try:
                parsed, completion = await self._client.chat.completions.create_with_completion(
                    model=self._settings.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_model=response_model,
                    # После транспортного повтора переспрашивать модель о
                    # структуре незачем: повторяем ровно один запрос.
                    max_retries=0 if transport_attempt else max(0, attempts - 1),
                    context=dict(context) if context else None,
                    temperature=0,
                    extra_body=extra_body,
                )
            except InstructorRetryException as error:
                refusal = _provider_error(error)
                if refusal is None:
                    _log_call(self._settings.model, prompt_version, started, error.last_completion)
                    logger.warning(
                        "llm: prompt_version=%s no usable answer in %s attempts",
                        prompt_version,
                        attempts,
                    )
                    raise LLMResponseError(
                        f"LLM не вернула пригодный ответ за {attempts} попыток",
                        _problems(error),
                    ) from error
                if _is_retryable_refusal(refusal) and await self._pause_before_retry(
                    transport_attempt, refusal
                ):
                    transport_attempt += 1
                    continue
                _log_call(self._settings.model, prompt_version, started, error.last_completion)
                raise LLMError(f"запрос к LLM не удался: {refusal}") from error
            except openai.OpenAIError as error:
                if _is_retryable_refusal(error) and await self._pause_before_retry(
                    transport_attempt, error
                ):
                    transport_attempt += 1
                    continue
                _log_call(self._settings.model, prompt_version, started, None)
                raise LLMError(f"запрос к LLM не удался: {error}") from error
            _log_call(self._settings.model, prompt_version, started, completion)
            return parsed

    async def _pause_before_retry(self, attempt: int, error: BaseException) -> bool:
        """Выдержать паузу перед повтором временного отказа провайдера.

        Returns:
            ``True``, если повтор разрешён; ``False`` — попытки исчерпаны.
        """
        if attempt >= self._settings.transport_retries:
            return False
        delay = self._settings.transport_backoff_seconds * (2**attempt)
        logger.warning(
            "llm: временный отказ провайдера (%s), повтор %s/%s через %.1f с",
            error,
            attempt + 1,
            self._settings.transport_retries,
            delay,
        )
        if delay > 0:
            await asyncio.sleep(delay)
        return True


def client_from_env(env: Mapping[str, str] | None = None) -> LLMClient:
    """Создать клиента по настройкам окружения.

    Args:
        env: Источник переменных; по умолчанию — окружение процесса.

    Returns:
        Готовый клиент; вызывающая сторона обязана его закрыть.

    Raises:
        LLMConfigurationError: не заданы адрес, модель или ключ.
    """
    settings = LLMSettings.from_env(env)
    if not settings.is_configured:
        raise LLMConfigurationError("LLM не настроена: не заданы " + ", ".join(settings.missing()))
    return OpenAILLMClient(settings)


def _api_root(base_url: str) -> str:
    """Привести адрес к корню API: база может включать ``/chat/completions``."""
    url = base_url.strip().rstrip("/")
    suffix = "/chat/completions"
    return url[: -len(suffix)] if url.endswith(suffix) else url


def _provider_error(error: BaseException) -> openai.OpenAIError | None:
    """Найти отказ провайдера в цепочке причин.

    Instructor переспрашивает и на ошибках транспорта, а в ``failed_attempts``
    кладёт только нарушения проверки. Поэтому отказ ищется по цепочке причин:
    таймаут, 429 или 5xx — это отказ провайдера, а не «плохой ответ модели».
    """
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, openai.OpenAIError):
            return current
        current = current.__cause__ or current.__context__
    return None


def _reasoning_body(settings: LLMSettings, reasoning: bool | None) -> dict[str, Any] | None:
    """Параметр рассуждений для тела запроса.

    ``reasoning_effort`` понимает и сам DeepSeek (``none`` выключает
    рассуждения), и OpenAI-совместимые шлюзы. Если пользователь не выбирал
    режим, параметр не передаётся: остаётся поведение провайдера.
    """
    if reasoning is None:
        return None
    return {"reasoning_effort": settings.reasoning_effort if reasoning else "none"}


def _is_retryable_refusal(error: openai.OpenAIError) -> bool:
    """Временный отказ провайдера, а не ответ по существу запроса.

    Сюда относятся сетевые сбои и таймауты, ограничение частоты (429) и
    серверные ошибки (5xx). Остальные ответы — например, 400 или 401 — не
    повторяются: повтор не исправит неверный запрос или ключ.
    """
    if isinstance(error, (openai.APIConnectionError, openai.APITimeoutError)):
        return True
    if isinstance(error, (openai.RateLimitError, openai.InternalServerError)):
        return True
    return isinstance(error, openai.APIStatusError) and (
        error.status_code == 429 or error.status_code >= 500
    )


def _problems(error: InstructorRetryException) -> list[str]:
    """Собрать тексты ошибок всех неудачных попыток."""
    problems = [
        str(attempt.exception).strip()
        for attempt in getattr(error, "failed_attempts", None) or ()
        if getattr(attempt, "exception", None) is not None
    ]
    return problems or [str(error).strip()]


def _log_call(model: str, prompt_version: str, started: float, completion: Any) -> None:
    """Записать в лог модель, версию промпта, токены и длительность вызова."""
    usage = getattr(completion, "usage", None)
    details = getattr(usage, "completion_tokens_details", None)
    logger.info(
        "llm: model=%s prompt_version=%s prompt_tokens=%s completion_tokens=%s"
        " total_tokens=%s reasoning_tokens=%s duration_ms=%s",
        model,
        prompt_version,
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
        getattr(usage, "total_tokens", None),
        getattr(details, "reasoning_tokens", None),
        int((time.monotonic() - started) * 1000),
    )
