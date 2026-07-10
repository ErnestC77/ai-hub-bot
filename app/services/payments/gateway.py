from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import CreditPackage, Payment, User


@dataclass
class PaymentCreateResult:
    payment: Payment
    kind: Literal["external_url", "telegram_invoice"]
    confirmation_url: str | None = None
    invoice_link: str | None = None


class PaymentGateway(ABC):
    provider: PaymentProvider

    @abstractmethod
    async def create_credit_payment(
        self, session: AsyncSession, user: User, package: CreditPackage
    ) -> PaymentCreateResult: ...

    @abstractmethod
    async def check_payment_status(self, session: AsyncSession, payment: Payment) -> PaymentStatus: ...

    @abstractmethod
    async def refund_payment(self, session: AsyncSession, payment: Payment) -> bool: ...


GATEWAYS: dict[PaymentProvider, PaymentGateway] = {}


def register_gateway(gateway: PaymentGateway) -> None:
    GATEWAYS[gateway.provider] = gateway
