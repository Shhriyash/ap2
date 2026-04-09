from __future__ import annotations

from abc import ABC, abstractmethod

from shared_lib.contracts.payment import (
    BalanceResponse,
    PaymentTransferRequest,
    PaymentTransferResponse,
    PaymentValidateRequest,
    PaymentValidateResponse,
    RefundRequest,
    ReversalRequest,
    TransactionStatusResponse,
    VerifyReceiverRequest,
    VerifyReceiverResponse,
)


class PaymentProvider(ABC):
    @abstractmethod
    def validate(self, payload: PaymentValidateRequest) -> PaymentValidateResponse: ...

    @abstractmethod
    def transfer(self, payload: PaymentTransferRequest) -> PaymentTransferResponse: ...

    @abstractmethod
    def get_status(self, transaction_id: str) -> TransactionStatusResponse: ...

    @abstractmethod
    def get_balance(self, requestor_user_id: str, target_user_id: str) -> BalanceResponse: ...

    @abstractmethod
    def verify_receiver(self, payload: VerifyReceiverRequest) -> VerifyReceiverResponse: ...

    @abstractmethod
    def refund(self, payload: RefundRequest) -> PaymentTransferResponse: ...

    @abstractmethod
    def reverse(self, payload: ReversalRequest) -> PaymentTransferResponse: ...
