from dataclasses import dataclass


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400

    def __post_init__(self) -> None:
        super().__init__(self.message)


class ConflictError(AppError):
    def __init__(
        self,
        message: str = "The request conflicts with existing data.",
        *,
        code: str = "CONFLICT",
    ) -> None:
        super().__init__(code, message, 409)


class ResourceNotFoundError(AppError):
    def __init__(
        self,
        message: str = "The requested resource was not found.",
    ) -> None:
        super().__init__("RESOURCE_NOT_FOUND", message, 404)


class AuthenticationError(AppError):
    def __init__(
        self,
        message: str = "Authentication failed.",
    ) -> None:
        super().__init__("AUTHENTICATION_FAILED", message, 401)


class AuthorizationError(AppError):
    def __init__(
        self,
        message: str = "You are not authorized to perform this action.",
    ) -> None:
        super().__init__("AUTHORIZATION_FAILED", message, 403)


class MediaValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("INVALID_MEDIA", message, 422)


class MediaUploadTooLargeError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("MEDIA_TOO_LARGE", message, 413)


class MediaProcessorUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "MEDIA_PROCESSOR_UNAVAILABLE",
            "Video processing is temporarily unavailable.",
            503,
        )


class MediaProcessingTimeoutError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "MEDIA_PROCESSING_TIMEOUT",
            "Video processing exceeded the server time limit. "
            "Try a shorter or lower-resolution video.",
            503,
        )


class MediaStorageError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "MEDIA_STORAGE_ERROR",
            "The media file could not be stored. Please try again.",
            500,
        )
