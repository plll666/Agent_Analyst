"""Корневые сертификаты из хранилища ОС.

Корпоративные шлюзы и MITM-прокси подписывают HTTPS сертификатами корпоративного
управляющего центра, которых нет в ``certifi``. Python-пакет ``truststore``
умеет читать хранилище Windows, macOS и Linux, поэтому клиент LLM использует
его вместо встроенного набора — иначе исходящий вызов к провайдеру падает с
``CERTIFICATE_VERIFY_FAILED`` на машинах с корпоративным TLS.

Модуль подключает хранилище ОС при импорте. Если пакета нет или хранилище не
читается, работа продолжается на обычном ``certifi``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _inject() -> bool:
    """Подключить хранилище ОС к ssl.

    Returns:
        ``True``, если хранилище ОС подключено, ``False`` — останется certifi.
    """
    try:
        import truststore
    except ImportError:
        return False
    try:
        truststore.inject_into_ssl()
    except Exception as error:  # noqa: BLE001 - запасной путь обязателен
        logger.warning("хранилище ОС не подключено: %s", error)
        return False
    return True


_root_store = _inject()
"""Признак подключения хранилища ОС; проверяется тестами."""
