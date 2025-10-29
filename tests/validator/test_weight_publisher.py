import pytest
from unittest.mock import  Mock

from qbittensor.validator.weights.WeightPublisher import WeightPublisher
from tests.test_utils import get_mock_metagraph, get_mock_keypair


@pytest.fixture
def mock_metagraph():
    """Mock metagraph for testing"""
    metagraph = get_mock_metagraph(num_axons=5)
    metagraph.netuid = 2
    return metagraph


@pytest.fixture
def mock_wallet():
    """Mock wallet for testing"""
    wallet = get_mock_keypair()
    return wallet


@pytest.fixture
def weight_publisher(mock_metagraph, mock_wallet):
    """Create a WeightPublisher instance for testing"""
    return WeightPublisher(mock_metagraph, mock_wallet, "unit_test")


class TestWeightPublisher:
    """Test cases for the WeightPublisher class"""

    def test_init(self, mock_metagraph, mock_wallet):
        """Test WeightPublisher initialization"""
        publisher = WeightPublisher(mock_metagraph, mock_wallet, "unit_test")
        
        assert publisher.metagraph == mock_metagraph
        assert publisher.wallet == mock_wallet

    def test_publish_succes(self, weight_publisher):
        """Test successful weight publishing on first attempt"""
        uids = [1, 2, 3]
        weights = [0.3, 0.3, 0.4]

        # Mock successful set_weights call
        mock_subtensor = Mock()
        mock_subtensor.set_weights.return_value = (True, "Success")
        weight_publisher.metagraph.subtensor = mock_subtensor
        
        success, message = weight_publisher.publish(uids, weights)
        
        assert success is True
        assert message == ""
        mock_subtensor.set_weights.assert_called_once_with(
            wallet=weight_publisher.wallet,
            netuid=weight_publisher.metagraph.netuid,
            uids=uids,
            weights=weights,
            wait_for_inclusion=True,
            wait_for_finalization=False,
        )

    def test_publish_parameters_passed_correctly(self, weight_publisher):
        """Test that all parameters are passed correctly to set_weights"""
        uids = [1, 2, 3]
        weights = [0.3, 0.3, 0.4]

        mock_subtensor = Mock()
        mock_subtensor.set_weights.return_value = (True, "Success")
        weight_publisher.metagraph.subtensor = mock_subtensor

        weight_publisher.publish(uids, weights)

        # Verify the call was made with correct parameters
        call_args = mock_subtensor.set_weights.call_args
        assert call_args[1]["wallet"] == weight_publisher.wallet
        assert call_args[1]["netuid"] == weight_publisher.metagraph.netuid
        assert call_args[1]["uids"] == uids
        assert call_args[1]["weights"] == weights
        assert call_args[1]["wait_for_inclusion"] is True
        assert call_args[1]["wait_for_finalization"] is False

    def test_publish_empty_uids_and_weights(self, weight_publisher):
        """Test publishing with empty UIDs and weights lists"""
        uids = []
        weights = []

        mock_subtensor = Mock()
        mock_subtensor.set_weights.return_value = (True, "Success")
        weight_publisher.metagraph.subtensor = mock_subtensor

        success, message = weight_publisher.publish(uids, weights)

        assert success is True
        assert message == ""
        mock_subtensor.set_weights.assert_called_once_with(
            wallet=weight_publisher.wallet,
            netuid=weight_publisher.metagraph.netuid,
            uids=uids,
            weights=weights,
            wait_for_inclusion=True,
            wait_for_finalization=False,
        )

    def test_publish_single_uid_weight(self, weight_publisher):
        """Test publishing with single UID and weight"""
        uids = [1]
        weights = [1.0]

        mock_subtensor = Mock()
        mock_subtensor.set_weights.return_value = (True, "Success")
        weight_publisher.metagraph.subtensor = mock_subtensor

        success, message = weight_publisher.publish(uids, weights)

        assert success is True
        assert message == ""
        mock_subtensor.set_weights.assert_called_once_with(
            wallet=weight_publisher.wallet,
            netuid=weight_publisher.metagraph.netuid,
            uids=uids,
            weights=weights,
            wait_for_inclusion=True,
            wait_for_finalization=False,
        )

    def test_publish_large_number_of_uids(self, weight_publisher):
        """Test publishing with a large number of UIDs and weights"""
        uids = list(range(100))  # 100 UIDs
        weights = [0.01] * 100  # 100 weights of 0.01 each

        mock_subtensor = Mock()
        mock_subtensor.set_weights.return_value = (True, "Success")
        weight_publisher.metagraph.subtensor = mock_subtensor

        success, message = weight_publisher.publish(uids, weights)

        assert success is True
        assert message == ""
        mock_subtensor.set_weights.assert_called_once_with(
            wallet=weight_publisher.wallet,
            netuid=weight_publisher.metagraph.netuid,
            uids=uids,
            weights=weights,
            wait_for_inclusion=True,
            wait_for_finalization=False,
        )

    def test_publish_weights_summing_to_one(self, weight_publisher):
        """Test publishing with weights that sum to 1.0"""
        uids = [1, 2, 3]
        weights = [0.25, 0.25, 0.5]  # Sums to 1.0

        mock_subtensor = Mock()
        mock_subtensor.set_weights.return_value = (True, "Success")
        weight_publisher.metagraph.subtensor = mock_subtensor

        success, message = weight_publisher.publish(uids, weights)

        assert success is True
        assert message == ""
        mock_subtensor.set_weights.assert_called_once_with(
            wallet=weight_publisher.wallet,
            netuid=weight_publisher.metagraph.netuid,
            uids=uids,
            weights=weights,
            wait_for_inclusion=True,
            wait_for_finalization=False,
        )

    def test_publish_weights_not_summing_to_one(self, weight_publisher):
        """Test publishing with weights that don't sum to 1.0"""
        uids = [1, 2, 3]
        weights = [0.3, 0.3, 0.3]  # Sums to 0.9

        mock_subtensor = Mock()
        mock_subtensor.set_weights.return_value = (True, "Success")
        weight_publisher.metagraph.subtensor = mock_subtensor

        success, message = weight_publisher.publish(uids, weights)

        assert success is True
        assert message == ""
        mock_subtensor.set_weights.assert_called_once_with(
            wallet=weight_publisher.wallet,
            netuid=weight_publisher.metagraph.netuid,
            uids=uids,
            weights=weights,
            wait_for_inclusion=True,
            wait_for_finalization=False,
        )

    def test_publish_with_negative_weights(self, weight_publisher):
        """Test publishing with negative weights (edge case)"""
        uids = [1, 2, 3]
        weights = [-0.1, 0.6, 0.5]  # Contains negative weight

        mock_subtensor = Mock()
        mock_subtensor.set_weights.return_value = (True, "Success")
        weight_publisher.metagraph.subtensor = mock_subtensor

        success, message = weight_publisher.publish(uids, weights)

        assert success is True
        assert message == ""
        mock_subtensor.set_weights.assert_called_once_with(
            wallet=weight_publisher.wallet,
            netuid=weight_publisher.metagraph.netuid,
            uids=uids,
            weights=weights,
            wait_for_inclusion=True,
            wait_for_finalization=False,
        )

    def test_publish_with_zero_weights(self, weight_publisher):
        """Test publishing with zero weights"""
        uids = [1, 2, 3]
        weights = [0.0, 0.5, 0.5]  # Contains zero weight

        mock_subtensor = Mock()
        mock_subtensor.set_weights.return_value = (True, "Success")
        weight_publisher.metagraph.subtensor = mock_subtensor

        success, message = weight_publisher.publish(uids, weights)

        assert success is True
        assert message == ""
        mock_subtensor.set_weights.assert_called_once_with(
            wallet=weight_publisher.wallet,
            netuid=weight_publisher.metagraph.netuid,
            uids=uids,
            weights=weights,
            wait_for_inclusion=True,
            wait_for_finalization=False,
        )

    def test_publish_metagraph_subtensor_not_set(self, weight_publisher):
        """Test publishing when metagraph.subtensor is not set"""
        uids = [1, 2, 3]
        weights = [0.3, 0.3, 0.4]

        # Remove subtensor attribute
        delattr(weight_publisher.metagraph, "subtensor")

        # This should fail when trying to call set_weights
        success, message = weight_publisher.publish(uids, weights)
        assert success is False
        assert "exception:" in message

    def test_publish_wallet_not_set(self, weight_publisher):
        """Test publishing when wallet is not set"""
        uids = [1, 2, 3]
        weights = [0.3, 0.3, 0.4]

        # Remove wallet attribute
        delattr(weight_publisher, "wallet")

        # This should fail when trying to call set_weights
        success, message = weight_publisher.publish(uids, weights)
        assert success is False
        assert "exception:" in message
