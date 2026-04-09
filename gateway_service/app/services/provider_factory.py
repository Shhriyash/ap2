from sqlalchemy.orm import Session

from app.providers.base import PaymentProvider
from app.providers.dummy import DummyPaymentProvider


def build_provider(db: Session) -> PaymentProvider:
    return DummyPaymentProvider(db)
