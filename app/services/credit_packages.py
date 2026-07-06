from dataclasses import dataclass


@dataclass(frozen=True)
class CreditPackage:
    code: str
    name: str
    credits: int
    price_rub: float
    price_stars: int


CREDIT_PACKAGES: list[CreditPackage] = [
    CreditPackage(code="credits_100", name="100 кредитов", credits=100, price_rub=99, price_stars=50),
    CreditPackage(code="credits_500", name="500 кредитов", credits=500, price_rub=399, price_stars=200),
    CreditPackage(code="credits_2000", name="2000 кредитов", credits=2000, price_rub=1299, price_stars=650),
]


def get_package(code: str) -> CreditPackage | None:
    return next((p for p in CREDIT_PACKAGES if p.code == code), None)


def list_packages() -> list[CreditPackage]:
    return CREDIT_PACKAGES
