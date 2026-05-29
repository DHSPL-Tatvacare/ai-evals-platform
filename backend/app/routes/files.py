"""Files API routes."""
import io
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, get_auth_context
from app.auth.permissions import require_permission, require_app_access
from app.config import settings
from app.database import get_db
from app.models.application_uploaded_file import ApplicationUploadedFile
from app.openapi_examples import err, ok
from app.schemas.file import FileResponse as FileResponseSchema
from app.services.file_storage import file_storage

router = APIRouter(prefix="/api/files", tags=["files"])

_FILE_EXAMPLE = {
    "id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
    "originalName": "call-0420.mp3",
    "mimeType": "audio/mpeg",
    "sizeBytes": 482133,
    "storagePath": "uploads/2026/05/1a2b3c4d.mp3",
    "createdAt": "2026-05-20T09:14:00Z",
    "tenantId": "3a2e1b0c-9d8e-7f6a-5b4c-3d2e1f0a9b8c",
    "userId": "9b1f2c3d-4e5a-6b7c-8d9e-0f1a2b3c4d5e",
}

_MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
_ALLOWED_MIMES = set(m.strip() for m in settings.ALLOWED_UPLOAD_MIMES.split(",") if m.strip())


@router.post(
    "/upload",
    response_model=FileResponseSchema,
    status_code=201,
    summary="Upload a file",
    description=(
        "Upload a single file as `multipart/form-data` and get back a stored file record. "
        "Reference the returned `id` from a listing's `audioFile`/`transcriptFile` field. "
        "Uploads are capped in size and restricted to allowed MIME types.\n\n"
        "**Authentication:** Bearer token with `asset:manage`."
    ),
    responses={
        201: ok("The stored file record.", _FILE_EXAMPLE),
        400: err("The file's MIME type is not in the allowed list.", "File type 'application/x-msdownload' not allowed"),
        413: err("The file exceeds the maximum upload size.", "File exceeds 100MB limit"),
    },
)
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    auth: AuthContext = require_permission('asset:manage'),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file and create a file record."""
    contents = await file.read()

    if len(contents) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit")

    if file.content_type and file.content_type not in _ALLOWED_MIMES:
        raise HTTPException(
            400, detail=f"File type '{file.content_type}' not allowed",
        )

    storage_path = await file_storage.save(contents, file.filename or "unnamed")

    record = ApplicationUploadedFile(
        original_name=file.filename or "unnamed",
        mime_type=file.content_type,
        size_bytes=len(contents),
        storage_path=storage_path,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.get(
    "/{file_id}",
    response_model=FileResponseSchema,
    summary="Get file metadata",
    description=(
        "Return a file's metadata — original name, MIME type, size, and timestamps — "
        "without downloading its contents.\n\n"
        "**Authentication:** Bearer token. Only your own files are visible."
    ),
    responses={
        200: ok("The file's metadata.", _FILE_EXAMPLE),
        404: err("No such file for your tenant and user.", "File not found"),
    },
)
async def get_file_metadata(
    file_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Get file metadata by ID."""
    result = await db.execute(
        select(ApplicationUploadedFile).where(
            ApplicationUploadedFile.id == file_id,
            ApplicationUploadedFile.tenant_id == auth.tenant_id,
            ApplicationUploadedFile.user_id == auth.user_id,
        )
    )
    file_rec = result.scalar_one_or_none()
    if not file_rec:
        raise HTTPException(status_code=404, detail="File not found")
    return file_rec


@router.get(
    "/{file_id}/download",
    summary="Download a file",
    description=(
        "Stream a file's raw bytes back as an attachment, with its original filename and "
        "content type preserved.\n\n"
        "**Authentication:** Bearer token. Only your own files can be downloaded."
    ),
    responses={
        200: {"description": "The file's binary content, served as an attachment.", "content": {"application/octet-stream": {}}},
        404: err("No such file for your tenant and user.", "File not found"),
    },
)
async def download_file(
    file_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Download a file by ID."""
    result = await db.execute(
        select(ApplicationUploadedFile).where(
            ApplicationUploadedFile.id == file_id,
            ApplicationUploadedFile.tenant_id == auth.tenant_id,
            ApplicationUploadedFile.user_id == auth.user_id,
        )
    )
    file_rec = result.scalar_one_or_none()
    if not file_rec:
        raise HTTPException(status_code=404, detail="File not found")

    content = await file_storage.read(file_rec.storage_path)
    return StreamingResponse(
        io.BytesIO(content),
        media_type=file_rec.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file_rec.original_name}"'},
    )


@router.delete(
    "/{file_id}",
    summary="Delete a file",
    description=(
        "Delete a file from storage and remove its record. Listings that still reference "
        "the file will no longer resolve it, so delete only when it's truly unused.\n\n"
        "**Authentication:** Bearer token with `asset:manage`."
    ),
    responses={
        200: ok("The file was deleted.", {"deleted": True, "id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"}),
        404: err("No such file for your tenant and user.", "File not found"),
    },
)
async def delete_file(
    file_id: UUID,
    auth: AuthContext = require_permission('asset:manage'),
    db: AsyncSession = Depends(get_db),
):
    """Delete a file and its record."""
    result = await db.execute(
        select(ApplicationUploadedFile).where(
            ApplicationUploadedFile.id == file_id,
            ApplicationUploadedFile.tenant_id == auth.tenant_id,
            ApplicationUploadedFile.user_id == auth.user_id,
        )
    )
    file_rec = result.scalar_one_or_none()
    if not file_rec:
        raise HTTPException(status_code=404, detail="File not found")

    await file_storage.delete(file_rec.storage_path)
    await db.delete(file_rec)
    await db.commit()

    return {"deleted": True, "id": str(file_id)}
