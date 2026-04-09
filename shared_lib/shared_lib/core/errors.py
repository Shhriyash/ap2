class DomainError(Exception):
    def __init__(self, message: str, code: str = "domain_error") -> None:
        super().__init__(message)
        self.code = code
