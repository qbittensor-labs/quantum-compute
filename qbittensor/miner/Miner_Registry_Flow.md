## Miner side flows

- `neurons/miner.py`
  - Submits new jobs to the background registry (`JobRegistry`).

- `qbittensor/miner/runtime/job_registry.py`
  - Background poller that tracks submitted jobs, polls provider status, and persists completions.
  - Writes to `completed_circuits` and full receipts to `completed_jobs`.

- `qbittensor/miner/providers/`
  - Provider adapter interface (`base.py`) and implementations (e.g., `mock.py`).
  - Registry (`registry.py`) resolves an adapter by name via `PROVIDER` env.

- `qbittensor/miner/miner_table_initializer.py`
  - Creates miner tables: `completed_circuits`, `completed_jobs` (+ indexes).

1. Validator calls miner
2. Miner:
   - Loads completed jobs newer than `last_circuit` and appends to `synapse.completed_jobs`.
   - Drops old rows older than a TTL.
   - If the job is new (as in not ran yet), submits to provider with `JobRegistry.submit`.
   - fills `synapse.miner_status` with identity and qpu capabilities.
3. `JobRegistry`:
   - Polls provider for each submitted job
   - completion:
     - `completed_circuits(execution_id, shots, validator_hotkey, solution_bitstring, timestamp)`
     - `completed_jobs(...)` full provider receipt (timestamps, results, metadata).
4. Next validator request has `last_circuit` so the miner returns only new completions.

### Switching miner providers
- Set `PROVIDER` to select the adapter:
  - `export PROVIDER=mock` (currently mock)
  - Future adapters (e.g., `aws,inq,qbraid,riggeti`) should be added under `qbittensor/miner/providers/` and registered in `registry.py`.
- The miner will automatically use the selected adapter and route jobs accordingly.

### How to add a new provider adapter
1. Make `ProviderAdapter` methods in a new file (e.g., `providers/ibm.py`):
   - `list_devices`, `list_capabilities`, `submit`, `poll`, `cancel`, `get_job_receipt`.
   - Map provider statuses to: `QUEUED | RUNNING | COMPLETED | FAILED | CANCELLED`.
   - Include measurement counts in `JobReceipt.results["measurementCounts"]` 
2. Register the adapter in `providers/registry.py` and select with `PROVIDER=<name>`.
