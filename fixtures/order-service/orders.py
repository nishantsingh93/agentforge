"""Small owned fixture; never imported by the scenario loader."""


def normalize_status(status: str | None) -> str:
    if status is None:
        return "pending"
    return status.lower()
