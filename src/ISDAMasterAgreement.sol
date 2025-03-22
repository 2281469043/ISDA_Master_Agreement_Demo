// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IDerivativeContract {
    function terminate() external;
    function clearBalance(uint256 amountForA, uint256 amountForB) external;
}

contract ISDAMasterAgreement {
    // Reentrancy guard variable
    bool private locked;

    // Reentrancy guard modifier
    modifier nonReentrant() {
        require(!locked, "ReentrancyGuard: reentrant call");
        locked = true;
        _;
        locked = false;
    }
    
    // Constructor: No parameters upon deployment, no initialization needed
    constructor() {
        // Empty constructor
    }

    // Structure to store derivative contract information (records the participating parties for voting verification)
    struct DerivativeInfo {
        address partyA;        // Derivative contract party A
        address partyB;        // Derivative contract party B
        bool isTerminated;     // Termination status
    }

    // Structure to store termination proposal information
    struct TerminationProposal {
        address derivativeAddress; // Target derivative contract address
        address proposer;          // Proposal initiator
        bool partyAVoted;          // Whether party A has voted
        bool partyBVoted;          // Whether party B has voted
        bool executed;             // Whether the proposal has been executed
    }

    // Mapping: Derivative contract address => Derivative contract information
    mapping(address => DerivativeInfo) public derivativeContracts;
    // Mapping: Proposal ID => Termination proposal information
    mapping(uint256 => TerminationProposal) public terminationProposals;
    uint256 public proposalCount; // Proposal counter

    // Event declarations
    event DerivativeRegistered(address indexed derivativeAddress, address partyA, address partyB);
    event PaymentFailed(address indexed derivativeAddress, uint256 obligationId, address reporter);
    event DefaultReported(address indexed derivativeAddress, string reason, address reporter);
    event BankruptcyReported(address indexed derivativeAddress, string details, address reporter);
    event TerminationProposed(uint256 proposalId, address derivativeAddress, address proposer);
    event Voted(uint256 proposalId, address voter);
    event TerminationExecuted(address indexed derivativeAddress);
    event BalanceClearedByMaster(address indexed derivativeAddress, uint256 amountForA, uint256 amountForB);


    /**
     * @notice Registers a derivative contract and records its participating parties.
     * @param derivativeAddress The address of the derivative contract (a deployed logic contract)
     * @param partyA The derivative contract party A
     * @param partyB The derivative contract party B
     */
    function registerDerivativeContract(
        address derivativeAddress, 
        address partyA, 
        address partyB
    ) external {
        require(derivativeAddress != address(0), "Invalid derivative address");
        require(derivativeContracts[derivativeAddress].partyA == address(0), "Already registered");
        derivativeContracts[derivativeAddress] = DerivativeInfo(partyA, partyB, false);
        emit DerivativeRegistered(derivativeAddress, partyA, partyB);
    }

    /**
     * @notice Reports a payment failure event.
     * @param derivativeAddress The target derivative contract address (must be registered)
     * @param obligationId The associated obligation ID
     */
    function reportPaymentFailed(address derivativeAddress, uint256 obligationId) external {
        require(derivativeContracts[derivativeAddress].partyA != address(0), "Derivative not registered");
        emit PaymentFailed(derivativeAddress, obligationId, msg.sender);
    }
 
    /**
     * @notice Reports a default event.
     * @param derivativeAddress The target derivative contract address
     * @param reason A description of the default reason
     */
    function reportDefault(address derivativeAddress, string calldata reason) external {
        require(derivativeContracts[derivativeAddress].partyA != address(0), "Derivative not registered");
        emit DefaultReported(derivativeAddress, reason, msg.sender);
    }

    /**
     * @notice Reports a bankruptcy event.
     * @param derivativeAddress The target derivative contract address
     * @param details A description of the bankruptcy details
     */
    function reportBankruptcy(address derivativeAddress, string calldata details) external {
        require(derivativeContracts[derivativeAddress].partyA != address(0), "Derivative not registered");
        emit BankruptcyReported(derivativeAddress, details, msg.sender);
    }

    /**
     * @notice Proposes termination for a derivative contract.
     * @param derivativeAddress The target derivative contract address
     */
    function proposeTermination(address derivativeAddress) external {
        DerivativeInfo memory info = derivativeContracts[derivativeAddress];
        require(info.partyA != address(0), "Derivative not registered");
        require(!info.isTerminated, "Already terminated");

        uint256 proposalId = proposalCount++;
        terminationProposals[proposalId] = TerminationProposal({
            derivativeAddress: derivativeAddress,
            proposer: msg.sender,
            partyAVoted: false,
            partyBVoted: false,
            executed: false
        });
        emit TerminationProposed(proposalId, derivativeAddress, msg.sender);
    }

    /**
     * @notice Votes for a termination proposal.
     * Only the participating parties (partyA or partyB) recorded during registration can vote.
     * @param proposalId The proposal ID
     */
    function voteForTermination(uint256 proposalId) external nonReentrant {
        TerminationProposal storage proposal = terminationProposals[proposalId];
        require(!proposal.executed, "Already executed");
        DerivativeInfo memory info = derivativeContracts[proposal.derivativeAddress];
        require(info.partyA != address(0), "Derivative not registered");
        require(msg.sender == info.partyA || msg.sender == info.partyB, "Not a derivative party");

        // If msg.sender is partyA, mark partyAVoted; if partyB, mark partyBVoted
        if (msg.sender == info.partyA) {
            require(!proposal.partyAVoted, "Party A already voted");
            proposal.partyAVoted = true;
        } else if (msg.sender == info.partyB) {
            require(!proposal.partyBVoted, "Party B already voted");
            proposal.partyBVoted = true;
        }
        emit Voted(proposalId, msg.sender);

        // Execute termination when both parties have voted
        if (proposal.partyAVoted && proposal.partyBVoted) {
            executeTermination(proposalId);
        }
    }

    /**
     * @notice Internal function to execute a termination proposal.
     * It calls the target derivative contract's terminate() function and updates its registration status.
     * @param proposalId The proposal ID
     */
    function executeTermination(uint256 proposalId) internal {
        TerminationProposal storage proposal = terminationProposals[proposalId];
        require(!proposal.executed, "Already executed");
        proposal.executed = true;

        address derivativeAddress = proposal.derivativeAddress;
        derivativeContracts[derivativeAddress].isTerminated = true;

        // Use try/catch to call the derivative contract's terminate() method
        try IDerivativeContract(derivativeAddress).terminate() {
            // Call succeeded
        } catch {
            revert("Derivative termination failed");
        }
        emit TerminationExecuted(derivativeAddress);
    }

    /**
     * @notice Clears the balance in the derivative contract.
     * The ISDA Master Agreement specifies the distribution amounts, and then instructs the derivative contract to clear its balance.
     * The sum of amountForA and amountForB must equal the total balance in the derivative contract.
     * @param derivativeAddress The target derivative contract address.
     * @param amountForA The amount to distribute to Party A.
     * @param amountForB The amount to distribute to Party B.
     */
    function clearDerivativeBalance(
        address derivativeAddress, 
        uint256 amountForA, 
        uint256 amountForB
    ) external {
        DerivativeInfo memory info = derivativeContracts[derivativeAddress];
        require(info.partyA != address(0), "Derivative not registered");
        require(info.isTerminated, "Derivative not terminated");
        
        // Query the balance of the derivative contract
        uint256 totalBalance = address(derivativeAddress).balance;
        require(totalBalance > 0, "No balance to clear");
        require(amountForA + amountForB == totalBalance, "Distribution amounts must equal total balance");

        try IDerivativeContract(derivativeAddress).clearBalance(amountForA, amountForB) {
        } catch {
            revert("Clear balance failed");
        }
        emit BalanceClearedByMaster(derivativeAddress, amountForA, amountForB);
    }

}
