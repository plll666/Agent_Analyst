import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

UNAUTHENTICATED = "UNAUTHENTICATED"
INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
EMAIL_TAKEN = "EMAIL_TAKEN"
NOT_FOUND = "NOT_FOUND"
VALIDATION_ERROR = "VALIDATION_ERROR"
FORBIDDEN = "FORBIDDEN"
METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
INTERNAL_ERROR = "INTERNAL_ERROR"

HTTP_STATUS_CODES = {
    404: NOT_FOUND,
    405: METHOD_NOT_ALLOWED,
}


class ApiError(Exception):
    """Ошибка с кодом из контракта.

    Тело ответа всегда ``{"detail": {"code", "message"}}`` — фронт разбирает только
    такой формат, включая ошибки валидации.
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message

    def payload(self) -> dict[str, Any]:
        return {"detail": {"code": self.code, "message": self.message}}


def _envelope(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"detail": {"code": code, "message": message}}
    )


def install_exception_handlers(app: FastAPI) -> None:
    """Свести все ошибки к одному формату: иначе фронт получает два разных вида ответа."""
    app.add_exception_handler(
        ApiError, lambda _r, exc: JSONResponse(exc.payload(), exc.status_code)
    )

    @app.exception_handler(RequestValidationError)
    async def _on_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'][1:])}: {error['msg']}"
            for error in exc.errors()
        )
        return _envelope(422, VALIDATION_ERROR, problems or "Некорректные данные запроса")

    @app.exception_handler(StarletteHTTPException)
    async def _on_http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_STATUS_CODES.get(exc.status_code, VALIDATION_ERROR)
        return _envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(ResponseValidationError)
    async def _on_response_validation(
        _request: Request, exc: ResponseValidationError
    ) -> JSONResponse:
        """Ответ не сошёлся с ``response_model`` — это баг сервера, а не вина клиента.

        Брать ``ResponseValidationError`` в хендлере запроса бессмысленно: он брат
        ``RequestValidationError`` по общему ``ValidationException``, а не его подкласс.
        Причину уходит в лог, наружу — короткое сообщение без устройства DTO.
        """
        logger.error(
            "Ответ не соответствует response_model на %s: %s",
            _request.url.path,
            exc.errors(),
        )
        return _envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            INTERNAL_ERROR,
            "Внутренняя ошибка сервера: ответ не соответствует контракту",
        )

    @app.exception_handler(Exception)
    async def _on_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        """Конверт держится на любой ошибке: дефолт Starlette фронт не разберёт."""
        logger.exception("Необработанная ошибка на %s", _request.url.path)
        return _envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            INTERNAL_ERROR,
            f"Внутренняя ошибка сервера: {type(exc).__name__}",
        )
