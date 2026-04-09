import uuid


def make_idempotency_key(prefix: str = "pay") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
