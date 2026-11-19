"""Phone number normalization (US only for now: all depots are in one state)."""

import re


def normalize_us(raw: str) -> str:
    """Return E.164 (+1XXXXXXXXXX) or raise ValueError with a human-readable message."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        digits = "1" + digits
    # NANP: area code and exchange can't start with 0 or 1.
    if len(digits) != 11 or not digits.startswith("1") or digits[1] in "01" or digits[4] in "01":
        raise ValueError(f"“{raw}” isn't a valid US phone number. Use 10 digits, e.g. (518) 555-0123.")
    return "+" + digits
