from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models import SupportMessage, SupportTicket, User

router = APIRouter(prefix="/auth/support/tickets", tags=["Support"])


async def identity(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to access support tickets.")
    try:
        claims = jwt.decode(authorization[7:], get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"], issuer="car-rental-auth", audience="car-rental-platform")
        return {"id": UUID(claims["sub"]), "role": claims.get("role", "customer")}
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(401, "Your session is invalid or expired.") from exc


class TicketCreate(BaseModel):
    subject: str = Field(min_length=4, max_length=160)
    message: str = Field(min_length=1, max_length=10000)


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    parent_id: UUID | None = None


class TicketUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|in_progress|waiting_customer|resolved|closed)$")
    priority: str | None = Field(default=None, pattern="^(low|normal|high|urgent)$")
    assigned_to: str | None = Field(default=None, max_length=320)


def message_dict(row: SupportMessage):
    return {"id": str(row.id), "ticket_id": str(row.ticket_id), "author_id": str(row.author_id), "author_name": row.author_name, "author_role": row.author_role, "parent_id": str(row.parent_id) if row.parent_id else None, "body": row.body, "created_at": row.created_at}


async def ticket_payload(db: AsyncSession, ticket: SupportTicket):
    messages = (await db.scalars(select(SupportMessage).where(SupportMessage.ticket_id == ticket.id).order_by(SupportMessage.created_at, SupportMessage.id))).all()
    return {"id": str(ticket.id), "customer_id": str(ticket.customer_id), "subject": ticket.subject, "status": ticket.status, "priority": ticket.priority, "assigned_to": ticket.assigned_to, "created_at": ticket.created_at, "updated_at": ticket.updated_at, "messages": [message_dict(item) for item in messages]}


@router.post("", status_code=201)
async def create_ticket(payload: TicketCreate, actor=Depends(identity), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, actor["id"])
    if not user:
        raise HTTPException(401, "Account not found.")
    ticket = SupportTicket(customer_id=user.id, subject=payload.subject.strip())
    db.add(ticket)
    await db.flush()
    db.add(SupportMessage(ticket_id=ticket.id, author_id=user.id, author_name=user.full_name, author_role=user.role, body=payload.message.strip()))
    await db.commit()
    await db.refresh(ticket)
    return await ticket_payload(db, ticket)


@router.get("")
async def list_tickets(all_tickets: bool = Query(default=False), actor=Depends(identity), db: AsyncSession = Depends(get_db)):
    query = select(SupportTicket).order_by(SupportTicket.updated_at.desc())
    if actor["role"] != "platform-admin" or not all_tickets:
        query = query.where(SupportTicket.customer_id == actor["id"])
    tickets = (await db.scalars(query)).all()
    return [await ticket_payload(db, item) for item in tickets]


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: UUID, actor=Depends(identity), db: AsyncSession = Depends(get_db)):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket or (ticket.customer_id != actor["id"] and actor["role"] != "platform-admin"):
        raise HTTPException(404, "Support ticket not found.")
    return await ticket_payload(db, ticket)


@router.post("/{ticket_id}/messages", status_code=201)
async def reply_ticket(ticket_id: UUID, payload: MessageCreate, actor=Depends(identity), db: AsyncSession = Depends(get_db)):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket or (ticket.customer_id != actor["id"] and actor["role"] != "platform-admin"):
        raise HTTPException(404, "Support ticket not found.")
    if ticket.status in {"resolved", "closed"} and actor["role"] != "platform-admin":
        raise HTTPException(409, "This ticket is closed. Reopen it through support before replying.")
    if payload.parent_id:
        parent = await db.get(SupportMessage, payload.parent_id)
        if not parent or parent.ticket_id != ticket.id:
            raise HTTPException(400, "Thread reply must reference a message from this ticket.")
    user = await db.get(User, actor["id"])
    message = SupportMessage(ticket_id=ticket.id, author_id=user.id, author_name=user.full_name, author_role=user.role, parent_id=payload.parent_id, body=payload.body.strip())
    db.add(message)
    if actor["role"] == "platform-admin" and ticket.status == "open":
        ticket.status = "in_progress"
    elif actor["role"] != "platform-admin":
        ticket.status = "open"
    await db.commit()
    await db.refresh(message)
    return message_dict(message)


@router.patch("/{ticket_id}")
async def update_ticket(ticket_id: UUID, payload: TicketUpdate, actor=Depends(identity), db: AsyncSession = Depends(get_db)):
    if actor["role"] != "platform-admin":
        raise HTTPException(403, "Administrator access is required.")
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Support ticket not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(ticket, key, value)
    await db.commit()
    await db.refresh(ticket)
    return await ticket_payload(db, ticket)


@router.delete("/{ticket_id}", status_code=204)
async def delete_ticket(ticket_id: UUID, actor=Depends(identity), db: AsyncSession = Depends(get_db)):
    if actor["role"] != "platform-admin":
        raise HTTPException(403, "Administrator access is required.")
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Support ticket not found.")
    await db.delete(ticket)
    await db.commit()
