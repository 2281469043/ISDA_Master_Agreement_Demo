// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract DerivativeContract{
    // Termination status
    bool public terminated;
    // The address of the ISDA Master Agreement allowed to trigger actions
    address public masterAgreement;
    // Participating parties
    address public partyA;
    address public partyB;

    event Terminated(address indexed caller);
    event BalanceCleared(uint256 totalBalance, uint256 amountForA, uint256 amountForB);

    /**
     * @notice Constructor to set the ISDA Master Agreement address and parties.
     * @param _masterAgreement The address of the ISDA Master Agreement.
     * @param _partyA The address of Party A.
     * @param _partyB The address of Party B.
     */
    constructor(address _masterAgreement, address _partyA, address _partyB) payable {
        require(_masterAgreement != address(0), "Invalid master agreement address");
        require(_partyA != address(0) && _partyB != address(0), "Invalid party address");
        require(_partyA != _partyB, "Parties must be distinct");
        masterAgreement = _masterAgreement;
        partyA = _partyA;
        partyB = _partyB;
    }

    /**
     * @notice Terminates the derivative contract.
     * Only callable by the ISDA Master Agreement.
     */
    function terminate() external{
        require(msg.sender == masterAgreement, "Not authorized");
        require(!terminated, "Already terminated");
        terminated = true;
        emit Terminated(msg.sender);
    }

    /**
     * @notice Clears the contract's balance and distributes it to Party A and Party B.
     * Only callable by the ISDA Master Agreement, and only after termination.
     * @param amountForA The amount to transfer to Party A.
     * @param amountForB The amount to transfer to Party B.
     */
    function clearBalance(uint256 amountForA, uint256 amountForB) external{
        require(msg.sender == masterAgreement, "Not authorized");
        require(terminated, "Contract not terminated");
        uint256 total = address(this).balance;
        require(total >= amountForA + amountForB, "Insufficient balance");
        payable(partyA).transfer(amountForA);
        payable(partyB).transfer(amountForB);
        emit BalanceCleared(total, amountForA, amountForB);
    }

    // Allow the contract to receive Ether
    receive() external payable {}
}
