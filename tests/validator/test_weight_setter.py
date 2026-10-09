from unittest.mock import Mock

from qbittensor.utils.services.telemetry import TelemetryService
from qbittensor.validator.weights.weight_setter import WeightSetter
from tests.test_utils import get_mock_metagraph


def _excess_snapshot():
    return {
        "miners": [
            {"miner_hotkey": "hk0", "cost": 80, "completed": 8, "failed": 0},
            {"miner_hotkey": "hk1", "cost": 20, "completed": 2, "failed": 0},
        ],
        "credit_usd": 1,
        "tao_usd": 400,
        "alpha_price": 1.0,
        "miner_emission_alpha": 1.0,
        "cost_markup": 1.2,
        "stake_exponent": 0.5,
    }


def test_weights_from_snapshot_uses_metagraph_hotkeys():
    mg = get_mock_metagraph(num_axons=3)
    mg.owner_hotkey = None
    mg.raw = None
    ws = WeightSetter(mg, telemetry_service=Mock(spec=TelemetryService))
    weights = ws.weights_from_snapshot(_excess_snapshot())
    assert weights is not None
    assert len(weights) == 3
    assert abs(weights[0] - 0.8) < 1e-9
    assert abs(weights[1] - 0.2) < 1e-9
    assert abs(weights[2]) < 1e-12


def test_weights_from_snapshot_pads_a_short_stake_vector():
    mg = get_mock_metagraph(num_axons=3)
    mg.S = [0.0, 10.0]
    mg.owner_hotkey = "hk2"
    ws = WeightSetter(mg, telemetry_service=Mock(spec=TelemetryService))
    snap = {
        "miners": [
            {"miner_hotkey": "hk0", "cost": 200, "completed": 1, "failed": 0},
            {"miner_hotkey": "hk1", "cost": 200, "completed": 1, "failed": 0},
        ],
        "credit_usd": 1,
        "tao_usd": 400,
        "alpha_price": 1.0,
        "miner_emission_alpha": 1.0,
        "cost_markup": 1.2,
        "stake_exponent": 0.5,
    }
    weights = ws.weights_from_snapshot(snap)
    assert weights is not None
    assert abs(weights[0]) < 1e-9
    assert abs(weights[1] - 0.6) < 1e-9
    assert abs(weights[2] - 0.4) < 1e-9


def test_weights_from_snapshot_accepts_explicit_hotkeys():
    mg = get_mock_metagraph(num_axons=5)
    mg.owner_hotkey = None
    mg.raw = None
    ws = WeightSetter(mg, telemetry_service=Mock(spec=TelemetryService))
    weights = ws.weights_from_snapshot(
        _excess_snapshot(),
        hotkeys=["hk1", "hk0"],
        stakes=[1.0, 1.0],
    )
    assert weights is not None
    assert len(weights) == 2
    assert abs(weights[0] - 0.2) < 1e-9
    assert abs(weights[1] - 0.8) < 1e-9
