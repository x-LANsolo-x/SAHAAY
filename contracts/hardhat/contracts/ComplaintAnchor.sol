// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ComplaintAnchor
 * @dev Immutable complaint anchoring with privacy-first design (hashes only, NO PII)
 * 
 * Features:
 * - Store only cryptographic hashes (NO personal data)
 * - Replay protection via nonce tracking
 * - Tamper-proof audit trail
 * - Event emission for off-chain indexing
 */
contract ComplaintAnchor {
    
    // Complaint anchor structure (NO PII - hashes only)
    struct Anchor {
        bytes32 complaintHash;      // SHA256 of complaint metadata
        bytes32 statusHash;         // SHA256 of current status
        bytes32 slaHash;            // SHA256 of SLA parameters
        uint256 createdAt;          // Creation timestamp
        uint256 lastUpdatedAt;      // Last update timestamp
        uint256 statusNonce;        // Replay protection counter
        bool exists;                // Existence flag
    }
    
    // Mapping: complaintHash => Anchor
    mapping(bytes32 => Anchor) public anchors;
    
    // Events for off-chain tracking
    event ComplaintAnchored(
        bytes32 indexed complaintHash,
        bytes32 slaHash,
        uint256 createdAt,
        uint256 nonce
    );
    
    event StatusUpdated(
        bytes32 indexed complaintHash,
        bytes32 statusHash,
        uint256 updatedAt,
        uint256 nonce
    );
    
    // Errors
    error AnchorAlreadyExists(bytes32 complaintHash);
    error AnchorNotFound(bytes32 complaintHash);
    error InvalidNonce(uint256 provided, uint256 expected);
    error InvalidTimestamp(uint256 timestamp);
    
    /**
     * @dev Create initial complaint anchor (hashes only, NO PII)
     * @param complaintHash SHA256 hash of complaint metadata
     * @param slaHash SHA256 hash of SLA parameters
     * @param statusHash Initial status hash
     * @param createdAt Creation timestamp (Unix seconds)
     * @param nonce Initial nonce (for replay protection)
     */
    function createComplaintAnchor(
        bytes32 complaintHash,
        bytes32 slaHash,
        bytes32 statusHash,
        uint256 createdAt,
        uint256 nonce
    ) external {
        // Validation: Anchor must not already exist
        if (anchors[complaintHash].exists) {
            revert AnchorAlreadyExists(complaintHash);
        }
        
        // Validation: Timestamp must be reasonable (not too far in past/future)
        require(
            createdAt <= block.timestamp + 1 hours,
            "Timestamp too far in future"
        );
        require(
            createdAt >= block.timestamp - 30 days,
            "Timestamp too old"
        );
        
        // Validation: Hashes must not be zero
        require(complaintHash != bytes32(0), "Invalid complaint hash");
        require(slaHash != bytes32(0), "Invalid SLA hash");
        require(statusHash != bytes32(0), "Invalid status hash");
        
        // Create anchor
        anchors[complaintHash] = Anchor({
            complaintHash: complaintHash,
            statusHash: statusHash,
            slaHash: slaHash,
            createdAt: createdAt,
            lastUpdatedAt: createdAt,
            statusNonce: nonce,
            exists: true
        });
        
        emit ComplaintAnchored(complaintHash, slaHash, createdAt, nonce);
    }
    
    /**
     * @dev Update complaint status with replay protection
     * @param complaintHash SHA256 hash of complaint (identifier)
     * @param statusHash New status hash
     * @param updatedAt Update timestamp
     * @param nonce New nonce (must be > previous nonce)
     */
    function updateStatusAnchor(
        bytes32 complaintHash,
        bytes32 statusHash,
        uint256 updatedAt,
        uint256 nonce
    ) external {
        // Validation: Anchor must exist
        if (!anchors[complaintHash].exists) {
            revert AnchorNotFound(complaintHash);
        }
        
        Anchor storage anchor = anchors[complaintHash];
        
        // Replay protection: Nonce must be greater than previous
        if (nonce <= anchor.statusNonce) {
            revert InvalidNonce(nonce, anchor.statusNonce + 1);
        }
        
        // Validation: Timestamp must be after creation and not too far in future
        require(
            updatedAt >= anchor.createdAt,
            "Update timestamp before creation"
        );
        require(
            updatedAt <= block.timestamp + 1 hours,
            "Timestamp too far in future"
        );
        
        // Validation: Status hash must not be zero
        require(statusHash != bytes32(0), "Invalid status hash");
        
        // Update anchor
        anchor.statusHash = statusHash;
        anchor.lastUpdatedAt = updatedAt;
        anchor.statusNonce = nonce;
        
        emit StatusUpdated(complaintHash, statusHash, updatedAt, nonce);
    }
    
    /**
     * @dev Get anchor details
     * @param complaintHash SHA256 hash of complaint
     * @return Anchor structure
     */
    function getAnchor(bytes32 complaintHash) 
        external 
        view 
        returns (Anchor memory) 
    {
        if (!anchors[complaintHash].exists) {
            revert AnchorNotFound(complaintHash);
        }
        return anchors[complaintHash];
    }
    
    /**
     * @dev Check if anchor exists
     * @param complaintHash SHA256 hash of complaint
     * @return bool True if anchor exists
     */
    function anchorExists(bytes32 complaintHash) 
        external 
        view 
        returns (bool) 
    {
        return anchors[complaintHash].exists;
    }
    
    /**
     * @dev Get current nonce for replay protection
     * @param complaintHash SHA256 hash of complaint
     * @return uint256 Current nonce
     */
    function getCurrentNonce(bytes32 complaintHash) 
        external 
        view 
        returns (uint256) 
    {
        if (!anchors[complaintHash].exists) {
            revert AnchorNotFound(complaintHash);
        }
        return anchors[complaintHash].statusNonce;
    }
    
    /**
     * @dev Verify status hash matches current anchor
     * @param complaintHash SHA256 hash of complaint
     * @param expectedStatusHash Expected status hash
     * @return bool True if hash matches
     */
    function verifyStatusHash(
        bytes32 complaintHash, 
        bytes32 expectedStatusHash
    ) 
        external 
        view 
        returns (bool) 
    {
        if (!anchors[complaintHash].exists) {
            return false;
        }
        return anchors[complaintHash].statusHash == expectedStatusHash;
    }
}
