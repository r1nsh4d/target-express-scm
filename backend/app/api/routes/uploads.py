from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models.user import User
from app.services.storage import (
    ALLOWED_TYPES,
    MAX_BYTES,
    StorageError,
    build_key,
    is_configured,
    put_object,
)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

# What a photograph is evidence OF. Keeps the bucket navigable and lets a
# retention policy treat driver photos differently from receipts later.
KINDS = {
    "loading",      # the stacked, labelled consignment going into the vehicle
    "delivery",     # the unloaded goods and the receiver
    "odometer",     # the meter, at the start and the end
    "receipt",      # toll, fuel, unloading slips
    "signature",
    "other",
}


class UploadOut(BaseModel):
    url: str
    key: str
    content_type: str
    size: int


class StorageStatusOut(BaseModel):
    configured: bool
    bucket: str | None = None


@router.get("/status", response_model=StorageStatusOut)
def storage_status(_: User = Depends(get_current_user)) -> StorageStatusOut:
    """Lets the client hide photo controls rather than offer a button that
    cannot work."""
    from app.core.config import settings

    return StorageStatusOut(
        configured=is_configured(),
        bucket=settings.s3_bucket if is_configured() else None,
    )


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),
    kind: str = Form(default="other"),
    _: User = Depends(get_current_user),
) -> UploadOut:
    """Store one photograph and return the URL to save against the record.

    The URL goes on the freight point, the leg or the expense — this endpoint
    only stores the bytes.
    """
    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Object storage is not configured on this server",
        )

    if kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown upload kind '{kind}'")

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"{content_type or 'That file type'} is not accepted. Use a photo or a PDF.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty")
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"That file is {len(data) // 1_000_000} MB. The limit is "
            f"{MAX_BYTES // 1_000_000} MB.",
        )

    try:
        stored = put_object(data, build_key(kind, file.filename, content_type), content_type)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return UploadOut(
        url=stored.url, key=stored.key, content_type=stored.content_type, size=stored.size
    )
