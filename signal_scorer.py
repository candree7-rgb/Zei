"""
Signal Scoring System for Batch Processing

When multiple signals arrive at the same time, this module scores each
signal based on trend analysis and risk/reward to select the best one.

Scoring Criteria:
1. Trend Leg (lower is better): Leg 1 > Leg 2 > Leg 3
2. Pullback Status (in pullback is better)
3. Risk/Reward Ratio (higher is better)
4. Trend Alignment (aligned is required)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from trend_analysis import analyze_trend, timeframe_to_interval, TrendAnalysis


@dataclass
class ScoredSignal:
    """Signal with analysis score."""
    signal: Dict[str, Any]
    analysis: Optional[TrendAnalysis]
    score: float
    rr_ratio: float
    skip_reason: Optional[str]


def calculate_rr_ratio(signal: Dict[str, Any]) -> float:
    """
    Calculate Risk/Reward ratio for a signal.

    R:R = (TP1 distance from entry) / (SL distance from entry)
    Higher is better.
    """
    entry = float(signal.get("trigger", 0))
    sl = signal.get("sl_price")
    tps = signal.get("tp_prices", [])

    if not entry or not sl or not tps:
        return 0.0

    sl = float(sl)
    tp1 = float(tps[0]) if tps else 0

    if not tp1:
        return 0.0

    side = signal.get("side", "buy").lower()

    if side == "buy":
        # LONG: TP above entry, SL below entry
        reward = tp1 - entry
        risk = entry - sl
    else:
        # SHORT: TP below entry, SL above entry
        reward = entry - tp1
        risk = sl - entry

    if risk <= 0:
        return 0.0

    return reward / risk


def score_signal(
    signal: Dict[str, Any],
    analysis: Optional[TrendAnalysis],
    max_allowed_leg: int = 3
) -> Tuple[float, Optional[str]]:
    """
    Calculate score for a signal based on trend analysis.

    Scoring:
    - Base: 100 points
    - Leg bonus: (max_leg - current_leg + 1) * 20 points
    - Pullback bonus: +15 points
    - R:R bonus: rr_ratio * 10 points (capped at 30)

    Returns:
        (score, skip_reason) - skip_reason is None if signal is valid
    """
    if not analysis:
        return 0.0, "No trend analysis available"

    # Check if should skip
    if analysis.recommendation == "SKIP":
        return 0.0, analysis.reason

    # Base score
    score = 100.0

    # Leg bonus (lower leg = higher score)
    # Leg 1: +60, Leg 2: +40, Leg 3: +20
    leg = analysis.current_leg
    if leg > 0 and leg <= max_allowed_leg:
        leg_bonus = (max_allowed_leg - leg + 1) * 20
        score += leg_bonus
    elif leg > max_allowed_leg:
        return 0.0, f"Leg {leg} > max allowed {max_allowed_leg}"

    # Pullback bonus (best entries are during pullbacks)
    if analysis.is_pullback:
        score += 15

    # R:R bonus
    rr = calculate_rr_ratio(signal)
    rr_bonus = min(rr * 10, 30)  # Cap at 30 points
    score += rr_bonus

    # LATE warning penalty (still trades but lower priority)
    if analysis.recommendation == "LATE":
        score -= 20

    return score, None


def score_signals_batch(
    signals: List[Dict[str, Any]],
    bybit,
    category: str,
    max_allowed_leg: int = 3,
    swing_lookback: int = 5,
    trend_candles: int = 200,
    log: Optional[logging.Logger] = None
) -> List[ScoredSignal]:
    """
    Score a batch of signals and return sorted by score (highest first).

    Args:
        signals: List of parsed signals
        bybit: Bybit API client for fetching klines
        category: "linear" for USDT perpetual
        max_allowed_leg: Maximum allowed leg for entry
        swing_lookback: Candles for swing detection
        trend_candles: Number of candles to fetch
        log: Optional logger

    Returns:
        List of ScoredSignal, sorted by score descending
    """
    scored = []

    for sig in signals:
        symbol = sig.get("symbol", "UNKNOWN")
        side = sig.get("side", "buy")
        timeframe = sig.get("timeframe", "H1")

        if log:
            log.info(f"📊 Scoring {symbol} {side.upper()} ({timeframe})...")

        # Fetch klines and analyze trend
        analysis = None
        try:
            interval = timeframe_to_interval(timeframe)
            candles = bybit.klines(category, symbol, interval, trend_candles)

            if candles and len(candles) >= 50:
                analysis = analyze_trend(
                    candles=candles,
                    signal_side=side,
                    max_allowed_leg=max_allowed_leg,
                    swing_lookback=swing_lookback,
                    log=None  # Don't spam logs during batch
                )
        except Exception as e:
            if log:
                log.warning(f"⚠️ Trend analysis failed for {symbol}: {e}")

        # Calculate score
        score, skip_reason = score_signal(sig, analysis, max_allowed_leg)
        rr = calculate_rr_ratio(sig)

        scored_sig = ScoredSignal(
            signal=sig,
            analysis=analysis,
            score=score,
            rr_ratio=rr,
            skip_reason=skip_reason
        )
        scored.append(scored_sig)

        if log:
            if skip_reason:
                log.info(f"   ❌ SKIP: {skip_reason}")
            else:
                leg = analysis.current_leg if analysis else "?"
                pullback = "pullback" if (analysis and analysis.is_pullback) else "impulse"
                log.info(f"   ✅ Score: {score:.0f} | Leg {leg} ({pullback}) | R:R {rr:.2f}")

    # Sort by score descending
    scored.sort(key=lambda x: x.score, reverse=True)

    return scored


def select_best_signals(
    scored_signals: List[ScoredSignal],
    max_count: int = 1,
    log: Optional[logging.Logger] = None
) -> List[Dict[str, Any]]:
    """
    Select the best signals from a scored batch.

    Args:
        scored_signals: List of ScoredSignal from score_signals_batch()
        max_count: Maximum number of signals to return
        log: Optional logger

    Returns:
        List of best signals (raw signal dicts)
    """
    # Filter out skipped signals
    valid = [s for s in scored_signals if s.skip_reason is None and s.score > 0]

    if not valid:
        if log:
            log.info("📭 No valid signals in batch after filtering")
        return []

    # Take top N
    best = valid[:max_count]

    if log:
        log.info(f"🏆 Selected {len(best)} best signal(s) from {len(scored_signals)} total:")
        for i, s in enumerate(best):
            sym = s.signal.get("symbol", "?")
            side = s.signal.get("side", "?").upper()
            leg = s.analysis.current_leg if s.analysis else "?"
            log.info(f"   #{i+1}: {sym} {side} | Score: {s.score:.0f} | Leg {leg} | R:R {s.rr_ratio:.2f}")

    return [s.signal for s in best]
