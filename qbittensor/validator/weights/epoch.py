"""Deterministic SN48 weight vector from a platform-frozen epoch snapshot."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


def miner_share(
    total_cost: float,
    credit_usd: float,
    tao_usd: float,
    miner_emission_tao: float,
    markup: float,
    alpha_price: float = 0.0,
    miner_emission_alpha: float = 0.0,
) -> float:
    """Share of emission for this cost, capped at 1. Returns 0 when a price is missing."""
    cost_usd = total_cost * credit_usd
    if cost_usd <= 0:
        return 0.0
    emission_alpha = miner_emission_alpha
    if emission_alpha <= 0 and miner_emission_tao > 0 and alpha_price > 0:
        emission_alpha = miner_emission_tao / alpha_price
    if tao_usd <= 0 or alpha_price <= 0 or emission_alpha <= 0:
        return 0.0
    cost_alpha = cost_usd / tao_usd / alpha_price
    return min(1.0, markup * cost_alpha / emission_alpha)


def _reliability(completed: float, failed: float) -> float:
    denom = completed + failed
    if denom <= 0:
        return 1.0
    return completed / denom


def _stake_term(stake: float, stake_exponent: float) -> float:
    stake = max(0.0, stake)
    if stake_exponent == 0:
        return 1.0
    if stake <= 0:
        return 0.0
    return stake ** stake_exponent


def _emission_alpha(
    miner_emission_tao: float,
    alpha_price: float,
    miner_emission_alpha: float,
) -> float:
    if miner_emission_alpha > 0:
        return miner_emission_alpha
    if miner_emission_tao > 0 and alpha_price > 0:
        return miner_emission_tao / alpha_price
    return 0.0


def has_unpriced_cost(snapshot: Mapping[str, Any]) -> bool:
    """True when the book has quote cost and a price or emission is missing."""
    tao_usd = float(snapshot.get("tao_usd") or 0)
    alpha_price = float(snapshot.get("alpha_price") or 0)
    emission_alpha = _emission_alpha(
        float(snapshot.get("miner_emission_tao") or 0),
        alpha_price,
        float(snapshot.get("miner_emission_alpha") or 0),
    )
    if tao_usd > 0 and alpha_price > 0 and emission_alpha > 0:
        return False
    for row in snapshot.get("miners") or []:
        if isinstance(row, Mapping) and float(row.get("cost") or 0) > 0:
            return True
    return False


def weights_from_epoch(
    snapshot: Mapping[str, Any],
    hotkeys: Sequence[str],
    stakes: Sequence[float],
    owner_hotkey: Optional[str] = None,
) -> Optional[List[float]]:
    """Weight vector for one epoch. Returns None when a required price or hotkey is missing."""
    n = len(hotkeys)
    weights = [0.0] * n
    miners = snapshot.get("miners") or []
    by_hk: Dict[str, Mapping[str, Any]] = {}
    for row in miners:
        hk = row.get("miner_hotkey")
        if isinstance(hk, str) and hk:
            by_hk[hk] = row

    credit_usd = float(snapshot.get("credit_usd") or 1)
    tao_usd = float(snapshot.get("tao_usd") or 0)
    emission = float(snapshot.get("miner_emission_tao") or 0)
    alpha_price = float(snapshot.get("alpha_price") or 0)
    emission_alpha = _emission_alpha(
        emission,
        alpha_price,
        float(snapshot.get("miner_emission_alpha") or 0),
    )
    markup = float(snapshot.get("cost_markup") or 1.2)
    stake_exp = float(snapshot.get("stake_exponent") or 0.5)
    burn_hk = owner_hotkey or snapshot.get("owner_hotkey") or snapshot.get("burn_hotkey")
    if not isinstance(burn_hk, str) or not burn_hk.strip():
        burn_hk = None

    fx_ok = tao_usd > 0 and alpha_price > 0 and emission_alpha > 0
    if not fx_ok and has_unpriced_cost(snapshot):
        return None
    # (rank desc, hotkey asc, index, alpha owed, quote cost)
    ranked: List[tuple] = []
    if fx_ok:
        for i, hk in enumerate(hotkeys):
            row = by_hk.get(hk)
            if row is None or hk == burn_hk:
                continue
            cost = float(row.get("cost") or 0)
            if cost <= 0:
                continue
            stake = float(stakes[i]) if i < len(stakes) else 0.0
            rank = _reliability(
                float(row.get("completed") or 0),
                float(row.get("failed") or 0),
            ) * _stake_term(stake, stake_exp)
            owed = markup * cost * credit_usd / tao_usd / alpha_price
            ranked.append((-rank, hk, i, owed, cost))
        ranked.sort()

    tol = 1e-9 * max(1.0, emission_alpha)
    total_owed = sum(row[3] for row in ranked)
    total_cost = sum(row[4] for row in ranked)
    if ranked and total_cost > 0 and total_owed <= emission_alpha + tol:
        for _neg_rank, _hk, idx, _owed, cost in ranked:
            weights[idx] = cost / total_cost
        return weights

    paid = [0.0] * n
    remaining = emission_alpha if fx_ok else 0.0
    for _neg_rank, _hk, idx, owed, _cost in ranked:
        if owed <= remaining + tol:
            pay = min(owed, remaining)
            paid[idx] = pay
            remaining -= pay
        else:
            break

    if emission_alpha > 0:
        for i in range(n):
            weights[i] = paid[i] / emission_alpha

    burn_share = 1.0 - sum(weights)
    if burn_share > 1e-12:
        if burn_hk is None or burn_hk not in hotkeys:
            return None
        weights[list(hotkeys).index(burn_hk)] += burn_share

    return weights
