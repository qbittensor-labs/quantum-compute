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

> **Coming soon — open mining.** Open mining is live on mainnet in a short validation period while we test the code end to end. Official miner onboarding opens shortly (within the next week). To be first in line, join the [Discord](https://discord.gg/xJ9JKPMJQD).

## Introduction

The Quantum Compute subnet is unlike any other subnet on Bittensor. It taps into Bittensor's decentralized incentive mechanism to make one of the world's most powerful, scarce, and most expensive resources—quantum computers—available to users from all walks of life, who might otherwise not have access to them. For those who might have had access, they would not experiment freely due to prohibitive costs and limited availability. Now they can.

## Why Is This Important?

Quantum computing holds the promise to fundamentally transform the world. Many of humanity's biggest problems are currently bound by the limits of classical computational power; quantum computing holds the promise to meaningfully impact them, if not to outright solve them.

While amazing progress has been made in the production of quantum computers in recent years, the advancement of algorithms and the applications of known algorithms is much slower. This is because quantum computers are:

- **Expensive:** Costing between $5,000-$15,000/hr
- **High Error Rate:** It's not uncommon for error rates to be above 0.1% per operation for single-qubit operations and above 1% per operation for two-qubit operations.
- **Scarce:** The total number of computational qubits on Earth is in the tens of thousands, and the number of systems is fewer than 100. For the systems that are accessible, users have to wait hours or days to access them.

Leveraging Bittensor's innovative incentive mechanisms, we are making quantum computing substantially more accessible to innovators from all walks of life. In many cases, it will be free.

We are doing this because we believe that inviting more brilliant minds to innovate will unlock game changing improvements by 1) applying known quantum algorithms to real world use cases, 2) making incremental and step function improvements to existing quantum algorithms, and 3) discovering new quantum algorithms that will unlock entirely new swaths of potential.

## Why Bittensor?

Bittensor is on a mission to transform the world by democratizing innovation through decentralized incentives for the entire universe of innovators, creating an equal playing field for all.

While Bittensor's brilliant strategy, incentive mechanisms, core technology, and innovative investors and supporters will be critical to the success of this subnet and to the delivery of this unparalleled value, the role of miners has evolved. In the first phase, miners were the elite few who could bring physical access to these scarce resources—quantum computers. With open mining, that changes: miners provide verifiable access to quantum compute through trusted quantum providers, and anyone with skin in the game can participate.

With this vision in mind, let's explore participation.

## Who Can Mine?

