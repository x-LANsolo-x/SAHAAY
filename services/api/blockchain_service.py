"""Blockchain service for anchoring complaints to smart contract.

Features:
- Graceful degradation (workflow continues on blockchain failure)
- Async retry mechanism
- Transaction tracking
- Error logging without disrupting API
"""
import logging
from typing import Optional
from datetime import datetime

from services.api import models
from services.api.blockchain_hash import prepare_blockchain_payload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BlockchainServiceError(Exception):
    """Raised when blockchain operation fails (non-critical)."""
    pass


class BlockchainService:
    """Service for interacting with ComplaintAnchor smart contract.
    
    This service implements graceful degradation:
    - If blockchain fails, complaint workflow continues
    - Failures are logged and retried asynchronously
    - No hard failures in API responses
    """
    
    def __init__(self, web3_provider: Optional[str] = None, contract_address: Optional[str] = None):
        """Initialize blockchain service.
        
        Args:
            web3_provider: Web3 RPC URL (e.g., Polygon RPC)
            contract_address: Deployed contract address
        """
        self.web3_provider = web3_provider
        self.contract_address = contract_address
        self.enabled = web3_provider is not None and contract_address is not None
        
        if not self.enabled:
            logger.warning("Blockchain service disabled (no provider/contract configured)")
    
    def anchor_complaint(self, db, complaint: models.Complaint) -> tuple[bool, Optional[str]]:
        """Anchor complaint to blockchain (graceful degradation).
        
        This method NEVER raises exceptions to API layer. If blockchain fails,
        it logs the error and returns False, allowing workflow to continue.
        
        Args:
            db: Database session
            complaint: Complaint to anchor
            
        Returns:
            tuple of (success: bool, tx_hash: Optional[str])
        """
        if not self.enabled:
            logger.info(f"Blockchain disabled, skipping anchor for complaint {complaint.id}")
            return False, None
        
        try:
            # Step 1: Compute hashes (NO PII)
            payload = prepare_blockchain_payload(complaint)
            
            # Step 2: Call blockchain contract
            tx_hash = self._send_to_blockchain(payload)
            
            # Step 3: Success - mark as anchored
            anchor = models.BlockchainAnchor(
                entity_type="complaint",
                entity_id=complaint.id,
                complaint_hash=payload["complaint_hash"],
                status_hash=payload["status_hash"],
                sla_params_hash=payload["sla_params_hash"],
                created_at_timestamp=payload["created_at_timestamp"],
                updated_at_timestamp=payload["updated_at_timestamp"],
                event_id=payload["event_id"],
                anchor_version=payload["version"],
                blockchain_tx_hash=tx_hash,
                blockchain_status="pending",  # Will be confirmed by worker
            )
            db.add(anchor)
            db.commit()
            
            logger.info(f"Complaint {complaint.id} anchored to blockchain: {tx_hash}")
            return True, tx_hash
            
        except Exception as e:
            # Step 4: Failure - continue off-chain workflow
            logger.error(f"Blockchain anchor failed for complaint {complaint.id}: {e}")
            
            # Store pending anchor for retry
            try:
                anchor = models.BlockchainAnchor(
                    entity_type="complaint",
                    entity_id=complaint.id,
                    complaint_hash=payload["complaint_hash"],
                    status_hash=payload["status_hash"],
                    sla_params_hash=payload["sla_params_hash"],
                    created_at_timestamp=payload["created_at_timestamp"],
                    updated_at_timestamp=payload["updated_at_timestamp"],
                    event_id=payload["event_id"],
                    anchor_version=payload["version"],
                    blockchain_status="pending_retry",  # Will retry
                )
                db.add(anchor)
                db.commit()
            except Exception as db_error:
                logger.error(f"Failed to store pending anchor: {db_error}")
            
            # Return False but DO NOT raise exception
            return False, None
    
    def update_status_anchor(self, db, complaint: models.Complaint, anchor_id: str) -> tuple[bool, Optional[str]]:
        """Update complaint status on blockchain (graceful degradation).
        
        Args:
            db: Database session
            complaint: Complaint with updated status
            anchor_id: Original anchor ID to update
            
        Returns:
            tuple of (success: bool, tx_hash: Optional[str])
        """
        if not self.enabled:
            return False, None
        
        try:
            from services.api.blockchain_hash import generate_status_hash
            
            # Get original anchor for nonce
            anchor = db.get(models.BlockchainAnchor, anchor_id)
            if not anchor:
                logger.error(f"Anchor {anchor_id} not found")
                return False, None
            
            # Compute new status hash
            status_hash = generate_status_hash(complaint)
            
            # Prepare update payload
            payload = {
                "complaint_hash": anchor.complaint_hash,
                "status_hash": status_hash,
                "updated_at": int(complaint.updated_at.timestamp()),
                "nonce": anchor.updated_at_timestamp + 1,  # Increment nonce
            }
            
            # Call blockchain
            tx_hash = self._update_on_blockchain(payload)
            
            # Update anchor record
            anchor.status_hash = status_hash
            anchor.updated_at_timestamp = payload["updated_at"]
            anchor.blockchain_tx_hash = tx_hash
            anchor.blockchain_status = "pending"
            db.commit()
            
            logger.info(f"Status updated on blockchain for complaint {complaint.id}: {tx_hash}")
            return True, tx_hash
            
        except Exception as e:
            logger.error(f"Blockchain status update failed for complaint {complaint.id}: {e}")
            return False, None
    
    def _send_to_blockchain(self, payload: dict) -> str:
        """Send transaction to blockchain contract.
        
        This is where actual Web3 interaction happens.
        For MVP: Simulated. In production: Use web3.py
        
        Args:
            payload: Blockchain payload with hashes
            
        Returns:
            Transaction hash
            
        Raises:
            BlockchainServiceError: If transaction fails
        """
        # TODO: In production, use web3.py:
        # from web3 import Web3
        # w3 = Web3(Web3.HTTPProvider(self.web3_provider))
        # contract = w3.eth.contract(address=self.contract_address, abi=CONTRACT_ABI)
        # tx = contract.functions.createComplaintAnchor(
        #     payload["complaint_hash"],
        #     payload["sla_params_hash"],
        #     payload["status_hash"],
        #     payload["created_at_timestamp"],
        #     int(payload["event_id"].split("_")[1])  # Extract nonce
        # ).transact()
        # return tx.hex()
        
        # For MVP: Simulate transaction
        import secrets
        if secrets.randbelow(10) < 9:  # 90% success rate for testing
            return f"0x{secrets.token_hex(32)}"
        else:
            raise BlockchainServiceError("Simulated blockchain failure")
    
    def _update_on_blockchain(self, payload: dict) -> str:
        """Update status on blockchain contract.
        
        Args:
            payload: Update payload with status hash and nonce
            
        Returns:
            Transaction hash
        """
        # TODO: In production, use web3.py:
        # tx = contract.functions.updateStatusAnchor(
        #     payload["complaint_hash"],
        #     payload["status_hash"],
        #     payload["updated_at"],
        #     payload["nonce"]
        # ).transact()
        # return tx.hex()
        
        # For MVP: Simulate
        import secrets
        if secrets.randbelow(10) < 9:
            return f"0x{secrets.token_hex(32)}"
        else:
            raise BlockchainServiceError("Simulated update failure")
    
    def retry_pending_anchors(self, db) -> dict:
        """Retry all pending/failed anchors asynchronously.
        
        This should be called by a background worker periodically.
        
        Args:
            db: Database session
            
        Returns:
            dict with retry statistics
        """
        pending = db.query(models.BlockchainAnchor).filter(
            models.BlockchainAnchor.blockchain_status.in_(["pending_retry", "failed"])
        ).all()
        
        retried = 0
        succeeded = 0
        failed = 0
        
        for anchor in pending:
            try:
                # Get original complaint
                complaint = db.get(models.Complaint, anchor.entity_id)
                if not complaint:
                    logger.warning(f"Complaint {anchor.entity_id} not found for anchor {anchor.id}")
                    continue
                
                # Retry anchor
                payload = {
                    "complaint_hash": anchor.complaint_hash,
                    "status_hash": anchor.status_hash,
                    "sla_params_hash": anchor.sla_params_hash,
                    "created_at_timestamp": anchor.created_at_timestamp,
                    "updated_at_timestamp": anchor.updated_at_timestamp,
                    "event_id": anchor.event_id,
                    "version": anchor.anchor_version,
                }
                
                tx_hash = self._send_to_blockchain(payload)
                
                # Update anchor
                anchor.blockchain_tx_hash = tx_hash
                anchor.blockchain_status = "pending"
                db.commit()
                
                retried += 1
                succeeded += 1
                logger.info(f"Retry successful for anchor {anchor.id}: {tx_hash}")
                
            except Exception as e:
                failed += 1
                logger.error(f"Retry failed for anchor {anchor.id}: {e}")
                # Update failure count or mark as permanently failed
        
        return {
            "total_pending": len(pending),
            "retried": retried,
            "succeeded": succeeded,
            "failed": failed,
        }


# Global service instance (configured from environment)
blockchain_service = BlockchainService(
    web3_provider=None,  # TODO: Set from env var
    contract_address=None,  # TODO: Set from env var
)
