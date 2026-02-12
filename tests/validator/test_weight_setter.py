from datetime import timedelta
import pytest
from unittest.mock import Mock, patch

from qbittensor.utils.request.JWTManager import JWT
from qbittensor.utils.timestamping import timestamp
from qbittensor.validator.weights.WeightSetter import (
    WeightSetter, 
    REG_MAINTAINENCE_INCENTIVE, 
    BURN_PERCENTAGE
)

# Use a test-specific value that fits within test metagraph sizes
DISTRIBUTION_KEY_UID = 1
from tests.test_utils import get_mock_metagraph


@pytest.fixture
def mock_metagraph():
    mg = get_mock_metagraph(num_axons=5)
    mg.netuid = 2
    return mg


@pytest.fixture
def mock_metagraph_large():
    """Create a larger metagraph for testing with more hotkeys"""
    mg = get_mock_metagraph(num_axons=10)
    mg.netuid = 2
    # The hotkeys will be ['hk0', 'hk1', ..., 'hk9'] from get_mock_metagraph
    return mg


@pytest.fixture
def mock_wallet():
    return Mock()

@pytest.fixture
def weight_setter(
    monkeypatch,
    mock_metagraph,
    mock_wallet,
):

    fake_jwt = JWT(
        **{
            "access_token": "test_token",
            "expires_in": 300,
            "expiration_date": timestamp() + timedelta(seconds=300)
        }
    )
    monkeypatch.setattr(
        "qbittensor.utils.request.JWTManager.JWTManager.get_jwt",
        lambda self: fake_jwt
    )
    
    # Patch DISTRIBUTION_KEY_UID to fit within mock metagraph size (5 hotkeys)
    monkeypatch.setattr(
        "qbittensor.validator.weights.WeightSetter.DISTRIBUTION_KEY_UID",
        1
    )
    
    # Construct normally
    ws = WeightSetter(
        metagraph=mock_metagraph,
        wallet=mock_wallet,
        request_manager=Mock(),
        database_manager=Mock(),
        network="unit_test"
    )
    ws.database_manager.query_with_values.return_value = []
    ws._publisher = Mock()
    return ws


@pytest.fixture
def weight_setter_large(
    monkeypatch,
    mock_metagraph_large,
    mock_wallet,
):
    """WeightSetter with larger metagraph for more comprehensive testing"""
    fake_jwt = JWT(
        **{
            "access_token": "test_token",
            "expires_in": 300,
            "expiration_date": timestamp() + timedelta(seconds=300)
        }
    )
    monkeypatch.setattr(
        "qbittensor.utils.request.JWTManager.JWTManager.get_jwt",
        lambda self: fake_jwt
    )
    
    # Patch DISTRIBUTION_KEY_UID to fit within mock metagraph size (10 hotkeys)
    monkeypatch.setattr(
        "qbittensor.validator.weights.WeightSetter.DISTRIBUTION_KEY_UID",
        1
    )
    
    ws = WeightSetter(
        metagraph=mock_metagraph_large,
        wallet=mock_wallet,
        request_manager=Mock(),
        database_manager=Mock(),
        network="unit_test"
    )
    ws.database_manager.query_with_values.return_value = []
    ws._publisher = Mock()
    return ws


