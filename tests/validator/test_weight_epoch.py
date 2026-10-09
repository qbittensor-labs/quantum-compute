from qbittensor.validator.weights.epoch import (
    has_unpriced_cost,
    miner_share,
    weights_from_epoch,
)


def test_miner_share_burns_without_oracle():
    assert miner_share(100, 1, 0, 0, 1.2) == 0.0
    assert miner_share(100, 1, 10, 0, 1.2) == 0.0
    # tao_usd and TAO emission present, alpha_price missing
    assert miner_share(100, 1, 400, 10, 1.2) == 0.0


def test_miner_share_zero_cost_is_all_burn():
    assert miner_share(0, 1, 400, 10, 1.2) == 0.0


def test_miner_share_markup_then_cap_at_one():
    # 1.2 * 10 credits * $1 / $400 TAO = 0.03 TAO; emission 1 TAO → 3%
    share = miner_share(10, 1, 400, 1, 1.2, alpha_price=1.0, miner_emission_alpha=1.0)
    assert abs(share - 0.03) < 1e-9
    # crowded: 1.2 * 1000 / 400 = 3 TAO needed, emission 1 → 100% to miners
    assert miner_share(1000, 1, 400, 1, 1.2, alpha_price=1.0, miner_emission_alpha=1.0) == 1.0


def test_miner_share_alpha_matches_tao_when_price_applied():
    """Emission is alpha. TAO = alpha * alpha_price; USD = TAO * tao_usd."""
    # 2 alpha * 0.5 TAO/alpha = 1 TAO emission; same 0.03 share as 1 TAO path
    share = miner_share(
        10, 1, 400, 0, 1.2, alpha_price=0.5, miner_emission_alpha=2.0
    )
    assert abs(share - 0.03) < 1e-9
    # Converted TAO emission 1.0 with alpha_price 0.5 → 2 alpha
    share2 = miner_share(
        10, 1, 400, 1.0, 1.2, alpha_price=0.5, miner_emission_alpha=0
    )
    assert abs(share2 - 0.03) < 1e-9


def test_weights_skip_when_burn_missing():
    snap = {
        "miners": [],
        "total_cost": 0,
        "credit_usd": 1,
        "tao_usd": 400,
        "miner_emission_tao": 10,
        "cost_markup": 1.2,
        "stake_exponent": 0.5,
        "owner_hotkey": "5Burn",
    }
    assert weights_from_epoch(snap, ["hk0", "hk1"], [1, 1]) is None


def test_weights_skip_when_cost_book_has_no_price():
    snap = {
        "miners": [
            {"miner_hotkey": "hk0", "cost": 10, "completed": 1, "failed": 0},
        ],
        "credit_usd": 1,
        "tao_usd": 0,
        "alpha_price": 0,
        "miner_emission_tao": 0,
        "miner_emission_alpha": 0,
        "cost_markup": 1.2,
        "owner_hotkey": "hk1",
    }
    assert has_unpriced_cost(snap) is True
    assert weights_from_epoch(snap, ["hk0", "hk1"], [10, 1]) is None


def test_weights_all_burn_when_no_cost_and_no_price():
    snap = {
        "miners": [],
        "total_cost": 0,
        "credit_usd": 1,
        "tao_usd": 0,
        "alpha_price": 0,
        "miner_emission_tao": 0,
        "cost_markup": 1.2,
        "owner_hotkey": "hk1",
    }
    assert has_unpriced_cost(snap) is False
    w = weights_from_epoch(snap, ["hk0", "hk1"], [10, 1])
    assert w is not None
    assert abs(w[1] - 1.0) < 1e-12


def test_weights_all_burn_when_no_cost():
    snap = {
        "miners": [],
        "total_cost": 0,
        "credit_usd": 1,
        "tao_usd": 400,
        "miner_emission_tao": 10,
        "cost_markup": 1.2,
        "stake_exponent": 0.5,
        "owner_hotkey": "hk1",
    }
    w = weights_from_epoch(snap, ["hk0", "hk1"], [10, 1])
    assert w is not None
    assert abs(w[0]) < 1e-12
    assert abs(w[1] - 1.0) < 1e-12


def test_excess_emission_splits_by_cost_and_does_not_burn():
    snap = {
        "miners": [
            {"miner_hotkey": "hk0", "cost": 80, "completed": 8, "failed": 0},
            {"miner_hotkey": "hk1", "cost": 20, "completed": 2, "failed": 0},
        ],
        "total_cost": 100,
        "credit_usd": 1,
        "tao_usd": 400,
        "alpha_price": 1.0,
        "miner_emission_tao": 1,
        "miner_emission_alpha": 1.0,
        "cost_markup": 1.2,
        "stake_exponent": 0.0,
        "owner_hotkey": "hk2",
    }
    w = weights_from_epoch(snap, ["hk0", "hk1", "hk2"], [1, 1, 1])
    assert w is not None
    assert abs(sum(w) - 1.0) < 1e-9
    assert abs(w[0] - 0.8) < 1e-9
    assert abs(w[1] - 0.2) < 1e-9
    assert abs(w[2]) < 1e-12


