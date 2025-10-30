# Quantum Compute Miner

The miner node provides gate‑based quantum compute capacity to the platform. Miners connect to real OpenQASM 2.0/3.0 gate‑model quantum computers, receive circuit jobs from validators, execute them on the target device, and return results.


Because real QPU access is required (see [README.md](../../README.md) for details). You must be a direct operator or have a formal documented partnership with a provider. If you meet these requirements please contact us at support@openquantum.com.

## Core Responsibilities

The miner performs several key functions:

### Job Ingestion

Miners receive execution requests containing references to quantum circuits (e.g., OpenQASM). The miner downloads input data, and runs the job on a real quantum device through its provider adapter.

### QPU Execution

Using a provider adapter, the miner submits circuits to a target QPU, polls for progress, and manages cancellations. The adapter abstracts each provider’s API.

### Status & Telemetry

The miner reports identity, capabilities, availability, queue depth, and pricing to the job server. 

### Result Finalization

When a job completes, the miner uploads results (counts, bitstrings, metadata, timestamps) and keeps completion records that validators can collect.

### Error Handling

Provider and network errors are captured and forwarded to the job server. Jobs are marked failed or cancelled as appropriate.

## Get Started

### Hardware Requirements

Recommended for Miners:
- 2 vcpu
- 100gb storage
- Reliable network egress to your QPU provider


### 1. Install Python 3.11 or above

```bash
python3 --version
```

### 2. Create and Activate Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Bittensor

```bash
pip install --upgrade bittensor
pip install bittensor-cli
```

### 4. Register Your Wallet

Register on subnet 48:

```bash
btcli subnet register --wallet.name <wallet_name> --wallet.hotkey <hotkey_name> --netuid 48
```

### 5. Clone and Install the Repository

```bash
git clone https://github.com/qbittensor-labs/quantum-compute.git
cd quantum-compute
pip install -e .
```

### 6. Install PM2 (optional but recommended)

```bash
npm install -g pm2
```

### 8. Start Miner

```bash
pm2 start --name your_miner_name \
  python neurons/miner.py \
  --wallet.name <wallet_name> \
  --wallet.hotkey <hotkey_name> \
  --netuid 48 \
  --subtensor.network finney \
  --logging.trace
```

## Implement a Provider Adapter

Miners must integrate a provider adapter to bridge the miner runtime with a specific QPU provider or an on‑prem device.

- Location: `qbittensor/miner/providers/`
- Protocol: `ProviderAdapter` (see `base.py`)

Your adapter must implement the following methods:

- list_devices() → List[Device]
- list_capabilities() → List[Capability]
- get_capability(device_id: Optional[str]) → Optional[Capability]
- submit(circuit_data: str, device_id: Optional[str], shots: Optional[int]) → JobHandle
- poll(handle: JobHandle) → BaseExecutionStatus
- cancel(handle: JobHandle) → None
- get_job_receipt(handle: JobHandle) → JobReceipt
- get_availability(device_id: Optional[str]) → Optional[AvailabilityStatus]
- get_pricing(device_id: Optional[str]) → Optional[Dict[str, float]]

### Register Your Adapter

Add your adapter to the factory in `qbittensor/miner/providers/registry.py`:
- Map a unique key (e.g., `"my_qpu`) to a zero‑arg factory that returns your adapter instance.
- Select it via `export PROVIDER=<your_key>`.

### Adapter Responsibilities in Practice

- Share status: implement `get_availability()` and `get_pricing()`; the miner runtime collects and forwards this periodically.
- Run jobs: implement `submit()` to create a provider job and return a `JobHandle`.
- Send results: implement `get_job_receipt()` returning counts/bitstrings, timestamps, cost, and metadata when jobs complete.
- Queues: your availability should accurately reflect queue depth/position if available; the runtime also applies local back‑pressure via `MINER_MAX_INFLIGHT`.
- Capabilities: return accurate `Capability` values (qubits, native gates) and keep them stable per device_id.

