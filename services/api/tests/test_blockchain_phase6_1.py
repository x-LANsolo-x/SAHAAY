import pytest
from datetime import datetime, timedelta

from services.api import models
from services.api.blockchain_hash import (
    validate_no_pii,
    canonical_json,
    compute_sha256,
    generate_complaint_hash,
    generate_status_hash,
    generate_sla_params_hash,
    generate_event_id,
    verify_hash,
    prepare_blockchain_payload,
    PIILeakageError,
)


def test_canonical_json_deterministic():
    """Test that canonical JSON is deterministic (same input = same output)."""
    data1 = {"b": 2, "a": 1, "c": 3}
    data2 = {"c": 3, "a": 1, "b": 2}
    
    result1 = canonical_json(data1)
    result2 = canonical_json(data2)
    
    assert result1 == result2
    assert result1 == '{"a":1,"b":2,"c":3}'


def test_canonical_json_no_whitespace():
    """Test that canonical JSON has no whitespace."""
    data = {"key": "value", "number": 42}
    result = canonical_json(data)
    
    assert ' ' not in result
    assert '\n' not in result
    assert '\t' not in result


def test_compute_sha256_deterministic():
    """Test that SHA256 hash is deterministic."""
    text = "test string"
    
    hash1 = compute_sha256(text)
    hash2 = compute_sha256(text)
    
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 = 32 bytes = 64 hex chars


def test_compute_sha256_different_inputs():
    """Test that different inputs produce different hashes."""
    hash1 = compute_sha256("input1")
    hash2 = compute_sha256("input2")
    
    assert hash1 != hash2


def test_validate_no_pii_safe_data():
    """Test that safe data passes PII validation."""
    safe_data = {
        "complaint_id": "abc123",
        "category": "service_quality",
        "status": "submitted",
        "created_at": "2024-01-01T00:00:00",
    }
    
    # Should not raise
    validate_no_pii(safe_data)


def test_validate_no_pii_rejects_user_id():
    """Test that user_id is rejected as PII."""
    unsafe_data = {
        "complaint_id": "abc123",
        "user_id": "user123",  # PII!
    }
    
    with pytest.raises(PIILeakageError) as exc_info:
        validate_no_pii(unsafe_data)
    
    assert "user_id" in str(exc_info.value)


def test_validate_no_pii_rejects_username():
    """Test that username is rejected as PII."""
    unsafe_data = {
        "complaint_id": "abc123",
        "username": "john_doe",  # PII!
    }
    
    with pytest.raises(PIILeakageError):
        validate_no_pii(unsafe_data)


def test_validate_no_pii_rejects_contact_info():
    """Test that contact_info is rejected as PII."""
    unsafe_data = {
        "complaint_id": "abc123",
        "contact_info": "phone@example.com",  # PII!
    }
    
    with pytest.raises(PIILeakageError):
        validate_no_pii(unsafe_data)


def test_validate_no_pii_rejects_feedback_comments():
    """Test that feedback_comments is rejected as PII."""
    unsafe_data = {
        "complaint_id": "abc123",
        "feedback_comments": "Great service!",  # PII!
    }
    
    with pytest.raises(PIILeakageError):
        validate_no_pii(unsafe_data)


def test_validate_no_pii_rejects_description():
    """Test that description is rejected (may contain PII)."""
    unsafe_data = {
        "complaint_id": "abc123",
        "description": "I went to clinic...",  # May contain PII!
    }
    
    with pytest.raises(PIILeakageError):
        validate_no_pii(unsafe_data)


def test_validate_no_pii_rejects_email_variants():
    """Test that any field with 'email' is rejected."""
    unsafe_data = {
        "complaint_id": "abc123",
        "user_email": "test@example.com",  # PII!
    }
    
    with pytest.raises(PIILeakageError):
        validate_no_pii(unsafe_data)


def test_validate_no_pii_rejects_phone_variants():
    """Test that any field with 'phone' is rejected."""
    unsafe_data = {
        "complaint_id": "abc123",
        "phone_number": "1234567890",  # PII!
    }
    
    with pytest.raises(PIILeakageError):
        validate_no_pii(unsafe_data)


def test_validate_no_pii_rejects_name_variants():
    """Test that any field with 'name' (except category name) is rejected."""
    unsafe_data = {
        "complaint_id": "abc123",
        "full_name": "John Doe",  # PII!
    }
    
    with pytest.raises(PIILeakageError):
        validate_no_pii(unsafe_data)


