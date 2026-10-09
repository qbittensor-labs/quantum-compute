# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

"""
Central constants for Quantum Compute (SN 48).

Shared magic values, defaults, and identifiers used across the miner,
validator, protocol, and utilities. This replaces scattered definitions.
"""

from datetime import timedelta

# Subnet identifier (used for auth, logging, etc.)
NETUID: int = 48

# Special synapse ID used when validator only wants to collect existing
# miner results without sending new work.
COLLECT_SYNAPSE_ID: str = "_collect_only"

# Sentinel timestamp representing "beginning of time" for last-circuit tracking.
START_OF_TIME: str = "0000-00-00 00:00:00"

# How long (in days) to retain completed circuit execution records in the
# miner's local DB before pruning.
COMPLETED_CIRCUIT_TTL: int = 14

# How long (in days) to retain validator execution_metrics rows, measured
# from time_sent. A hotkey that stays registered is otherwise never trimmed.
EXECUTION_METRICS_TTL_DAYS: int = 90

# Common timestamp format used for DB fields and protocol values.
# Must be lexicographically sortable for correct "most recent" logic.
TIMESTAMP_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# Miner runtime intervals
STATUS_UPDATE_INTERVAL_S: int = 30
JOB_POLL_INTERVAL_S: float = 30.0
LOCK_TIMEOUT_S: float = 5.0

# Validator timing
TIMER_COUNTDOWN: timedelta = timedelta(hours=1)
