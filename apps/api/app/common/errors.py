from fastapi import HTTPException, status


class NotFoundError(HTTPException):
    def __init__(self, resource: str) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} not found")


class ConflictError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class UnauthorizedError(HTTPException):
    def __init__(self, detail: str = "Unauthorized") -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class RateLimitError(HTTPException):
    def __init__(self, detail: str = "Too many requests") -> None:
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


class ServiceUnavailableError(HTTPException):
    def __init__(self, detail: str = "Service temporarily unavailable") -> None:
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
