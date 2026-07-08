from pydantic import BaseModel


class MeOut(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str | None
    is_admin: bool
    default_model_code: str | None
    credits_balance: int
    total_credits_purchased: int
    total_credits_spent: int
