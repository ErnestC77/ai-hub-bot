import enum


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


class ModelProvider(str, enum.Enum):
    openrouter = "openrouter"
    fal = "fal"


class ModelCategory(str, enum.Enum):
    text = "text"
    image = "image"
    video = "video"


class ModelTier(str, enum.Enum):
    economy = "economy"
    standard = "standard"
    premium = "premium"
    pro = "pro"
    ultra = "ultra"


class CostUnit(str, enum.Enum):
    tokens = "tokens"
    image = "image"
    megapixel = "megapixel"
    second = "second"
    video = "video"


class RequestStatus(str, enum.Enum):
    pending = "pending"
    reserved = "reserved"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


class CreditTxType(str, enum.Enum):
    purchase = "purchase"
    spend = "spend"
    refund = "refund"
    reserve = "reserve"
    release = "release"
    admin_adjustment = "admin_adjustment"
