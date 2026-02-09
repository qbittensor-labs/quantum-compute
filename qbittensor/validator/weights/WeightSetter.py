from datetime import timedelta, datetime, timezone
import bittensor as bt
from typing import Dict, List, Tuple

from qbittensor.utils.telemetry.TelemetryService import TelemetryService
from qbittensor.validator.reward.burn_uid import get_burn_uid
from pkg.database.database_manager import DatabaseManager
from qbittensor.utils.Timer import Timer
from qbittensor.utils.request.RequestManager import RequestManager
from qbittensor.validator.weights.WeightPublisher import WeightPublisher

DISTRIBUTION_KEY_UID = 220
LOG_NS = "🏋  [setting weights]"
BURN_PERCENTAGE = 0.90
LOOKBACK_PERIOD = timedelta(days=14)
REG_MAINTAINENCE_INCENTIVE = 0.001
TOTAL_MAINTENANCE_INCENTIVE = 0.01

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
        # onboarded_miner_hotkeys = ["TSTHK1", "TSTHK2", "TSTHK3", "TSTHK4"]
        weights: List[float] = self._get_weights(onboarded_miner_hotkeys)
        uids: List[int] = list(range(len(weights)))
        non_zero: List[Tuple[int, float]] = []
        for uid, weight in zip(uids, weights):
            if weight > 0:
                non_zero.append((uid, weight))
        bt.logging.info(f"{LOG_NS} setting weights. Non-zero miner weights: {non_zero}")
        self.telemetry_service.vali_record_weights(weights)
        self._publisher.publish(uids, weights)
        
    def _get_execution_costs_per_hotkey(self) -> List[tuple]:
        min_time: datetime = datetime.now(timezone.utc) - LOOKBACK_PERIOD
        query: str = """
            SELECT miner_hotkey, SUM(cost) as total_cost
            FROM successful_job 
            WHERE created_at > ? 
            AND cost IS NOT NULL 
            GROUP BY miner_hotkey
        """
        values: tuple = (min_time,)
        results: list = self.database_manager.query_with_values(query, values)
        if not results:
            bt.logging.info("Failed to find miner hotkey / completed job counts")
            return []
        if len(results) == 0:
            bt.logging.info("No miner hotkey / completed job counts")
            return []
        return results
    
    def _get_hotkey_proportions(self, hotkey_cost_list: List[tuple]) -> Dict[str, float]:
        sum: int = 0
        for entry in hotkey_cost_list:
            sum += entry[1]
        if sum == 0:
            bt.logging.info("Found 0 sum of all hotkey counts.")
            return {}
        hotkey_proportion_dict: Dict[str, float] = {}
        for entry in hotkey_cost_list:
            hotkey: str = entry[0]
            miner_total_cost: int = entry[1]
            proportion: float = miner_total_cost / sum
            hotkey_proportion_dict[hotkey] = proportion
        return hotkey_proportion_dict

    def _get_weights(self, onboarded_miner_hotkeys: List[str]) -> List[float]:
        """Calculate weights for the given hotkeys."""
        weights = [0.0] * len(self.metagraph.hotkeys)
        
        bt.logging.info(f"DEBUG Onboarded miner keys: {onboarded_miner_hotkeys}")
        
        costs_per_hotkey: List[tuple] = self._get_execution_costs_per_hotkey()
        bt.logging.info(f"DEBUG Costs Per Hotkey Result: {costs_per_hotkey}")
        proportions: Dict[str, float] = self._get_hotkey_proportions(costs_per_hotkey)
        bt.logging.info(f"DEBUG Proportions dict: {proportions}")
        
        # Create sets
        all_onboarded_keys_set: set = set(onboarded_miner_hotkeys)   # All onboarded miner keys
        all_keys_in_proportions_set: set = set(proportions.keys())   # All keys with proportions
        all_metagraph_hotkeys_set: set = set(self.metagraph.hotkeys) # All keys in metagrah
        
        # Set operations
        onboarded_keys_in_metagraph_set: set = all_onboarded_keys_set.intersection(all_metagraph_hotkeys_set) # Onboarded miner keys that are in the metagraph
        keys_needing_maintenance_set: set = onboarded_keys_in_metagraph_set.difference(all_keys_in_proportions_set) # Onboarded miner keys that are in the metagraph but not in the proportions dict
        
        keys_needing_maintenance: List[str] = list(keys_needing_maintenance_set)
        bt.logging.info(f"DEBUG Keys needing maintenance: {keys_needing_maintenance}")
        maintenance_amount: float = 0.0
        if len(keys_needing_maintenance) > 0:
            maintenance_amount = TOTAL_MAINTENANCE_INCENTIVE / len(keys_needing_maintenance)
        non_maintenance_multiplier: float = 1 - TOTAL_MAINTENANCE_INCENTIVE
        
        bt.logging.info(f"DEBUG Maintenance Amount: {maintenance_amount} | Non-Maintenance multiplier: {non_maintenance_multiplier}")
        tmp_weights: List[float] = [0.0] * len(self.metagraph.hotkeys)
        
        for uid, hotkey in enumerate(self.metagraph.hotkeys):
            if hotkey in proportions:
                final_proportion: float = proportions[hotkey] * non_maintenance_multiplier
                tmp_weights[uid] = final_proportion
            elif hotkey in onboarded_miner_hotkeys:
                tmp_weights[uid] = maintenance_amount
                
        bt.logging.info(f"DEBUG Proposed weights: {tmp_weights}")
        new_weights_non_zero: List[Tuple[int, str, float]] = []
        for uid, weight in enumerate(tmp_weights):
            if weight > 0:
                new_weights_non_zero.append((uid, self.metagraph.hotkeys[uid], weight))
        bt.logging.info(f"DEBUG Proposed non-zero weights")
        for entry in new_weights_non_zero:
            bt.logging.info(f"    UID: {entry[0]} | Hotkey: {entry[1]} | Weight: {entry[2]}")
            
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