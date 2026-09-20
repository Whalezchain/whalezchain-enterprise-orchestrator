from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ..mainnet.block_builder import MainnetBlockBuilder
from ..mainnet.state_transition import MainnetStateTransition
from ..mainnet.transaction import MainnetTransaction


MAINNET_CHAIN_ID = "whalezchain-mainnet-v1"


class MainnetCandidateService:
    """
    Phase 24A canonical mainnet candidate path.

    This service:
      signed transaction
        -> deterministic state transition
        -> pending block candidate
        -> deterministic receipt

    It does NOT finalize blocks or persist canonical mainnet state.
    """

    def __init__(
        self,
        *,
        chain_id: str = MAINNET_CHAIN_ID,
        proposer_id: str = "whalezchain-phase24a-candidate",
    ):
        self.chain_id = chain_id
        self.proposer_id = proposer_id
        self.state_transition = MainnetStateTransition()
        self.block_builder = MainnetBlockBuilder()

    def execute_transfer_candidate(
        self,
        *,
        transaction: MainnetTransaction,
        initial_state: Mapping[str, Mapping[str, str]],
        height: int = 0,
        previous_block_hash: str = "",
        timestamp: str | None = None,
        known_tx_hashes: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if transaction.transaction_type != "transfer":
            raise ValueError(
                "Phase 24A supports transaction_type=transfer only"
            )

        if transaction.chain_id != self.chain_id:
            raise ValueError("transaction chain_id does not match candidate chain")

        candidate_timestamp = timestamp or datetime.now(
            timezone.utc
        ).isoformat()

        transition = self.state_transition.apply(
            dict(initial_state),
            [transaction],
            chain_id=self.chain_id,
            known_tx_hashes=known_tx_hashes,
        )

        block = self.block_builder.build(
            chain_id=self.chain_id,
            height=height,
            previous_block_hash=previous_block_hash,
            timestamp=candidate_timestamp,
            transactions=[transaction],
            resulting_state_root=transition["state_root"],
            proposer_id=self.proposer_id,
        )

        transition_evidence = transition["transitions"][0]

        receipt = {
            "receipt_type": "whalezchain_mainnet_candidate_receipt_v1",
            "status": "EXECUTED_CANDIDATE",
            "finalized": False,
            "tx_hash": transaction.tx_hash,
            "tx_id": transaction.tx_id,
            "block_height": block.height,
            "block_hash": block.block_hash,
            "transaction_root": block.transaction_root,
            "before_state_root": transition_evidence["before_state_root"],
            "resulting_state_root": transition["state_root"],
            "state_transition_status": transition_evidence["status"],
            "consensus": block.consensus_evidence,
        }

        return {
            "status": "EXECUTED_CANDIDATE",
            "finalized": False,
            "transaction": transaction.signed_dict(),
            "transition": transition,
            "block": block,
            "receipt": receipt,
        }


def execute_transfer_candidate(**kwargs: Any) -> dict[str, Any]:
    return MainnetCandidateService().execute_transfer_candidate(**kwargs)
