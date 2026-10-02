"""
BALA BTC Strategy Engine
Initial version: signal generation only.
No live orders are placed by this module.
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np


@dataclass
class Signal:
    side: str
    entry: float
    stop_loss: float
    target_1: float
    target_2: float
    reason: str
    quality: str


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()

    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["atr"] = tr.rolling(14).mean()
    df["volume_ma"] = df["volume"].rolling(20).mean()

    return df


def bala_signal(df: pd.DataFrame) -> Optional[Signal]:
    """
    Basic BALA confirmation:

    1. Trend
    2. Liquidity sweep
    3. Displacement / momentum
    4. Volume confirmation
    5. Risk-based SL and targets

    Returns None when there is no valid setup.
    """

    if len(df) < 30:
        return None

    df = add_indicators(df)

    c = df.iloc[-1]
    p = df.iloc[-2]

    atr = float(c["atr"])

    if not np.isfinite(atr) or atr <= 0:
        return None

    recent_high = float(df["high"].iloc[-11:-1].max())
    recent_low = float(df["low"].iloc[-11:-1].min())

    volume_ok = (
        pd.isna(c["volume_ma"])
        or float(c["volume"]) >= float(c["volume_ma"]) * 1.2
    )

    bullish_trend = c["ema9"] > c["ema21"]
    bearish_trend = c["ema9"] < c["ema21"]

    bullish_displacement = (
        c["close"] > c["open"]
        and (c["close"] - c["open"]) >= atr * 0.5
    )

    bearish_displacement = (
        c["close"] < c["open"]
        and (c["open"] - c["close"]) >= atr * 0.5
    )

    # Liquidity sweep + reclaim
    bullish_sweep = (
        p["low"] < recent_low
        and c["close"] > recent_low
    )

    bearish_sweep = (
        p["high"] > recent_high
        and c["close"] < recent_high
    )

    # BALA BUY
    if (
        bullish_trend
        and bullish_sweep
        and bullish_displacement
        and volume_ok
    ):
        entry = float(c["close"])
        stop = float(min(p["low"], c["low"]) - atr * 0.25)

        risk = entry - stop

        if risk <= 0:
            return None

        return Signal(
            side="BUY",
            entry=entry,
            stop_loss=stop,
            target_1=entry + risk * 1.5,
            target_2=entry + risk * 2.5,
            reason="Bullish liquidity sweep + displacement + trend + volume",
            quality="A",
        )

    # BALA SELL
    if (
        bearish_trend
        and bearish_sweep
        and bearish_displacement
        and volume_ok
    ):
        entry = float(c["close"])
        stop = float(max(p["high"], c["high"]) + atr * 0.25)

        risk = stop - entry

        if risk <= 0:
            return None

        return Signal(
            side="SELL",
            entry=entry,
            stop_loss=stop,
            target_1=entry - risk * 1.5,
            target_2=entry - risk * 2.5,
            reason="Bearish liquidity sweep + displacement + trend + volume",
            quality="A",
        )

    return None
