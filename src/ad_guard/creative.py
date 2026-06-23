"""Creative / GenAI safety approval headers — NeMo, Bedrock, generic."""

from __future__ import annotations

# Headers set upstream by NeMo Guardrails, Bedrock Guardrails, or internal safety proxy.
NEMO_APPROVAL_HEADERS = (
    "X-Nemo-Approved",
    "X-Nemo-Safety-Passed",
    "X-Bedrock-Guard-Passed",
    "X-Creative-Approved",
)


def parse_creative_approved(headers: dict[str, str]) -> bool | None:
    """
    Return True if any known safety header affirms approval,
    False if a header is present but denies, None if absent.
    """
    for name in NEMO_APPROVAL_HEADERS:
        raw = headers.get(name, "").strip().lower()
        if not raw:
            continue
        if raw in {"1", "true", "yes", "approved", "pass", "passed"}:
            return True
        if raw in {"0", "false", "no", "denied", "fail", "failed", "blocked"}:
            return False
    return None
