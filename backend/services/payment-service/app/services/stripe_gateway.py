import stripe

from app.core.config import get_settings


def _client() -> stripe.StripeClient:
    key = get_settings().stripe_secret_key
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")
    return stripe.StripeClient(key)


def create_payment_intent(*, amount: int, currency: str, booking_id: str, idempotency_key: str):
    return _client().v1.payment_intents.create(
        {
            "amount": amount,
            "currency": currency,
            "automatic_payment_methods": {"enabled": True},
            "metadata": {"booking_id": booking_id},
        },
        options={"idempotency_key": idempotency_key},
    )


def retrieve_payment_intent(intent_id: str):
    return _client().v1.payment_intents.retrieve(intent_id)


def construct_webhook_event(payload: bytes, signature: str):
    secret = get_settings().stripe_webhook_secret
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")
    return stripe.Webhook.construct_event(payload, signature, secret)
