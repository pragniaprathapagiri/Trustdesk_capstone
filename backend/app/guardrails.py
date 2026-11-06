import re

INJECTION_PATTERNS = [
    r"ignore (?:all )?(?:identity |verification |security )?(?:checks?|policy)",
    r"hidden coupon", r"issue.*coupon", r"system prompt", r"api key",
    r"internal notes", r"do not tell", r"bypass"
]
PII_PATTERNS = [r"\b\d{12,19}\b", r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"]


def assess(text: str) -> dict:
    lower = text.lower()
    injection = [p for p in INJECTION_PATTERNS if re.search(p, lower)]
    pii = [p for p in PII_PATTERNS if re.search(p, text, re.IGNORECASE)]
    return {
        "safe": not injection,
        "injection_detected": bool(injection),
        "pii_detected": bool(pii),
        "matched_patterns": injection,
    }
