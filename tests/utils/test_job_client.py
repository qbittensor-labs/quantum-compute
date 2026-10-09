# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

from unittest.mock import Mock

from qbittensor.protocol import COLLECT_SYNAPSE_ID
from qbittensor.utils.services.job import JobClient


def _client_with_rm(rm) -> JobClient:
    client = JobClient.__new__(JobClient)
    client.request_manager = rm
    client.ca_base_url = "http://ca.test"
    return client


def test_get_execution_for_classes_builds_query():
    rm = Mock()
    resp = Mock()
    resp.status_code = 204
    rm.get.return_value = resp
    client = _client_with_rm(rm)

    result = client.get_execution_for_classes(
        ["quantumrings:qasm3", "ionq:forte-1"],
        actor_id="5abc",
    )

    rm.get.assert_called_once()
    args, kwargs = rm.get.call_args
    assert args[0] == "executions"
    params = kwargs.get("params") or (args[1] if len(args) > 1 else {})
    assert params["backend_classes"] == "quantumrings:qasm3,ionq:forte-1"
    assert params["actor_id"] == "5abc"
    assert result["execution_id"] == COLLECT_SYNAPSE_ID


def test_get_execution_for_classes_parses_200():
    rm = Mock()
    resp = Mock()
    resp.status_code = 200
    resp.json.return_value = {
        "execution_id": "exec-1",
        "backend_class": "quantumrings:qasm3",
        "shots": 10,
    }
    rm.get.return_value = resp
    client = _client_with_rm(rm)
    result = client.get_execution_for_classes(["quantumrings:qasm3"])
    assert result["execution_id"] == "exec-1"
    assert result["backend_class"] == "quantumrings:qasm3"


def test_report_spark_posts_classes():
    rm = Mock()
    client = _client_with_rm(rm)
    client.report_spark(["quantumrings:qasm3", "ionq:forte-1"])
    rm.post.assert_called_once()
    args, kwargs = rm.post.call_args
    assert args[0] == "spark/report"
    assert kwargs.get("json") == {"classes": ["quantumrings:qasm3", "ionq:forte-1"]}


def test_patch_execution_raises_on_400():
    rm = Mock()
    resp = Mock()
    resp.status_code = 400
    resp.text = '{"message":["status must be one of the following values: Pending, Queued, Running, Completed, Failed"]}'
    rm.patch.return_value = resp
    client = _client_with_rm(rm)
    from qbittensor.utils.services.exceptions import JobApiError
    try:
        client.patch_execution("exec-1", {"status": "ExecutionStatus.COMPLETED"})
        raise AssertionError("expected JobApiError")
    except JobApiError as err:
        assert err.status_code == 400
        text = str(err)
        assert "status=400" in text
        assert "status must be one of the following values" in text


def test_patch_backend_ignores_404_and_403():
    rm = Mock()
    client = _client_with_rm(rm)
    client.patch_backend({"accepting_jobs": True})
    rm.patch.assert_called_once()
    _, kwargs = rm.patch.call_args
    assert kwargs.get("ignore_codes") == [404, 403]
