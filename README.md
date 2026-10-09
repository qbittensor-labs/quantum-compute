<div align="center">

<img src="./logo.png"/>

# **Quantum Compute** (SN 48) <!-- omit in toc -->
[![Discord Chat](https://img.shields.io/discord/1395424987816661103)](https://discord.gg/xJ9JKPMJQD)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

[Discord](https://discord.gg/xJ9JKPMJQD) • [Network](https://taostats.io/subnets/48) • [Website](https://www.qbittensorlabs.com/quantum) • [GitHub](https://github.com/qbittensor-labs/quantum-compute)

</div>

---

# Quantum Compute (Bittensor Subnet 48)

Miners run gate-based quantum circuits. Validators query miners and set on-chain weights for completed work.

Miner setup *_COMING SOON_*: [qbittensor/miner/README.md](qbittensor/miner/README.md)

## Validator setup

For complete validator operator instructions (high-level operation, local database, requirements, entry point) see the dedicated guide:

**→ [qbittensor/validator/README.md](qbittensor/validator/README.md)**

### Quick launch

```bash
git clone https://github.com/qbittensor-labs/quantum-compute.git
cd quantum-compute
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .

python neurons/validator.py \
  --netuid 48 \
  --subtensor.network finney \
  --logging.info \
  --wallet.name <your_wallet_name> \
  --wallet.hotkey <your_hotkey> \
  --neuron.axon_off
```

## Miner setup

See the dedicated miner operator guide:

**→ [qbittensor/miner/README.md](qbittensor/miner/README.md)**

## Development

For contributor setup, testing, and linting (including the required `pip install -e .` step and `pip install -r requirements-dev.txt`), see [CONTRIBUTING.md](CONTRIBUTING.md).

