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

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def normalize_measurement_counts(results: Optional[Dict[str, Any]],
                                 shots: Optional[int]) -> Tuple[Optional[Dict[str, int]], Optional[str]]:
    """Normalize provider result payloads into a measurementCounts dict and best bitstring.

    Accepts various shapes:
    - {"measurementCounts": {"00": 10, "11": 5}}
    - {"counts": {"00": 10, "11": 5}} (alternate key)
    - {"probabilities": {"00": 0.5, "11": 0.5}} (convert to counts if shots provided)
    - {"measurements": ["00", "11", ...]} (collapse to counts)

    Returns a tuple: (counts_dict_or_none, best_bitstring_or_none)
    """
    if not isinstance(results, dict):
        return None, None

    counts = None
    for key in ("measurementCounts", "counts", "measurement_counts"):
        if isinstance(results.get(key), dict):
            try:
                counts = {str(k): int(v) for k, v in results[key].items()}
                break
            except Exception:
                counts = None
                break

    if counts is None and isinstance(results.get("probabilities"), dict) and shots is not None and shots > 0:
        try:
            probs = {str(k): float(v) for k, v in results["probabilities"].items()}
            counts = {k: max(0, int(round(p * shots))) for k, p in probs.items()}
        except Exception:
            counts = None

    if counts is None and isinstance(results.get("measurements"), (list, tuple)):
        try:
            measurements = [str(x) for x in results["measurements"]]
            tmp: Dict[str, int] = {}
            for m in measurements:
                tmp[m] = tmp.get(m, 0) + 1
            counts = tmp
        except Exception:
            counts = None

    best = None
    if isinstance(counts, dict) and counts:
        try:
            best = max(counts.items(), key=lambda kv: kv[1])[0]
        except Exception:
            best = None

    return counts, best