def test_excess_emission_does_not_need_the_owner():
    snap = {
        "miners": [
            {"miner_hotkey": "hk0", "cost": 80, "completed": 1, "failed": 0},
            {"miner_hotkey": "hk1", "cost": 20, "completed": 1, "failed": 3},
        ],
        "total_cost": 100,
        "credit_usd": 1,
        "tao_usd": 400,
        "alpha_price": 1.0,
        "miner_emission_alpha": 1.0,
        "cost_markup": 1.2,
        "stake_exponent": 0.5,
    }
    w = weights_from_epoch(snap, ["hk0", "hk1"], [1, 10_000])
    assert w is not None
    assert abs(w[0] - 0.8) < 1e-9
    assert abs(w[1] - 0.2) < 1e-9


def test_oversized_single_miner_is_cut_and_burned():
    """A payout larger than the epoch pays nothing."""
    snap = {
        "miners": [
            {"miner_hotkey": "hk0", "cost": 500, "completed": 1, "failed": 0},
        ],
        "total_cost": 500,
        "credit_usd": 1,
        "tao_usd": 400,
        "alpha_price": 1.0,
        "miner_emission_tao": 1,
        "miner_emission_alpha": 1.0,
        "cost_markup": 1.2,
        "stake_exponent": 0.0,
        "owner_hotkey": "hk1",
    }
    w = weights_from_epoch(snap, ["hk0", "hk1"], [1, 1])
    assert w is not None
    assert abs(w[0]) < 1e-12
    assert abs(w[1] - 1.0) < 1e-9


def test_hard_cutoff_pays_higher_rank_in_full_and_drops_the_tail():
    """Each 200-credit quote needs 0.6 alpha. Pot is 1.0. Higher √stake is paid."""
    snap = {
        "miners": [
            {"miner_hotkey": "hk0", "cost": 200, "completed": 1, "failed": 0},
            {"miner_hotkey": "hk1", "cost": 200, "completed": 1, "failed": 0},
        ],
        "total_cost": 400,
        "credit_usd": 1,
        "tao_usd": 400,
        "alpha_price": 1.0,
        "miner_emission_tao": 1,
        "miner_emission_alpha": 1.0,
        "cost_markup": 1.2,
        "stake_exponent": 0.5,
        "owner_hotkey": "hk2",
    }
    # rank hk0 = 1 * sqrt(100) = 10; hk1 = 1 * sqrt(25) = 5
    w = weights_from_epoch(snap, ["hk0", "hk1", "hk2"], [100, 25, 0])
    assert w is not None
    assert abs(sum(w) - 1.0) < 1e-9
    assert abs(w[0] - 0.6) < 1e-9
    assert abs(w[1]) < 1e-12
    assert abs(w[2] - 0.4) < 1e-9


def test_hard_cutoff_ranks_reliability_above_a_larger_quote():
    """Clean miner needs 0.3; flaky miner needs 0.6. Pot 0.5 pays only the clean one."""
    snap = {
        "miners": [
            {"miner_hotkey": "hk0", "cost": 100, "completed": 2, "failed": 0},
            {"miner_hotkey": "hk1", "cost": 200, "completed": 1, "failed": 1},
        ],
        "total_cost": 300,
        "credit_usd": 1,
        "tao_usd": 400,
        "alpha_price": 1.0,
        "miner_emission_alpha": 0.5,
        "cost_markup": 1.2,
        "stake_exponent": 0.5,
        "owner_hotkey": "hk2",
    }
    # equal stake: rank hk0 = 1, hk1 = 0.5
    w = weights_from_epoch(snap, ["hk0", "hk1", "hk2"], [100, 100, 0])
    assert w is not None
    assert abs(w[0] - 0.3 / 0.5) < 1e-9
    assert abs(w[1]) < 1e-12
    assert abs(w[2] - (1.0 - 0.6)) < 1e-9


def test_equal_rank_tie_breaks_by_hotkey():
    snap = {
        "miners": [
            {"miner_hotkey": "hk1", "cost": 200, "completed": 1, "failed": 0},
            {"miner_hotkey": "hk0", "cost": 200, "completed": 1, "failed": 0},
        ],
        "total_cost": 400,
        "credit_usd": 1,
        "tao_usd": 400,
        "alpha_price": 1.0,
        "miner_emission_alpha": 1.0,
        "cost_markup": 1.2,
        "stake_exponent": 0.5,
        "owner_hotkey": "hk2",
    }
    w = weights_from_epoch(snap, ["hk0", "hk1", "hk2"], [100, 100, 0])
    assert w is not None
    assert abs(w[0] - 0.6) < 1e-9
    assert abs(w[1]) < 1e-12
    assert abs(w[2] - 0.4) < 1e-9


def test_room_for_everyone_splits_emission_by_cost_ignoring_stake():
    snap = {
        "miners": [
            {"miner_hotkey": "hk0", "cost": 80, "completed": 1, "failed": 0},
            {"miner_hotkey": "hk1", "cost": 20, "completed": 1, "failed": 0},
        ],
        "total_cost": 100,
        "credit_usd": 1,
        "tao_usd": 400,
        "alpha_price": 1.0,
        "miner_emission_alpha": 1.0,
        "cost_markup": 1.2,
        "stake_exponent": 0.5,
        "owner_hotkey": "hk2",
    }
    w = weights_from_epoch(snap, ["hk0", "hk1", "hk2"], [10_000, 1, 0])
    assert w is not None
    assert abs(w[0] - 0.8) < 1e-9
    assert abs(w[1] - 0.2) < 1e-9
    assert abs(w[2]) < 1e-12
