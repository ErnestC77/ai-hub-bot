def mask_secret(value: str | None) -> str:
    """Только для debug-вывода. По умолчанию ключи вообще не логируются."""
    if not value:
        return "NOT_SET"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"
