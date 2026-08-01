"""
High-level wrapper over calls to the URLReputationOracle contract from
Python (genlayer-py). Used by the DAO governance and DeFi pool screening
examples (backend scripts, not frontend).

API and network names verified against the real `genlayer-py` package
(installed and confirmed via inspect.signature on the version used while
writing this file), not just against the documentation.
"""

from genlayer_py import create_client, create_account
from genlayer_py.chains import localnet, studionet, testnet_asimov, testnet_bradbury
from genlayer_py.types import TransactionStatus, ExecutionResult

_CHAINS = {
    "localnet": localnet,
    "studionet": studionet,
    "testnet_asimov": testnet_asimov,
    "testnet_bradbury": testnet_bradbury,
}


def get_chain(name: str):
    if name not in _CHAINS:
        raise ValueError(f"Unknown network: '{name}'. Options: {list(_CHAINS)}")
    return _CHAINS[name]


def create_read_client(chain_name: str):
    """
    Read-only client.

    Verification note: in `genlayer-js`, `readContract` falls back to the
    zero address if no account is passed (`account?.address ??
    client.account?.address ?? zeroAddress`), so a client with no account
    works fine for reads. In the installed version of `genlayer-py`
    (verified by reading the real source code, not just the docs), the
    equivalent `read_contract` method does NOT have that fallback: it
    raises `GenLayerError("No account provided and no account is
    connected")` if `self.local_account` is `None`, because it needs
    `local_account.address` for the `from` field of the read request.
    That's why an account is generated here too, even though it never
    signs anything - it only supplies a valid sender address for
    read-only calls.
    """
    return create_client(chain=get_chain(chain_name), account=create_account())


def create_write_client(chain_name: str, account=None):
    """
    Write client for scripts/backends. By default it generates a fresh
    account - in production, load a persistent service account (e.g. a
    private key from environment variables / secret manager).
    """
    return create_client(chain=get_chain(chain_name), account=account or create_account())


def has_report(read_client, contract_address: str, url: str) -> bool:
    return read_client.read_contract(
        address=contract_address,
        function_name="has_report",
        args=[url],
    )


def get_report(read_client, contract_address: str, url: str) -> dict:
    return read_client.read_contract(
        address=contract_address,
        function_name="get_report",
        args=[url],
    )


def analyze_url(write_client, contract_address: str, url: str) -> str:
    """
    Triggers analyze(url) and waits for the transaction to be ACCEPTED by
    validator consensus. Can take several seconds (web fetch + LLM call
    x2, once for the leader and once for each validator verifying it).

    Note: `account` is intentionally not passed here. The real signature
    of `write_contract` does `account if account is not None else
    self.local_account` - i.e. if omitted, it automatically uses the
    account the client was created with (`create_write_client`). Passing
    `write_client.account` would be a bug: that attribute is NOT the
    signing account, it's a generic object inherited from web3.py's `Eth`
    class (GenLayerClient extends `web3.eth.eth.Eth`). The real signing
    account lives at `write_client.local_account`.
    """
    tx_hash = write_client.write_contract(
        address=contract_address,
        function_name="analyze",
        args=[url],
        # `value` is an int, defaulting to 0 in the real write_contract
        # signature; kept explicit here only to document that no GEN is sent.
        value=0,
    )
    receipt = write_client.wait_for_transaction_receipt(
        transaction_hash=tx_hash,
        status=TransactionStatus.ACCEPTED,
    )
    if receipt.get("tx_execution_result_name") != ExecutionResult.FINISHED_WITH_RETURN.value:
        raise RuntimeError(
            f"analyze({url}) failed on-chain: {receipt.get('tx_execution_result_name')}"
        )
    return tx_hash


def ensure_analyzed(read_client, write_client, contract_address: str, url: str) -> dict:
    """
    Returns the report for `url`, analyzing it first if no report exists
    yet.
    """
    if not has_report(read_client, contract_address, url):
        analyze_url(write_client, contract_address, url)
    return get_report(read_client, contract_address, url)
