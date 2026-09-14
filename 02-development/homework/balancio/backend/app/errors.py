class AppError(Exception):
    """A friendly, domain-specific error safe to show to end users.

    Never wraps a stack trace or internal exception name - `message` is
    exactly what the client should display.
    """

    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def bad_request(message: str) -> AppError:
    return AppError(message, status_code=400)


def unauthorized(message: str) -> AppError:
    return AppError(message, status_code=401)


def forbidden(message: str) -> AppError:
    return AppError(message, status_code=403)


def not_found(message: str) -> AppError:
    return AppError(message, status_code=404)


def conflict(message: str) -> AppError:
    return AppError(message, status_code=409)
