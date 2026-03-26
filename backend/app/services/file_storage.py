"""File storage abstraction. Local filesystem for dev, Azure Blob for production."""
import os
import uuid
import aiofiles
from pathlib import Path
from app.config import settings


class FileStorageService:
    """Handles file read/write to local disk or Azure Blob Storage."""

    def __init__(self):
        if settings.FILE_STORAGE_TYPE == "local":
            self.base_path = Path(settings.FILE_STORAGE_PATH)
            self.base_path.mkdir(parents=True, exist_ok=True)

    async def save(self, file_bytes: bytes, original_name: str) -> str:
        """Save file bytes. Returns the storage key (local path or blob name)."""
        file_id = str(uuid.uuid4())
        ext = Path(original_name).suffix
        filename = f"{file_id}{ext}"

        if settings.FILE_STORAGE_TYPE == "local":
            file_path = self.base_path / filename
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(file_bytes)
            return str(file_path)

        elif settings.FILE_STORAGE_TYPE == "azure_blob":
            from azure.storage.blob.aio import BlobServiceClient
            client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
            async with client:
                container = client.get_container_client(settings.AZURE_STORAGE_CONTAINER)
                await container.upload_blob(filename, file_bytes, overwrite=True)
            return filename

        raise ValueError(f"Unknown storage type: {settings.FILE_STORAGE_TYPE}")

    async def read(self, storage_path: str) -> bytes:
        """Read file bytes from storage key."""
        if settings.FILE_STORAGE_TYPE == "local":
            async with aiofiles.open(storage_path, "rb") as f:
                return await f.read()

        elif settings.FILE_STORAGE_TYPE == "azure_blob":
            from azure.storage.blob.aio import BlobServiceClient
            client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
            async with client:
                container = client.get_container_client(settings.AZURE_STORAGE_CONTAINER)
                blob = container.get_blob_client(storage_path)
                stream = await blob.download_blob()
                return await stream.readall()

        raise NotImplementedError(f"Read not implemented for {settings.FILE_STORAGE_TYPE}")

    async def delete(self, storage_path: str) -> None:
        """Delete file from storage."""
        if settings.FILE_STORAGE_TYPE == "local":
            path = Path(storage_path)
            if path.exists():
                os.remove(path)
            return

        elif settings.FILE_STORAGE_TYPE == "azure_blob":
            from azure.storage.blob.aio import BlobServiceClient
            client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
            async with client:
                container = client.get_container_client(settings.AZURE_STORAGE_CONTAINER)
                blob = container.get_blob_client(storage_path)
                await blob.delete_blob(delete_snapshots="include")
            return

        raise NotImplementedError(f"Delete not implemented for {settings.FILE_STORAGE_TYPE}")


file_storage = FileStorageService()
