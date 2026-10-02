"""
BTCUSDT market data module.

Uses Binance public market data only.
No API key or trading permission is required here.
"""

import time
import requests
import pandas as pd


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


def get_klines(
    symbol="BTCUSDT",
    interval="1m",
    limit=200,
):
    """Fetch recent BTC candles from Binance public API."""

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }

    response = requests.get(
        BINANCE_KLINES_URL,
        params=params,
        timeout=10,
    )

    response.raise_for_status()

    data = response.json()

    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trades",
        "taker_buy_base",
        "taker_buy_quote",
        "unused",
    ]

    df = pd.DataFrame(data, columns=columns)

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["open_time"] = pd.to_datetime(
        df["open_time"],
        unit="ms",
        utc=True,
    )

    df["close_time"] = pd.to_datetime(
        df["close_time"],
        unit="ms",
        utc=True,
    )

    return df


def get_latest_price(symbol="BTCUSDT"):
    """Return the latest BTCUSDT price."""

    url = "https://api.binance.com/api/v3/ticker/price"

    response = requests.get(
        url,
        params={"symbol": symbol},
        timeout=10,
    )

    response.raise_for_status()

    return float(response.json()["price"])


if __name__ == "__main__":
    candles = get_klines("BTCUSDT", "1m", 5)

    print("BALA BTC MARKET DATA")
    print("--------------------")
    print(candles[["open_time", "open", "high", "low", "close", "volume"]])

    print()
    print("Latest BTCUSDT:", get_latest_price("BTCUSDT"))
