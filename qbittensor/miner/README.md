# Miner (*_COMING SOON_*)

The miner (`neurons/miner.py`) receives circuit jobs from validators over Bittensor synapses, submits them through a provider adapter, uploads results, and returns status on a later validator query.

Implementation is under `qbittensor/miner/`.

## High-level operation

The miner:

- Serves an axon so validators can query it with `CircuitSynapse` requests.
- Downloads circuit input (e.g. QASM) and submits it through the configured provider adapter.
- Polls the provider for job progress, handles cancel/fail paths, and uploads results.
- Returns finished and in-flight execution metadata on subsequent validator queries.

## Local database

- **Path pattern**: `data/miner_<hotkey>.db` (directory overridden by `DATA_DIR` / `--neuron.data_dir`)
- Schema is applied via versioned migrations in `qbittensor/database/migrations/`.
- Used for in-flight and completed executions the runtime must track across restarts.

## Operational requirements

- Python **3.12+** and an editable install of this repo (`pip install -e .` from the root; pins **Bittensor SDK v11**).
- Network access to Open Quantum (jobs, scheduler, management, tensorauth, telemetry — see `qbittensor/utils/env.py`).
- A registered hotkey on **netuid 48**.
- At least **5000 alpha** staked on that hotkey. Validators query miners below the floor and assign new jobs only to miners at or above it. The floor is the validator setting `WEIGHT_MIN_MINER_STAKE_ALPHA` (default 5000).
- `PUBLIC_BACKEND_CLASSES` set to the classes this miner accepts. An empty list advertises nothing, and no jobs are placed.
- `--axon.external_ip` set to a public address validators can dial (see entry point below).
- `--axon.ip` set to the address this process binds. Miners on one machine share a port only when each binds a different address. The port defaults to 8091.
- 20 GB free on the data-directory disk for a neuron-ops install.
- `BT_WALLET_PASSWORD` when the wallet is encrypted.

## Provider adapter

Miners integrate a provider adapter under `qbittensor/miner/providers/`:

- Protocol: `ProviderAdapter` in `base.py`
- Register a factory key in `qbittensor/miner/providers/registry.py`
- Select it with `export PROVIDER=<your_key>`

Required surface:

- `list_devices()`, `list_capabilities()`, `get_capability(device_id)`
- `submit(...)`, `poll(...)`, `cancel(...)`, `get_job_receipt(...)`
- `get_availability(...)`, `get_pricing(...)`

`MINER_MAX_INFLIGHT` (default 1000) caps how many pending jobs count as locally available. It does not rate-limit the synapse.

### Open Quantum (`PROVIDER=openquantum`)

Submits each accepted circuit to Open Quantum on the class the validator sent. The organization on `OPENQUANTUM_ORGANIZATION_ID` pays for the job.

Provider status is stored locally and returned on the next validator query.

If the organization balance is below `OPENQUANTUM_MIN_CREDITS` (default 50), the miner rate-limits new synapses.

```bash
export PROVIDER=openquantum
export OPENQUANTUM_ORGANIZATION_ID=<uuid>
export OPENQUANTUM_CLIENT_ID=<sdk key id>
export OPENQUANTUM_CLIENT_SECRET=<sdk key secret>
export PUBLIC_BACKEND_CLASSES=<classes this miner accepts>
export OPENQUANTUM_MIN_CREDITS=50
export OPENQUANTUM_SCHEDULER_URL=https://scheduler.openquantum.com
export OPENQUANTUM_MANAGEMENT_URL=https://management.openquantum.com
```

Pack file: `miner.pack.yaml`.

## Entry point

```bash
python neurons/miner.py \
  --netuid 48 \
  --subtensor.network finney \
  --logging.info \
  --wallet.name <your_wallet_name> \
  --wallet.hotkey <your_hotkey> \
  --axon.external_ip <PUBLIC_IP>
```

(Use your usual Bittensor config flags / wallet as for any subnet miner.)

**SDK v11 notes:**

- Set `--axon.external_ip` to the public address validators dial. If it is omitted, ServeAxon publishes the outbound interface address, which is often a private IP.
- Network defaults to `finney`. Override with `--subtensor.network` (`test` or `local`) or a `ws(s)://` URL via `--subtensor.chain_endpoint`.
