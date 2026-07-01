from typing import List, Tuple
import bittensor as bt


class WeightPublisher:
    """
    Thin wrapper for publishing weights to the chain
    """

    def __init__(self, metagraph: bt.Metagraph, wallet: bt.Wallet, network: str):
        self.metagraph: bt.Metagraph = metagraph
        self.wallet: bt.Wallet = wallet
        self.network: str = network

    def publish(self, uids: List[int], weights: List[float]) -> Tuple[bool, str]:
        bt.logging.info("🏋 [setting weights] Attempting to set weights")

        if self.network == "local":
            bt.logging.info("🏋 [setting weights] Skipping set_weights on local network")
            return True, ""
        
        st: bt.Subtensor | None = getattr(self.metagraph, "subtensor", None)
        if st is None:
            return False, "exception: metagraph.subtensor missing"
        if getattr(self, "wallet", None) is None:
            return False, "exception: wallet missing"

        result = st.set_weights(
            wallet=self.wallet,
            netuid=self.metagraph.netuid,
            uids=uids,
            weights=weights,
            wait_for_inclusion=True,
            wait_for_finalization=False,
        )
        # v10: ExtrinsicResponse; fall back for old tuple return
        if hasattr(result, "success"):
            success = bool(getattr(result, "success", False))
            message = getattr(result, "message", "") or getattr(result, "error_message", "")
        elif isinstance(result, (list, tuple)):
            success = bool(result[0]) if result else False
            message = result[1] if len(result) > 1 else ""
        else:
            success = bool(result)
            message = ""
        if success:
            return True, ""
        else:
            return False, f"set_weights_failed: {message}"