Anyone. With open mining, you no longer need to own or operate a physical quantum computer. Miners execute real user circuits through **trusted quantum providers**: quantum platforms certified by the [Open Quantum Certificate Authority](https://ca.openquantum.com/). Every result carries a cryptographic *proof of compute* signed by the provider, so validators can verify that each job genuinely ran on authorized quantum hardware without trusting the miner. Open Quantum is the first trusted provider on that list, and the list is open.

Two things are required to mine:

1. A registered hotkey on netuid 48 with at least **5,000 alpha** staked to it. Skin in the game is the admission ticket: work is dispatched in proportion to stake.
2. A funded account with a trusted quantum provider, to pay for the metered compute your miner executes.

For the full incentive mechanism (dispatch, verification, and weight setting), read the [open-mining whitepaper](https://www.qbittensorlabs.com/news/sn48-open-mining-whitepaper).

## How to Mine

Register a hotkey on netuid 48, stake at least 5,000 alpha to it, configure an account with a trusted quantum provider (Open Quantum is the first supported provider), and run the miner. The miner operator guide covers setup end to end:

**→ [qbittensor/miner/README.md](qbittensor/miner/README.md)**

If you own or operate a quantum computer and want to sell capacity into the network, or you run a quantum platform and want to join the trusted-provider list, contact support@openquantum.com.

## How Much Does It Cost?

At launch, Quantum Compute offers base-level quantum computing free of charge to end users. How long it remains free will depend very much on a number of factors, including, but not limited to: supply vs. demand, queue lengths, subnet alpha performance, use cases, etc.

While the basic computing is provided for free, OpenQuantum.com will also provide premium upgrades that can be paid for.

These include:

1. Priority Execution: Have a deadline? This paid feature lets you jump to the front of the line, to get your quantum job done next.

2. Increasing the Number of Shots: By default, a limited number of shots are provided for free. These shots vary by platform but are more limited than most users need for serious computing. Users can pay to increase the cap on the number of shots.

3. Private Execution: Users can also opt to execute jobs off-chain, in a completely private way. This passes the execution costs through to the end-user, but ensures that their quantum circuit and the results are both kept private and are not broadcast to our network of validators and miners, but instead is routed directly to and from the QPU.

## Data Transparency in the Free Tier

On the free tier, the circuit, the results, and the execution metadata are visible to the operators who run the job. By using that tier, users agree to that visibility.

While we will not be making any personal information public, we will also capture anonymous demographic data and associate it with the circuits.

This dataset will quickly become one of the most robust datasets available to answer questions about the market's adoption of quantum computing. What types of algorithms are the most popular? Which quantum computers perform the best? What are certain regions or demographics doing when compared to others? And more.

## What is Open Quantum?

While Bittensor is the engine for this vehicle, the association with crypto is not something that most of the quantum market is comfortable with. Open Quantum is our partner platform, built and operated by Quantum Rings (a company that focuses entirely on the traditional quantum computing market).

Open Quantum provides the two-sided marketplace presented to the market and will provide a very comfortable user experience that is removed from crypto. It will transact in USD.

In the initial rollout, Open Quantum will focus on providing the two-sided market with quantum users (researchers, students, corporates, enthusiasts, etc.) on one side and QPUs (quantum processing units) on the other.

In subsequent phases, Open Quantum will also become the go-to-market for the Quantum Challenges that will be presented by our sister subnet, Quantum Innovate (Subnet 63).

## Roadmap

Our roadmap outlines the evolution of Quantum Compute, starting with foundational enhancements and scaling to transformative capabilities. We categorize milestones into "Small" (near-term, quick wins) and "Bigger" (mid-to-long-term, ambitious expansions) phases.

### Small (Near-Term Milestones)

- **eCommerce to Buy Credits:** Introduce a seamless online store on OpenQuantum.com for users to purchase premium credits using fiat (USD) or crypto, enabling instant access to upgraded features without delays.
- **Wallet Linking + Earn Credits:** Allow users to connect crypto wallets to earn credits monthly by holding alpha in either SN 63 or SN48.
- **Native SDKs for Popular Quantum Frameworks:** Develop native SDKs for Qiskit, PennyLane, and Cirq, enabling seamless integration with existing quantum developer workflows.
- **Referral Program:** Allow users to earn credits by referring friends to the service.
- **OAuth for Partner Integration:** Enable secure, standardized authentication via OAuth to facilitate seamless integration with partner platforms, allowing quantum developers and organizations to embed our services effortlessly.

### Bigger (Mid-to-Long-Term Milestones)

- **Closed Loop HPC Simulation Endpoints:** Integrate select hosted HPC simulations that have end-to-end closed loop verification.
- **Native Onboarding for Quantum Developer Ecosystems:** Onboard Open Quantum as a native offering within leading quantum developer ecosystems, providing seamless, built-in access to decentralized quantum resources for developers worldwide.
- **Integration with Quantum Innovation Challenges (Subnet 63):** Directly integrate with Subnet 63 to market and launch innovation challenges, incentivizing top quantum experts to collaborate on solving the field's biggest problems and driving breakthrough advancements.
- **Proof of Compute + Decentralized HPC Simulation Endpoints:** Implement verifiable proof-of-compute protocols to ensure transparent, tamper-proof execution, alongside fully decentralized traditional miners for scalable HPC simulations across the Bittensor network.
- **Uber of Quantum Computing:** Evolve into a global, on-demand platform—the "Uber" for quantum resources—featuring real-time matching of users with available QPUs, dynamic pricing, and AI-driven optimization for instant quantum job dispatching.

Join us in revolutionizing quantum access—contact us today to get started.

## Incentive

On-chain weights pay miner hotkeys for verified, metered work. Every job carries a *proof of compute* signed by a trusted quantum provider, and every validator computes the same weights from the same shared snapshot. The full mechanism (dispatch, verification, and weight setting) is described in the [open-mining whitepaper](https://www.qbittensorlabs.com/news/sn48-open-mining-whitepaper).

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

