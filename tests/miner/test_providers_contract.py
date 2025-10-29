import pytest

from qbittensor.miner.providers.base import ProviderAdapter, JobHandle, BaseExecutionStatus, JobReceipt
from qbittensor.miner.providers.mock import MockProviderAdapter


@pytest.mark.parametrize("adapter_cls", [MockProviderAdapter])
def test_provider_contract_basic(adapter_cls):
    adapter: ProviderAdapter = adapter_cls()
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


