from flask import Flask, render_template, request, redirect, url_for, flash
from web3 import Web3
import json

app = Flask(__name__)
app.secret_key = "some_secret_key"  # Used for flash messages

# Connect to the anvil test network (newer web3.py uses is_connected())
w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
if w3.is_connected():
    print("Connected to anvil!")
else:
    print("Connection failed!")

# Global variables: store accounts (private keys, wallets) and Master Agreement contract address
party_a_private_key = None
party_b_private_key = None
party_a = None
party_b = None
master_agreement_address = None

deployed_derivatives = []
last_deployed_derivative = None

# Load the Master Agreement ABI from file
with open('abi/MACAbi.json', 'r') as f:
    data = json.load(f)
    if isinstance(data, dict) and "abi" in data:
        master_agreement_abi = data["abi"]
    else:
        master_agreement_abi = data

@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("index.html",
                           master_agreement_address=master_agreement_address,
                           party_a=party_a,
                           party_b=party_b,
                           deployed_derivatives=deployed_derivatives,
                           last_deployed_derivative=last_deployed_derivative)

@app.route("/set_accounts", methods=["POST"])
def set_accounts():
    global party_a_private_key, party_b_private_key, party_a, party_b
    pk_a = request.form.get("party_a_pk", "").strip()
    pk_b = request.form.get("party_b_pk", "").strip()
    if not pk_a or not pk_b:
        flash("Please enter private keys for Party A and Party B!", "error")
        return redirect(url_for("index"))
    try:
        party_a_private_key = pk_a
        party_b_private_key = pk_b
        party_a = w3.eth.account.from_key(party_a_private_key)
        party_b = w3.eth.account.from_key(party_b_private_key)
        flash("Accounts set successfully!", "success")
    except Exception as e:
        flash(f"Failed to set accounts: {str(e)}", "error")
    return redirect(url_for("index"))

@app.route("/set_master", methods=["POST"])
def set_master():
    global master_agreement_address
    master_addr = request.form.get("master_address", "").strip()
    if master_addr and w3.is_address(master_addr):
        master_agreement_address = master_addr
        flash("Master Agreement contract address set successfully", "success")
    else:
        flash("Please enter a valid Master Agreement contract address!", "error")
    return redirect(url_for("index"))

def get_master_contract(wallet):
    """Helper function: create a contract instance based on the global master_agreement_address and ABI."""
    if master_agreement_address is None:
        raise Exception("Master Agreement contract address is not set!")
    return w3.eth.contract(address=master_agreement_address, abi=master_agreement_abi)

def send_transaction(tx, account):
    """Helper function: sign the transaction, send it, and wait for the receipt."""
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt

# ----------------------------
# Deploy Derivative Contract
# ----------------------------
@app.route("/deploy_derivative", methods=["POST"])
def deploy_derivative():
    # Requires Party A account and Master Agreement contract address to be set
    if party_a is None or master_agreement_address is None:
        flash("Please set the accounts and Master Agreement contract address first!", "error")
        return redirect(url_for("index"))
    
    # Get the derivative contract source file path, deployment parameters, and deposit amount from the form
    derivative_path = request.form.get("derivative_path", "").strip()
    input_partyA = request.form.get("deploy_party_a", "").strip()
    input_partyB = request.form.get("deploy_party_b", "").strip()
    deposit_amount_str = request.form.get("deposit_amount", "0").strip()  # New field: deposit amount (in Ether)
    
    if not derivative_path:
        flash("Please enter the source file path for the derivative contract!", "error")
        return redirect(url_for("index"))
    if not (w3.is_address(input_partyA) and w3.is_address(input_partyB)):
        flash("Please enter valid addresses for Party A and Party B!", "error")
        return redirect(url_for("index"))
    
    try:
        from solcx import compile_files, install_solc
        install_solc('0.8.0')  # Install the appropriate compiler version per the contract's pragma
        compiled = compile_files([derivative_path], output_values=["abi", "bin"])
        contract_key = list(compiled.keys())[0]  # Assume there's only one contract in the file
        derivative_abi = compiled[contract_key]["abi"]
        derivative_bytecode = compiled[contract_key]["bin"]
    except Exception as e:
        flash(f"Failed to compile derivative contract: {str(e)}", "error")
        return redirect(url_for("index"))
    
    try:
        # Convert the deposit amount to wei
        deposit_value = w3.to_wei(deposit_amount_str, "ether")
        
        # Deploy the contract using Party A's wallet
        Contract = w3.eth.contract(abi=derivative_abi, bytecode=derivative_bytecode)
        nonce = w3.eth.get_transaction_count(party_a.address)
        tx = Contract.constructor(master_agreement_address, input_partyA, input_partyB).build_transaction({
            "from": party_a.address,
            "nonce": nonce,
            "gas": 3000000,
            "gasPrice": w3.to_wei("1", "gwei"),
            "value": deposit_value
        })
        receipt = send_transaction(tx, party_a)
        deployed_derivatives.append(receipt.contractAddress)
        global last_deployed_derivative
        last_deployed_derivative = receipt.contractAddress
        
        flash(f"Derivative contract deployed successfully! Address: {receipt.contractAddress}", "success")
    except Exception as e:
        flash(f"Derivative contract deployment failed: {str(e)}", "error")
    return redirect(url_for("index"))

