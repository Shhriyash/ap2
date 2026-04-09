from sqlalchemy.orm import Session

from app.core.config import settings
from app.providers.base import PaymentProvider
from app.providers.dummy import DummyPaymentProvider
from app.providers.external_http import ExternalHttpPaymentProvider


def build_provider(db: Session) -> PaymentProvider:
    mode = settings.payment_provider_mode.lower().strip()
    if mode == "external":
        return ExternalHttpPaymentProvider()
    return DummyPaymentProvider(db)
