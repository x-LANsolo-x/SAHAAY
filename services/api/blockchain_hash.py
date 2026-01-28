"""Blockchain hash generation with PII protection.

This module generates deterministic hashes for blockchain anchoring while
ensuring NO PII (Personally Identifiable Information) is included.

Design principles:
1. Only hash non-PII metadata (complaint_id, category, status, timestamps)
2. Use canonical JSON (sorted keys, no whitespace) for determinism
3. Always use SHA256 for consistency
4. Validate input to reject any PII fields
"""
import hashlib
import json
from datetime import datetime
from typing import Any

from services.api import models


# PII fields that MUST NEVER be hashed or sent to blockchain
PII_FIELDS = {
    "user_id",
    "username",
    "contact_info",
    "contact_info_encrypted",
    "feedback_comments",
    "description",  # May contain PII
    "evidence",
    "filename",
    "changed_by_user_id",
    "actor_user_id",
    "email",
    "phone",
    "name",
    "address",
}


class PIILeakageError(Exception):
    """Raised when PII is detected in blockchain payload."""
    pass


def validate_no_pii(data: dict) -> None:
    """Validate that no PII fields are present in data.
    
    Args:
        data: Dictionary to validate
        
    Raises:
        PIILeakageError: If any PII field is detected
    """
    for key in data.keys():
        if key.lower() in PII_FIELDS or any(pii in key.lower() for pii in ["name", "email", "phone"]):
            raise PIILeakageError(f"PII field detected: {key}. Cannot include in blockchain payload.")


def canonical_json(data: dict) -> str:
    """Convert dict to canonical JSON string.
    
    Canonical format ensures deterministic hashing:
    - Keys sorted alphabetically
    - No whitespace
    - Consistent formatting
    
    Args:
        data: Dictionary to canonicalize
        
    Returns:
        Canonical JSON string
    """
    return json.dumps(data, sort_keys=True, separators=(',', ':'))


def compute_sha256(data: str) -> str:
    """Compute SHA256 hash of string.
    
    Args:
        data: String to hash
        
    Returns:
        Hex-encoded SHA256 hash
    """
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def generate_complaint_hash(complaint: models.Complaint) -> str:
    """Generate deterministic hash for complaint (NO PII).
    
    Payload includes:
    - complaint_id (not PII - internal ID)
    - category (enum value)
    - status (enum value)
    - current_level (escalation level)
    - created_at (timestamp)
    - sla_due_at (timestamp)
    - version (for future compatibility)
    
    Explicitly EXCLUDED (PII):
    - user_id, description, contact_info, feedback
    
    Args:
        complaint: Complaint model instance
        
    Returns:
        SHA256 hash (64 hex chars)
        
    Raises:
        PIILeakageError: If implementation accidentally includes PII
    """
    payload = {
        "complaint_id": complaint.id,
        "category": complaint.category.value,
        "status": complaint.status.value,
        "current_level": complaint.current_level,
        "created_at": complaint.created_at.isoformat(),
        "sla_due_at": complaint.sla_due_at.isoformat() if complaint.sla_due_at else None,
        "version": "1.0",
    }
    
    # Validate no PII
    validate_no_pii(payload)
    
    # Generate canonical JSON and hash
    canonical = canonical_json(payload)
    return compute_sha256(canonical)


def generate_status_hash(complaint: models.Complaint) -> str:
    """Generate hash for complaint status.
    
    Args:
        complaint: Complaint model instance
        
    Returns:
        SHA256 hash of status metadata
    """
    payload = {
        "complaint_id": complaint.id,
        "status": complaint.status.value,
        "current_level": complaint.current_level,
        "updated_at": complaint.updated_at.isoformat(),
        "resolved_at": complaint.resolved_at.isoformat() if complaint.resolved_at else None,
        "version": "1.0",
    }
    
    validate_no_pii(payload)
    canonical = canonical_json(payload)
    return compute_sha256(canonical)


def generate_sla_params_hash(complaint: models.Complaint) -> str:
    """Generate hash for SLA parameters.
    
    Args:
        complaint: Complaint model instance
        
    Returns:
        SHA256 hash of SLA metadata
    """
    payload = {
        "complaint_id": complaint.id,
        "category": complaint.category.value,
        "current_level": complaint.current_level,
        "sla_due_at": complaint.sla_due_at.isoformat() if complaint.sla_due_at else None,
        "created_at": complaint.created_at.isoformat(),
        "version": "1.0",
    }
    
    validate_no_pii(payload)
    canonical = canonical_json(payload)
    return compute_sha256(canonical)


def generate_event_id() -> str:
    """Generate unique event ID/nonce for blockchain transaction.
    
    Returns:
        Unique event ID (timestamp + random component)
    """
    import secrets
    timestamp = int(datetime.utcnow().timestamp() * 1000)  # milliseconds
    random_part = secrets.token_hex(8)
    return f"event_{timestamp}_{random_part}"


def verify_hash(original_data: dict, expected_hash: str) -> bool:
    """Verify that hash matches original data.
    
    Args:
        original_data: Original data dictionary
        expected_hash: Expected SHA256 hash
        
    Returns:
        True if hash matches, False otherwise
    """
    canonical = canonical_json(original_data)
    computed_hash = compute_sha256(canonical)
    return computed_hash == expected_hash


def prepare_blockchain_payload(complaint: models.Complaint) -> dict:
    """Prepare complete blockchain payload (hashes only, no PII).
    
    This is what would be sent to smart contract for anchoring.
    
    Args:
        complaint: Complaint model instance
        
    Returns:
        Dictionary with hashes and timestamps (NO PII)
        
    Raises:
        PIILeakageError: If any PII is detected
    """
    payload = {
        "complaint_hash": generate_complaint_hash(complaint),
        "status_hash": generate_status_hash(complaint),
        "sla_params_hash": generate_sla_params_hash(complaint),
        "created_at_timestamp": int(complaint.created_at.timestamp()),
        "updated_at_timestamp": int(complaint.updated_at.timestamp()),
        "event_id": generate_event_id(),
        "version": "1.0",
    }
    
    # Final validation - ensure no PII in payload
    validate_no_pii(payload)
    
    return payload