# ----------------------------
# Register Derivative Contract
# ----------------------------
@app.route("/register_derivative_contract", methods=["POST"])
def register_derivative_contract():
    derivative_addr = request.form.get("derivative_contract", "").strip()
    party_a_input = request.form.get("party_a_input", "").strip()
    party_b_input = request.form.get("party_b_input", "").strip()
    if not (w3.is_address(derivative_addr) and w3.is_address(party_a_input) and w3.is_address(party_b_input)):
        flash("Please enter valid addresses for the derivative contract, Party A, and Party B!", "error")
        return redirect(url_for("index"))
    try:
        # Registration is initiated by Party A
        master_contract = get_master_contract(party_a)
        nonce = w3.eth.get_transaction_count(party_a.address)
        tx = master_contract.functions.registerDerivativeContract(
            derivative_addr, party_a_input, party_b_input
        ).build_transaction({
            "from": party_a.address,
            "nonce": nonce,
            "gas": 300000,
            "gasPrice": w3.to_wei("1", "gwei")
        })
        receipt = send_transaction(tx, party_a)
        flash(f"Derivative contract registered successfully! Transaction receipt: {receipt.transactionHash.hex()}", "success")
    except Exception as e:
        flash(f"Derivative contract registration failed: {str(e)}", "error")
    return redirect(url_for("index"))

# ----------------------------
# Event Reporting (Unified)
# ----------------------------
@app.route("/report_event", methods=["POST"])
def report_event():
    # Get the user-input report address (no extra check, only validity is verified)
    reporter_address = request.form.get("reporter", "").strip()
    if not reporter_address or not w3.is_address(reporter_address):
        flash("Please enter a valid report address!", "error")
        return redirect(url_for("index"))
    
    # Simple check: determine which account matches the input address
    if party_a and party_a.address.lower() == reporter_address.lower():
        account = party_a
    elif party_b and party_b.address.lower() == reporter_address.lower():
        account = party_b
    else:
        flash("The address has no associated private key. Please set the account first!", "error")
        return redirect(url_for("index"))
    
    if master_agreement_address is None:
        flash("Please set the Master Agreement contract address first!", "error")
        return redirect(url_for("index"))
    
    event_type = request.form.get("event_type", "").strip()  # Expected: "default", "bankruptcy", "payment_failed"
    derivative_addr = request.form.get("report_derivative", "").strip()
    if not w3.is_address(derivative_addr):
        flash("Please enter a valid derivative contract address!", "error")
        return redirect(url_for("index"))
    
    master_contract = get_master_contract(account)
    nonce = w3.eth.get_transaction_count(account.address)
    tx = None

    try:
        if event_type == "default":
            reason = request.form.get("reason", "").strip()
            if not reason:
                flash("Please enter the reason for the default event!", "error")
                return redirect(url_for("index"))
            tx = master_contract.functions.reportDefault(derivative_addr, reason).build_transaction({
                "from": account.address,
                "nonce": nonce,
                "gas": 300000,
                "gasPrice": w3.to_wei("1", "gwei")
            })
        elif event_type == "bankruptcy":
            details = request.form.get("details", "").strip()
            if not details:
                flash("Please enter the details for the bankruptcy event!", "error")
                return redirect(url_for("index"))
            tx = master_contract.functions.reportBankruptcy(derivative_addr, details).build_transaction({
                "from": account.address,
                "nonce": nonce,
                "gas": 300000,
                "gasPrice": w3.to_wei("1", "gwei")
            })
        elif event_type == "payment_failed":
            obligation_id_str = request.form.get("obligation_id", "").strip()
            if not obligation_id_str.isdigit():
                flash("Please enter a valid obligation ID for the payment failure event!", "error")
                return redirect(url_for("index"))
            obligation_id = int(obligation_id_str)
            tx = master_contract.functions.reportPaymentFailed(derivative_addr, obligation_id).build_transaction({
                "from": account.address,
                "nonce": nonce,
                "gas": 300000,
                "gasPrice": w3.to_wei("1", "gwei")
            })
        else:
            flash("Please select a valid event type!", "error")
            return redirect(url_for("index"))
        
        receipt = send_transaction(tx, account)
        flash(f"{event_type} event reported successfully! Transaction receipt: {receipt.transactionHash.hex()}", "success")
    except Exception as e:
        flash(f"{event_type} event report failed: {str(e)}", "error")
    
    return redirect(url_for("index"))

