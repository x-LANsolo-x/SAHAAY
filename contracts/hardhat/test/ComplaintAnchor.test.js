const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("ComplaintAnchor", function () {
  let complaintAnchor;
  let owner;
  let addr1;
  
  // Sample test data (hashes only, NO PII)
  const complaintHash = ethers.keccak256(ethers.toUtf8Bytes("complaint_123"));
  const slaHash = ethers.keccak256(ethers.toUtf8Bytes("sla_params"));
  const statusHash1 = ethers.keccak256(ethers.toUtf8Bytes("submitted"));
  const statusHash2 = ethers.keccak256(ethers.toUtf8Bytes("under_review"));
  
  beforeEach(async function () {
    [owner, addr1] = await ethers.getSigners();
    
    const ComplaintAnchor = await ethers.getContractFactory("ComplaintAnchor");
    complaintAnchor = await ComplaintAnchor.deploy();
  });
  
  describe("createComplaintAnchor", function () {
    it("Should create a new complaint anchor", async function () {
      const now = await time.latest();
      const nonce = 1;
      
      await expect(
        complaintAnchor.createComplaintAnchor(
          complaintHash,
          slaHash,
          statusHash1,
          now,
          nonce
        )
      )
        .to.emit(complaintAnchor, "ComplaintAnchored")
        .withArgs(complaintHash, slaHash, now, nonce);
      
      // Verify anchor was created
      const anchor = await complaintAnchor.getAnchor(complaintHash);
      expect(anchor.complaintHash).to.equal(complaintHash);
      expect(anchor.slaHash).to.equal(slaHash);
      expect(anchor.statusHash).to.equal(statusHash1);
      expect(anchor.createdAt).to.equal(now);
      expect(anchor.statusNonce).to.equal(nonce);
      expect(anchor.exists).to.be.true;
    });
    
    it("Should reject duplicate complaint hash", async function () {
      const now = await time.latest();
      
      // Create first anchor
      await complaintAnchor.createComplaintAnchor(
        complaintHash,
        slaHash,
        statusHash1,
        now,
        1
      );
      
      // Try to create duplicate
      await expect(
        complaintAnchor.createComplaintAnchor(
          complaintHash,
          slaHash,
          statusHash1,
          now,
          1
        )
      ).to.be.revertedWithCustomError(complaintAnchor, "AnchorAlreadyExists");
    });
    
    it("Should reject zero complaint hash", async function () {
      const now = await time.latest();
      const zeroHash = ethers.ZeroHash;
      
      await expect(
        complaintAnchor.createComplaintAnchor(
          zeroHash,
          slaHash,
          statusHash1,
          now,
          1
        )
      ).to.be.revertedWith("Invalid complaint hash");
    });
    
    it("Should reject zero SLA hash", async function () {
      const now = await time.latest();
      const zeroHash = ethers.ZeroHash;
      
      await expect(
        complaintAnchor.createComplaintAnchor(
          complaintHash,
          zeroHash,
          statusHash1,
          now,
          1
        )
      ).to.be.revertedWith("Invalid SLA hash");
    });
    
    it("Should reject zero status hash", async function () {
      const now = await time.latest();
      const zeroHash = ethers.ZeroHash;
      
      await expect(
        complaintAnchor.createComplaintAnchor(
          complaintHash,
          slaHash,
          zeroHash,
          now,
          1
        )
      ).to.be.revertedWith("Invalid status hash");
    });
    
    it("Should reject timestamp too far in future", async function () {
      const now = await time.latest();
      const futureTime = now + 2 * 60 * 60; // 2 hours
      
      await expect(
        complaintAnchor.createComplaintAnchor(
          complaintHash,
          slaHash,
          statusHash1,
          futureTime,
          1
        )
      ).to.be.revertedWith("Timestamp too far in future");
    });
    
    it("Should reject timestamp too old", async function () {
      const now = await time.latest();
      const oldTime = now - 31 * 24 * 60 * 60; // 31 days ago
      
      await expect(
        complaintAnchor.createComplaintAnchor(
          complaintHash,
          slaHash,
          statusHash1,
          oldTime,
          1
        )
      ).to.be.revertedWith("Timestamp too old");
    });
  });
  
  describe("updateStatusAnchor", function () {
    beforeEach(async function () {
      // Create initial anchor
      const now = await time.latest();
      await complaintAnchor.createComplaintAnchor(
        complaintHash,
        slaHash,
        statusHash1,
        now,
        1
      );
    });
    
    it("Should update status with valid nonce", async function () {
      const now = await time.latest();
      const newNonce = 2;
      
      await expect(
        complaintAnchor.updateStatusAnchor(
          complaintHash,
          statusHash2,
          now,
          newNonce
        )
      )
        .to.emit(complaintAnchor, "StatusUpdated")
        .withArgs(complaintHash, statusHash2, now, newNonce);
      
      // Verify update
      const anchor = await complaintAnchor.getAnchor(complaintHash);
      expect(anchor.statusHash).to.equal(statusHash2);
      expect(anchor.statusNonce).to.equal(newNonce);
    });
    
    it("Should reject update for non-existent anchor", async function () {
      const now = await time.latest();
      const nonExistentHash = ethers.keccak256(ethers.toUtf8Bytes("nonexistent"));
      
      await expect(
        complaintAnchor.updateStatusAnchor(
          nonExistentHash,
          statusHash2,
          now,
          2
        )
      ).to.be.revertedWithCustomError(complaintAnchor, "AnchorNotFound");
    });
    
    it("Should reject nonce equal to previous (replay attack)", async function () {
      const now = await time.latest();
      const sameNonce = 1;
      
      await expect(
        complaintAnchor.updateStatusAnchor(
          complaintHash,
          statusHash2,
          now,
          sameNonce
        )
      ).to.be.revertedWithCustomError(complaintAnchor, "InvalidNonce");
    });
    
    it("Should reject nonce less than previous (replay attack)", async function () {
      const now = await time.latest();
      
      // Update once with nonce 2
      await complaintAnchor.updateStatusAnchor(
        complaintHash,
        statusHash2,
        now,
        2
      );
      
      // Try to use old nonce 1
      await expect(
        complaintAnchor.updateStatusAnchor(
          complaintHash,
          statusHash2,
          now,
          1
        )
      ).to.be.revertedWithCustomError(complaintAnchor, "InvalidNonce");
    });
    
    it("Should allow multiple sequential updates with increasing nonces", async function () {
      const now = await time.latest();
      
      // Update with nonce 2
      await complaintAnchor.updateStatusAnchor(complaintHash, statusHash2, now, 2);
      expect((await complaintAnchor.getAnchor(complaintHash)).statusNonce).to.equal(2);
      
      // Update with nonce 3
      await complaintAnchor.updateStatusAnchor(complaintHash, statusHash2, now, 3);
      expect((await complaintAnchor.getAnchor(complaintHash)).statusNonce).to.equal(3);
      
      // Update with nonce 100 (non-sequential but greater)
      await complaintAnchor.updateStatusAnchor(complaintHash, statusHash2, now, 100);
      expect((await complaintAnchor.getAnchor(complaintHash)).statusNonce).to.equal(100);
    });
    
    it("Should reject zero status hash", async function () {
      const now = await time.latest();
      const zeroHash = ethers.ZeroHash;
      
      await expect(
        complaintAnchor.updateStatusAnchor(
          complaintHash,
          zeroHash,
          now,
          2
        )
      ).to.be.revertedWith("Invalid status hash");
    });
    
    it("Should reject timestamp before creation", async function () {
      const anchor = await complaintAnchor.getAnchor(complaintHash);
      const beforeCreation = Number(anchor.createdAt) - 1;
      
      await expect(
        complaintAnchor.updateStatusAnchor(
          complaintHash,
          statusHash2,
          beforeCreation,
          2
        )
      ).to.be.revertedWith("Update timestamp before creation");
    });
  });
  
  describe("View functions", function () {
    beforeEach(async function () {
      const now = await time.latest();
      await complaintAnchor.createComplaintAnchor(
        complaintHash,
        slaHash,
        statusHash1,
        now,
        1
      );
    });
    
    it("Should check if anchor exists", async function () {
      expect(await complaintAnchor.anchorExists(complaintHash)).to.be.true;
      
      const nonExistent = ethers.keccak256(ethers.toUtf8Bytes("nonexistent"));
      expect(await complaintAnchor.anchorExists(nonExistent)).to.be.false;
    });
    
    it("Should get current nonce", async function () {
      expect(await complaintAnchor.getCurrentNonce(complaintHash)).to.equal(1);
      
      // Update and check new nonce
      const now = await time.latest();
      await complaintAnchor.updateStatusAnchor(complaintHash, statusHash2, now, 5);
      expect(await complaintAnchor.getCurrentNonce(complaintHash)).to.equal(5);
    });
    
    it("Should verify status hash", async function () {
      expect(
        await complaintAnchor.verifyStatusHash(complaintHash, statusHash1)
      ).to.be.true;
      
      expect(
        await complaintAnchor.verifyStatusHash(complaintHash, statusHash2)
      ).to.be.false;
    });
    
    it("Should return false for non-existent anchor verification", async function () {
      const nonExistent = ethers.keccak256(ethers.toUtf8Bytes("nonexistent"));
      expect(
        await complaintAnchor.verifyStatusHash(nonExistent, statusHash1)
      ).to.be.false;
    });
  });
  
  describe("No PII validation", function () {
    it("Should only store hashes (32 bytes), not strings", async function () {
      const now = await time.latest();
      
      // Attempt to store actual string data should fail at type level
      // (This test documents that the contract ONLY accepts bytes32)
      
      // Valid: bytes32 hash
      await complaintAnchor.createComplaintAnchor(
        complaintHash,
        slaHash,
        statusHash1,
        now,
        1
      );
      
      const anchor = await complaintAnchor.getAnchor(complaintHash);
      
      // Verify all hash fields are 32 bytes
      expect(anchor.complaintHash).to.have.lengthOf(66); // "0x" + 64 hex chars
      expect(anchor.slaHash).to.have.lengthOf(66);
      expect(anchor.statusHash).to.have.lengthOf(66);
      
      // Verify no string data is stored
      expect(typeof anchor.complaintHash).to.equal("string");
      expect(anchor.complaintHash.startsWith("0x")).to.be.true;
    });
  });
});
