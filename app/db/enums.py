import enum


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    canceled = "canceled"


class PaymentProvider(str, enum.Enum):
    telegram_stars = "telegram_stars"
    yookassa = "yookassa"
    manual = "manual"
    promo = "promo"


class PaymentStatus(str, enum.Enum):
    created = "created"
    pending = "pending"
    succeeded = "succeeded"
    canceled = "canceled"
    refunded = "refunded"
    failed = "failed"


class ModelCategory(str, enum.Enum):
    fast = "fast"
    medium = "medium"
    premium = "premium"
    image = "image"
    video = "video"


class ModelProvider(str, enum.Enum):
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    deepseek = "deepseek"
    piapi = "piapi"


class RequestStatus(str, enum.Enum):
    processing = "processing"
    success = "success"
    error = "error"


class CreditTxType(str, enum.Enum):
    deposit = "deposit"
    spend = "spend"
    refund = "refund"
    bonus = "bonus"
    manual_adjustment = "manual_adjustment"
