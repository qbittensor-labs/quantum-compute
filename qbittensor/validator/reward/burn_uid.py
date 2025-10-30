import bittensor as bt
from bittensor.core.metagraph import Metagraph


def get_burn_uid(metagraph: Metagraph) -> int:
    """
    Get the subnet owner UID (burn UID) for the given metagraph.
    Excess emissions beyond a miners cost will be burned using this UID.
    Args:
        metagraph: The metagraph instance containing subtensor and netuid
        
    Returns:
        int: The UID of the subnet owner hotkey
        
    Raises:
        ValueError: If unable to get subnet owner information
    """
    try:
        # Get the subtensor owner hotkey
        sn_owner_hotkey = metagraph.subtensor.query_subtensor(
            "SubnetOwnerHotkey",
            params=[metagraph.netuid],
        )
        
        # Get the UID of this hotkey
        sn_owner_uid = metagraph.subtensor.get_uid_for_hotkey_on_subnet(
            hotkey_ss58=sn_owner_hotkey,
            netuid=metagraph.netuid,
        )
        
        bt.logging.debug(f"Subnet owner UID: {sn_owner_uid}")
        
        return sn_owner_uid
        
    except Exception as e:
        bt.logging.error(f"Error getting burn UID: {e}")
        raise ValueError(f"Unable to get subnet owner UID: {e}")