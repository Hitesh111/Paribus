class CSVValidationError(ValueError):
    """Raised when the uploaded CSV does not match the expected contract."""


from typing import Optional


class HospitalDirectoryAPIError(RuntimeError):
    """Raised when the upstream hospital directory API returns an error."""

    def __init__(self, action: str, message: str, status_code: Optional[int] = None):
        self.action = action
        self.message = message
        self.status_code = status_code
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if self.status_code is None:
            return f"{self.action}: {self.message}"
        return f"{self.action} failed with status {self.status_code}: {self.message}"
