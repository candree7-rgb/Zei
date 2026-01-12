"""
Trend Analysis Module for Leg Detection

Based on Zeiierman's trend trading strategy:
- Uptrends: HH/HL structure, ~5 legs
- Downtrends: LH/LL structure, ~5 legs

Best entries: After Pullback #1-#2 (Legs 1-3)
Skip: Late entries (Leg 4-5) - higher reversal risk

References:
- https://docs.zeiierman.com/getting-started/trading-signals
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging


class TrendDirection(Enum):
    UP = "uptrend"
    DOWN = "downtrend"
    NEUTRAL = "neutral"


def calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    """
    Calculate Average True Range for measuring swing significance.

    Args:
        candles: List of candles (newest first from Bybit API)
        period: ATR period (default 14)

    Returns:
        ATR value
    """
    if len(candles) < period + 1:
        # Not enough data, estimate from recent range
        if candles:
            ranges = [c["high"] - c["low"] for c in candles[:min(10, len(candles))]]
            return sum(ranges) / len(ranges) if ranges else 0.0
        return 0.0

    # Reverse so oldest first
    candles_ordered = list(reversed(candles))

    true_ranges = []
    for i in range(1, len(candles_ordered)):
        high = candles_ordered[i]["high"]
        low = candles_ordered[i]["low"]
        prev_close = candles_ordered[i-1]["close"]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        true_ranges.append(tr)

    # Simple ATR (average of last `period` true ranges)
    if len(true_ranges) >= period:
        return sum(true_ranges[-period:]) / period
    return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0


@dataclass
class SwingPoint:
    """Represents a swing high or low point."""
    index: int          # Index in candles array
    price: float        # High for swing high, Low for swing low
    timestamp: int      # Candle timestamp
    is_high: bool       # True = swing high, False = swing low


@dataclass
class TrendLeg:
    """Represents a trend leg (impulse move)."""
    leg_number: int     # 1, 2, 3, 4, 5
    start_price: float
    end_price: float
    is_impulse: bool    # True = impulse (trend direction), False = pullback


@dataclass
class TrendAnalysis:
    """Result of trend analysis for a symbol."""
    direction: TrendDirection
    current_leg: int           # Which leg we're in (1-5+)
    is_pullback: bool          # Currently in pullback phase?
    swing_points: List[SwingPoint]
    legs: List[TrendLeg]
    recommendation: str        # "VALID", "LATE", "SKIP"
    reason: str                # Explanation


def detect_swing_points(candles: List[Dict[str, Any]], lookback: int = 5) -> List[SwingPoint]:
    """
    Detect swing highs and lows in price data.

    A swing high/low is confirmed when the high/low is higher/lower than
    the surrounding `lookback` candles on both sides.

    Args:
        candles: List of candles (newest first from Bybit API)
        lookback: Number of candles to look on each side (default 5)

    Returns:
        List of SwingPoints, ordered oldest to newest
    """
    # Reverse candles so oldest is first (easier to process)
    candles = list(reversed(candles))
    swing_points = []

    # Need at least lookback candles on each side
    for i in range(lookback, len(candles) - lookback):
        candle = candles[i]
        high = candle["high"]
        low = candle["low"]

        # Check for swing high
        is_swing_high = True
        for j in range(i - lookback, i + lookback + 1):
            if j == i:
                continue
            if candles[j]["high"] >= high:
                is_swing_high = False
                break

        # Check for swing low
        is_swing_low = True
        for j in range(i - lookback, i + lookback + 1):
            if j == i:
                continue
            if candles[j]["low"] <= low:
                is_swing_low = False
                break

        if is_swing_high:
            swing_points.append(SwingPoint(
                index=i,
                price=high,
                timestamp=candle["timestamp"],
                is_high=True
            ))
        if is_swing_low:
            swing_points.append(SwingPoint(
                index=i,
                price=low,
                timestamp=candle["timestamp"],
                is_high=False
            ))

    # Sort by index (time order)
    swing_points.sort(key=lambda sp: sp.index)
    return swing_points


def filter_significant_swings(
    swings: List[SwingPoint],
    atr: float,
    min_swing_atr: float = 1.5
) -> List[SwingPoint]:
    """
    Filter swings to only keep significant ones (move at least min_swing_atr * ATR).

    This removes noise from the swing detection and keeps only meaningful
    price movements that represent real trend legs.

    Args:
        swings: List of detected swing points
        atr: Average True Range value
        min_swing_atr: Minimum swing size in ATR multiples (default 1.5)

    Returns:
        Filtered list of significant swing points
    """
    if not swings or atr <= 0:
        return swings

    min_move = atr * min_swing_atr
    significant = []

    for i, swing in enumerate(swings):
        if i == 0:
            significant.append(swing)
            continue

        # Find previous swing of opposite type
        prev_opposite = None
        for j in range(i - 1, -1, -1):
            if swings[j].is_high != swing.is_high:
                prev_opposite = swings[j]
                break

        if prev_opposite is None:
            significant.append(swing)
            continue

        # Calculate move size from opposite swing
        move_size = abs(swing.price - prev_opposite.price)

        # Only keep if move is significant
        if move_size >= min_move:
            significant.append(swing)

    return significant


def find_major_trend_reversal(
    swings: List[SwingPoint],
    labels: List[str],
    direction: TrendDirection,
    atr: float,
    min_reversal_atr: float = 3.0
) -> int:
    """
    Find where a MAJOR trend reversal happened (not minor counter-moves).

    Instead of resetting at every HH/LL, we look for significant price structure
    changes that represent a real trend change.

    Args:
        swings: List of swing points
        labels: Swing labels (HH, HL, LH, LL)
        direction: Current trend direction
        atr: Average True Range
        min_reversal_atr: Minimum reversal size in ATR (default 3.0)

    Returns:
        Index in labels where major reversal happened
    """
    if not labels or not swings or direction == TrendDirection.NEUTRAL:
        return 0

    min_reversal_size = atr * min_reversal_atr

    # For uptrend: find where we made a significant HL after significant LL (trend change)
    # For downtrend: find where we made a significant LH after significant HH (trend change)

    if direction == TrendDirection.UP:
        # Walk backwards to find the MAJOR low that started this uptrend
        # This is where we made a higher low that was significantly higher than previous lows
        best_reversal_idx = 0
        last_significant_low = None
        last_significant_low_idx = 0

        for i, (swing, label) in enumerate(zip(swings, labels)):
            if not swing.is_high:  # It's a low
                if last_significant_low is not None:
                    # Check if this low is significantly higher (confirming uptrend)
                    if swing.price > last_significant_low + min_reversal_size:
                        # Found major reversal point
                        best_reversal_idx = last_significant_low_idx
                        break
                last_significant_low = swing.price
                last_significant_low_idx = i

        # If no major reversal found, use the last LL as start
        if best_reversal_idx == 0:
            for i in range(len(labels) - 1, -1, -1):
                if labels[i] == "LL":
                    best_reversal_idx = i + 1
                    break

        return min(best_reversal_idx, len(labels) - 1)

    elif direction == TrendDirection.DOWN:
        # Walk backwards to find the MAJOR high that started this downtrend
        best_reversal_idx = 0
        last_significant_high = None
        last_significant_high_idx = 0

        for i, (swing, label) in enumerate(zip(swings, labels)):
            if swing.is_high:  # It's a high
                if last_significant_high is not None:
                    # Check if this high is significantly lower (confirming downtrend)
                    if swing.price < last_significant_high - min_reversal_size:
                        # Found major reversal point
                        best_reversal_idx = last_significant_high_idx
                        break
                last_significant_high = swing.price
                last_significant_high_idx = i

        # If no major reversal found, use the last HH as start
        if best_reversal_idx == 0:
            for i in range(len(labels) - 1, -1, -1):
                if labels[i] == "HH":
                    best_reversal_idx = i + 1
                    break

        return min(best_reversal_idx, len(labels) - 1)

    return 0


def classify_swing_sequence(swings: List[SwingPoint]) -> Tuple[TrendDirection, List[str]]:
    """
    Classify swing sequence to determine trend direction.

    Uptrend: HH (Higher Highs) and HL (Higher Lows)
    Downtrend: LH (Lower Highs) and LL (Lower Lows)

    Returns:
        (TrendDirection, list of swing labels like ["HH", "HL", "HH", ...])
    """
    if len(swings) < 4:
        return TrendDirection.NEUTRAL, []

    labels = []
    last_high = None
    last_low = None

    hh_count = 0  # Higher Highs
    lh_count = 0  # Lower Highs
    hl_count = 0  # Higher Lows
    ll_count = 0  # Lower Lows

    for swing in swings:
        if swing.is_high:
            if last_high is not None:
                if swing.price > last_high:
                    labels.append("HH")
                    hh_count += 1
                else:
                    labels.append("LH")
                    lh_count += 1
            else:
                labels.append("H")  # First high
            last_high = swing.price
        else:
            if last_low is not None:
                if swing.price > last_low:
                    labels.append("HL")
                    hl_count += 1
                else:
                    labels.append("LL")
                    ll_count += 1
            else:
                labels.append("L")  # First low
            last_low = swing.price

    # Determine trend based on recent swings (last 6-8)
    recent_labels = labels[-8:] if len(labels) >= 8 else labels

    # Count recent patterns
    recent_hh = recent_labels.count("HH")
    recent_hl = recent_labels.count("HL")
    recent_lh = recent_labels.count("LH")
    recent_ll = recent_labels.count("LL")

    # Uptrend: mostly HH and HL
    if recent_hh + recent_hl > recent_lh + recent_ll and recent_hh >= 1 and recent_hl >= 1:
        return TrendDirection.UP, labels

    # Downtrend: mostly LH and LL
    if recent_lh + recent_ll > recent_hh + recent_hl and recent_lh >= 1 and recent_ll >= 1:
        return TrendDirection.DOWN, labels

    return TrendDirection.NEUTRAL, labels


def find_trend_start_index(labels: List[str], direction: TrendDirection) -> int:
    """
    Find where the current trend started (last reversal point).

    For Uptrend: Find last occurrence of LL before HH/HL pattern started
    For Downtrend: Find last occurrence of HH before LH/LL pattern started

    Returns:
        Index in labels where current trend started
    """
    if not labels or direction == TrendDirection.NEUTRAL:
        return 0

    # Walk backwards to find where trend changed
    if direction == TrendDirection.UP:
        # Find last LL (end of previous downtrend)
        for i in range(len(labels) - 1, -1, -1):
            if labels[i] == "LL":
                return i + 1  # Trend starts after last LL
        # No LL found - check for LH (also indicates previous downtrend)
        for i in range(len(labels) - 1, -1, -1):
            if labels[i] == "LH":
                return i + 1

    elif direction == TrendDirection.DOWN:
        # Find last HH (end of previous uptrend)
        for i in range(len(labels) - 1, -1, -1):
            if labels[i] == "HH":
                return i + 1  # Trend starts after last HH
        # No HH found - check for HL (also indicates previous uptrend)
        for i in range(len(labels) - 1, -1, -1):
            if labels[i] == "HL":
                return i + 1

    return 0


def count_legs(swings: List[SwingPoint], labels: List[str], direction: TrendDirection) -> Tuple[int, bool]:
    """
    Count trend legs based on swing sequence SINCE TREND STARTED.

    For Uptrend:
    - Leg 1: First HH after trend reversal
    - Pullback: HL after HH
    - Leg 2: Next HH after pullback
    - etc.

    For Downtrend:
    - Leg 1: First LL after trend reversal
    - Pullback: LH after LL
    - Leg 2: Next LL after pullback
    - etc.

    Returns:
        (current_leg_number, is_currently_in_pullback)
    """
    if not labels or direction == TrendDirection.NEUTRAL:
        return 0, False

    # Find where current trend started
    trend_start = find_trend_start_index(labels, direction)

    # Only count legs from trend start
    relevant_labels = labels[trend_start:]

    leg_count = 0
    in_pullback = False

    if direction == TrendDirection.UP:
        # Count HH as legs, HL as pullbacks
        for label in relevant_labels:
            if label == "HH":
                leg_count += 1
                in_pullback = False
            elif label == "HL":
                in_pullback = True

    elif direction == TrendDirection.DOWN:
        # Count LL as legs, LH as pullbacks
        for label in relevant_labels:
            if label == "LL":
                leg_count += 1
                in_pullback = False
            elif label == "LH":
                in_pullback = True

    # Minimum leg 1 if we have any trend structure
    if leg_count == 0 and len(relevant_labels) > 0:
        leg_count = 1

    return leg_count, in_pullback


def count_significant_legs(
    swings: List[SwingPoint],
    labels: List[str],
    direction: TrendDirection,
    atr: float,
    min_swing_atr: float = 1.5,
    min_reversal_atr: float = 3.0
) -> Tuple[int, bool, int, List[str]]:
    """
    Count trend legs using ATR-based significance filtering.

    Only counts legs that represent significant price moves (not noise).
    Uses major reversal detection instead of resetting at every HH/LL.

    Args:
        swings: List of swing points
        labels: Swing labels
        direction: Trend direction
        atr: Average True Range
        min_swing_atr: Minimum swing size in ATR multiples
        min_reversal_atr: Minimum reversal size in ATR multiples

    Returns:
        (leg_count, is_pullback, trend_start_idx, relevant_labels)
    """
    if not labels or direction == TrendDirection.NEUTRAL:
        return 0, False, 0, []

    # Filter to only significant swings
    significant_swings = filter_significant_swings(swings, atr, min_swing_atr)

    # Re-label the significant swings
    sig_labels = []
    last_high = None
    last_low = None

    for swing in significant_swings:
        if swing.is_high:
            if last_high is not None:
                if swing.price > last_high:
                    sig_labels.append("HH")
                else:
                    sig_labels.append("LH")
            else:
                sig_labels.append("H")
            last_high = swing.price
        else:
            if last_low is not None:
                if swing.price > last_low:
                    sig_labels.append("HL")
                else:
                    sig_labels.append("LL")
            else:
                sig_labels.append("L")
            last_low = swing.price

    # Find major trend reversal (not just any HH/LL)
    trend_start_idx = find_major_trend_reversal(
        significant_swings, sig_labels, direction, atr, min_reversal_atr
    )

    # Count legs from the major reversal point
    relevant_labels = sig_labels[trend_start_idx:] if trend_start_idx < len(sig_labels) else []

    leg_count = 0
    in_pullback = False

    if direction == TrendDirection.UP:
        for label in relevant_labels:
            if label == "HH":
                leg_count += 1
                in_pullback = False
            elif label == "HL":
                in_pullback = True

    elif direction == TrendDirection.DOWN:
        for label in relevant_labels:
            if label == "LL":
                leg_count += 1
                in_pullback = False
            elif label == "LH":
                in_pullback = True

    # Minimum leg 1 if we have any trend structure
    if leg_count == 0 and len(relevant_labels) > 0:
        leg_count = 1

    return leg_count, in_pullback, trend_start_idx, relevant_labels


def analyze_trend(
    candles: List[Dict[str, Any]],
    signal_side: str,  # "buy" or "sell"
    max_allowed_leg: int = 3,
    swing_lookback: int = 5,
    min_swing_atr: float = 1.5,
    min_reversal_atr: float = 3.0,
    log: Optional[logging.Logger] = None
) -> TrendAnalysis:
    """
    Analyze trend and determine if signal should be taken.

    Uses ATR-based filtering for accurate leg detection:
    - Only counts significant swings (moves >= min_swing_atr * ATR)
    - Only resets leg count at major reversals (moves >= min_reversal_atr * ATR)

    Args:
        candles: Candlestick data from Bybit (newest first)
        signal_side: "buy" for long, "sell" for short
        max_allowed_leg: Maximum leg number to allow entry (default 3)
        swing_lookback: Lookback period for swing detection (default 5)
        min_swing_atr: Minimum swing size in ATR multiples (default 1.5)
        min_reversal_atr: Minimum reversal size in ATR multiples (default 3.0)
        log: Optional logger

    Returns:
        TrendAnalysis with recommendation
    """
    # Calculate ATR for significance filtering
    atr = calculate_atr(candles)

    # Detect all swing points
    swings = detect_swing_points(candles, lookback=swing_lookback)

    if len(swings) < 4:
        return TrendAnalysis(
            direction=TrendDirection.NEUTRAL,
            current_leg=0,
            is_pullback=False,
            swing_points=swings,
            legs=[],
            recommendation="SKIP",
            reason=f"Not enough swing points ({len(swings)}) to determine trend"
        )

    # Filter to significant swings for trend classification
    significant_swings = filter_significant_swings(swings, atr, min_swing_atr)

    if len(significant_swings) < 4:
        # Fall back to all swings if not enough significant ones
        significant_swings = swings
        if log:
            log.info(f"📊 Not enough significant swings, using all {len(swings)} swings")

    # Classify swing sequence using significant swings
    direction, labels = classify_swing_sequence(significant_swings)

    # Count legs using ATR-based detection
    current_leg, is_pullback, trend_start_idx, relevant_labels = count_significant_legs(
        swings, labels, direction, atr, min_swing_atr, min_reversal_atr
    )

    if log:
        log.info(f"📊 Trend Analysis: {direction.value}, Leg {current_leg}, Pullback={is_pullback}")
        log.info(f"   ATR={atr:.4f}, MinSwing={atr * min_swing_atr:.4f}, MinReversal={atr * min_reversal_atr:.4f}")
        log.info(f"   All swings: {len(swings)}, Significant swings: {len(significant_swings)}")
        log.info(f"   Significant swing labels: {labels[-12:]}")
        log.info(f"   Major reversal at idx {trend_start_idx}, counting from: {relevant_labels}")

    # Validate signal against trend
    # BUY signal should be in UPTREND
    # SELL signal should be in DOWNTREND
    signal_side_lower = signal_side.lower()

    # Check trend alignment
    if signal_side_lower == "buy" and direction != TrendDirection.UP:
        return TrendAnalysis(
            direction=direction,
            current_leg=current_leg,
            is_pullback=is_pullback,
            swing_points=swings,
            legs=[],
            recommendation="SKIP",
            reason=f"BUY signal but trend is {direction.value} (need uptrend)"
        )

    if signal_side_lower == "sell" and direction != TrendDirection.DOWN:
        return TrendAnalysis(
            direction=direction,
            current_leg=current_leg,
            is_pullback=is_pullback,
            swing_points=swings,
            legs=[],
            recommendation="SKIP",
            reason=f"SELL signal but trend is {direction.value} (need downtrend)"
        )

    # Check leg number
    if current_leg > max_allowed_leg:
        return TrendAnalysis(
            direction=direction,
            current_leg=current_leg,
            is_pullback=is_pullback,
            swing_points=swings,
            legs=[],
            recommendation="SKIP",
            reason=f"Late trend entry - Leg {current_leg} > max allowed {max_allowed_leg} (reversal risk)"
        )

    # Best entries are during pullbacks
    if is_pullback:
        return TrendAnalysis(
            direction=direction,
            current_leg=current_leg,
            is_pullback=is_pullback,
            swing_points=swings,
            legs=[],
            recommendation="VALID",
            reason=f"Good entry - {direction.value} Leg {current_leg} pullback (early trend)"
        )

    # Not in pullback but still early enough
    if current_leg <= 2:
        return TrendAnalysis(
            direction=direction,
            current_leg=current_leg,
            is_pullback=is_pullback,
            swing_points=swings,
            legs=[],
            recommendation="VALID",
            reason=f"Acceptable entry - {direction.value} Leg {current_leg} (early trend)"
        )

    # Leg 3 without pullback - caution
    return TrendAnalysis(
        direction=direction,
        current_leg=current_leg,
        is_pullback=is_pullback,
        swing_points=swings,
        legs=[],
        recommendation="LATE",
        reason=f"Caution - {direction.value} Leg {current_leg}, not in pullback (elevated risk)"
    )


def timeframe_to_interval(timeframe: str) -> str:
    """
    Convert signal timeframe to Bybit kline interval.

    Args:
        timeframe: "H1", "M15", "H4", "D1" etc.

    Returns:
        Bybit interval: "60", "15", "240", "D" etc.
    """
    mapping = {
        "M1": "1",
        "M3": "3",
        "M5": "5",
        "M15": "15",
        "M30": "30",
        "H1": "60",
        "H2": "120",
        "H4": "240",
        "H6": "360",
        "H12": "720",
        "D1": "D",
        "D": "D",
        "W1": "W",
        "W": "W",
    }
    return mapping.get(timeframe.upper(), "60")  # Default to 1h


def get_htf_for_signal(signal_tf: str) -> str:
    """
    Get Higher TimeFrame for a signal timeframe.

    M15 → H4
    H1  → H4
    H4  → D1
    """
    htf_mapping = {
        "M5": "H1",
        "M15": "H4",
        "M30": "H4",
        "H1": "H4",
        "H2": "H4",
        "H4": "D",
        "H6": "D",
        "H12": "D",
    }
    return htf_mapping.get(signal_tf.upper(), "H4")


def get_simple_trend_direction(candles: List[Dict[str, Any]], swing_lookback: int = 5) -> TrendDirection:
    """
    Get simple trend direction from candles (no full analysis, just direction).
    Used for HTF alignment check.
    """
    swings = detect_swing_points(candles, lookback=swing_lookback)
    if len(swings) < 4:
        return TrendDirection.NEUTRAL

    direction, _ = classify_swing_sequence(swings)
    return direction


def check_htf_alignment(
    bybit,
    category: str,
    symbol: str,
    signal_side: str,  # "buy" or "sell"
    signal_tf: str,    # "M15", "H1", etc.
    swing_lookback: int = 5,
    htf_candles: int = 100,
    log: Optional[logging.Logger] = None
) -> Tuple[bool, str]:
    """
    Check if Higher TimeFrame trend aligns with signal direction.

    For 80% winrate, only take signals that align with HTF trend.
    This filters out counter-trend bounces.

    Args:
        bybit: Bybit client instance
        category: "linear" for futures
        symbol: Trading symbol
        signal_side: "buy" or "sell"
        signal_tf: Signal timeframe ("M15", "H1", etc.)
        swing_lookback: Lookback for swing detection
        htf_candles: Number of HTF candles to fetch
        log: Optional logger

    Returns:
        (is_aligned: bool, reason: str)
    """
    try:
        # Get HTF interval
        htf = get_htf_for_signal(signal_tf)
        htf_interval = timeframe_to_interval(htf)

        # Fetch HTF candles
        htf_candles_data = bybit.klines(category, symbol, htf_interval, htf_candles)

        if not htf_candles_data or len(htf_candles_data) < 50:
            if log:
                log.warning(f"⚠️ Not enough HTF ({htf}) candles for {symbol}, allowing entry")
            return True, f"HTF data insufficient, allowing entry"

        # Get HTF trend direction
        htf_direction = get_simple_trend_direction(htf_candles_data, swing_lookback)

        signal_side_lower = signal_side.lower()

        if log:
            log.info(f"📊 HTF Check: {htf} trend = {htf_direction.value} | Signal = {signal_side_lower.upper()}")

        # Check alignment
        if signal_side_lower == "buy":
            if htf_direction == TrendDirection.UP:
                return True, f"HTF ({htf}) uptrend aligns with LONG signal ✓"
            elif htf_direction == TrendDirection.DOWN:
                return False, f"HTF ({htf}) is DOWNTREND - LONG signal is counter-trend"
            else:
                # Neutral - allow with caution
                return True, f"HTF ({htf}) neutral, allowing LONG with caution"

        else:  # sell
            if htf_direction == TrendDirection.DOWN:
                return True, f"HTF ({htf}) downtrend aligns with SHORT signal ✓"
            elif htf_direction == TrendDirection.UP:
                return False, f"HTF ({htf}) is UPTREND - SHORT signal is counter-trend"
            else:
                # Neutral - allow with caution
                return True, f"HTF ({htf}) neutral, allowing SHORT with caution"

    except Exception as e:
        if log:
            log.warning(f"⚠️ HTF alignment check failed: {e}, allowing entry")
        return True, f"HTF check failed ({e}), allowing entry"
