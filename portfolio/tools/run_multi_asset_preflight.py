"""
Pre-Flight Diagnostic Suite for Multi-Asset-Class Momentum (Equities + Bonds + Commodities + FX)
Executes Rule 7 Protocol:
1. Correlation & Effective Diversification (N_eff) across 15 Multi-Asset Instruments
2. Untuned Baseline Simulation (12-Month Formation Window, 2007-2020 Dev Set)
3. Walk-Forward Sub-Period Stability Check (3 Chronological Blocks)
4. Asset-Class & Per-Instrument Attribution Breakdown
"""
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
import yfinance as yf
from core.multi_asset_engine import MultiAssetEngine, MultiAssetConfig

MULTI_ASSET_TICKERS = {
    'SP500': 'SPY', 'NASDAQ': 'QQQ', 'RUSSELL': 'IWM', 'DOW': 'DIA',
    'US10Y': 'IEF', 'US30Y': 'TLT',
    'GOLD': 'GLD', 'CRUDE_OIL': 'USO', 'SILVER': 'SLV', 'NAT_GAS': 'UNG',
    'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'USDJPY': 'JPY=X', 'AUDUSD': 'AUDUSD=X', 'USDCAD': 'CAD=X'
}

def run_multi_asset_preflight():
    print("="*105)
    print(" PRE-FLIGHT DIAGNOSTIC SUITE: MULTI-ASSET TIME SERIES MOMENTUM")
    print(" Universe: 15 Instruments Across 4 Asset Classes (Equities + Bonds + Commodities + FX)")
    print(" Causal Thesis: Slow institutional information diffusion & portfolio rebalancing (Moskowitz et al. 2012)")
    print("="*105 + "\n")

    print("Fetching 15+ years of continuous daily data for 15 Multi-Asset Instruments...")
    raw = yf.download(list(MULTI_ASSET_TICKERS.values()), start="2004-01-01", end="2026-01-01", interval="1d")
    close_df = raw['Close'].copy()
    inv_map = {v: k for k, v in MULTI_ASSET_TICKERS.items()}
    close_df = close_df.rename(columns=inv_map).sort_index().dropna(how='all')

    # Define Development set (2007-04-18 to 2020-01-01) where all 15 instruments have history
    dev_df = close_df[(close_df.index >= "2007-04-18") & (close_df.index < "2020-01-01")].dropna().copy()
    oos_df = close_df[(close_df.index >= "2020-01-01") & (close_df.index <= "2025-12-31")].dropna().copy()

    print(f"Data Split Loaded:")
    print(f"  Development Set: {dev_df.index.min().strftime('%Y-%m-%d')} to {dev_df.index.max().strftime('%Y-%m-%d')} ({len(dev_df)} days)")
    print(f"  Out-of-Sample Set: {oos_df.index.min().strftime('%Y-%m-%d')} to {oos_df.index.max().strftime('%Y-%m-%d')} ({len(oos_df)} days - SEALED)")

    # --- STEP 1: Correlation & Effective Diversification (N_eff) ---
    print("\n" + "="*105)
    print(" DIAGNOSTIC 1: CORRELATION & EFFECTIVE DIVERSIFICATION (N_eff)")
    print("="*105 + "\n")

    daily_rets = dev_df.pct_change().dropna()
    corr_matrix = daily_rets.corr()

    n = len(corr_matrix)
    off_diag_corrs = corr_matrix.values[np.triu_indices(n, k=1)]
    avg_corr = np.mean(off_diag_corrs)

    eigenvalues = np.linalg.eigvals(corr_matrix.values)
    n_eff_eigen = (np.sum(eigenvalues)**2) / np.sum(eigenvalues**2)

    print(f"Multi-Asset Diversification Metrics:")
    print(f"  Total Instruments (N):               {n} across 4 Asset Classes")
    print(f"  Average Pairwise Correlation (rho):  {avg_corr:+.3f}")
    print(f"  Effective Bets (Eigenvalue Ratio):  {n_eff_eigen:.2f} out of {n}")
    print(f"  FX-Only Baseline Effective Bets:     3.20 out of 7")
    print(f"  -> Diversification Gain:             +{n_eff_eigen - 3.20:.2f} additional independent risk drivers!")

    # --- STEP 2: Untuned Baseline Run (12-Month Formation Window, 2007–2020 Dev Set) ---
    print("\n\n" + "="*105)
    print(" DIAGNOSTIC 2: UNTUNED BASELINE SIMULATION (12-Month Formation Window, 2007–2020 Dev Set)")
    print("="*105 + "\n")

    engine = MultiAssetEngine(dev_df)
    res_12m = engine.run_simulation(formation_months=12)

    print(f"  FULL 13-YEAR MULTI-ASSET DEV SET PERFORMANCE (2007–2020):")
    print(f"    Annualized Return:       {res_12m['ann_return']*100:+.2f}% per year")
    print(f"    Annualized Volatility:   {res_12m['ann_vol']*100:.2f}% per year")
    print(f"    Sharpe Ratio:            {res_12m['sharpe']:+.3f}")
    print(f"    Max Drawdown:            {res_12m['max_drawdown']*100:.2f}%")
    print(f"    Calmar Ratio:            {res_12m['calmar']:+.3f}")

    # --- STEP 3: Sub-Period Stability Check ---
    print("\n\n" + "="*105)
    print(" DIAGNOSTIC 3: SUB-PERIOD STABILITY BREAKDOWN (3 Chronological Blocks)")
    print("="*105 + "\n")

    sub_periods = [
        ("2008-01-01", "2012-01-01", "Period 1: GFC Crisis & Recovery (2008 – 2011)"),
        ("2012-01-01", "2016-01-01", "Period 2: QE / Rate Drought (2012 – 2015)"),
        ("2016-01-01", "2020-01-01", "Period 3: Late Cycle / Range (2016 – 2019)")
    ]

    for start_d, end_d, label in sub_periods:
        sub_rets = res_12m['daily_returns'][(res_12m['daily_returns'].index >= start_d) & (res_12m['daily_returns'].index < end_d)]
        if len(sub_rets) > 0:
            sub_eq = (1.0 + sub_rets).cumprod()
            sub_yrs = len(sub_rets) / 252.0
            sub_ann_ret = (sub_eq.iloc[-1] ** (1.0 / sub_yrs)) - 1.0
            sub_ann_vol = sub_rets.std() * np.sqrt(252)
            sub_sharpe = (sub_rets.mean() * 252) / sub_ann_vol if sub_ann_vol > 0 else 0.0
            sub_peak = sub_eq.cummax()
            sub_mdd = ((sub_peak - sub_eq) / sub_peak).max()
            
            print(f"    {label:<52}: Sharpe {sub_sharpe:+.3f} | Ann. Return {sub_ann_ret*100:+.2f}% | Max DD {sub_mdd*100:.2f}%")

    # --- STEP 4: Asset Class & Per-Instrument Attribution ---
    print("\n\n" + "="*105)
    print(" DIAGNOSTIC 4: ASSET-CLASS & PER-INSTRUMENT ATTRIBUTION")
    print("="*105 + "\n")

    print("  ASSET CLASS SUMMARY:")
    print(f"    {'Asset Class':<18} {'Ann Return':>12} {'Sharpe':>10} {'Cum Return %':>15}")
    print("    " + "-"*60)
    for ac, info in res_12m['asset_class_summary'].items():
        print(f"    {ac:<18} {info['ann_return']*100:>+11.2f}% {info['sharpe']:>+10.3f} {info['cum_return']*100:>+14.2f}%")

    print("\n  INDIVIDUAL INSTRUMENT BREAKDOWN:")
    print(f"    {'Ticker':<12} {'Asset Class':<15} {'Ann Return':>12} {'Sharpe':>10} {'Long Cum %':>12} {'Short Cum %':>12} {'Net Cum %':>12}")
    print("    " + "-"*85)

    total_long = 0.0
    total_short = 0.0

    for ticker, info in res_12m['inst_breakdown'].items():
        print(f"    {ticker:<12} {info['asset_class']:<15} {info['ann_return']*100:>+11.2f}% {info['sharpe']:>+10.3f} {info['long_cum_return']*100:>+11.2f}% {info['short_cum_return']*100:>+11.2f}% {info['net_cum_return']*100:>+11.2f}%")
        total_long += info['long_cum_return']
        total_short += info['short_cum_return']

    print("    " + "-"*85)
    print(f"    {'PORTFOLIO':<12} {'ALL (15)':<15} {res_12m['ann_return']*100:>+11.2f}% {res_12m['sharpe']:>+10.3f} {total_long*100:>+11.2f}% {total_short*100:>+11.2f}% {(total_long+total_short)*100:>+11.2f}%")

    print("\n" + "="*105 + "\n")

if __name__ == "__main__":
    run_multi_asset_preflight()
