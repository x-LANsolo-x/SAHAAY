const hre = require("hardhat");

async function main() {
  console.log("Deploying ComplaintAnchor contract...");
  
  // Get the contract factory
  const ComplaintAnchor = await hre.ethers.getContractFactory("ComplaintAnchor");
  
  // Deploy the contract
  const complaintAnchor = await ComplaintAnchor.deploy();
  
  await complaintAnchor.waitForDeployment();
  
  const address = await complaintAnchor.getAddress();
  
  console.log(`ComplaintAnchor deployed to: ${address}`);
  console.log(`Network: ${hre.network.name}`);
  console.log(`Deployer: ${(await hre.ethers.getSigners())[0].address}`);
  
  // Save deployment info
  const fs = require("fs");
  const deploymentInfo = {
    network: hre.network.name,
    contractAddress: address,
    deployedAt: new Date().toISOString(),
    deployer: (await hre.ethers.getSigners())[0].address
  };
  
  fs.writeFileSync(
    `deployments/${hre.network.name}.json`,
    JSON.stringify(deploymentInfo, null, 2)
  );
  
  console.log(`Deployment info saved to deployments/${hre.network.name}.json`);
  
  // Verify on block explorer (if not localhost)
  if (hre.network.name !== "hardhat" && hre.network.name !== "localhost") {
    console.log("\nWaiting for block confirmations...");
    await complaintAnchor.deploymentTransaction().wait(6);
    
    console.log("\nVerifying contract on block explorer...");
    try {
      await hre.run("verify:verify", {
        address: address,
        constructorArguments: []
      });
      console.log("Contract verified!");
    } catch (error) {
      console.log("Verification failed:", error.message);
    }
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
