// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "forge-std/Script.sol";
import "../src/ISDAMasterAgreement.sol";

contract DeployMaster is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("DEPLOYER_PRIVATE_KEY");
                
        vm.startBroadcast(deployerPrivateKey);
        ISDAMasterAgreement master = new ISDAMasterAgreement();
        vm.stopBroadcast();
        
        console.log("Master Agreement deployed at:", address(master));
    }
}
