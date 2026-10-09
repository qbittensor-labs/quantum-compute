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

import pytest

from qbittensor.miner.providers.base import ProviderAdapter, JobHandle, BaseExecutionStatus, JobReceipt
from qbittensor.miner.providers.mock import MockProviderAdapter
from qbittensor.miner.providers.openquantum.adapter import OpenQuantumAdapter
from qbittensor.miner.providers.openquantum.config import OpenQuantumConfig


def _openquantum_dry():
    return OpenQuantumAdapter(
        config=OpenQuantumConfig(
            access_token=None,
            organization_id=None,
            scheduler_url="http://scheduler",
            management_url="http://management",
            dry_run=True,
            min_credits=100.0,
            queue_priority_id="prio",
            execution_plan_id="plan",
            subcategory_id="oth:oth",
            http_timeout_s=5,
        )
    )


@pytest.mark.parametrize("adapter_factory", [MockProviderAdapter, _openquantum_dry])
def test_provider_contract_basic(adapter_factory):
    adapter: ProviderAdapter = adapter_factory()
    devices = adapter.list_devices()
    assert len(devices) >= 1
    caps = adapter.list_capabilities()
    assert len(caps) >= 1
    cap = adapter.get_capability(devices[0].device_id)
    assert cap is not None

    handle = adapter.submit("OPENQASM 2.0; // test", device_id=devices[0].device_id, shots=10)
    assert isinstance(handle, JobHandle)
    status = adapter.poll(handle)
    assert isinstance(status, BaseExecutionStatus)
    receipt = adapter.get_job_receipt(handle)
    assert isinstance(receipt, JobReceipt)
    price = adapter.get_pricing(devices[0].device_id)
    assert isinstance(price, dict) and set(price.keys()) & {"perTask", "perShot", "perMinute"}
