# Miner FAQ

Checks for a miner that is running and not receiving work. Setup is in the [miner guide](README.md).

Validators query every reachable miner on a regular cadence. A query is not a job. A job is a circuit the miner downloads and submits to Open Quantum.

## Why am I not getting jobs?

Work through these in order. Stop at the first one that fails.

### 1. Validators cannot reach the axon

The process has to be registered on netuid 48 and serving. Validators dial the address published on the chain.

- `--axon.external_ip` is the public address validators dial. If you omit it, the published address is often a private IP, and validators cannot connect.
- `--axon.ip` is the address this process binds. The port defaults to 8091. That port has to accept inbound connections.
- An address of `0.0.0.0` or a port of `0` is ignored.
- After you start, or after you change IP or port, the chain record can take about 20 minutes to update. Validators use that record.
- Two missed answers cause that validator to skip new work for about 45 to 75 minutes. The skip clears after a successful answer.

With `--logging.info`, a reachable miner prints `Accepted hotkey` when a validator connects. No such line means validators are not reaching you.

Run one hotkey in one process. A second process on the same hotkey looks like a miner that sometimes fails to answer.

### 2. Stake is under 5,000 alpha

Validators assign new jobs to hotkeys with at least 5,000 alpha staked. Below that floor they still query you, and they do not assign new work.

Above the floor, a larger stake receives more of the jobs. Meeting the floor does not reserve a share of every job.

### 3. The provider account cannot pay for a job

The organization on `OPENQUANTUM_ORGANIZATION_ID` pays for each circuit. Startup requires that id and either an SDK key (`OPENQUANTUM_CLIENT_ID` and `OPENQUANTUM_CLIENT_SECRET`) or `OPENQUANTUM_ACCESS_TOKEN`.

If the balance is under `OPENQUANTUM_MIN_CREDITS` (default 50), the miner refuses new work until the balance is restored. Add credits and leave the process running. Validators pick that up on a later query.

`OPENQUANTUM_DRY_RUN` must be unset or `0`. A dry run does not produce a certificate, and a job without a certificate does not complete.

### 4. This validator is skipping you

A validator skips a miner for 24 hours after either of these:

- The result had no certificate, the certificate did not match the job, or the same certificate proof was reused on a different job.
- The miner held a job and stopped answering for about 45 minutes.

The skip is local to that validator. Other validators learn it only when they see the same failure. Stay up for the whole job. A process that exits and comes back keeps polling a job it already submitted.

## What does the certificate do?

You do not create or install a certificate. Open Quantum runs the circuit. Its certificate authority signs a proof of that run: the circuit, the result, the shot count, and the backend class.

The miner returns that proof with the same result bytes. Validators check the proof before the job counts. A result with no proof, a proof for a different circuit or result, or a proof already used on another job is rejected.

Leave the circuit, the shot count, and the backend class as the validator sent them.

## I connected, and then nothing happened

`Accepted hotkey` means a validator reached the axon. It does not mean a job was assigned.

A real assignment is followed by a circuit download and a submit to Open Quantum. Submit failures are easier to see with `--logging.debug`. Return to `--logging.info` after the check. Useful lines:

- `Provider requested per-request rate limit` means the balance is under the credit floor.
- `Submit failed` or `Provider submit failed` means Open Quantum refused the circuit. The organization may be out of credits, or it may already have as many jobs in flight as the provider allows.
- `has no completion proof` means the provider finished a job and did not return a certificate in time. That result cannot complete.

## The miner was working and then went quiet

Check the same list again.

- The credit balance fell under the floor.
- The public address or port changed and the chain record is stale.
- A validator skipped the hotkey for 24 hours.
- Two missed answers started a 45 to 75 minute skip.
- The queue for your classes is empty.

An encrypted wallet needs `BT_WALLET_PASSWORD`. Without it the process does not stay up.
