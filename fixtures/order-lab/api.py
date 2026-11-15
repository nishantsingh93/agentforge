"""Stable transport contract: status string or ValueError from the service."""

from service import normalize_status


def order_response(status: str | None) -> dict[str, str]:
    return {"status": normalize_status(status)}
