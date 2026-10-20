import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.api import payments as payment_api
from app.core.database import Base
from app.models import Payment, PaymentDeliveryOutbox, ProcessedStripeEvent
from app.repositories import PaymentRepository
from app.services import stripe_gateway
from app.services import payment_delivery
from app.services.payment_delivery import process_next_delivery


class FakeServiceClient:
    instances = []
    fail_receipt_once = False
    booking_conflict = False

    def __init__(self, *_, **__):
        self.posts = []
        self.gets = []
        self.__class__.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, *, headers, json):
        self.posts.append((url, headers, json))
        if url.endswith("/bookings/internal/payment-confirmations"):
            if self.__class__.booking_conflict:
                return httpx.Response(409, json={"detail": "booking hold expired"})
            return httpx.Response(200, json={
                "id": json["booking_id"],
                "customer_id": str(CUSTOMER_ID),
                "pickup_at": "2030-01-01T10:00:00Z",
                "return_at": "2030-01-01T12:00:00Z",
                "vehicle_make": "TestMake",
                "vehicle_model": "TestModel",
                "vehicle_color": "TestColor",
                "vehicle_license_plate": "TEST-PLATE",
            })
        if url.endswith("/receipts") and self.__class__.fail_receipt_once:
            self.__class__.fail_receipt_once = False
            return httpx.Response(503, json={"detail": "temporary failure"})
        if url.endswith("/receipts"):
            return httpx.Response(201, json={"receipt_number": "RCT-TEST-001"})
        if url.endswith("/notifications/email"):
            return httpx.Response(202, json={"status": "pending"})
        raise AssertionError(f"Unexpected POST URL: {url}")

    async def get(self, url, *, headers):
        self.gets.append((url, headers))
        return httpx.Response(200, json={"email": "renter@example.com"})


CUSTOMER_ID = uuid4()


def _request() -> Request:
    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "method": "POST",
        "scheme": "http", "path": "/payments/webhooks/stripe",
        "raw_path": b"/payments/webhooks/stripe", "query_string": b"",
        "headers": [], "server": ("test", 80), "client": ("test", 1),
    }
    return Request(scope, receive)


def test_success_webhook_retries_cross_service_steps_and_is_idempotent(monkeypatch):
    async def run():
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        booking_id, payment_id = uuid4(), uuid4()
        event_id, intent_id = f"evt_{uuid4().hex}", f"pi_{uuid4().hex}"
        event = {"id": event_id, "type": "payment_intent.succeeded", "data": {"object": {
            "id": intent_id, "amount": 10000, "amount_received": 10000,
            "currency": "usd", "status": "succeeded",
        }}}
        settings = SimpleNamespace(
            payment_to_booking_api_key=SecretStr("booking-key"),
            booking_service_url="http://booking-service",
            receipt_service_api_key=SecretStr("receipt-key"),
            receipt_service_url="http://receipt-service",
            auth_service_api_key=SecretStr("auth-key"),
            auth_service_url="http://auth-service",
            notification_service_api_key=SecretStr("notification-key"),
            notification_service_url="http://notification-service",
        )
        monkeypatch.setattr(payment_api, "get_settings", lambda: settings)
        monkeypatch.setattr(payment_delivery, "get_settings", lambda: settings)
        monkeypatch.setattr(stripe_gateway, "construct_webhook_event", lambda *_: event)
        monkeypatch.setattr(payment_api.httpx, "AsyncClient", FakeServiceClient)
        FakeServiceClient.instances.clear()
        FakeServiceClient.fail_receipt_once = True
        async with sessions() as session:
            session.add(Payment(
                id=payment_id, booking_id=booking_id, idempotency_key="test-payment",
                stripe_payment_intent_id=intent_id, amount_minor=10000,
                currency="usd", status="requires_payment_method",
            ))
            await session.commit()

        async with sessions() as session:
            first = await payment_api.stripe_webhook(_request(), "mock-signature", session)
        async with sessions() as session:
            duplicate = await payment_api.stripe_webhook(_request(), "mock-signature", session)
            payment = await session.get(Payment, payment_id)
            processed = await session.get(ProcessedStripeEvent, event_id)
            outbox = await session.get(PaymentDeliveryOutbox, event_id)
            assert payment.status == "succeeded_pending_delivery"
            assert processed is not None
            assert outbox.status == "pending"
            assert await session.scalar(select(ProcessedStripeEvent.event_id).where(
                ProcessedStripeEvent.event_id == event_id
            )) == event_id
        assert first == {"received": True, "delivery_queued": True}
        assert duplicate == {"received": True}
        assert FakeServiceClient.instances == []

        async with sessions() as session:
            assert await process_next_delivery(session)
        async with sessions() as session:
            outbox = await session.get(PaymentDeliveryOutbox, event_id)
            assert outbox.status == "pending"
            assert outbox.attempt_count == 1
            outbox.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
        async with sessions() as session:
            assert await process_next_delivery(session)
        async with sessions() as session:
            payment = await session.get(Payment, payment_id)
            outbox = await session.get(PaymentDeliveryOutbox, event_id)
            assert payment.status == "succeeded"
            assert outbox.status == "delivered"
        assert len(FakeServiceClient.instances) == 2
        posted_urls = [url for client in FakeServiceClient.instances for url, _, _ in client.posts]
        assert posted_urls.count("http://booking-service/bookings/internal/payment-confirmations") == 2
        assert posted_urls.count("http://receipt-service/receipts") == 2
        assert posted_urls.count("http://notification-service/notifications/email") == 1
        notification = next(
            payload for client in FakeServiceClient.instances for url, _, payload in client.posts
            if url.endswith("/notifications/email")
        )
        assert notification["recipient"] == "renter@example.com"
        assert "Total paid" in notification["text_body"]
        assert "RCT-TEST-001" in notification["html_body"]
        assert "TestMake TestModel" in notification["html_body"]
        await engine.dispose()

    asyncio.run(run())


