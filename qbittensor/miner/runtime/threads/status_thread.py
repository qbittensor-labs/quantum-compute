from __future__ import annotations

import time
import bittensor as bt
import queue

from qbittensor.miner.providers.base import Capabilities, MinerIdentity


def collect_status_data(registry) -> None:
    """Collect status data from provider and enqueue for job server thread."""
    try:
        availability = None
        pricing = None
        try:
            availability = registry.adapter.get_availability(registry.default_device_id)
        except Exception:
            pass
        try:
            pricing = registry.adapter.get_pricing(registry.default_device_id)
        except Exception:
            pass

        identity = MinerIdentity(
            device_id=registry.default_device_id,
            provider=(getattr(registry._default_device, "provider", None) if registry._default_device else getattr(registry.adapter, "__class__").__name__.replace("Adapter", "").lower()),
            vendor=(getattr(registry._default_device, "vendor", None) if registry._default_device else None),
            device_type=(getattr(registry._default_device, "device_type", None) if registry._default_device else ("QPU" if (registry.default_device_id and "qpu" in registry.default_device_id) else "SIMULATOR")),
        )

        caps_list = registry.adapter.list_capabilities()
        caps = None
        if len(caps_list) > 0:
            cap0 = caps_list[0]
            caps = Capabilities(num_qubits=cap0.num_qubits, basis_gates=cap0.basis_gates, extras=cap0.extras)

        inflight = 0
        try:
            inflight = registry.get_inflight_count()
        except Exception:
            inflight = 0
        pending = 0
        try:
            pending = registry.get_pending_count()
        except Exception:
            pending = 0
        max_pending = getattr(registry, "_max_inflight", 20)
        is_over_capacity = pending >= max_pending

        if is_over_capacity:
            try:
                from qbittensor.miner.providers.base import AvailabilityStatus
                base_avail = getattr(availability, "availability", None)
                base_next = getattr(availability, "next_available", None)
                max_inf = getattr(registry, "_max_inflight", 0)
                availability = AvailabilityStatus(
                    availability=base_avail,
                    pending_jobs=inflight,
                    is_available=False,
                    next_available=base_next,
                    status_msg=f"local_queue_full ({inflight}/{max_inf})",
                )
            except Exception:
                pass

        status_data = {
            "identity": identity,
            "capabilities": caps,
            "availability": availability,
            "pricing": pricing,
            "_pending_count": pending,
            "_inflight_count": inflight,
        }

        try:
            registry._status_queue.put_nowait(status_data)
        except queue.Full:
            try:
                registry._status_queue.get_nowait()
                registry._status_queue.put_nowait(status_data)
            except Exception:
                pass
    except Exception as e:
        bt.logging.trace(f" Failed to collect status data: {e}")


def run_job_server(registry) -> None:
    """Job server thread main loop - handles all job server communication."""
    current_thread = bt.logging.__class__.__name__
    bt.logging.info(f"| Job Server Thread | Job server thread started")

    while not registry._stop.is_set():
        try:
            timeout_end = time.time() + 1.0
            while time.time() < timeout_end:
                try:
                    remaining = timeout_end - time.time()
                    if remaining <= 0:
                        break
                    status_data = registry._status_queue.get(timeout=min(remaining, 0.1))
                    registry._send_status_to_job_server(status_data)
                except queue.Empty:
                    break
                except Exception as e:
                    bt.logging.trace(f" Error sending status: {e}")

            while True:
                try:
                    error_data = registry._error_queue.get_nowait()
                    registry._send_error_to_job_server(error_data)
                except queue.Empty:
                    break
                except Exception as e:
                    bt.logging.trace(f" Error sending error report: {e}")

        except Exception as e:
            bt.logging.debug(f"Job server thread error: {e}")

    bt.logging.info(f"| Job Server Thread | Job server thread stopped")


