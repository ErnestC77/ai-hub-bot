from app.db.enums import ModelCategory

# category -> (tariff limit column, usage_limits used column)
CATEGORY_LIMIT_FIELD: dict[ModelCategory, tuple[str, str]] = {
    ModelCategory.fast: ("fast_limit", "fast_used"),
    ModelCategory.medium: ("medium_limit", "medium_used"),
    ModelCategory.premium: ("premium_limit", "premium_used"),
    ModelCategory.image: ("image_limit", "images_used"),
}
