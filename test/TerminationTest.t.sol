// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "forge-std/Test.sol";
import "../src/DerivativeC.sol";
import "../src/ISDAMasterAgreement.sol";

/**
 * @title DerivativeContractTest
 * @dev Tests the termination process of the derivative contract via the ISDA Master Agreement.
 *      The test verifies that a termination proposal created via the derivative contract
 *      can be completed by having partyB vote directly on the master agreement.
 */
contract DerivativeContractTest is Test {
    DerivativeContract derivative;
    ISDAMasterAgreement master;
    
    // Define two parties for the derivative contract.
    address partyA = address(0x1);
    address partyB = address(0x2);
    
    // Set an indebtedness threshold (arbitrary value for testing).
    uint256 indebtednessThreshold = 1000;
    
    // Use transaction ID 1 for testing termination.
    uint256 transactionId = 1;

    function setUp() public {
        // Deploy the bilateral derivative contract with partyA and partyB.
        derivative = new DerivativeContract(partyA, partyB, indebtednessThreshold);
        // Retrieve the deployed master agreement instance.
        master = derivative.masterAgreement();
    }
    
    function testDerivativeTermination() public {
        // Step 1: Mark the transaction as affected.
        // Use vm.prank to simulate a call from partyA.
        vm.prank(partyA);
        derivative.markTransactionAffected(transactionId, "Flag transaction for termination");
        
        // Step 2: Propose termination for the affected transaction.
        // When partyA calls proposeTerminationForTransaction, the master agreement records partyA's vote.
        vm.prank(partyA);
        derivative.proposeTerminationForTransaction(transactionId);
        // The proposal is assumed to have ID 0 (the first proposal).

        // Step 3: Have partyB vote on the termination proposal.
        // Since wrapper calls from the derivative contract lose the original msg.sender,
        // partyB must vote directly on the master agreement.
        vm.prank(partyB);
        master.voteForTermination(0);
        
        // Step 4: Verify that the transaction is terminated.
        bool terminated = master.terminatedTransactions(transactionId);
        assertTrue(terminated, "Transaction should be terminated");
    }
}
