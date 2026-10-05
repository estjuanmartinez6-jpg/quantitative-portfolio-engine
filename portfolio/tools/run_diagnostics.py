"""
Diagnostic Suite: 
1. Pairwise Correlation & Effective Diversification (N_eff)
2. Extended History Test (2003-2019 Dev Set covering pre-2009 cycle)
"""
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
import yfinance as yf
from core.data_loader import load_split_datasets, TICKERS
from core.momentum_engine import MomentumEngine

def run_diagnostics():
    print("="*100)
    print(" DIAGNOSTIC 1: CORRELATION & EFFECTIVE DIVERSIFICATION (N_eff)")
    print("="*100 + "\n")

    dev_df, _ = load_split_datasets()
    daily_rets = dev_df.pct_change().dropna()

    corr_matrix = daily_rets.corr()
    print("Pairwise Correlation Matrix (2010–2020 Dev Set):")
    print(corr_matrix.round(3))

    # Calculate average pairwise correlation (excluding self-correlation on diagonal)
    n = len(corr_matrix)
    off_diag_corrs = corr_matrix.values[np.triu_indices(n, k=1)]
    avg_corr = np.mean(off_diag_corrs)

    # Method 1: Eigenvalue Ratio N_eff = (sum lambda)^2 / sum(lambda^2)
    eigenvalues = np.linalg.eigvals(corr_matrix.values)
    n_eff_eigen = (np.sum(eigenvalues)**2) / np.sum(eigenvalues**2)

    # Method 2: Simple Proxy 1 / avg_corr
    n_eff_proxy = 1.0 / avg_corr if avg_corr > 0 else n

    print(f"\nDiversification Metrics:")
    print(f"  Total Instruments (N):               {n}")
    print(f"  Average Pairwise Correlation (rho):  {avg_corr:+.3f}")
    print(f"  Effective Bets (Eigenvalue Ratio):  {n_eff_eigen:.2f} out of {n}")
    print(f"  Effective Bets (1 / avg_rho proxy):  {n_eff_proxy:.2f} out of {n}")
    
    if n_eff_eigen < 3.5:
        print(f"  -> Structural Finding: High USD-centric co-movement reduces effective diversification to only ~{n_eff_eigen:.1f} independent bets.")

    print("\n" + "="*100)
    print(" DIAGNOSTIC 2: EXTENDED HISTORY TEST (2003–2019 Dev Set)")
    print("="*100 + "\n")

    print("Fetching extended daily data starting from 2003-01-01...")
    raw_ext = yf.download(list(TICKERS.values()), start="2003-01-01", end="2026-01-01", interval="1d")
    close_ext = raw_ext['Close'].copy()
    inv_map = {v: k for k, v in TICKERS.items()}
    close_ext = close_ext.rename(columns=inv_map).sort_index().dropna(how='all')

    # Define extended Dev set (2003-01-01 to 2019-12-31) and OOS (2020 to 2025)
    ext_dev_df = close_ext[(close_ext.index >= "2003-01-01") & (close_ext.index < "2020-01-01")].dropna().copy()
    
    print(f"Extended Development Set Loaded:")
    print(f"  Date Range: {ext_dev_df.index.min().strftime('%Y-%m-%d')} to {ext_dev_df.index.max().strftime('%Y-%m-%d')} ({len(ext_dev_df)} trading days)")

    ext_engine = MomentumEngine(ext_dev_df)
    res_ext = ext_engine.run_simulation(formation_months=12)

    print(f"\n  EXTENDED 17-YEAR DEV SET PERFORMANCE (2003–2019):")
    print(f"    Annualized Return:       {res_ext['ann_return']*100:+.2f}% per year")
    print(f"    Annualized Volatility:   {res_ext['ann_vol']*100:.2f}% per year")
    print(f"    Sharpe Ratio:            {res_ext['sharpe']:+.3f}")
    print(f"    Max Drawdown:            {res_ext['max_drawdown']*100:.2f}%")
    print(f"    Calmar Ratio:            {res_ext['calmar']:+.3f}")

    # Sub-Period Stability across 4 Multi-Year Cycles
    print("\n  SUB-PERIOD STABILITY BREAKDOWN (4 Chronological Blocks):")
    
    ext_sub_periods = [
        ("2004-01-01", "2008-01-01", "Period 1: Pre-GFC Cycle (2004 – 2007)"),
        ("2008-01-01", "2012-01-01", "Period 2: GFC & Recovery (2008 – 2011)"),
        ("2012-01-01", "2016-01-01", "Period 3: QE / Central Bank Drought (2012 – 2015)"),
        ("2016-01-01", "2020-01-01", "Period 4: Late Cycle / Range (2016 – 2019)")
    ]

    for start_d, end_d, label in ext_sub_periods:
        sub_rets = res_ext['daily_returns'][(res_ext['daily_returns'].index >= start_d) & (res_ext['daily_returns'].index < end_d)]
        if len(sub_rets) > 0:
            sub_eq = (1.0 + sub_rets).cumprod()
            sub_yrs = len(sub_rets) / 252.0
            sub_ann_ret = (sub_eq.iloc[-1] ** (1.0 / sub_yrs)) - 1.0
            sub_ann_vol = sub_rets.std() * np.sqrt(252)
            sub_sharpe = (sub_rets.mean() * 252) / sub_ann_vol if sub_ann_vol > 0 else 0.0
            sub_peak = sub_eq.cummax()
            sub_mdd = ((sub_peak - sub_eq) / sub_peak).max()
            
            print(f"    {label:<48}: Sharpe {sub_sharpe:+.3f} | Ann. Return {sub_ann_ret*100:+.2f}% | Max DD {sub_mdd*100:.2f}%")

    print("\n  PER-INSTRUMENT BREAKDOWN (Extended 2003–2019):")
    print(f"    {'Ticker':<10} {'Ann Return':>12} {'Sharpe':>10} {'Long Cum %':>12} {'Short Cum %':>12} {'Net Cum %':>12}")
    print("    " + "-"*70)
    for ticker, info in res_ext['inst_breakdown'].items():
        print(f"    {ticker:<10} {info['ann_return']*100:>+11.2f}% {info['sharpe']:>+10.3f} {info['long_cum_return']*100:>+11.2f}% {info['short_cum_return']*100:>+11.2f}% {info['net_cum_return']*100:>+11.2f}%")

    print("\n" + "="*100 + "\n")

if __name__ == "__main__":
    run_diagnostics()
