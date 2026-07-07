from enum import StrEnum


class Provider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    PERPLEXITY = "perplexity"
    ELEVENLABS = "elevenlabs"
    RUNWAY = "runway"
    STABILITY = "stability"
    FAL = "fal"
    REPLICATE = "replicate"
    LUMA = "luma"
    OPENROUTER = "openrouter"
    PIAPI = "piapi"


class KeyPurpose(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    MUSIC = "music"
    SEARCH = "search"
    PREMIUM = "premium"
    FAST_VIDEO = "fast_video"
    FALLBACK = "fallback"
    DEV = "dev"
