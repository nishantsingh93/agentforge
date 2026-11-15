"""Order business rules live here, not in the transport adapter."""

VALID_STATUSES = {"pending", "paid", "cancelled"}


def normalize_status(status: str | None) -> str:
    value = "pending" if status is None else status.lower()
    if value not in VALID_STATUSES:
        raise ValueError("unsupported status")
    return value