def test_generate_complaint_hash():
    """Test complaint hash generation."""
    # Create mock complaint
    complaint = models.Complaint(
        id="complaint_123",
        category=models.ComplaintCategory.service_quality,
        status=models.ComplaintStatus.submitted,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    
    hash1 = generate_complaint_hash(complaint)
    
    # Verify hash properties
    assert len(hash1) == 64  # SHA256
    assert all(c in '0123456789abcdef' for c in hash1)  # Hex
    
    # Verify deterministic
    hash2 = generate_complaint_hash(complaint)
    assert hash1 == hash2


def test_generate_complaint_hash_changes_with_data():
    """Test that hash changes when complaint data changes."""
    complaint1 = models.Complaint(
        id="complaint_123",
        category=models.ComplaintCategory.service_quality,
        status=models.ComplaintStatus.submitted,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    
    complaint2 = models.Complaint(
        id="complaint_123",
        category=models.ComplaintCategory.staff_behavior,  # Different!
        status=models.ComplaintStatus.submitted,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    
    hash1 = generate_complaint_hash(complaint1)
    hash2 = generate_complaint_hash(complaint2)
    
    assert hash1 != hash2


def test_generate_status_hash():
    """Test status hash generation."""
    complaint = models.Complaint(
        id="complaint_123",
        category=models.ComplaintCategory.service_quality,
        status=models.ComplaintStatus.under_review,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 2, 12, 0, 0),
        resolved_at=None,
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
    )
    
    hash_result = generate_status_hash(complaint)
    
    assert len(hash_result) == 64
    assert all(c in '0123456789abcdef' for c in hash_result)


def test_generate_sla_params_hash():
    """Test SLA params hash generation."""
    complaint = models.Complaint(
        id="complaint_123",
        category=models.ComplaintCategory.service_quality,
        status=models.ComplaintStatus.submitted,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    
    hash_result = generate_sla_params_hash(complaint)
    
    assert len(hash_result) == 64


def test_generate_event_id_unique():
    """Test that event IDs are unique."""
    id1 = generate_event_id()
    id2 = generate_event_id()
    
    assert id1 != id2
    assert id1.startswith("event_")
    assert id2.startswith("event_")


def test_verify_hash_success():
    """Test hash verification with correct data."""
    data = {"a": 1, "b": 2, "c": 3}
    canonical = canonical_json(data)
    expected_hash = compute_sha256(canonical)
    
    assert verify_hash(data, expected_hash)


def test_verify_hash_failure():
    """Test hash verification fails with incorrect data."""
    data1 = {"a": 1, "b": 2}
    data2 = {"a": 1, "b": 3}  # Different value
    
    canonical1 = canonical_json(data1)
    hash1 = compute_sha256(canonical1)
    
    assert not verify_hash(data2, hash1)


def test_prepare_blockchain_payload_no_pii():
    """Test that blockchain payload contains NO PII."""
    complaint = models.Complaint(
        id="complaint_123",
        user_id="user_456",  # PII in DB, but NOT in payload
        category=models.ComplaintCategory.service_quality,
        description="Long wait times",  # PII in DB, but NOT in payload
        status=models.ComplaintStatus.submitted,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
    )
    
    payload = prepare_blockchain_payload(complaint)
    
    # Verify payload structure
    assert "complaint_hash" in payload
    assert "status_hash" in payload
    assert "sla_params_hash" in payload
    assert "created_at_timestamp" in payload
    assert "updated_at_timestamp" in payload
    assert "event_id" in payload
    assert "version" in payload
    
    # Verify NO PII in payload
    assert "user_id" not in payload
    assert "description" not in payload
    assert "contact_info" not in payload
    assert "feedback_comments" not in payload
    
    # Verify all values are hashes or timestamps
    assert len(payload["complaint_hash"]) == 64
    assert len(payload["status_hash"]) == 64
    assert len(payload["sla_params_hash"]) == 64
    assert isinstance(payload["created_at_timestamp"], int)
    assert isinstance(payload["updated_at_timestamp"], int)


def test_prepare_blockchain_payload_deterministic():
    """Test that payload is deterministic for same complaint."""
    complaint = models.Complaint(
        id="complaint_123",
        category=models.ComplaintCategory.service_quality,
        status=models.ComplaintStatus.submitted,
        current_level=1,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 0, 0),
        sla_due_at=datetime(2024, 1, 8, 12, 0, 0),
    )
    
    payload1 = prepare_blockchain_payload(complaint)
    payload2 = prepare_blockchain_payload(complaint)
    
    # Hashes should be identical
    assert payload1["complaint_hash"] == payload2["complaint_hash"]
    assert payload1["status_hash"] == payload2["status_hash"]
    assert payload1["sla_params_hash"] == payload2["sla_params_hash"]
    assert payload1["created_at_timestamp"] == payload2["created_at_timestamp"]
    
    # Event IDs should be different (unique nonces)
    assert payload1["event_id"] != payload2["event_id"]


def test_static_pii_check_comprehensive():
    """Comprehensive test: ensure all known PII fields are blocked."""
    pii_test_cases = [
        {"user_id": "123"},
        {"username": "john"},
        {"contact_info": "phone"},
        {"contact_info_encrypted": "encrypted"},
        {"feedback_comments": "good"},
        {"description": "issue"},
        {"evidence": "file"},
        {"filename": "doc.pdf"},
        {"changed_by_user_id": "456"},
        {"actor_user_id": "789"},
        {"email": "test@example.com"},
        {"phone": "1234567890"},
        {"name": "John Doe"},
        {"address": "123 Street"},
        {"user_email": "test@test.com"},
        {"phone_number": "999"},
        {"full_name": "Jane"},
    ]
    
    for pii_data in pii_test_cases:
        with pytest.raises(PIILeakageError):
            validate_no_pii(pii_data)
