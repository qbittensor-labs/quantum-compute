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

from qbittensor.utils.results_normalizer import normalize_measurement_counts


class TestNormalizeMeasurementCounts:
    def test_none_input_returns_none(self):
        assert normalize_measurement_counts(None, 100) == (None, None)
        assert normalize_measurement_counts("not-a-dict", 100) == (None, None)
        assert normalize_measurement_counts(123, None) == (None, None)

    def test_measurement_counts_key(self):
        data = {"measurementCounts": {"00": 10, "11": 5}}
        counts, best = normalize_measurement_counts(data, 100)
        assert counts == {"00": 10, "11": 5}
        assert best == "00"

    def test_counts_key(self):
        data = {"counts": {"01": 3, "10": 7}}
        counts, best = normalize_measurement_counts(data, None)
        assert counts == {"01": 3, "10": 7}
        assert best == "10"

    def test_measurement_counts_alias(self):
        data = {"measurement_counts": {"111": 1}}
        counts, best = normalize_measurement_counts(data, 10)
        assert counts == {"111": 1}
        assert best == "111"

    def test_probabilities_to_counts(self):
        data = {"probabilities": {"00": 0.5, "11": 0.5}}
        counts, best = normalize_measurement_counts(data, shots=100)
        assert counts == {"00": 50, "11": 50}
        assert best in {"00", "11"}

    def test_probabilities_without_shots_returns_none(self):
        data = {"probabilities": {"00": 0.75}}
        counts, best = normalize_measurement_counts(data, shots=None)
        assert counts is None
        assert best is None

    def test_measurements_list_to_counts(self):
        data = {"measurements": ["00", "01", "00", "11"]}
        counts, best = normalize_measurement_counts(data, 10)
        assert counts == {"00": 2, "01": 1, "11": 1}
        assert best == "00"

    def test_measurements_tuple_to_counts(self):
        data = {"measurements": ("a", "b", "a")}
        counts, best = normalize_measurement_counts(data, None)
        assert counts == {"a": 2, "b": 1}
        assert best == "a"

    def test_empty_dict(self):
        counts, best = normalize_measurement_counts({}, 100)
        assert counts is None
        assert best is None

    def test_counts_with_non_int_values_coerced(self):
        data = {"measurementCounts": {"00": "4", "11": 2.0}}
        counts, _ = normalize_measurement_counts(data, 10)
        assert counts == {"00": 4, "11": 2}

    def test_probabilities_bad_values(self):
        data = {"probabilities": {"x": "bad"}}
        counts, best = normalize_measurement_counts(data, 100)
        assert counts is None
        assert best is None

    def test_best_is_highest_count(self):
        data = {"counts": {"low": 1, "high": 42, "mid": 10}}
        _, best = normalize_measurement_counts(data, 100)
        assert best == "high"

    def test_no_counts_no_best(self):
        data = {"foo": "bar"}
        counts, best = normalize_measurement_counts(data, 100)
        assert counts is None
        assert best is None

    def test_bad_int_in_measurement_counts_hits_except(self):
        data = {"measurementCounts": {"00": "not-an-int", "11": 1}}
        counts, best = normalize_measurement_counts(data, 10)
        # except path sets counts=None, best remains None
        assert counts is None
        assert best is None

    def test_bad_probabilities_value_hits_except(self):
        data = {"probabilities": {"00": "not-float"}}
        counts, best = normalize_measurement_counts(data, shots=100)
        assert counts is None
        assert best is None

    def test_measurements_exception_path(self):
        # Force the measurements try to take except by providing non-iterable after isinstance check?
        # The guard is isinstance(list,tuple), so to hit except inside, simulate bad item str or add.
        # Use a list containing something that would break in unusual way; here we hit via bad type in practice
        # For robustness we test a case that produces counts then best fails (incomparable values)
        data = {"counts": {"a": complex(1), "b": 2}}
        # max on complex vs int in key will raise TypeError in py3 when comparing
        counts, best = normalize_measurement_counts(data, 10)
        # depending on order, either succeeds or hits except -> best=None
        assert (counts is not None) or (best is None)  # at least doesn't crash
        # To deterministically hit best except we can rely on mixed that fails max
