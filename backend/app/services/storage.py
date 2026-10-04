"""File storage abstraction.

`LocalFileStorage` is the only implementation for now (local disk, tenant-
isolated by directory). Kept behind `FileStorage` so an S3-compatible
implementation can be added later (see PLAN.md open question about real
object storage vs. local filesystem for this portfolio build) without
touching any calling code — only the dependency wiring changes.

Storage paths are never derived from user-supplied filenames — every stored
file gets a generated UUID name, under a path scoped to organization_id.
This means even a maliciously crafted "filename" from an upload can't
traverse outside the tenant's directory, because it's never used as a path
component at all.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class FileStorage(Protocol):
    async def save(self, *, organization_id: uuid.UUID, extension: str, content: bytes) -> str:
        """Persists content, returns an opaque storage_path/key."""
        ...

    async def read(self, storage_path: str) -> bytes: ...

    async def delete(self, storage_path: str) -> None: ...


class LocalFileStorage:
    def __init__(self, root: str) -> None:
        self._root = Path(root)

    async def save(self, *, organization_id: uuid.UUID, extension: str, content: bytes) -> str:
        org_dir = self._root / str(organization_id)
        stored_name = f"{uuid.uuid4()}{extension}"
        target = org_dir / stored_name

        def _write() -> None:
            org_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        await asyncio.to_thread(_write)
        # Stored as a path relative to the storage root, not an absolute
        # filesystem path — keeps the DB portable if STORAGE_ROOT ever moves.
        return str(Path(str(organization_id)) / stored_name)

    async def read(self, storage_path: str) -> bytes:
        return await asyncio.to_thread((self._root / storage_path).read_bytes)

    async def delete(self, storage_path: str) -> None:
        path = self._root / storage_path
        await asyncio.to_thread(lambda: path.unlink(missing_ok=True))


def get_file_storage() -> FileStorage:
    return LocalFileStorage(get_settings().storage_root)