def test_success_webhook_rejects_stripe_amount_mismatch(monkeypatch):
    async def run():
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        event_id, intent_id = f"evt_{uuid4().hex}", f"pi_{uuid4().hex}"
        event = {"id": event_id, "type": "payment_intent.succeeded", "data": {"object": {
            "id": intent_id, "amount": 999, "amount_received": 999,
            "currency": "usd", "status": "succeeded",
        }}}
        monkeypatch.setattr(stripe_gateway, "construct_webhook_event", lambda *_: event)
        monkeypatch.setattr(payment_api.httpx, "AsyncClient", FakeServiceClient)
        async with sessions() as session:
            session.add(Payment(
                booking_id=uuid4(), idempotency_key="mismatch-payment",
                stripe_payment_intent_id=intent_id, amount_minor=10000,
                currency="usd", status="requires_payment_method",
            ))
            await session.commit()
        async with sessions() as session:
            with pytest.raises(HTTPException) as failure:
                await payment_api.stripe_webhook(_request(), "mock-signature", session)
        assert failure.value.status_code == 400
        await engine.dispose()

    asyncio.run(run())


def test_successful_charge_with_expired_booking_is_recorded_for_reconciliation(monkeypatch):
    async def run():
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        booking_id, payment_id = uuid4(), uuid4()
        event_id, intent_id = f"evt_{uuid4().hex}", f"pi_{uuid4().hex}"
        event = {"id": event_id, "type": "payment_intent.succeeded", "data": {"object": {
            "id": intent_id, "amount": 10000, "amount_received": 10000,
            "currency": "usd", "status": "succeeded",
        }}}
        settings = SimpleNamespace(
            payment_to_booking_api_key=SecretStr("booking-key"),
            booking_service_url="http://booking-service",
        )
        monkeypatch.setattr(payment_api, "get_settings", lambda: settings)
        monkeypatch.setattr(payment_delivery, "get_settings", lambda: settings)
        monkeypatch.setattr(stripe_gateway, "construct_webhook_event", lambda *_: event)
        monkeypatch.setattr(payment_api.httpx, "AsyncClient", FakeServiceClient)
        FakeServiceClient.instances.clear()
        FakeServiceClient.booking_conflict = True
        async with sessions() as session:
            session.add(Payment(
                id=payment_id, booking_id=booking_id, idempotency_key="unapplied-payment",
                stripe_payment_intent_id=intent_id, amount_minor=10000,
                currency="usd", status="requires_payment_method",
            ))
            await session.commit()
        async with sessions() as session:
            result = await payment_api.stripe_webhook(_request(), "mock-signature", session)
            payment = await session.get(Payment, payment_id)
            assert payment.status == "succeeded_pending_delivery"
            processed = await session.get(ProcessedStripeEvent, event_id)
            assert processed is not None
        assert result == {"received": True, "delivery_queued": True}
        async with sessions() as session:
            await process_next_delivery(session)
            payment = await session.get(Payment, payment_id)
            outbox = await session.get(PaymentDeliveryOutbox, event_id)
            assert payment.status == "succeeded_unapplied"
            assert outbox.status == "reconciliation_required"
        assert len(FakeServiceClient.instances) == 1
        await engine.dispose()

    asyncio.run(run())


def test_failed_outbox_delivery_can_be_listed_and_retried():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        payment_id, booking_id = uuid4(), uuid4()
        event_id = f"evt_{uuid4().hex}"
        async with sessions() as session:
            payment = Payment(
                id=payment_id,
                booking_id=booking_id,
                idempotency_key="failed-outbox-payment",
                stripe_payment_intent_id=f"pi_{uuid4().hex}",
                amount_minor=10000,
                currency="usd",
                status="succeeded_pending_delivery",
            )
            session.add(payment)
            session.add(PaymentDeliveryOutbox(
                event_id=event_id,
                payment_id=payment_id,
                event_type="payment_intent.succeeded",
                status="processing",
                locked_until=datetime.now(UTC),
            ))
            await session.commit()

        async with sessions() as session:
            repository = PaymentRepository(session)
            entry = await session.get(PaymentDeliveryOutbox, event_id)
            await repository.mark_delivery_failed(entry, "temporary failure", max_attempts=1)
            payment = await session.get(Payment, payment_id)
            assert payment.status == "succeeded_delivery_failed"
            failed = await repository.list_failed_deliveries()
            assert [item.event_id for item in failed] == [event_id]

        async with sessions() as session:
            entry = await PaymentRepository(session).retry_failed_delivery(event_id)
            payment = await session.get(Payment, payment_id)
            assert entry.status == "pending"
            assert entry.attempt_count == 0
            assert entry.last_error is None
            assert payment.status == "succeeded_pending_delivery"

        await engine.dispose()

    asyncio.run(run())
