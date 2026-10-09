# Validator

The validator (`neurons/validator.py`) **fetches quantum compute jobs** from the Open Quantum platform, **queries miners** over Bittensor synapses, **collects results**, and **sets weights** from the epoch snapshot.

For implementation details (miner selection, synapse handling, scoring, weight setting, etc.), see the source under `qbittensor/validator/`.

## High-level operation

The validator periodically:

- Pulls work from the job / platform APIs (authenticated with the validator hotkey).
- Selects the next eligible miner and sends a `CircuitSynapse` query.
- Collects finished executions from miners and records metrics.
- Sets on-chain weights from the computed scores.

Full details live in the code under `qbittensor/validator/`.

## Local database

- **Path pattern**: `data/validator_<hotkey>.db` (directory overridden by `DATA_DIR` / `--neuron.data_dir`)
- Schema is applied via versioned migrations in `qbittensor/database/migrations/`.
- Used for miner tracking, execution metrics, the collect watermark (`last_circuit`), in-flight executions, `miner_capabilities`, and `miner_ban`. Weights are not stored locally.

## Operational requirements

- Python **3.12+** and an editable install of this repo (`pip install -e .` from the root; pins **Bittensor SDK v11**).
- Network access to Open Quantum APIs (job / tensorauth / telemetry — see `qbittensor/utils/env.py`).
- A registered hotkey on **netuid 48**.
- Modest host resources (CPU/disk); no GPU required for the current quantum-compute validator path.

v1.0 -> v2.0 Upgrade Guide: [UPGRADE.md](UPGRADE.md).

## Entry point

```bash
python neurons/validator.py \
  --netuid 48 \
  --subtensor.network finney \
  --logging.info \
  --wallet.name <your_wallet_name> \
  --wallet.hotkey <your_hotkey> \
  --neuron.axon_off
```

(Use your usual Bittensor config flags / wallet as for any subnet validator.)

**SDK v11 notes:**

- Network defaults to `finney`. Override with `--subtensor.network` (`test` or `local`) or a `ws(s)://` URL via `--subtensor.chain_endpoint`.
- `--neuron.axon_off` keeps the validator from publishing an axon. Miners set `--axon.external_ip` to the public address validators dial.
