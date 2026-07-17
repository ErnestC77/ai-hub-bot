from enum import StrEnum


class Provider(StrEnum):
    # Только реально используемые провайдеры (см. api_key_manager._PURPOSE_ATTR).
    FAL = "fal"
    OPENROUTER = "openrouter"


class KeyPurpose(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    FALLBACK = "fallback"
    DEV = "dev"
