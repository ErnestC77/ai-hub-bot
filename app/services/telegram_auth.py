import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_INIT_DATA_AGE_SECONDS = 60 * 60  # 1ч (было 24ч): меньше окно replay утёкшего initData


class InvalidInitDataError(Exception):
    pass


def parse_and_validate_init_data(
    init_data: str, bot_token: str, max_age_seconds: int = MAX_INIT_DATA_AGE_SECONDS
) -> dict:
    """Проверяет подпись Telegram WebApp initData и возвращает разобранные поля.

    Алгоритм из офиц. документации Telegram:
    secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
    hash = HMAC_SHA256(key=secret_key, msg=data_check_string)
    """
    if not init_data:
        raise InvalidInitDataError("empty init data")

    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError as exc:
        raise InvalidInitDataError("malformed init data") from exc

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InvalidInitDataError("missing hash")

    data_check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise InvalidInitDataError("hash mismatch")

    auth_date = parsed.get("auth_date")
    try:
        is_expired = auth_date is None or time.time() - int(auth_date) > max_age_seconds
    except ValueError as exc:
        raise InvalidInitDataError("malformed auth_date") from exc
    if is_expired:
        raise InvalidInitDataError("init data expired")

    if "user" in parsed:
        try:
            parsed["user"] = json.loads(parsed["user"])
        except json.JSONDecodeError as exc:
            raise InvalidInitDataError("malformed user field") from exc

    return parsed
