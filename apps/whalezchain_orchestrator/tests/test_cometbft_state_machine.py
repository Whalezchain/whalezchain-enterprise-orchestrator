"""Real deterministic ABCI application state tests (internal devnet only)."""
import os

import pytest

from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
from whalezchain_orchestrator.mainnet.cometbft_state_machine import (
    CometABCIError, WhalezCometApplication,
)
from whalezchain_orchestrator.mainnet.transaction import canonical_json
from whalezchain_orchestrator.tests.mainnet_test_helpers import (
    account, signed_mainnet_transaction,
)
from whalezchain_orchestrator.tests.test_mainnet_chain_store_persistence import _genesis


NETWORK = "whalezchain-internal-devnet-test1"
COMET_HASH = "ab" * 32
PROPOSER = "01" * 20


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.delenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", raising=False)
    directory = tmp_path / "isolated-node1"
    store = MainnetChainStore(directory)
    store.initialize_genesis(_genesis())
    return WhalezCometApplication(directory, NETWORK)


def signed_transfer(nonce=0):
    tx = signed_mainnet_transaction(
        tx_id="abci-transfer-1" if nonce == 0 else "abci-transfer-2",
        sender_label="alice", recipient_label="bob",
        asset_symbol="PTN", amount="1.00000000", nonce=nonce,
        ordering_key=f"{nonce + 1:020d}",
    )
    return canonical_json(tx.signed_dict())


def finalize_one(app, raws=(), height=1):
    return app.finalize_block(
        height=height,
        block_hash=COMET_HASH if height == 1 else "cd" * 32,
        timestamp="2026-11-23T04:30:00Z",
        proposer_address=PROPOSER,
        raws=raws,
    )


def test_initial_hash_binds_both_roots(app):
    info = app.info()
    assert info["height"] == 0
    assert len(info["app_hash"]) == 64
    genesis = app.store.load_genesis()
    assert app.init_chain(NETWORK, genesis["genesis_hash"]) == info
    with pytest.raises(CometABCIError, match="network chain ID"):
        app.init_chain("not-whalezchain", genesis["genesis_hash"])
    with pytest.raises(CometABCIError, match="genesis differ"):
        app.init_chain(NETWORK, "00" * 32)


def test_real_signed_transfer_staged_without_premature_commit(app):
    tx = signed_transfer()
    before = app.info()
    assert app.check_tx(tx)
    assert app.process_proposal((tx,))
    assert app.prepare_proposal((tx,), max_bytes=65536) == [tx]
    assert app.info() == before
    proposal = finalize_one(app, (tx,))
    assert proposal["tx_count"] == 1
    assert app.info() == before
    committed = app.commit()
    assert committed["app_hash"] == proposal["app_hash"]
    assert app.info()["height"] == 1
    assert app.info()["app_hash"] != before["app_hash"]
    state = app.store.replay_state()
    assert state[account("alice")]["PTN"] == "9.00000000"
    assert state[account("bob")]["PTN"] == "1.00000000"
    assert app.store.verify_chain()["verified"]
    restarted = WhalezCometApplication(app.store.root, NETWORK)
    assert restarted.info() == app.info()
    assert not restarted.check_tx(tx)
    with pytest.raises(CometABCIError, match="without FinalizeBlock"):
        restarted.commit()


def test_empty_consensus_block_persists_deterministic_chain_hash(app):
    proposal = finalize_one(app)
    with pytest.raises(CometABCIError, match="already staged"):
        finalize_one(app)
    assert app.store.finalized_head()["height"] == -1
    app.commit()
    assert app.store.finalized_head()["height"] == 0
    assert app.info()["app_hash"] == proposal["app_hash"]
    assert app.store.verify_chain()["verified"]


def test_tamper_replay_and_proposal_policy_do_not_mutate(app):
    valid = signed_transfer()
    malformed = b'{"chain_id":"whalezchain-mainnet-v1","chain_id":"duplicated"}'
    noncanonical = b'{ "chain_id": "whalezchain-mainnet-v1" }'
    assert not app.check_tx(malformed)
    assert not app.check_tx(noncanonical)
    assert not app.process_proposal((valid, valid))
    assert not app.process_proposal((malformed,))
    assert app.prepare_proposal((malformed, valid, valid), max_bytes=65536) == [valid]
    assert app.store.finalized_head()["height"] == -1
    with pytest.raises(ValueError):
        finalize_one(app, (malformed,))
    assert app.store.finalized_head()["height"] == -1


def test_wrong_height_or_identity_cannot_stage(app):
    with pytest.raises(CometABCIError, match="height"):
        finalize_one(app, height=2)
    with pytest.raises(CometABCIError, match="identity"):
        app.finalize_block(
            height=1, block_hash=COMET_HASH,
            timestamp="2026-11-23T04:30:00Z",
            proposer_address="not-hex", raws=(),
        )
    assert app.store.finalized_head()["height"] == -1


def test_live_mainnet_flag_cannot_activate_devnet_path(app, monkeypatch):
    monkeypatch.setenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "true")
    with pytest.raises(CometABCIError, match="forbidden"):
        app.info()
    with pytest.raises(CometABCIError, match="forbidden"):
        app.commit()
    with pytest.raises(CometABCIError, match="forbidden"):
        WhalezCometApplication(app.store.root, NETWORK)
    monkeypatch.delenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED")
    assert app.store.finalized_head()["height"] == -1


def test_internal_devnet_cannot_attach_to_non_test_genesis(monkeypatch, tmp_path):
    from whalezchain_orchestrator.mainnet.genesis import build_genesis

    monkeypatch.delenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", raising=False)
    source = _genesis()
    non_test = build_genesis(
        genesis_timestamp=source.genesis_timestamp,
        initial_state=source.initial_state,
        validators=source.validator_config,
        authority_config={"mode": "production"},
        economic_state=source.economic_state,
    )
    root = tmp_path / "non-test-chain"
    MainnetChainStore(root).initialize_genesis(non_test)
    with pytest.raises(CometABCIError, match="synthetic test genesis"):
        WhalezCometApplication(root, NETWORK)
