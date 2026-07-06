from app.services.payments.gateway import register_gateway
from app.services.payments.stars_service import TelegramStarsPaymentService
from app.services.payments.yookassa_service import YooKassaPaymentService


def register_all_gateways() -> None:
    register_gateway(TelegramStarsPaymentService())
    register_gateway(YooKassaPaymentService())
