# Quantum Compute Validator

## Core Responsibilities

The validator performs several key functions:

### Job Distribution

The validator continuously fetches quantum computing requests from OpenQuantum users. These requests contain quantum circuits (programs) that need to be executed. The validator then intelligently distributes these jobs to registered miners in the network.

### Miner Coordination

As miners join and leave the network, the validator keeps track of who's active and available. It maintains a database of registered miners and manages communication with them through a query-response system. When a job is ready, the validator selects an appropriate miner and sends them the work.

### Quality Assurance

When miners complete their quantum computing tasks, they send results back to the validator. The validator checks these responses to ensure they're valid and complete. It tracks metrics like execution time and success rates to understand how well each miner is performing.

### Result Handling

Once a miner successfully completes a job, the validator collects the results and forwards them back to the job server. If a job fails or a miner doesn't respond, the validator marks it for retry and handles the error gracefully.

## Get Started

### Hardware Requirements

**Recommended for Validators:**
- 2 vcpu 
- 80gb storage

## Setup Steps

### 1. Install Python 3.11 or above

Ensure you have Python 3.11 installed on your system. You can check your Python version with:
```bash
python3 --version
```

### 2. Create and Activate Virtual Environment

Create a new Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Bittensor

Install the latest version of Bittensor:
```bash
pip install --upgrade bittensor
pip install bittensor-cli # If you don't already have it
```

### 4. Register Your Wallet

You'll need to register your wallet on subnet 48:

```bash
# Register on subnet 48
btcli subnet register --wallet.name <wallet_name> --wallet.hotkey <hotkey_name> --netuid 48
```

### 5. Clone and Install the Repository

```bash
git clone https://github.com/qbittensor-labs/quantum-compute.git
cd quantum-compute
```

### 6. Install Requirements

Install all required dependencies:
```bash
pip install -r requirements.txt
pip install -e .
```

### 7. Install PM2 (if not already installed)

```bash
npm install -g pm2
```

### 8. Start validator

```bash
pm2 start --name your_process_name_here \
  python neurons/validator.py \
  --wallet.name <wallet_name> \
  --wallet.hotkey <hotkey_name> \
  --netuid 48 \
  --subtensor.network finney \
  --logging.trace
```