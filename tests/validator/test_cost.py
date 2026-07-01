import pytest
from unittest.mock import Mock, patch
from datetime import timedelta

from qbittensor.validator.reward.cost import CostConfirmation
from qbittensor.utils.request.RequestManager import RequestManager
from tests.test_utils import get_mock_keypair


@pytest.fixture
def mock_rm(monkeypatch):
    kp = get_mock_keypair()
    rm = RequestManager(kp)
    # global jwt patch from conftest
    return rm


def test_cost_confirmation_init(mock_rm):
    db = Mock()
    cc = CostConfirmation(db, mock_rm)
    assert cc.timer is not None
    assert cc.timer._timeout == timedelta(minutes=30)


def test_get_rows_queries_db(mock_rm):
    db = Mock()
    db.query.return_value = [("hk1", "exec1")]
    cc = CostConfirmation(db, mock_rm)
    rows = cc._get_rows()
    assert rows == [("hk1", "exec1")]
    db.query.assert_called()


@patch("qbittensor.validator.reward.cost.RequestManager")
def test_handle_cost_response_updates_on_200(mock_rm_cls, mock_rm):
    db = Mock()
    cc = CostConfirmation(db, mock_rm)
    resp = Mock(status_code=200)
    resp.json.return_value = {"cost": 42}
    with patch.object(cc, "_update_cost_in_db") as mock_upd:
        cc._handle_cost_response(resp, "hk", "e1")
        mock_upd.assert_called_once_with("hk", "e1", 42)


def test_handle_cost_response_drops_on_404(mock_rm):
    db = Mock()
    cc = CostConfirmation(db, mock_rm)
    resp = Mock(status_code=404)
    with patch.object(cc, "_drop_row") as mock_drop:
        cc._handle_cost_response(resp, "hk", "e1")
        mock_drop.assert_called_once_with("hk", "e1")
