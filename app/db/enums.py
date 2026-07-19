import enum


class PaymentProvider(str, enum.Enum):
    telegram_stars = "telegram_stars"
    yookassa = "yookassa"
    manual = "manual"
    promo = "promo"
    crypto = "crypto"


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


class ModelOptionKind(str, enum.Enum):
    quality = "quality"    # разрешение/размер: resolution, image_size, video_quality
    duration = "duration"  # длина видео: duration, num_frames+frames_per_second
    audio = "audio"        # generate_audio у Veo -- удваивает цену, см. спек
    aspect_ratio = "aspect_ratio"  # формат кадра: aspect_ratio (у Ovi -- resolution-пары)


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
    referral_bonus = "referral_bonus"
    welcome_bonus = "welcome_bonus"
    first_purchase_bonus = "first_purchase_bonus"
