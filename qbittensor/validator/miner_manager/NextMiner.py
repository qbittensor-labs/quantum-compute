import bittensor as bt
from pydantic import BaseModel, ConfigDict

class BasicMiner(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    hotkey: str
    uid: int
    axon: bt.AxonInfo

    def __repr__(self) -> str:
        return f"BasicMiner(hotkey={self.hotkey}, uid={self.uid}, axon={self.axon})"

class NextMiner:

    def __init__(self, metagraph: bt.Metagraph) -> None:
        self.metagraph = metagraph
        self._index = 0

    def get_next_miner(self) -> BasicMiner:
        """Get the next Miner object in the list"""
        try:
            hotkey: str = self.metagraph.hotkeys[self._index]
            axon: bt.AxonInfo = self._get_axon_from_metagraph()
            bt.logging.debug(f"Axon type: {type(axon)} for miner {hotkey} at index {self._index}")
            return BasicMiner(hotkey=hotkey, uid=self._index, axon=axon)
        finally:
            self._increment_miner_index()
    
    def _get_axon_from_metagraph(self) -> bt.AxonInfo:
        """Gets the axon associated with a miner"""
        return self.metagraph.axons[self._index]

    def _increment_miner_index(self):
        """Maintain the index by incrementing"""
        self._index = (self._index + 1) % len(self.metagraph.hotkeys)
