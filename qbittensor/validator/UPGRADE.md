# Validator v1.0 -> v2.0

Python 3.12 or newer.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

*_Note:_ You may need to use a new virtualenv if the python version was not 3.12 previously.*

Existing run command still works. Add `--neuron.axon_off`.

```bash
python neurons/validator.py \
  --netuid 48 \
  --subtensor.network finney \
  --wallet.name <wallet_name> \
  --wallet.hotkey <hotkey_name> \
  --logging.trace \
  --neuron.axon_off
```

Optional new flag: `--neuron.data_dir`.
