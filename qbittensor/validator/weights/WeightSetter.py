from datetime import timedelta
import bittensor as bt
from typing import List, Tuple

from qbittensor.utils.telemetry.TelemetryService import TelemetryService
from qbittensor.validator.reward.burn_uid import get_burn_uid
from pkg.database.database_manager import DatabaseManager
from qbittensor.utils.Timer import Timer
from qbittensor.utils.request.RequestManager import RequestManager
from qbittensor.validator.weights.WeightPublisher import WeightPublisher

DISTRIBUTION_KEY_UID = 220
LOG_NS = "🏋  [setting weights]"
REG_MAINTAINENCE_INCENTIVE = 0.001
BURN_PERCENTAGE = 0.90

class WeightSetter:
    """
    Periodic weight calculation & publishing.
    """
    def __init__(
        self,
        metagraph: bt.Metagraph,
        wallet: bt.Wallet,
        request_manager: RequestManager,
        database_manager: DatabaseManager,
        network: str,
    ):
        self.metagraph: bt.Metagraph = metagraph
        self.wallet: bt.Wallet = wallet
        self.request_manager: RequestManager = request_manager
        self.network = network

        self.database_manager: DatabaseManager = database_manager
        self._publisher: WeightPublisher = WeightPublisher(metagraph, wallet, network)
        self.timer: Timer = Timer(timedelta(minutes=30), self._set_weights, run_on_start=True)
        self.telemetry_service = TelemetryService(request_manager)

    
    def check_timer(self) -> None:
        """Check if it's time to run the weight setting process."""
        bt.logging.debug(f"{LOG_NS} checking timer on network={self.network}.")
        self.timer.check_timer()

    def _set_weights(self) -> None:
        bt.logging.info(f"{LOG_NS} start")
        onboarded_miner_hotkeys = self._get_onboarded_miner_hotkeys()
        weights: List[float] = self._get_weights(onboarded_miner_hotkeys)
        uids: List[int] = list(range(len(weights)))
        non_zero: List[Tuple[int, float]] = []
        for uid, weight in zip(uids, weights):
            if weight > 0:
                non_zero.append((uid, weight))
        bt.logging.info(f"{LOG_NS} setting weights. Non-zero miner weights: {non_zero}")
        self.telemetry_service.vali_record_weights(weights)
        self._publisher.publish(uids, weights)
        

    def _get_weights(self, onboarded_miner_hotkeys: List[str]) -> List[float]:
        """Calculate weights for the given hotkeys."""
        weights = [0.0] * len(self.metagraph.hotkeys)
        
        for uid, hotkey in enumerate(self.metagraph.hotkeys):
            if hotkey in onboarded_miner_hotkeys:
                weights[uid] = REG_MAINTAINENCE_INCENTIVE

        burn_uid = self._get_burn_uid()
        weights[burn_uid] = BURN_PERCENTAGE # Set the burn amount
        weights[DISTRIBUTION_KEY_UID] = 1 - BURN_PERCENTAGE - (REG_MAINTAINENCE_INCENTIVE * len(onboarded_miner_hotkeys)) # Set the distribution key weight

        return weights

    def _get_burn_uid(self) -> int:
        """Use optional util if present; otherwise constant fallback for tests."""
        try:

            return get_burn_uid(self.metagraph)
        except Exception:
            return 34 # owner uid
        
    def _get_onboarded_miner_hotkeys(self) -> List[str]:
        """Fetch list of onboarded miners from the job server."""
        try:
            endpoint = "backends/hotkeys"
            response = self.request_manager.get(endpoint=endpoint)
            data = response.json()
            bt.logging.debug(f"{LOG_NS} Fetched onboarded miners: {data}")
            return data
        except Exception as e:
            bt.logging.error(f"{LOG_NS} Failed to fetch onboarded miners: {e}")
            return []