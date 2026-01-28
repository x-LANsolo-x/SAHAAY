# Technical PRD — Blockchain (ShikayatChain + HealthChain anchors)

## 1. Scope
Use blockchain (Polygon per deck) for:
- **ShikayatChain:** immutable complaint records, SLA timers, escalation enforcement
- **HealthChain:** tamper-evident anchors for portable records (store hashes, not raw health data)
- **Evidence integrity:** IPFS for evidence artifacts; on-chain references

## 2. Principles
- **No raw PII on-chain.** Only hashes, pointers, and minimal metadata.
- **Auditability + privacy:** verifiable integrity without exposing sensitive content.
- **Low cost:** batch anchoring; <₹1/tx target from deck.

## 3. ShikayatChain requirements
### 3.1 Complaint lifecycle (on-chain + off-chain)
- Off-chain system stores full complaint payload (encrypted).
- On-chain contract stores:
  - complaintId
  - hashed payload digest
  - timestamps
  - assigned authority role
  - SLA duration + deadline
  - escalation state
  - closure hash + feedback requirement marker

### 3.2 SLA & escalation (smart contracts)
- Auto-escalation path: District → State → National.
- Enforce deadlines:
  - if `now > deadline` and not resolved, state transitions to escalated.

### 3.3 Anonymous & safe filing
- Support anonymous complaints by using pseudonymous identifiers.
- Optional verifiable credential proofs for eligibility (without identity disclosure).

### 3.4 Performance scoring
- On-chain or off-chain computed score anchored periodically.

## 4. HealthChain anchoring
- Anchor:
  - encounter summaries
  - prescription hashes
  - vaccination certificate references
- Provide verifiable audit trail of modifications.

## 5. IPFS evidence
- Evidence uploaded to IPFS (or pinning service) with encryption.
- Store CID on-chain as hash pointer.

## 6. Key contract interfaces (sketch)
- `createComplaint(hash payloadHash, bytes32 evidenceCidHash, uint256 slaSeconds, uint8 authorityLevel)`
- `updateStatus(uint256 complaintId, uint8 newStatus, bytes32 updateHash)`
- `escalate(uint256 complaintId)`
- `closeComplaint(uint256 complaintId, bytes32 closureHash)`

## 7. Security
- Contract audits.
- Admin key management (multisig).
- Replay protection and idempotency.

## 8. MVP deliverables
- Complaint creation + receipt (tx hash).
- SLA timer + manual trigger to verify escalation.
- IPFS evidence pointer.
- Basic HealthChain anchor for one record type.
