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


def count_legs(swings: List[SwingPoint], labels: List[str], direction: TrendDirection) -> Tuple[int, bool]:
    """
    Count trend legs based on swing sequence.

    For Uptrend:
    - Leg 1: First HH after trend starts
    - Pullback: HL after HH
    - Leg 2: Next HH after pullback
    - etc.

    For Downtrend:
    - Leg 1: First LL after trend starts
    - Pullback: LH after LL
    - Leg 2: Next LL after pullback
    - etc.

    Returns:
        (current_leg_number, is_currently_in_pullback)
    """
    if not labels or direction == TrendDirection.NEUTRAL:
        return 0, False

    leg_count = 0
    in_pullback = False

    if direction == TrendDirection.UP:
        # Count HH as legs, HL as pullbacks
        for label in labels:
            if label == "HH":
                leg_count += 1
                in_pullback = False
            elif label == "HL":
                in_pullback = True

    elif direction == TrendDirection.DOWN:
        # Count LL as legs, LH as pullbacks
        for label in labels:
            if label == "LL":
                leg_count += 1
                in_pullback = False
            elif label == "LH":
                in_pullback = True

    return leg_count, in_pullback


def analyze_trend(
    candles: List[Dict[str, Any]],
    signal_side: str,  # "buy" or "sell"
    max_allowed_leg: int = 3,
    swing_lookback: int = 5,
    log: Optional[logging.Logger] = None
) -> TrendAnalysis:
    """
    Analyze trend and determine if signal should be taken.

    Args:
        candles: Candlestick data from Bybit (newest first)
        signal_side: "buy" for long, "sell" for short
        max_allowed_leg: Maximum leg number to allow entry (default 3)
        swing_lookback: Lookback period for swing detection (default 5)
        log: Optional logger

    Returns:
        TrendAnalysis with recommendation
    """
    # Detect swing points
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

    # Classify swing sequence
    direction, labels = classify_swing_sequence(swings)

    # Count legs
    current_leg, is_pullback = count_legs(swings, labels, direction)

    if log:
        log.info(f"📊 Trend Analysis: {direction.value}, Leg {current_leg}, Pullback={is_pullback}")
        log.info(f"   Swing sequence (last 10): {labels[-10:]}")

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