# ----------------------------
# Termination Process: Propose Termination and Vote
# ----------------------------
@app.route("/propose_termination_a", methods=["POST"])
def propose_termination_a():
    derivative_addr = request.form.get("propose_derivative_a", "").strip()
    if not w3.is_address(derivative_addr):
        flash("Please enter a valid derivative contract address for Party A's proposal!", "error")
        return redirect(url_for("index"))
    try:
        master_contract = get_master_contract(party_a)
        nonce = w3.eth.get_transaction_count(party_a.address)
        tx = master_contract.functions.proposeTermination(derivative_addr).build_transaction({
            "from": party_a.address,
            "nonce": nonce,
            "gas": 300000,
            "gasPrice": w3.to_wei("1", "gwei")
        })
        receipt = send_transaction(tx, party_a)
        
        # Parse the TerminationProposed event log to get the proposalId
        logs = master_contract.events.TerminationProposed().process_receipt(receipt)
        if logs and len(logs) > 0:
            proposal_id = logs[0]['args']['proposalId']
            flash(f"Party A successfully proposed termination! Proposal ID: {proposal_id}", "success")
        else:
            flash("Party A successfully proposed termination, but Proposal ID was not parsed.", "success")
    except Exception as e:
        flash(f"Party A's termination proposal failed: {str(e)}", "error")
    return redirect(url_for("index"))

@app.route("/propose_termination_b", methods=["POST"])
def propose_termination_b():
    derivative_addr = request.form.get("propose_derivative_b", "").strip()
    if not w3.is_address(derivative_addr):
        flash("Please enter a valid derivative contract address for Party B's proposal!", "error")
        return redirect(url_for("index"))
    try:
        master_contract = get_master_contract(party_b)
        nonce = w3.eth.get_transaction_count(party_b.address)
        tx = master_contract.functions.proposeTermination(derivative_addr).build_transaction({
            "from": party_b.address,
            "nonce": nonce,
            "gas": 300000,
            "gasPrice": w3.to_wei("1", "gwei")
        })
        receipt = send_transaction(tx, party_b)
        
        # Parse the TerminationProposed event log to get the proposalId
        logs = master_contract.events.TerminationProposed().process_receipt(receipt)
        if logs and len(logs) > 0:
            proposal_id = logs[0]['args']['proposalId']
            flash(f"Party B successfully proposed termination! Proposal ID: {proposal_id}", "success")
        else:
            flash("Party B successfully proposed termination, but Proposal ID was not parsed.", "success")
    except Exception as e:
        flash(f"Party B's termination proposal failed: {str(e)}", "error")
    return redirect(url_for("index"))

@app.route("/vote_termination_a", methods=["POST"])
def vote_termination_a():
    proposal_id_str = request.form.get("proposal_id_a", "").strip()
    if not proposal_id_str.isdigit():
        flash("Please enter a valid proposal ID for Party A!", "error")
        return redirect(url_for("index"))
    proposal_id = int(proposal_id_str)
    try:
        master_contract = get_master_contract(party_a)
        nonce = w3.eth.get_transaction_count(party_a.address)
        tx = master_contract.functions.voteForTermination(proposal_id).build_transaction({
            "from": party_a.address,
            "nonce": nonce,
            "gas": 300000,
            "gasPrice": w3.to_wei("1", "gwei")
        })
        receipt = send_transaction(tx, party_a)
        flash(f"Party A voted successfully! Transaction receipt: {receipt.transactionHash.hex()}", "success")
    except Exception as e:
        flash(f"Party A's vote failed: {str(e)}", "error")
    return redirect(url_for("index"))

