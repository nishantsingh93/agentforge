"""Trusted in-memory synthetic grants; never real credentials or agent authority."""

import math
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from agentforge.core.artifacts import digest_bytes
from agentforge.core.schemas import ActionRequest
from agentforge.core.trace import canonical_json


class ApprovalError(ValueError):
    """Missing, mismatched, expired or consumed synthetic grant."""


def request_binding(request: ActionRequest, *, include_token: bool = False) -> str:
    try:
        request = ActionRequest.model_validate_json(request.model_dump_json())
    except (ValueError, TypeError, AttributeError):
        raise ApprovalError("invalid approval request contract") from None
    return digest_bytes(
        canonical_json(
            request.model_dump(mode="json", exclude=set() if include_token else {"approval_token"})
        )
    )


@dataclass(frozen=True, repr=False)
class _Grant:
    run_id: str
    binding: str
    policy_version: str
    issued: float
    expires: float


class ApprovalRegistry:
    """Trusted issuer only. Grants and opaque references stay in memory."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._grants: dict[str, _Grant] = {}

    def issue(
        self, request: ActionRequest, run_id: str, policy_version: str, *, ttl_seconds: float = 60.0
    ) -> str:
        if any(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value) is None
            for value in (run_id, policy_version)
        ):
            raise ApprovalError("invalid grant identity")
        now = self._clock()
        if not math.isfinite(now) or not math.isfinite(ttl_seconds) or not 0 < ttl_seconds <= 3600:
            raise ApprovalError("invalid grant lifetime")
        binding = request_binding(request)
        reference = "synthetic-" + uuid.uuid4().hex
        self._grants[reference] = _Grant(run_id, binding, policy_version, now, now + ttl_seconds)
        return reference

    def validate(
        self, request: ActionRequest, run_id: str, policy_version: str, *, consume: bool = False
    ) -> None:
        reference = request.approval_token
        grant = self._grants.get(reference) if reference is not None else None
        now = self._clock()
        if (
            grant is None
            or not math.isfinite(now)
            or now < grant.issued
            or now >= grant.expires
            or grant.run_id != run_id
            or grant.policy_version != policy_version
            or grant.binding != request_binding(request)
        ):
            raise ApprovalError("synthetic approval invalid or unavailable")
        if consume:
            assert reference is not None
            del self._grants[reference]
