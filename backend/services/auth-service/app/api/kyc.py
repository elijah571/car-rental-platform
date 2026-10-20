from datetime import UTC, datetime
from pathlib import PurePath
from uuid import UUID

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _access_claims, _require_admin, verify_internal_service_key
from app.core.config import get_settings
from app.core.database import get_db
from app.models import KycDocument, User

router = APIRouter(tags=["Identity verification"])
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}
DOCUMENT_TYPES = {"driver_license", "identity_document"}


def _fernet() -> Fernet:
    # Derive a dedicated encryption key from the deployment JWT secret. The
    # HKDF context separates this key from token signing use.
    secret = get_settings().jwt_secret.get_secret_value().encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"drivewell-kyc-v1", info=b"private-document-storage").derive(secret)
    import base64
    return Fernet(base64.urlsafe_b64encode(key))


def _identity(authorization: str | None) -> tuple[UUID, str]:
    claims = _access_claims(authorization)
    try:
        return UUID(claims["sub"]), str(claims.get("role", "customer"))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="Your session is invalid or expired.") from exc


async def _latest_documents(db: AsyncSession, user_ids: list[UUID]) -> list[KycDocument]:
    if not user_ids:
        return []
    result = await db.scalars(select(KycDocument).where(KycDocument.user_id.in_(user_ids)).order_by(KycDocument.created_at.desc()))
    latest: dict[tuple[UUID, str], KycDocument] = {}
    for document in result:
        latest.setdefault((document.user_id, document.document_type), document)
    return list(latest.values())


def _summary(documents: list[KycDocument]) -> dict:
    by_type = {doc.document_type: doc for doc in documents}
    statuses = {kind: (by_type[kind].status if kind in by_type else "missing") for kind in DOCUMENT_TYPES}
    overall = "verified" if all(value == "approved" for value in statuses.values()) else "rejected" if "rejected" in statuses.values() else "pending" if "pending" in statuses.values() else "not_submitted"
    return {"status": overall, "documents": statuses}


class ReviewRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=500)


@router.get("/auth/kyc")
async def kyc_status(authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    user_id, _ = _identity(authorization)
    documents = await _latest_documents(db, [user_id])
    return _summary(documents)


@router.post("/auth/kyc/documents/{document_type}", status_code=status.HTTP_201_CREATED)
async def submit_document(document_type: str, authorization: str | None = Header(default=None), file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    user_id, _ = _identity(authorization)
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=422, detail="Document type must be driver_license or identity_document.")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Upload a PDF, JPEG, or PNG document.")
    content = await file.read(MAX_DOCUMENT_BYTES + 1)
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Documents must be no larger than 5 MB.")
    signature_matches = (
        (file.content_type == "application/pdf" and content.startswith(b"%PDF-"))
        or (file.content_type == "image/jpeg" and content.startswith(b"\xff\xd8\xff"))
        or (file.content_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n"))
    )
    if not signature_matches:
        raise HTTPException(status_code=415, detail="The uploaded file does not match its declared PDF, JPEG, or PNG format.")
    safe_name = PurePath(file.filename or "document").name[:180]
    existing = await db.scalar(
        select(KycDocument)
        .where(KycDocument.user_id == user_id, KycDocument.document_type == document_type)
        .order_by(KycDocument.created_at.desc())
        .limit(1)
    )
    if existing is None:
        existing = KycDocument(user_id=user_id, document_type=document_type, encrypted_content=b"", content_type=file.content_type, original_filename=safe_name)
        db.add(existing)
    existing.encrypted_content = _fernet().encrypt(content)
    existing.content_type = file.content_type
    existing.original_filename = safe_name
    existing.status = "pending"
    existing.review_note = None
    existing.reviewed_by = None
    existing.reviewed_at = None
    existing.created_at = datetime.now(UTC)
    await db.commit()
    return {"status": "pending", "document_type": document_type, "message": "Document submitted for administrator review."}


@router.get("/auth/admin/kyc")
async def admin_kyc_list(authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    _require_admin(authorization)
    users = (await db.scalars(select(User).order_by(User.created_at.desc()).limit(500))).all()
    docs = await _latest_documents(db, [user.id for user in users])
    grouped: dict[UUID, list[KycDocument]] = {}
    for doc in docs:
        grouped.setdefault(doc.user_id, []).append(doc)
    return [{"user": {"id": str(user.id), "name": user.full_name, "email": user.email}, **_summary(grouped.get(user.id, [])), "items": [{"id": str(doc.id), "type": doc.document_type, "status": doc.status, "filename": doc.original_filename, "submitted_at": doc.created_at, "review_note": doc.review_note} for doc in grouped.get(user.id, [])]} for user in users if grouped.get(user.id)]


@router.get("/auth/admin/kyc/documents/{document_id}")
async def admin_kyc_document(document_id: UUID, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    _require_admin(authorization)
    doc = await db.get(KycDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="KYC document not found.")
    try:
        content = _fernet().decrypt(doc.encrypted_content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="KYC document could not be decrypted.") from exc
    safe_filename = "".join(character for character in doc.original_filename if character.isalnum() or character in "._-")[:120] or "document"
    return Response(content, media_type=doc.content_type, headers={"Content-Disposition": f'inline; filename="{safe_filename}"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/auth/admin/kyc/documents/{document_id}/review")
async def admin_review_kyc(document_id: UUID, payload: ReviewRequest, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    claims = _require_admin(authorization)
    doc = await db.get(KycDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="KYC document not found.")
    doc.status = payload.decision
    doc.review_note = payload.note
    doc.reviewed_by = UUID(claims["sub"])
    doc.reviewed_at = datetime.now(UTC)
    await db.commit()
    return {"id": str(doc.id), "status": doc.status, "review_note": doc.review_note}


@router.get("/auth/internal/users/{auth_subject}/rental-eligibility", dependencies=[Depends(verify_internal_service_key)])
async def rental_eligibility(auth_subject: str, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.auth_subject == auth_subject))
    if user is None or not user.is_active or not user.is_email_verified:
        raise HTTPException(status_code=403, detail="An active, email-verified account is required to rent.")
    docs = await _latest_documents(db, [user.id])
    summary = _summary(docs)
    return {"eligible": summary["status"] == "verified", **summary}
