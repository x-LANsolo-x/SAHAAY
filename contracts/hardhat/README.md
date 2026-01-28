# SAHAAY ComplaintAnchor Smart Contract

Privacy-first blockchain anchoring for complaint immutability. **NO PII on-chain.**

## Overview

The ComplaintAnchor contract provides immutable anchoring for complaint data using only cryptographic hashes. This ensures:

- **Privacy**: No personal information on blockchain
- **Immutability**: Tamper-proof audit trail
- **Transparency**: Anyone can verify data integrity
- **Security**: Replay protection via nonce tracking

## Contract Functions

### `createComplaintAnchor()`

Creates initial complaint anchor (hashes only).

**Parameters:**
- `bytes32 complaintHash` - SHA256 of complaint metadata
- `bytes32 slaHash` - SHA256 of SLA parameters
- `bytes32 statusHash` - Initial status hash
- `uint256 createdAt` - Creation timestamp (Unix seconds)
- `uint256 nonce` - Initial nonce (replay protection)

**Validation:**
- ✅ Anchor must not already exist
- ✅ Hashes must not be zero
- ✅ Timestamp must be reasonable (within 30 days past, 1 hour future)

**Emits:** `ComplaintAnchored` event

### `updateStatusAnchor()`

Updates complaint status with replay protection.

**Parameters:**
- `bytes32 complaintHash` - Complaint identifier
- `bytes32 statusHash` - New status hash
- `uint256 updatedAt` - Update timestamp
- `uint256 nonce` - New nonce (must be > previous)

**Validation:**
- ✅ Anchor must exist
- ✅ Nonce must be greater than previous (replay protection)
- ✅ Timestamp must be after creation
- ✅ Status hash must not be zero

**Emits:** `StatusUpdated` event

### View Functions

- `getAnchor(bytes32)` - Get complete anchor details
- `anchorExists(bytes32)` - Check if anchor exists
- `getCurrentNonce(bytes32)` - Get current nonce
- `verifyStatusHash(bytes32, bytes32)` - Verify status hash

## Installation

```bash
cd contracts/hardhat
npm install
```

## Testing

Run comprehensive test suite:

```bash
npm test
```

Expected output: All tests pass ✅

Test coverage:
- ✅ Create anchor validation
- ✅ Duplicate prevention
- ✅ Replay attack protection (nonce)
- ✅ Status update validation
- ✅ Timestamp validation
- ✅ Zero hash rejection
- ✅ View functions
- ✅ No PII validation

## Compilation

Compile contracts:

```bash
npm run compile
```

## Deployment

### Local Hardhat Network

```bash
# Terminal 1: Start local node
npx hardhat node

# Terminal 2: Deploy
npm run deploy:local
```

### Mumbai Testnet (Polygon)

1. Set environment variables:
```bash
export MUMBAI_RPC_URL="https://rpc-mumbai.maticvigil.com"
export PRIVATE_KEY="your_private_key"
```

2. Deploy:
```bash
npm run deploy:testnet
```

### Polygon Mainnet

```bash
export POLYGON_RPC_URL="https://polygon-rpc.com"
export PRIVATE_KEY="your_private_key"
npx hardhat run scripts/deploy.js --network polygon
```

## Integration with Backend

The backend (`services/api/`) integrates with this contract via:

1. **Hash Generation** (`blockchain_hash.py`)
   - Generates complaint/status/SLA hashes
   - Validates no PII in payload

2. **Blockchain Anchoring** (`app.py`)
   - POST `/blockchain/anchor/complaint/{id}`
   - Sends hashes to smart contract
   - Stores tx_hash in database

3. **Verification** (`app.py`)
   - GET `/blockchain/verify/{anchor_id}`
   - Recomputes hashes from database
   - Compares with on-chain hashes

## Security Features

### Replay Protection

Nonce-based replay protection prevents attackers from replaying old transactions:

```solidity
// Nonce must increase with each update
require(nonce > anchor.statusNonce, "Invalid nonce");
```

### Timestamp Validation

Prevents timestamp manipulation:
- Not too far in past (> 30 days)
- Not too far in future (> 1 hour)
- Update timestamp must be after creation

### Zero Hash Prevention

All hashes must be non-zero (real data):

```solidity
require(complaintHash != bytes32(0), "Invalid hash");
```

### No PII Storage

Contract ONLY accepts `bytes32` (32-byte hashes), making it impossible to store strings or personal data.

## Gas Optimization

- ✅ Optimized storage layout
- ✅ Minimal storage operations
- ✅ Efficient mappings
- ✅ No arrays (O(1) lookups)

Estimated gas costs:
- Create anchor: ~80,000 gas
- Update status: ~50,000 gas
- View functions: Free (no gas)

## Events

### ComplaintAnchored

Emitted when new complaint is anchored:

```solidity
event ComplaintAnchored(
    bytes32 indexed complaintHash,
    bytes32 slaHash,
    uint256 createdAt,
    uint256 nonce
);
```

### StatusUpdated

Emitted when status is updated:

```solidity
event StatusUpdated(
    bytes32 indexed complaintHash,
    bytes32 statusHash,
    uint256 updatedAt,
    uint256 nonce
);
```

## Example Usage

```javascript
const { ethers } = require("ethers");

// Connect to contract
const contract = new ethers.Contract(address, abi, signer);

// Create anchor (hashes only!)
const complaintHash = ethers.keccak256(ethers.toUtf8Bytes("complaint_123"));
const slaHash = ethers.keccak256(ethers.toUtf8Bytes("sla_params"));
const statusHash = ethers.keccak256(ethers.toUtf8Bytes("submitted"));

const tx = await contract.createComplaintAnchor(
    complaintHash,
    slaHash,
    statusHash,
    Math.floor(Date.now() / 1000), // Unix timestamp
    1 // Initial nonce
);
await tx.wait();

// Update status
const newStatusHash = ethers.keccak256(ethers.toUtf8Bytes("resolved"));
const updateTx = await contract.updateStatusAnchor(
    complaintHash,
    newStatusHash,
    Math.floor(Date.now() / 1000),
    2 // Incremented nonce
);
await updateTx.wait();

// Verify
const anchor = await contract.getAnchor(complaintHash);
console.log("Status hash:", anchor.statusHash);
console.log("Current nonce:", anchor.statusNonce);
```

## License

MIT
