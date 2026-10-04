"""File upload validation.

Defends against three distinct things, per spec §37/§40:
  1. Oversized uploads (denial-of-service via disk/memory exhaustion)
  2. Disallowed file types
  3. Spoofed file types — a renamed .exe with a ".pdf" extension is caught
     here because the extension alone is never trusted; the actual byte
     content is sniffed via libmagic and cross-checked against what the
     extension claims to be.

Filenames are never used to build a filesystem path (see app/services/storage.py) —
this module only sanitizes the *display* name so a user can't smuggle path
traversal or control characters into what gets shown back to them.
"""

import re

import magic

_ALLOWED_TYPES: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".txt": {"text/plain"},
    ".md": {"text/plain", "text/markdown"},
    ".csv": {"text/plain", "text/csv"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".gif": {"image/gif"},
    ".webp": {"image/webp"},
}


class FileValidationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def sanitize_display_filename(filename: str) -> str:
    """Strips path components and control characters. This is for safe
    *display* only — the stored filename on disk is always a generated UUID,
    never derived from user input (see storage.py).
    """
    name = filename.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:500] or "unnamed"


def validate_upload(*, filename: str, content: bytes, max_size_bytes: int) -> tuple[str, str]:
    """Validates a single uploaded file's size, extension, and sniffed content
    type. Returns (extension, sniffed_mime_type) on success.

    Raises FileValidationError with a client-safe message on any failure.
    """
    if len(content) == 0:
        raise FileValidationError("The uploaded file is empty.")
    if len(content) > max_size_bytes:
        max_mb = max_size_bytes / (1024 * 1024)
        raise FileValidationError(f"File exceeds the maximum allowed size of {max_mb:.0f}MB.")

    safe_name = sanitize_display_filename(filename)
    extension = _extract_extension(safe_name)
    if extension not in _ALLOWED_TYPES:
        allowed = ", ".join(sorted(_ALLOWED_TYPES))
        raise FileValidationError(
            f"File type '{extension or '(none)'}' is not supported. Allowed types: {allowed}."
        )

    sniffed_type = magic.from_buffer(content, mime=True)
    if sniffed_type not in _ALLOWED_TYPES[extension]:
        raise FileValidationError(
            f"File content does not match its extension ({extension}). "
            f"Detected type: {sniffed_type}."
        )

    return extension, sniffed_type


def _extract_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()
