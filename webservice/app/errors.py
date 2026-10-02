"""도메인 예외. API 계층에서 HTTP 상태코드로 매핑된다(시험계획서 v1.1 4.2절)."""


class AppError(Exception):
    http_status = 500
    code = "INTERNAL_ERROR"


class ValidationError(AppError):
    http_status = 400
    code = "VALIDATION_ERROR"


class AuthenticationError(AppError):
    http_status = 401
    code = "AUTHENTICATION_FAILED"


class PermissionDeniedError(AppError):
    http_status = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    http_status = 404
    code = "NOT_FOUND"


class DuplicateUsernameError(AppError):
    http_status = 409
    code = "DUPLICATE_USERNAME"


class DuplicateApplicationError(AppError):
    http_status = 409
    code = "DUPLICATE_APPLICATION"


class InvalidTransitionError(AppError):
    http_status = 409
    code = "INVALID_TRANSITION"
