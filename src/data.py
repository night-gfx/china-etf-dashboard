from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data_etfs.csv"


@dataclass
class ResolvedSeries:
    label: str
    index_name: str
    index_url: str
    etf_name: str
    isin: str
    inception: pd.Timestamp
    ter: float
    distribution: str
    yahoo_ticker: str
    quote_currency: str
    series_eur: pd.Series


def load_registry() -> pd.DataFrame:
    df = pd.read_csv(REGISTRY_PATH, parse_dates=["inception"])
    df = df.sort_values(["index_order", "inception", "etf_name"]).reset_index(drop=True)
    df["label"] = df["etf_name"] + " (" + df["index_name"] + ")"
    return df


def oldest_candidate_per_index(registry: pd.DataFrame) -> pd.DataFrame:
    return (
        registry.sort_values(["index_order", "inception"])
        .groupby("index_name", sort=False, as_index=False)
        .first()
    )


def _clean_download(df: pd.DataFrame, ticker: str) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)

    # yfinance may return either ordinary columns or a ticker-level MultiIndex.
    if isinstance(df.columns, pd.MultiIndex):
        if "Adj Close" in df.columns.get_level_values(0):
            x = df["Adj Close"]
        elif "Close" in df.columns.get_level_values(0):
            x = df["Close"]
        else:
            return pd.Series(dtype=float)
        if isinstance(x, pd.DataFrame):
            if ticker in x.columns:
                s = x[ticker]
            else:
                s = x.iloc[:, 0]
        else:
            s = x
    else:
        col = "Adj Close" if "Adj Close" in df.columns else "Close" if "Close" in df.columns else None
        if col is None:
            return pd.Series(dtype=float)
        s = df[col]

    s = pd.to_numeric(s, errors="coerce").dropna()
    if isinstance(s.index, pd.DatetimeIndex):
        if s.index.tz is not None:
            s.index = s.index.tz_localize(None)
        s.index = s.index.normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


def download_adjusted_close(ticker: str, start: str = "2000-01-01") -> pd.Series:
    """Yahoo adjusted close: practical ETF total-return proxy incl. distributions/splits."""
    df = yf.download(
        ticker,
        start=start,
        auto_adjust=False,
        actions=False,
        progress=False,
        threads=False,
        timeout=20,
    )
    return _clean_download(df, ticker)


def detect_currency(ticker: str, fallback: str = "EUR") -> str:
    try:
        fi = yf.Ticker(ticker).fast_info
        cur = fi.get("currency") if hasattr(fi, "get") else fi["currency"]
        if cur:
            return str(cur)
    except Exception:
        pass
    return str(fallback or "EUR").upper()


def _normalize_quote_units(series: pd.Series, currency: str) -> tuple[pd.Series, str]:
    currency = currency.upper()
    if currency in {"GBP", "GBX", "GBPENCE", "GBP PENCE", "GBP."}:
        # Yahoo commonly reports London pence instruments as GBp/GBX. If metadata
        # identifies pence, convert to pounds. If it says GBP, leave unchanged.
        return series, "GBP"
    if currency in {"GBP", "EUR", "USD", "CHF", "HKD", "SGD", "JPY", "CNY", "CNH"}:
        return series, currency
    if currency in {"GBPENCE", "GBP_PENCE", "GBPENCESTERLING", "GBPENCESTERLING"}:
        return series / 100.0, "GBP"
    if currency in {"GBPENCE", "GBPC"}:
        return series / 100.0, "GBP"
    # yfinance often returns the exact token "GBp" before upper-casing -> GBP.
    # We cannot distinguish it after upper-casing; the first candidate is EUR/Xetra
    # for all registry rows, so this is only a fallback edge case.
    return series, currency


def fx_to_eur(currency: str, index: pd.DatetimeIndex) -> pd.Series:
    currency = currency.upper()
    if currency == "EUR":
        return pd.Series(1.0, index=index)
    pair = f"{currency}EUR=X"
    fx = download_adjusted_close(pair, start=max("2000-01-01", str(index.min().date())))
    if fx.empty:
        raise RuntimeError(f"Kein Yahoo-FX-Kurs für {pair} verfügbar.")
    fx = fx.reindex(index).ffill().bfill()
    return fx


def convert_to_eur(series: pd.Series, currency: str) -> tuple[pd.Series, str]:
    raw_currency = str(currency or "EUR")
    # Handle Yahoo's GBp/GBX explicitly before capitalization.
    if raw_currency in {"GBp", "GBX", "GBp."}:
        series = series / 100.0
        currency = "GBP"
    else:
        series, currency = _normalize_quote_units(series, raw_currency.upper())

    if currency == "EUR":
        return series, currency
    fx = fx_to_eur(currency, series.index)
    return (series * fx).dropna(), currency


def resolve_row(row: pd.Series) -> ResolvedSeries:
    errors: list[str] = []
    for ticker in str(row["yahoo_candidates"]).split("|"):
        ticker = ticker.strip()
        if not ticker:
            continue
        try:
            s = download_adjusted_close(ticker)
            if len(s) < 30:
                errors.append(f"{ticker}: zu wenig Daten")
                continue
            currency = detect_currency(ticker, str(row.get("fallback_currency", "EUR")))
            s_eur, detected = convert_to_eur(s, currency)
            if len(s_eur) < 30:
                errors.append(f"{ticker}: zu wenig EUR-Daten")
                continue
            label = f'{row["etf_name"]} ({row["index_name"]})'
            return ResolvedSeries(
                label=label,
                index_name=str(row["index_name"]),
                index_url=str(row["index_url"]),
                etf_name=str(row["etf_name"]),
                isin=str(row["isin"]),
                inception=pd.Timestamp(row["inception"]),
                ter=float(row["ter"]),
                distribution=str(row["distribution"]),
                yahoo_ticker=ticker,
                quote_currency=detected,
                series_eur=s_eur.rename(label),
            )
        except Exception as exc:
            errors.append(f"{ticker}: {exc}")
    raise RuntimeError("; ".join(errors) or "Kein Yahoo-Ticker verfügbar")


def resolve_oldest_available_for_index(index_name: str, registry: pd.DataFrame) -> ResolvedSeries:
    """Try ETFs in fund-inception order; first Yahoo-resolvable series wins."""
    subset = registry[registry["index_name"] == index_name].sort_values("inception")
    errors: list[str] = []
    for _, row in subset.iterrows():
        try:
            return resolve_row(row)
        except Exception as exc:
            errors.append(f'{row["etf_name"]}: {exc}')
    raise RuntimeError(f"Keine Yahoo-Serie für {index_name}. " + " | ".join(errors))


def resolve_selected_rows(rows: Iterable[pd.Series]) -> tuple[list[ResolvedSeries], list[str]]:
    resolved: list[ResolvedSeries] = []
    warnings: list[str] = []
    for row in rows:
        try:
            resolved.append(resolve_row(row))
        except Exception as exc:
            warnings.append(f'{row["etf_name"]}: {exc}')
    return resolved, warnings


def combine_series(items: list[ResolvedSeries]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    return pd.concat([x.series_eur for x in items], axis=1).sort_index()
