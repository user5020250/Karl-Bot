import re

SUFFIXES = {
    "k": 1_000,
    "m": 1_000_000,
    "b": 1_000_000_000,
    "t": 1_000_000_000_000,
}

_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([kmbt]?)", re.IGNORECASE)


class AmountParseError(ValueError):
    """Raised with a user-facing message when an amount string can't be parsed."""


def parse_amount(text: str, available: int | None = None) -> int:
    """Parses a user-supplied amount string.

    Supports plain whole numbers, decimals with k/m/b/t suffixes
    (e.g. '1000', '1k', '2.5m', '1b', '1t'), and the literal 'all'
    (requires `available` to be provided).

    Raises AmountParseError with a friendly message on invalid input.
    """
    if text is None:
        raise AmountParseError("Enter a valid whole number (e.g. `1000`, `1k`, `2.5m`) or `all`.")

    cleaned = text.strip().lower().replace(",", "")

    if cleaned == "all":
        if available is None:
            raise AmountParseError("`all` is not supported for this command.")
        if available <= 0:
            raise AmountParseError("You have nothing to use `all` on.")
        return available

    match = _AMOUNT_RE.fullmatch(cleaned)
    if not match:
        raise AmountParseError("Enter a valid whole number (e.g. `1000`, `1k`, `2.5m`) or `all`.")

    number = float(match.group(1))
    suffix = match.group(2)
    if suffix:
        number *= SUFFIXES[suffix]

    value = round(number)
    if value <= 0:
        raise AmountParseError("Amount must be greater than zero.")
    return value