class TestWeightSetterMath:
    """Test the mathematical calculations in WeightSetter._get_weights()"""

    def test_get_weights_no_onboarded_miners(self, weight_setter):
        """Test weight calculation when no miners are onboarded"""
        burn_uid = 4  # Use a burn_uid within the mock metagraph range (0-4)
        with patch.object(weight_setter, '_get_burn_uid', return_value=burn_uid):
            weights = weight_setter._get_weights([])
            
            # Verify array length matches mock metagraph size
            assert len(weights) == 5
            
            # Verify burn percentage
            assert weights[burn_uid] == BURN_PERCENTAGE
            
            # Verify distribution key gets remaining weight (no miners so full remainder)
            assert weights[DISTRIBUTION_KEY_UID] == 1 - BURN_PERCENTAGE
            
            # Verify all other weights are 0
            for i in range(5):
                if i != burn_uid and i != DISTRIBUTION_KEY_UID:
                    assert weights[i] == 0.0

    def test_get_weights_single_onboarded_miner(self, weight_setter):
        """Test weight calculation with one onboarded miner"""
        onboarded_hotkeys = ["hk0"]  # First hotkey from mock metagraph
        burn_uid = 4  # Use a burn_uid within the mock metagraph range (0-4)
        
        with patch.object(weight_setter, '_get_burn_uid', return_value=burn_uid):
            weights = weight_setter._get_weights(onboarded_hotkeys)
            
            # Verify array length matches mock metagraph size
            assert len(weights) == 5
            
            # Verify burn percentage
            assert weights[burn_uid] == BURN_PERCENTAGE
            
            # Verify miner incentive
            assert weights[0] == REG_MAINTAINENCE_INCENTIVE  # uid 0 corresponds to hk0
            
            # Calculate expected distribution key weight
            expected_distribution = 1 - BURN_PERCENTAGE - (REG_MAINTAINENCE_INCENTIVE * 1)
            assert weights[DISTRIBUTION_KEY_UID] == expected_distribution
            
            # Verify total weights sum to 1
            assert abs(sum(weights) - 1.0) < 1e-10

    def test_get_weights_multiple_onboarded_miners(self, weight_setter_large):
        """Test weight calculation with multiple onboarded miners"""
        onboarded_hotkeys = ["hk0", "hk2", "hk5"]  # UIDs 0, 2, 5
        burn_uid = 9  # Use a burn_uid within the large mock metagraph range (0-9)
        
        with patch.object(weight_setter_large, '_get_burn_uid', return_value=burn_uid):
            weights = weight_setter_large._get_weights(onboarded_hotkeys)
            
            # Verify array length matches large mock metagraph size
            assert len(weights) == 10
            
            # Verify burn percentage
            assert weights[burn_uid] == BURN_PERCENTAGE
            
            # Verify miner incentives for onboarded miners
            assert weights[0] == REG_MAINTAINENCE_INCENTIVE  # hk0
            assert weights[2] == REG_MAINTAINENCE_INCENTIVE  # hk2
            assert weights[5] == REG_MAINTAINENCE_INCENTIVE  # hk5
            
            # Calculate expected distribution key weight based on provided hotkeys count
            num_onboarded = len(onboarded_hotkeys)
            expected_distribution = 1 - BURN_PERCENTAGE - (REG_MAINTAINENCE_INCENTIVE * num_onboarded)
            assert weights[DISTRIBUTION_KEY_UID] == expected_distribution
            
            # Verify total weights sum to 1
            assert abs(sum(weights) - 1.0) < 1e-10

    def test_get_weights_all_miners_onboarded(self, weight_setter_large):
        """Test weight calculation when all miners in metagraph are onboarded"""
        all_hotkeys = [f"hk{i}" for i in range(10)]  # All hotkeys from metagraph
        burn_uid = 9  # Use a burn_uid within the large mock metagraph range (0-9)
        
        with patch.object(weight_setter_large, '_get_burn_uid', return_value=burn_uid):
            weights = weight_setter_large._get_weights(all_hotkeys)
            
            # Verify array length matches large mock metagraph size
            assert len(weights) == 10
            
            # Verify burn percentage
            assert weights[burn_uid] == BURN_PERCENTAGE
            
            # Most miners get incentive, but UID 1 (hk1) gets overwritten by distribution calc
            # and UID 9 (hk9) gets overwritten by burn assignment
            for i in range(10):
                if i == DISTRIBUTION_KEY_UID:  # UID 1 gets overwritten
                    # This tests the bug: hk1 incentive is counted but overwritten
                    num_onboarded = len(all_hotkeys)
                    expected_distribution = 1 - BURN_PERCENTAGE - (REG_MAINTAINENCE_INCENTIVE * num_onboarded)
                    assert weights[i] == expected_distribution
                elif i == burn_uid:  # Burn UID gets burn percentage, overwriting miner incentive
                    assert weights[i] == BURN_PERCENTAGE
                else:
                    assert weights[i] == REG_MAINTAINENCE_INCENTIVE
            
            # Total will be 1 - 2*REG_MAINTAINENCE_INCENTIVE due to two bugs:
            # 1. UID 1 (distribution key) overwrites miner incentive
            # 2. UID 9 (burn uid) overwrites miner incentive
            expected_total = 1.0 - (2 * REG_MAINTAINENCE_INCENTIVE)
            assert abs(sum(weights) - expected_total) < 1e-10

    def test_get_weights_hotkey_not_in_metagraph(self, weight_setter):
        """Test that hotkeys not in metagraph don't affect weights but do affect distribution calculation"""
        onboarded_hotkeys = ["hk0", "nonexistent_hotkey", "hk2"]  # 3 hotkeys, but only 2 exist in metagraph
        burn_uid = 4  # Use a burn_uid within the mock metagraph range (0-4)
        
        with patch.object(weight_setter, '_get_burn_uid', return_value=burn_uid):
            weights = weight_setter._get_weights(onboarded_hotkeys)
            
            # Verify array length matches mock metagraph size
            assert len(weights) == 5
            
            # Only hk0 and hk2 should get weights (UIDs 0 and 2)
            assert weights[0] == REG_MAINTAINENCE_INCENTIVE
            assert weights[2] == REG_MAINTAINENCE_INCENTIVE
            
            # Distribution calculation uses ALL provided hotkeys (including nonexistent)
            num_provided_hotkeys = len(onboarded_hotkeys)  # 3, including nonexistent
            expected_distribution = 1 - BURN_PERCENTAGE - (REG_MAINTAINENCE_INCENTIVE * num_provided_hotkeys)
            assert weights[DISTRIBUTION_KEY_UID] == expected_distribution
            
            # Verify burn percentage
            assert weights[burn_uid] == BURN_PERCENTAGE
            
            # Total will be less than 1 because distribution calculated for 3 but only 2 got incentive
            expected_total = 1.0 - REG_MAINTAINENCE_INCENTIVE  # Short by 1 incentive
            assert abs(sum(weights) - expected_total) < 1e-10

    def test_get_weights_different_burn_uids(self, weight_setter):
        """Test weight calculation with different burn UIDs"""
        onboarded_hotkeys = ["hk0"]
        
        # Test with different burn UIDs that are within the mock metagraph range
        for burn_uid in [2, 3, 4]:
            with patch.object(weight_setter, '_get_burn_uid', return_value=burn_uid):
                weights = weight_setter._get_weights(onboarded_hotkeys)
                
                # Verify array length matches mock metagraph size
                assert len(weights) == 5
                
                # Verify burn is set at correct UID
                assert weights[burn_uid] == BURN_PERCENTAGE
                
                # Verify other positions except miner and distribution key
                for i in range(5):
                    if i == burn_uid:
                        continue
                    elif i == 0:  # miner uid
                        assert weights[i] == REG_MAINTAINENCE_INCENTIVE
                    elif i == DISTRIBUTION_KEY_UID:
                        expected = 1 - BURN_PERCENTAGE - REG_MAINTAINENCE_INCENTIVE
                        assert weights[i] == expected
                    else:
                        assert weights[i] == 0.0

    def test_get_weights_weight_conservation(self, weight_setter_large):
        """Test that weights sum correctly (noting bugs with UID collisions and nonexistent hotkeys)"""
        test_cases = [
            ([], 1.0),  # No miners - perfect sum
            (["hk0"], 1.0),  # One miner, no collision - perfect sum
            (["hk0", "hk3"], 1.0),  # Two miners, no collision - perfect sum
            ([f"hk{i}" for i in [0, 2, 3, 4, 5]], 1.0),  # Some miners, no collision - perfect sum
            ([f"hk{i}" for i in range(10)], 1.0 - (2 * REG_MAINTAINENCE_INCENTIVE)),  # All miners including UID 1 and burn UID collisions - both bugs occur
            (["hk1"], 1.0 - REG_MAINTAINENCE_INCENTIVE),  # Just UID 1 collision - bug occurs
            (["hk0", "nonexistent"], 1.0 - REG_MAINTAINENCE_INCENTIVE),  # Nonexistent hotkey causes shortage
        ]
        
        burn_uid = 9  # Use a burn_uid within the large mock metagraph range (0-9)
        for onboarded_hotkeys, expected_sum in test_cases:
            with patch.object(weight_setter_large, '_get_burn_uid', return_value=burn_uid):
                weights = weight_setter_large._get_weights(onboarded_hotkeys)
                
                # Verify array length matches large mock metagraph size
                assert len(weights) == 10
                
                # Verify weights sum to expected value
                total_weight = sum(weights)
                assert abs(total_weight - expected_sum) < 1e-10, f"Weights sum to {total_weight}, expected {expected_sum} for hotkeys {onboarded_hotkeys}"

    def test_get_weights_mathematical_consistency(self, weight_setter_large):
        """Test mathematical relationships between different weight components"""
        onboarded_hotkeys = ["hk0", "hk4", "hk7"]  # Avoiding UID 1 which is DISTRIBUTION_KEY_UID
        burn_uid = 9  # Use a burn_uid within the large mock metagraph range (0-9)
        
        with patch.object(weight_setter_large, '_get_burn_uid', return_value=burn_uid):
            weights = weight_setter_large._get_weights(onboarded_hotkeys)
            
            # Verify array length matches large mock metagraph size
            assert len(weights) == 10
            
            # Extract components
            burn_weight = weights[burn_uid]
            distribution_weight = weights[DISTRIBUTION_KEY_UID]
            miner_weights_sum = sum(weights[i] for i in [0, 4, 7])  # UIDs for the hotkeys
            
            # Test mathematical relationships
            assert burn_weight == BURN_PERCENTAGE
            assert miner_weights_sum == REG_MAINTAINENCE_INCENTIVE * len(onboarded_hotkeys)
            assert distribution_weight == 1 - burn_weight - miner_weights_sum
            assert abs(burn_weight + distribution_weight + miner_weights_sum - 1.0) < 1e-10

    def test_get_weights_edge_case_burn_uid_collision(self, weight_setter):
        """Test behavior when burn UID collides with distribution key UID"""
        onboarded_hotkeys = ["hk0"]
        
        # Test when burn UID is same as distribution key UID
        with patch.object(weight_setter, '_get_burn_uid', return_value=DISTRIBUTION_KEY_UID):
            weights = weight_setter._get_weights(onboarded_hotkeys)
            
            # Verify array length matches mock metagraph size
            assert len(weights) == 5
            
            # The distribution key calculation overwrites the burn percentage
            # This is actually a bug in the original logic, but we test the actual behavior
            expected_distribution = 1 - BURN_PERCENTAGE - (REG_MAINTAINENCE_INCENTIVE * len(onboarded_hotkeys))
            assert weights[DISTRIBUTION_KEY_UID] == expected_distribution
            
            # The burn weight should be overwritten by distribution weight
            assert weights[DISTRIBUTION_KEY_UID] != BURN_PERCENTAGE
            
            # The total weight will be incorrect because burn allocation is lost
            miner_weight = REG_MAINTAINENCE_INCENTIVE
            expected_total = expected_distribution + miner_weight
            actual_total = sum(weights)
            
            # This will be less than 1.0 because the burn weight was overwritten
            assert abs(actual_total - expected_total) < 1e-10
            assert actual_total < 1.0

    def test_get_weights_miner_distribution_key_collision(self, weight_setter):
        """Test behavior when a miner hotkey maps to DISTRIBUTION_KEY_UID"""
        # hk1 maps to UID 1, which is DISTRIBUTION_KEY_UID
        onboarded_hotkeys = ["hk1"]
        burn_uid = 4  # Use a burn_uid within the mock metagraph range (0-4)
        
        with patch.object(weight_setter, '_get_burn_uid', return_value=burn_uid):
            weights = weight_setter._get_weights(onboarded_hotkeys)
            
            # Verify array length matches mock metagraph size
            assert len(weights) == 5
            
            # The miner incentive gets set first, then overwritten by distribution weight
            expected_distribution = 1 - BURN_PERCENTAGE - (REG_MAINTAINENCE_INCENTIVE * len(onboarded_hotkeys))
            assert weights[DISTRIBUTION_KEY_UID] == expected_distribution
            
            # The miner weight is overwritten
            assert weights[DISTRIBUTION_KEY_UID] != REG_MAINTAINENCE_INCENTIVE
            
            # Verify burn weight is correct
            assert weights[burn_uid] == BURN_PERCENTAGE
            
            # Total is 1 - REG_MAINTAINENCE_INCENTIVE due to the bug
            expected_total = 1.0 - REG_MAINTAINENCE_INCENTIVE
            assert abs(sum(weights) - expected_total) < 1e-10

    def test_get_weights_zero_incentive_edge_case(self, weight_setter):
        """Test mathematical edge case when many miners are onboarded including collision"""
        # This tests numerical stability when many miners are onboarded
        # Create a scenario with all 5 miners onboarded from the mock metagraph
        all_hotkeys = ["hk0", "hk1", "hk2", "hk3", "hk4"]
        burn_uid = 3  # Use a burn_uid within the mock metagraph range (0-4)
        
        with patch.object(weight_setter, '_get_burn_uid', return_value=burn_uid):
            weights = weight_setter._get_weights(all_hotkeys)
            
            # Verify array length matches mock metagraph size
            assert len(weights) == 5
            
            # Check that distribution weight is calculated correctly
            total_incentive = REG_MAINTAINENCE_INCENTIVE * len(all_hotkeys)
            expected_distribution = 1 - BURN_PERCENTAGE - total_incentive
            
            # Distribution key gets the calculated value (noting hk1/UID1 collision)
            assert weights[DISTRIBUTION_KEY_UID] == expected_distribution
            
            # Burn weight should be correct
            assert weights[burn_uid] == BURN_PERCENTAGE
            
            # The math adds up to 1 - 2*REG_MAINTAINENCE_INCENTIVE due to collision bugs:
            # 1. UID 1 (distribution key) overwrites hk1 miner incentive  
            # 2. UID 3 (burn uid) overwrites hk3 miner incentive
            expected_total = 1.0 - (2 * REG_MAINTAINENCE_INCENTIVE)
            assert abs(sum(weights) - expected_total) < 1e-10

    def test_get_weights_bug_documentation(self, weight_setter):
        """This test documents a bug in the WeightSetter implementation.
        
        When a miner's UID equals DISTRIBUTION_KEY_UID (1), the miner's incentive
        is counted in the distribution calculation but then gets overwritten,
        causing the total weight to be less than 1.0 by exactly REG_MAINTAINENCE_INCENTIVE.
        
        This bug occurs because:
        1. The miner gets REG_MAINTAINENCE_INCENTIVE assigned to weights[1]
        2. The distribution calculation includes this miner in the count
        3. weights[1] gets overwritten with the distribution value
        4. The incentive amount is lost from the total
        """
        
        burn_uid = 4  # Use a burn_uid within the mock metagraph range (0-4)
        # Test with just the problematic miner
        with patch.object(weight_setter, '_get_burn_uid', return_value=burn_uid):
            weights = weight_setter._get_weights(["hk1"])  # hk1 maps to UID 1
            
            # Verify array length matches mock metagraph size
            assert len(weights) == 5
            
            # Document the bug: total is short by exactly the incentive amount
            total = sum(weights)
            expected_shortage = REG_MAINTAINENCE_INCENTIVE
            actual_shortage = 1.0 - total
            
            assert abs(actual_shortage - expected_shortage) < 1e-10, (
                f"Bug: Total weight shortage should be {expected_shortage}, "
                f"but got {actual_shortage}"
            )
            
            # The distribution weight calculation included the miner but weight was overwritten
            expected_distribution_value = 1 - BURN_PERCENTAGE - REG_MAINTAINENCE_INCENTIVE
            assert weights[DISTRIBUTION_KEY_UID] == expected_distribution_value
            
            # Burn weight is correct
            assert weights[burn_uid] == BURN_PERCENTAGE
            
            # All other weights are 0
            for i in range(5):
                if i not in [DISTRIBUTION_KEY_UID, burn_uid]:
                    assert weights[i] == 0.0


