from __future__ import annotations

import numpy as np
import pandas as pd


def effective_german_equity_etf_tax_rate(
    withholding_tax: float = 0.25,
    solidarity_surcharge: float = 0.055,
    partial_exemption: float = 0.30,
) -> float:
    """Simplified effective rate on taxable gains, excluding church tax."""
    return withholding_tax * (1.0 + solidarity_surcharge) * (1.0 - partial_exemption)


def normalize_100(series: pd.Series) -> pd.Series:
    s = series.dropna()
    if s.empty:
        return s
    return (s / s.iloc[0] * 100.0).rename(series.name)


def after_tax_liquidation_index(series: pd.Series, effective_tax_rate: float) -> pd.Series:
    """
    Hypothetical after-tax liquidation value at each date.

    Positive cumulative gains since the comparison start are taxed once at the
    chosen effective rate. Losses are not credited. This is deliberately a
    simplified German-tax view: no Vorabpauschale, allowances, church tax,
    loss-netting or exact distribution tax timing.
    """
    gross = normalize_100(series)
    gain = gross - 100.0
    taxed_gain = np.where(gain > 0.0, gain * (1.0 - effective_tax_rate), gain)
    out = pd.Series(100.0 + taxed_gain, index=gross.index, name=series.name)
    return out


def transform_frame(
    prices: pd.DataFrame,
    after_tax: bool,
    effective_tax_rate: float,
    common_start: bool,
) -> pd.DataFrame:
    if prices.empty:
        return prices

    if common_start:
        data = prices.dropna(how="any")
        if data.empty:
            return data
        out = {}
        for col in data.columns:
            s = data[col]
            out[col] = (
                after_tax_liquidation_index(s, effective_tax_rate)
                if after_tax
                else normalize_100(s)
            )
        return pd.DataFrame(out)

    out = {}
    for col in prices.columns:
        s = prices[col].dropna()
        if s.empty:
            continue
        out[col] = (
            after_tax_liquidation_index(s, effective_tax_rate)
            if after_tax
            else normalize_100(s)
        )
    return pd.DataFrame(out)
