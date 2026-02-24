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
        weights = weight_setter._get_weights([])
        
        # Verify array length matches mock metagraph size
        assert len(weights) == 5
        
        # With no onboarded miners, all weights should be 0
        for i in range(5):
            assert weights[i] == 0.0
        
        # Total weight should be 0
        assert sum(weights) == 0.0

    def test_get_weights_single_onboarded_miner(self, weight_setter):
        """Test weight calculation with one onboarded miner"""
        onboarded_hotkeys = ["hk0"]  # First hotkey from mock metagraph
        
        weights = weight_setter._get_weights(onboarded_hotkeys)
        
        # Verify array length matches mock metagraph size
        assert len(weights) == 5
        
        # With one onboarded miner and no cost data, it gets full maintenance incentive
        from qbittensor.validator.weights.WeightSetter import TOTAL_MAINTENANCE_INCENTIVE
        assert weights[0] == TOTAL_MAINTENANCE_INCENTIVE  # uid 0 corresponds to hk0
        
        # All other weights should be 0
        for i in range(1, 5):
            assert weights[i] == 0.0
        
        # Total should equal maintenance incentive
        assert abs(sum(weights) - TOTAL_MAINTENANCE_INCENTIVE) < 1e-10

    def test_get_weights_multiple_onboarded_miners(self, weight_setter_large):
        """Test weight calculation with multiple onboarded miners"""
        onboarded_hotkeys = ["hk0", "hk2", "hk5"]  # UIDs 0, 2, 5
        
        weights = weight_setter_large._get_weights(onboarded_hotkeys)
        
        # Verify array length matches large mock metagraph size
        assert len(weights) == 10
        
        # With multiple onboarded miners and no cost data, they share maintenance incentive equally
        from qbittensor.validator.weights.WeightSetter import TOTAL_MAINTENANCE_INCENTIVE
        expected_per_miner = TOTAL_MAINTENANCE_INCENTIVE / len(onboarded_hotkeys)
        
        # Verify miner incentives for onboarded miners
        assert abs(weights[0] - expected_per_miner) < 1e-10  # hk0
        assert abs(weights[2] - expected_per_miner) < 1e-10  # hk2
        assert abs(weights[5] - expected_per_miner) < 1e-10  # hk5
        
        # All other weights should be 0
        for i in [1, 3, 4, 6, 7, 8, 9]:
            assert weights[i] == 0.0
        
        # Verify total weights sum to maintenance incentive
        assert abs(sum(weights) - TOTAL_MAINTENANCE_INCENTIVE) < 1e-10

    def test_get_weights_all_miners_onboarded(self, weight_setter_large):
        """Test weight calculation when all miners in metagraph are onboarded"""
        all_hotkeys = [f"hk{i}" for i in range(10)]  # All hotkeys from metagraph
        
        weights = weight_setter_large._get_weights(all_hotkeys)
        
        # Verify array length matches large mock metagraph size
        assert len(weights) == 10
        
        # With all miners onboarded and no cost data, they share maintenance incentive equally
        from qbittensor.validator.weights.WeightSetter import TOTAL_MAINTENANCE_INCENTIVE
        expected_per_miner = TOTAL_MAINTENANCE_INCENTIVE / len(all_hotkeys)
        
        # All miners should get equal share of maintenance incentive
        for i in range(10):
            assert abs(weights[i] - expected_per_miner) < 1e-10
        
        # Total should equal maintenance incentive
        assert abs(sum(weights) - TOTAL_MAINTENANCE_INCENTIVE) < 1e-10

    def test_get_weights_hotkey_not_in_metagraph(self, weight_setter):
        """Test that hotkeys not in metagraph are filtered out and don't get weights"""
        onboarded_hotkeys = ["hk0", "nonexistent_hotkey", "hk2"]  # 3 hotkeys, but only 2 exist in metagraph
        
        weights = weight_setter._get_weights(onboarded_hotkeys)
        
        # Verify array length matches mock metagraph size
        assert len(weights) == 5
        
        # Only hk0 and hk2 should get weights (UIDs 0 and 2), sharing maintenance incentive
        from qbittensor.validator.weights.WeightSetter import TOTAL_MAINTENANCE_INCENTIVE
        expected_per_miner = TOTAL_MAINTENANCE_INCENTIVE / 2  # Only 2 valid miners
        
        assert abs(weights[0] - expected_per_miner) < 1e-10  # hk0
        assert abs(weights[2] - expected_per_miner) < 1e-10  # hk2
        
        # All other weights should be 0
        for i in [1, 3, 4]:
            assert weights[i] == 0.0
        
        # Total should equal maintenance incentive
        assert abs(sum(weights) - TOTAL_MAINTENANCE_INCENTIVE) < 1e-10

    def test_get_weights_different_scenarios(self, weight_setter):
        """Test weight calculation with different onboarded miner scenarios"""
        from qbittensor.validator.weights.WeightSetter import TOTAL_MAINTENANCE_INCENTIVE
        
        # Test single miner scenarios
        for miner_hotkey in ["hk0", "hk1", "hk2", "hk3", "hk4"]:
            onboarded_hotkeys = [miner_hotkey]
            weights = weight_setter._get_weights(onboarded_hotkeys)
            
            # Verify array length matches mock metagraph size
            assert len(weights) == 5
            
            # Only the specified miner should get weight
            miner_uid = int(miner_hotkey[2])  # Extract uid from "hkX"
            assert weights[miner_uid] == TOTAL_MAINTENANCE_INCENTIVE
            
            # All other weights should be 0
            for i in range(5):
                if i != miner_uid:
                    assert weights[i] == 0.0
            
            # Total should equal maintenance incentive
            assert abs(sum(weights) - TOTAL_MAINTENANCE_INCENTIVE) < 1e-10

    def test_get_weights_weight_conservation(self, weight_setter_large):
        """Test that weights sum correctly with the maintenance incentive system"""
        from qbittensor.validator.weights.WeightSetter import TOTAL_MAINTENANCE_INCENTIVE
        
        test_cases = [
            ([], 0.0),  # No miners - zero sum
            (["hk0"], TOTAL_MAINTENANCE_INCENTIVE),  # One miner gets full maintenance incentive
            (["hk0", "hk3"], TOTAL_MAINTENANCE_INCENTIVE),  # Two miners share maintenance incentive
            (["hk0", "hk2", "hk3", "hk4", "hk5"], TOTAL_MAINTENANCE_INCENTIVE),  # Multiple miners share maintenance incentive
            ([f"hk{i}" for i in range(10)], TOTAL_MAINTENANCE_INCENTIVE),  # All miners share maintenance incentive
            (["hk0", "nonexistent"], TOTAL_MAINTENANCE_INCENTIVE),  # Nonexistent hotkey ignored, only valid miner gets incentive
        ]
        
        for onboarded_hotkeys, expected_sum in test_cases:
            weights = weight_setter_large._get_weights(onboarded_hotkeys)
            
            # Verify array length matches large mock metagraph size
            assert len(weights) == 10
            
            # Verify weights sum to expected value
            total_weight = sum(weights)
            assert abs(total_weight - expected_sum) < 1e-10, f"Weights sum to {total_weight}, expected {expected_sum} for hotkeys {onboarded_hotkeys}"

    def test_get_weights_mathematical_consistency(self, weight_setter_large):
        """Test mathematical relationships in the cost-based proportional system"""
        from qbittensor.validator.weights.WeightSetter import TOTAL_MAINTENANCE_INCENTIVE
        
        # Test case 1: Pure maintenance (no cost data)
        onboarded_hotkeys = ["hk0", "hk4", "hk7"]
        weights = weight_setter_large._get_weights(onboarded_hotkeys)
        
        # Verify array length matches large mock metagraph size
        assert len(weights) == 10
        
        # Each miner should get equal share of maintenance incentive
        expected_per_miner = TOTAL_MAINTENANCE_INCENTIVE / len(onboarded_hotkeys)
        assert abs(weights[0] - expected_per_miner) < 1e-10  # hk0
        assert abs(weights[4] - expected_per_miner) < 1e-10  # hk4  
        assert abs(weights[7] - expected_per_miner) < 1e-10  # hk7
        
        # All other weights should be 0
        for i in [1, 2, 3, 5, 6, 8, 9]:
            assert weights[i] == 0.0
        
        # Total should equal maintenance incentive
        assert abs(sum(weights) - TOTAL_MAINTENANCE_INCENTIVE) < 1e-10
        
        # Test case 2: Mixed cost data and maintenance
        weight_setter_large.database_manager.query_with_values.return_value = [('hk0', 100), ('hk4', 200)]
        weights = weight_setter_large._get_weights(onboarded_hotkeys)
        
        # hk0 and hk4 get proportional weights based on costs (reduced by maintenance)
        # hk7 gets maintenance incentive
        maintenance_multiplier = 1 - TOTAL_MAINTENANCE_INCENTIVE
        expected_hk0 = (100 / 300) * maintenance_multiplier  # 1/3 * 0.99
        expected_hk4 = (200 / 300) * maintenance_multiplier  # 2/3 * 0.99
        expected_hk7 = TOTAL_MAINTENANCE_INCENTIVE  # Full maintenance for hk7
        
        assert abs(weights[0] - expected_hk0) < 1e-10
        assert abs(weights[4] - expected_hk4) < 1e-10
        assert abs(weights[7] - expected_hk7) < 1e-10
        
        # Total should be approximately 1.0
        assert abs(sum(weights) - 1.0) < 1e-10

    def test_get_weights_with_cost_proportions(self, weight_setter):
        """Test weight calculation when miners have cost proportions from the database"""
        onboarded_hotkeys = ["hk0", "hk1", "hk2"]
        
        # Mock database to return cost data for some miners
        weight_setter.database_manager.query_with_values.return_value = [('hk0', 100), ('hk2', 300)]
        
        weights = weight_setter._get_weights(onboarded_hotkeys)
        
        # Verify array length matches mock metagraph size
        assert len(weights) == 5
        
        from qbittensor.validator.weights.WeightSetter import TOTAL_MAINTENANCE_INCENTIVE
        
        # hk0 and hk2 get proportional weights (reduced by maintenance incentive)
        # hk1 gets maintenance incentive (no cost data)
        maintenance_multiplier = 1 - TOTAL_MAINTENANCE_INCENTIVE
        total_costs = 100 + 300  # 400
        
        expected_hk0 = (100 / total_costs) * maintenance_multiplier  # 1/4 * 0.99 = 0.2475
        expected_hk2 = (300 / total_costs) * maintenance_multiplier  # 3/4 * 0.99 = 0.7425
        expected_hk1 = TOTAL_MAINTENANCE_INCENTIVE  # 0.01
        
        assert abs(weights[0] - expected_hk0) < 1e-10  # hk0
        assert abs(weights[1] - expected_hk1) < 1e-10  # hk1
        assert abs(weights[2] - expected_hk2) < 1e-10  # hk2
        
        # Other weights should be 0
        assert weights[3] == 0.0
        assert weights[4] == 0.0
        
        # Total should be approximately 1.0
        assert abs(sum(weights) - 1.0) < 1e-10

    def test_get_weights_large_scale_distribution(self, weight_setter):
        """Test weight distribution with all miners in a small metagraph"""
        # Test with all 5 miners from the mock metagraph
        all_hotkeys = ["hk0", "hk1", "hk2", "hk3", "hk4"]
        
        weights = weight_setter._get_weights(all_hotkeys)
        
        # Verify array length matches mock metagraph size
        assert len(weights) == 5
        
        from qbittensor.validator.weights.WeightSetter import TOTAL_MAINTENANCE_INCENTIVE
        
        # Each miner should get equal share of maintenance incentive
        expected_per_miner = TOTAL_MAINTENANCE_INCENTIVE / len(all_hotkeys)
        
        for i in range(5):
            assert abs(weights[i] - expected_per_miner) < 1e-10
        
        # Total should equal maintenance incentive
        assert abs(sum(weights) - TOTAL_MAINTENANCE_INCENTIVE) < 1e-10

    def test_get_weights_cost_based_system_documentation(self, weight_setter):
        """This test documents the cost-based proportional weight system.
        
        The WeightSetter now uses a cost-based approach where:
        1. Miners with cost data get proportional weights based on their execution costs
        2. The proportional weights are scaled by (1 - TOTAL_MAINTENANCE_INCENTIVE)
        3. Miners without cost data share the TOTAL_MAINTENANCE_INCENTIVE equally
        4. Miners not onboarded get no weight
        """
        
        from qbittensor.validator.weights.WeightSetter import TOTAL_MAINTENANCE_INCENTIVE
        
        # Test 1: Pure maintenance case (no cost data)
        weight_setter.database_manager.query_with_values.return_value = []
        weights = weight_setter._get_weights(["hk1"])
        
        assert len(weights) == 5
        assert weights[1] == TOTAL_MAINTENANCE_INCENTIVE  # hk1 gets full maintenance
        
        for i in [0, 2, 3, 4]:
            assert weights[i] == 0.0
        
        total = sum(weights)
        assert abs(total - TOTAL_MAINTENANCE_INCENTIVE) < 1e-10
        
        # Test 2: Mixed cost and maintenance case
        weight_setter.database_manager.query_with_values.return_value = [('hk1', 200)]
        weights = weight_setter._get_weights(["hk1", "hk3"])
        
        # hk1 has cost data, hk3 needs maintenance
        # hk1 gets: (200/200) * (1 - 0.01) = 1.0 * 0.99 = 0.99
        # hk3 gets: 0.01 (full maintenance incentive since it's the only maintenance miner)
        
        assert abs(weights[1] - 0.99) < 1e-10  # hk1 with cost data
        assert abs(weights[3] - 0.01) < 1e-10  # hk3 with maintenance
        
        for i in [0, 2, 4]:
            assert weights[i] == 0.0
        
        # Total should be 1.0
        assert abs(sum(weights) - 1.0) < 1e-10


