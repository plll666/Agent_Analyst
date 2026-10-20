"""Адаптер LLM: один вызов, который возвращает JSON-объект.

Провайдер задаётся переменными окружения, а не кодом: клиент говорит на
OpenAI-совместимом ``/chat/completions``, поэтому работает с DeepSeek, OpenRouter
и локальным vLLM без отдельной ветки под каждого.

Ответ модели — внешние данные. Он разбирается и проверяется здесь, а не в домене:
если провайдер вернул не JSON или не тот конверт, это ``LLMError``, а не падение
внутри разбора модели.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """LLM не ответила или ответила так, что использовать его нельзя."""


class LLMConfigurationError(LLMError):
    """Провайдер не задан: не хватает адреса, модели или ключа."""


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
            base_url=source.get("LLM_BASE_URL", "").strip().rstrip("/"),
            api_key=source.get("LLM_API_KEY", "").strip(),
            model=source.get("LLM_MODEL", "").strip(),
            timeout_seconds=float(source.get("LLM_TIMEOUT_SECONDS", "60")),
            max_attempts=max(1, int(source.get("LLM_MAX_ATTEMPTS", "3"))),
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
    """Один запрос к модели с ответом в виде JSON-объекта."""

    async def complete_json(self, *, system: str, user: str, prompt_version: str) -> dict[str, Any]:
        """Вернуть разобранный JSON-объект от модели.

        Args:
            system: Системная инструкция.
            user: Пользовательское сообщение с данными задачи.
            prompt_version: Версия промпта — попадает в лог вместе с числом токенов.

        Returns:
            Разобранный JSON-объект.
        """
        ...

    async def aclose(self) -> None:
        """Освободить соединения клиента."""
        ...


LLMFactory = Callable[[], LLMClient]


class HttpLLMClient:
    """OpenAI-совместимый клиент на ``httpx``."""

    def __init__(self, settings: LLMSettings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.timeout_seconds)
        self._owns_client = client is None

    async def aclose(self) -> None:
        """Закрыть соединения, если клиент создан этим объектом."""
        if self._owns_client:
            await self._client.aclose()

    async def complete_json(self, *, system: str, user: str, prompt_version: str) -> dict[str, Any]:
        """Запросить ответ и вернуть его как JSON-объект.

        Args:
            system: Системная инструкция.
            user: Пользовательское сообщение с данными задачи.
            prompt_version: Версия промпта — попадает в лог вместе с числом токенов.

        Returns:
            Разобранный JSON-объект.

        Raises:
            LLMError: сеть, HTTP-ошибка или тело ответа не является JSON-объектом.
        """
        if not self._settings.is_configured:
            raise LLMConfigurationError(
                "LLM не настроена: не заданы " + ", ".join(self._settings.missing())
            )
        request = {
            "model": self._settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        started = time.monotonic()
        try:
            response = await self._client.post(
                self._endpoint,
                json=request,
                headers={"Authorization": f"Bearer {self._settings.api_key}"},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            logger.warning(
                "llm: model=%s prompt_version=%s failed in %s ms: %s",
                self._settings.model,
                prompt_version,
                _duration_ms(started),
                error,
            )
            raise LLMError(f"запрос к LLM не удался: {error}") from error
        usage = _usage(response)
        logger.info(
            "llm: model=%s prompt_version=%s prompt_tokens=%s completion_tokens=%s"
            " total_tokens=%s duration_ms=%s",
            self._settings.model,
            prompt_version,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
            _duration_ms(started),
        )
        return _parse_body(response)

    @property
    def _endpoint(self) -> str:
        """Полный адрес: база может уже включать ``/chat/completions``."""
        if self._settings.base_url.endswith("/chat/completions"):
            return self._settings.base_url
        return f"{self._settings.base_url}/chat/completions"


async def request_validated[T](
    client: LLMClient,
    *,
    system: str,
    user: str,
    prompt_version: str,
    attempts: int,
    parse: Callable[[Mapping[str, Any]], T],
) -> T:
    """Спросить модель и разобрать ответ, повторяя попытку с текстом ошибки.

    Повтор нужен не из вежливости: модель иногда возвращает валидный JSON с
    невалидным документом. Вторая попытка получает список нарушений и чинит их,
    а не гадает заново.

    Args:
        client: Клиент LLM.
        system: Системная инструкция.
        user: Сообщение с данными задачи.
        prompt_version: Версия промпта для лога стоимости вызова.
        attempts: Сколько всего попыток сделать.
        parse: Разбор ответа; бросает ``ValueError``, если ответ не подходит.

    Returns:
        Результат разбора.

    Raises:
        LLMResponseError: ни одна попытка не дала пригодный ответ.
        LLMError: провайдер недоступен или вернул не JSON.
    """
    problems: list[str] = []
    last_error: LLMError | None = None
    for _ in range(max(1, attempts)):
        message = user
        if problems:
            message = f"{user}\n\n{_REPAIR.format(problems='; '.join(problems))}"
        try:
            payload = await client.complete_json(
                system=system, user=message, prompt_version=prompt_version
            )
        except LLMError as error:
            last_error = error
            problems = [str(error)]
            continue
        try:
            return parse(payload)
        except (ValidationError, ValueError) as error:
            problems = [str(error)]
    logger.warning(
        "llm: prompt_version=%s no usable answer in %s attempts", prompt_version, attempts
    )
    raise LLMResponseError(
        f"LLM не вернула пригодный ответ за {attempts} попыток", problems
    ) from last_error


_REPAIR = (
    "Предыдущий ответ не прошёл проверку: {problems}. "
    "Исправь нарушения и верни JSON заново, без пояснений вокруг."
)


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
    return HttpLLMClient(settings)


def _duration_ms(started: float) -> int:
    """Сколько миллисекунд прошло с момента старта."""
    return int((time.monotonic() - started) * 1000)


def _usage(response: httpx.Response) -> dict[str, int]:
    """Достать счётчики токенов из ответа провайдера.

    Провайдер может их не прислать — это не ошибка, а повод не писать в лог
    выдуманные числа.
    """
    try:
        body = response.json()
    except ValueError:
        return {}
    if not isinstance(body, Mapping):
        return {}
    usage = body.get("usage")
    if not isinstance(usage, Mapping):
        return {}
    return {
        str(key): int(value)
        for key, value in usage.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }


def _parse_body(response: httpx.Response) -> dict[str, Any]:
    """Достать JSON-объект из конверта ``chat/completions``."""
    try:
        body = response.json()
    except ValueError as error:
        raise LLMError("ответ LLM не является JSON") from error
    content = _message_content(body)
    stripped = _FENCE.sub("", content.strip())
    try:
        parsed = json.loads(stripped)
    except ValueError as error:
        raise LLMError(f"содержимое ответа LLM не разбирается как JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise LLMError("ответ LLM должен быть JSON-объектом")
    return {str(key): value for key, value in parsed.items()}


def _message_content(body: object) -> str:
    """Проверить конверт ответа и вернуть текст сообщения модели."""
    if not isinstance(body, Mapping):
        raise LLMError("ответ провайдера не является JSON-объектом")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMError("в ответе провайдера нет choices")
    first = choices[0]
    if not isinstance(first, Mapping):
        raise LLMError("элемент choices имеет неожиданный формат")
    message = first.get("message")
    if not isinstance(message, Mapping):
        raise LLMError("в ответе провайдера нет message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise LLMError("модель вернула пустое сообщение")
    return content