@app.route("/vote_termination_b", methods=["POST"])
def vote_termination_b():
    proposal_id_str = request.form.get("proposal_id_b", "").strip()
    if not proposal_id_str.isdigit():
        flash("Please enter a valid proposal ID for Party B!", "error")
        return redirect(url_for("index"))
    proposal_id = int(proposal_id_str)
    try:
        master_contract = get_master_contract(party_b)
        nonce = w3.eth.get_transaction_count(party_b.address)
        tx = master_contract.functions.voteForTermination(proposal_id).build_transaction({
            "from": party_b.address,
            "nonce": nonce,
            "gas": 300000,
            "gasPrice": w3.to_wei("1", "gwei")
        })
        receipt = send_transaction(tx, party_b)
        flash(f"Party B voted successfully! Transaction receipt: {receipt.transactionHash.hex()}", "success")
    except Exception as e:
        flash(f"Party B's vote failed: {str(e)}", "error")
    return redirect(url_for("index"))

# ----------------------------
# Clear Balance
# ----------------------------
@app.route("/clear_balance", methods=["POST"])
def clear_balance():
    derivative_addr = request.form.get("clear_derivative", "").strip()
    amount_a_str = request.form.get("amount_a", "").strip()
    amount_b_str = request.form.get("amount_b", "").strip()
    if not (w3.is_address(derivative_addr) and amount_a_str.isdigit() and amount_b_str.isdigit()):
        flash("Please enter a valid derivative contract address and amounts!", "error")
        return redirect(url_for("index"))
    amount_a = int(amount_a_str)
    amount_b = int(amount_b_str)
    try:
        # Clear balance is initiated by Party A
        master_contract = get_master_contract(party_a)
        nonce = w3.eth.get_transaction_count(party_a.address)
        tx = master_contract.functions.clearDerivativeBalance(derivative_addr, amount_a, amount_b).build_transaction({
            "from": party_a.address,
            "nonce": nonce,
            "gas": 300000,
            "gasPrice": w3.to_wei("1", "gwei")
        })
        receipt = send_transaction(tx, party_a)
        flash(f"Balance cleared successfully! Transaction receipt: {receipt.transactionHash.hex()}", "success")
    except Exception as e:
        flash(f"Failed to clear balance: {str(e)}", "error")
    return redirect(url_for("index"))

@app.route("/query_balance", methods=["POST"])
def query_balance():
    derivative_addr = request.form.get("query_derivative_balance", "").strip()
    if not w3.is_address(derivative_addr):
        flash("Please enter a valid derivative contract address!", "error")
        return redirect(url_for("index"))
    try:
        balance_wei = w3.eth.get_balance(derivative_addr)
        balance_eth = w3.from_wei(balance_wei, "ether")
        flash(f"Derivative contract {derivative_addr} balance: {balance_eth} Ether", "success")
    except Exception as e:
        flash(f"Failed to query balance: {str(e)}", "error")
    return redirect(url_for("index"))

@app.route("/query_termination", methods=["POST"])
def query_termination():
    derivative_addr = request.form.get("query_derivative_termination", "").strip()
    if master_agreement_address is None:
        flash("Please set the Master Agreement contract address first!", "error")
        return redirect(url_for("index"))
    if not w3.is_address(derivative_addr):
        flash("Please enter a valid derivative contract address!", "error")
        return redirect(url_for("index"))
    try:
        master_contract = get_master_contract(party_a)  # Can use party_b as well because public variables do not require permission
        info = master_contract.functions.derivativeContracts(derivative_addr).call()
        # info returns a tuple (partyA, partyB, isTerminated)
        is_terminated = info[2]
        flash(f"Derivative contract {derivative_addr} termination status: {'Terminated' if is_terminated else 'Not terminated'}", "success")
    except Exception as e:
        flash(f"Failed to query termination status: {str(e)}", "error")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
