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

from neurons.miner import Miner


def test_miner_secure_blacklist_defaults_applied():
    """Test the secure defaults classmethod directly (no full neuron construction needed)."""
    import bittensor as bt

    # Fresh config without blacklist section
    cfg = bt.Config()
    cfg = Miner._apply_secure_blacklist_defaults(cfg)
    assert cfg.blacklist.allow_non_registered is False
    assert cfg.blacklist.force_validator_permit is True

    # Calling again is idempotent
    cfg2 = Miner._apply_secure_blacklist_defaults(cfg)
    assert cfg2.blacklist.allow_non_registered is False

    # Also exercises config() classmethod path
    # (we don't construct full Miner here to avoid heavy side effects)
    c = Miner.config()
    assert c.blacklist.allow_non_registered is False
    assert c.blacklist.force_validator_permit is True
