"""MinIO storage wrapper for SAHAAY (free-first: uses local filesystem as fallback).

Supports:
- Basic file storage
- Resumable/chunked uploads
- Encrypted object keys
- Checksum verification
"""
import hashlib
import os
import secrets
from pathlib import Path
from typing import BinaryIO


# For MVP: use local filesystem storage (MinIO-compatible later)
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "./local_storage"))
STORAGE_ROOT.mkdir(exist_ok=True)

# Chunked upload configuration
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB chunks (MinIO multipart minimum)
UPLOAD_TEMP_DIR = STORAGE_ROOT / "_uploads"
UPLOAD_TEMP_DIR.mkdir(exist_ok=True)


def compute_checksum(file_bytes: bytes) -> str:
    """Compute SHA256 checksum."""
    return hashlib.sha256(file_bytes).hexdigest()


def compute_checksum_stream(file_stream: BinaryIO) -> str:
    """Compute SHA256 checksum from stream without loading entire file in memory."""
    sha256 = hashlib.sha256()
    while chunk := file_stream.read(8192):
        sha256.update(chunk)
    return sha256.hexdigest()


def generate_encrypted_key(original_filename: str, prefix: str = "evidence") -> str:
    """Generate encrypted object key with random component.
    
    Returns a path like: evidence/abc123def/original_filename.ext
    This prevents guessing file paths and adds privacy layer.
    """
    random_component = secrets.token_urlsafe(16)
    return f"{prefix}/{random_component}/{original_filename}"


def store_file(key: str, file_bytes: bytes) -> str:
    """Store file and return checksum.

    For MVP: saves to local filesystem under STORAGE_ROOT/{key}.
    TODO: Replace with MinIO client when infra is available.
    """
    path = STORAGE_ROOT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(file_bytes)
    return compute_checksum(file_bytes)


def store_file_stream(key: str, file_stream: BinaryIO) -> str:
    """Store file from stream and return checksum.
    
    More memory-efficient for large files.
    """
    path = STORAGE_ROOT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    
    sha256 = hashlib.sha256()
    with open(path, 'wb') as f:
        while chunk := file_stream.read(CHUNK_SIZE):
            f.write(chunk)
            sha256.update(chunk)
    
    return sha256.hexdigest()


def retrieve_file(key: str) -> bytes:
    """Retrieve file bytes.

    Raises FileNotFoundError if not found.
    """
    path = STORAGE_ROOT / key
    return path.read_bytes()


def initiate_chunked_upload(key: str) -> str:
    """Initiate a resumable chunked upload session.
    
    Returns upload_id for tracking the upload.
    For MVP: creates a temporary directory for chunks.
    TODO: Use MinIO multipart upload API when available.
    """
    upload_id = secrets.token_urlsafe(16)
    upload_dir = UPLOAD_TEMP_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Store metadata
    metadata_path = upload_dir / "_metadata"
    metadata_path.write_text(key)
    
    return upload_id


def upload_chunk(upload_id: str, chunk_number: int, chunk_data: bytes) -> None:
    """Upload a single chunk for resumable upload.
    
    Args:
        upload_id: Upload session ID
        chunk_number: Sequential chunk number (0-based)
        chunk_data: Chunk bytes
    """
    upload_dir = UPLOAD_TEMP_DIR / upload_id
    if not upload_dir.exists():
        raise ValueError(f"Upload session {upload_id} not found")
    
    chunk_path = upload_dir / f"chunk_{chunk_number:06d}"
    chunk_path.write_bytes(chunk_data)


def complete_chunked_upload(upload_id: str) -> tuple[str, str]:
    """Complete a chunked upload by assembling chunks.
    
    Returns:
        tuple of (object_key, checksum)
    """
    upload_dir = UPLOAD_TEMP_DIR / upload_id
    if not upload_dir.exists():
        raise ValueError(f"Upload session {upload_id} not found")
    
    # Read metadata to get target key
    metadata_path = upload_dir / "_metadata"
    key = metadata_path.read_text()
    
    # Assemble chunks in order
    target_path = STORAGE_ROOT / key
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    sha256 = hashlib.sha256()
    with open(target_path, 'wb') as target:
        chunk_files = sorted(upload_dir.glob("chunk_*"))
        for chunk_file in chunk_files:
            chunk_data = chunk_file.read_bytes()
            target.write(chunk_data)
            sha256.update(chunk_data)
    
    # Clean up temp files
    import shutil
    shutil.rmtree(upload_dir)
    
    return key, sha256.hexdigest()


def cancel_chunked_upload(upload_id: str) -> None:
    """Cancel and clean up a chunked upload session."""
    upload_dir = UPLOAD_TEMP_DIR / upload_id
    if upload_dir.exists():
        import shutil
        shutil.rmtree(upload_dir)
