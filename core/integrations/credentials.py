PLACEHOLDER_PREFIXES = (
    "cole-",
    "troque-",
    "placeholder",
    "changeme",
    "change-me",
    "your-",
    "seu-",
    "sua-",
)


def configured_value(value):
    value = str(value or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered in {"-", "none", "null"}:
        return ""
    if lowered.startswith(PLACEHOLDER_PREFIXES):
        return ""
    return value


def first_configured_value(*values):
    for value in values:
        normalized = configured_value(value)
        if normalized:
            return normalized
    return ""
