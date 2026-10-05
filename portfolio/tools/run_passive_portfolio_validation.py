"""
Passive Long-Only Portfolio Full Validation Diagnostic
Runs the naive buy-and-hold through the same diligence every active strategy received:
1. Per-instrument & per-asset-class concentration/attribution
2. Chronological stability (3 sub-periods: GFC, QE, Late Cycle)
3. N_eff for the long-only exposure pattern
4. OOS validation (only run if in-sample gate is passed)
"""
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
import yfinance as yf
from core.multi_asset_engine import MultiAssetConfig

MULTI_ASSET_TICKERS = {
    'SP500': 'SPY', 'NASDAQ': 'QQQ', 'RUSSELL': 'IWM', 'DOW': 'DIA',
    'US10Y': 'IEF', 'US30Y': 'TLT',
    'GOLD': 'GLD', 'CRUDE_OIL': 'USO', 'SILVER': 'SLV', 'NAT_GAS': 'UNG',
    'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'USDJPY': 'JPY=X',
    'AUDUSD': 'AUDUSD=X', 'USDCAD': 'CAD=X'
}

ASSET_CLASSES = MultiAssetConfig.ASSET_CLASSES


# -----------------------------------------------------------
# Engine: Long-Only Vol-Targeted Buy & Hold
# -----------------------------------------------------------
def run_long_only_engine(prices_df: pd.DataFrame):
    """
    Always long, vol-targeted portfolio.
    Returns daily_returns series, weights_history, and asset_contrib DataFrame.
    """
    tickers = list(prices_df.columns)
    n = len(tickers)
    daily_returns = prices_df.pct_change().fillna(0.0)
    rolling_vol = (
        daily_returns.rolling(window=MultiAssetConfig.VOL_ROLLING_DAYS).std()
        .fillna(0.01) * np.sqrt(MultiAssetConfig.TRADING_DAYS_PER_YEAR)
    ).clip(lower=0.02)

    inst_target_vol = MultiAssetConfig.TARGET_ANNUAL_VOL / np.sqrt(n)
    month_ends = prices_df.groupby(pd.Grouper(freq='ME')).apply(lambda x: x.index[-1] if len(x) > 0 else None)
    rebalance_dates = set(month_ends.dropna())

    weights_history = pd.DataFrame(0.0, index=prices_df.index, columns=tickers)
    current_weights = pd.Series(0.0, index=tickers)

    for i in range(len(prices_df)):
        date = prices_df.index[i]
        if date in rebalance_dates and i >= MultiAssetConfig.VOL_ROLLING_DAYS:
            vol = rolling_vol.loc[date]
            current_weights = inst_target_vol / vol
        weights_history.loc[date] = current_weights

    weights_history = weights_history.shift(1).fillna(0.0)
    asset_contrib = weights_history * daily_returns
    gross = asset_contrib.sum(axis=1)
    wt_changes = weights_history.diff().abs().fillna(0.0)
    costs = wt_changes.sum(axis=1) * MultiAssetConfig.SPREAD_PCT + \
            weights_history.abs().sum(axis=1) * MultiAssetConfig.DAILY_CARRY_PCT
    net = gross - costs

    active = net[weights_history.abs().sum(axis=1) > 0]
    ac_net = asset_contrib.copy()
    for col in ac_net.columns:
        ac_net[col] -= (wt_changes[col] * MultiAssetConfig.SPREAD_PCT + weights_history[col].abs() * MultiAssetConfig.DAILY_CARRY_PCT)

    return active, weights_history, ac_net


def perf_stats(daily_rets: pd.Series, label: str = ""):
    if len(daily_rets) == 0:
        return {}
    eq = (1.0 + daily_rets).cumprod()
    yrs = len(daily_rets) / 252.0
    ann_ret = (eq.iloc[-1] ** (1.0 / yrs)) - 1.0 if yrs > 0 else 0.0
    ann_vol = daily_rets.std() * np.sqrt(252)
    sharpe = (daily_rets.mean() * 252) / ann_vol if ann_vol > 0 else 0.0
    mdd = ((eq.cummax() - eq) / eq.cummax()).max()
    return {"ann_return": ann_ret, "ann_vol": ann_vol, "sharpe": sharpe, "max_dd": mdd, "years": yrs}


def run_validation(prices_df: pd.DataFrame, label: str = "Dev Set"):
    tickers = list(prices_df.columns)
    daily_rets, weights_history, ac_net = run_long_only_engine(prices_df)
    p = perf_stats(daily_rets, label)
    return p, daily_rets, ac_net


# -----------------------------------------------------------
# Main
# -----------------------------------------------------------
def main():
    print("="*110)
    print(" PASSIVE LONG-ONLY PORTFOLIO: FULL VALIDATION DIAGNOSTIC")
    print("="*110 + "\n")

    # Fetch data
    print("Fetching data...")
    raw = yf.download(list(MULTI_ASSET_TICKERS.values()), start="2004-01-01", end="2026-01-01", interval="1d")
    close_df = raw['Close'].copy()
    inv = {v: k for k, v in MULTI_ASSET_TICKERS.items()}
    close_df = close_df.rename(columns=inv).sort_index().dropna(how='all')

    dev_df  = close_df[(close_df.index >= "2007-04-18") & (close_df.index < "2020-01-01")].dropna().copy()
    oos_df  = close_df[(close_df.index >= "2020-01-01") & (close_df.index <= "2025-12-31")].dropna().copy()

    tickers = list(dev_df.columns)
    n = len(tickers)

    # ---- DIAGNOSTIC 1: Full Dev Set Performance + Attribution ----
    print("\n" + "="*110)
    print(" DIAGNOSTIC 1: Full Dev Set Performance & Attribution (2007–2020)")
    print("="*110 + "\n")

    dev_rets, dev_wt, dev_ac = run_long_only_engine(dev_df)
    p_dev = perf_stats(dev_rets)
    print(f"  Full 13-Year Dev Set (2007-2020):  Sharpe {p_dev['sharpe']:+.3f} | Ann. Return {p_dev['ann_return']*100:+.2f}% | Ann. Vol {p_dev['ann_vol']*100:.2f}% | Max DD {p_dev['max_dd']*100:.2f}%\n")

    # per-instrument attribution
    print(f"  {'Ticker':<12} {'Asset Class':<15} {'Ann Return':>12} {'Sharpe':>10} {'Cum Return %':>14} {'% of Total P&L':>16}")
    print("  " + "-"*82)

    total_cum = 0.0
    inst_info = {}
    for tic in tickers:
        s = dev_ac[tic].loc[dev_rets.index]
        p = perf_stats(s)
        cum = s.sum()
        total_cum += cum
        ac = ASSET_CLASSES.get(tic, 'Other')
        inst_info[tic] = {"ann_return": p.get("ann_return", 0), "sharpe": p.get("sharpe", 0), "cum": cum, "ac": ac}

    for tic, info in sorted(inst_info.items(), key=lambda x: -x[1]['cum']):
        pct_of_total = info['cum'] / total_cum * 100 if total_cum != 0 else 0.0
        print(f"  {tic:<12} {info['ac']:<15} {info['ann_return']*100:>+11.2f}% {info['sharpe']:>+10.3f} {info['cum']*100:>+13.2f}%   {pct_of_total:>10.1f}%")

    # Asset class rollup
    print("\n  ASSET CLASS ROLLUP:")
    print(f"  {'Class':<20} {'Cum Return %':>14} {'% of Total P&L':>16}")
    print("  " + "-"*55)
    ac_totals = {}
    for tic, info in inst_info.items():
        ac_totals.setdefault(info['ac'], 0.0)
        ac_totals[info['ac']] += info['cum']
    for ac, cum in sorted(ac_totals.items(), key=lambda x: -x[1]):
        pct = cum / total_cum * 100 if total_cum != 0 else 0.0
        print(f"  {ac:<20} {cum*100:>+13.2f}%   {pct:>10.1f}%")

    # ---- DIAGNOSTIC 2: Sub-Period Stability ----
    print("\n" + "="*110)
    print(" DIAGNOSTIC 2: Chronological Sub-Period Stability")
    print("="*110 + "\n")

    sub_periods = [
        ("2008-01-01", "2012-01-01", "Period 1: GFC & Recovery (2008-2011)"),
        ("2012-01-01", "2016-01-01", "Period 2: QE / Bull Market (2012-2015)"),
        ("2016-01-01", "2020-01-01", "Period 3: Late Cycle / Range (2016-2019)")
    ]
    all_periods_pass = True
    for s_d, e_d, label in sub_periods:
        sub_rets = dev_rets[(dev_rets.index >= s_d) & (dev_rets.index < e_d)]
        sp = perf_stats(sub_rets)
        status = "✓" if sp['sharpe'] > 0 else "✗ NEGATIVE"
        if sp['sharpe'] <= 0:
            all_periods_pass = False
        print(f"  {label:<48}: Sharpe {sp['sharpe']:+.3f} | Ann. Return {sp['ann_return']*100:+.2f}% | Max DD {sp['max_dd']*100:.2f}%  {status}")

    if all_periods_pass:
        print("\n  -> Gate: ALL 3 sub-periods positive. Chronological stability: PASSED.")
    else:
        print("\n  -> Gate: 1+ sub-periods negative. Chronological stability: FAILED.")

    # ---- DIAGNOSTIC 3: N_eff for Long-Only Configuration ----
    print("\n" + "="*110)
    print(" DIAGNOSTIC 3: N_eff — Effective Diversification (Long-Only Correlation Structure)")
    print("="*110 + "\n")

    # Use the actual daily contribution returns of the long-only portfolio for N_eff
    daily_inst_rets = dev_df.pct_change().dropna()
    corr_m = daily_inst_rets.corr()
    n_c = len(corr_m)
    off_diag = corr_m.values[np.triu_indices(n_c, k=1)]
    avg_rho = np.mean(off_diag)
    eigs = np.linalg.eigvals(corr_m.values)
    n_eff = (np.sum(eigs)**2) / np.sum(eigs**2)

    print(f"  Total Instruments (N):               {n_c}")
    print(f"  Avg Pairwise Correlation (all-long):  {avg_rho:+.3f}")
    print(f"  Effective Bets (Eigenvalue Ratio):   {n_eff:.2f} out of {n_c}")
    if n_eff >= 4.0:
        print(f"  -> Diversification Gate: Effective N ({n_eff:.2f}) >= 4.0. PASSED.")
        neff_pass = True
    else:
        print(f"  -> Diversification Gate: Effective N ({n_eff:.2f}) < 4.0. FAILED.")
        neff_pass = False

    # ---- GATE DECISION ----
    print("\n" + "="*110)
    print(" GATE DECISION: Is the portfolio eligible for OOS shot?")
    print("="*110 + "\n")

    gates = {
        "Sharpe > 0 (Dev Set)": p_dev['sharpe'] > 0,
        "All 3 Sub-Periods Positive Sharpe": all_periods_pass,
        "N_eff >= 4.0": neff_pass
    }
    for g_label, result in gates.items():
        print(f"  {'✓' if result else '✗'} {g_label}: {'PASS' if result else 'FAIL'}")

    oos_eligible = all(gates.values())
    print(f"\n  {'-> Portfolio is ELIGIBLE for OOS validation.' if oos_eligible else '-> Portfolio is NOT ELIGIBLE for OOS validation.'}")

    if not oos_eligible:
        print("  Stopping here. OOS gate not reached.")
        return

    # ---- DIAGNOSTIC 5: OOS Validation ----
    print("\n" + "="*110)
    print(" DIAGNOSTIC 5: SINGLE-SHOT OOS VALIDATION (2020–2025) — THIS SHOT IS NOW CONSUMED")
    print("="*110 + "\n")

    oos_rets, oos_wt, oos_ac = run_long_only_engine(oos_df)
    p_oos = perf_stats(oos_rets)
    print(f"  OOS (2020-2025):  Sharpe {p_oos['sharpe']:+.3f} | Ann. Return {p_oos['ann_return']*100:+.2f}% | Ann. Vol {p_oos['ann_vol']*100:.2f}% | Max DD {p_oos['max_dd']*100:.2f}%\n")

    print(f"  {'Ticker':<12} {'Asset Class':<15} {'Ann Return':>12} {'Sharpe':>10} {'Cum Return %':>14} {'% of Total P&L':>16}")
    print("  " + "-"*82)
    total_oos_cum = 0.0
    oos_info = {}
    for tic in tickers:
        s = oos_ac[tic].loc[oos_rets.index]
        po = perf_stats(s)
        cum = s.sum()
        total_oos_cum += cum
        ac = ASSET_CLASSES.get(tic, 'Other')
        oos_info[tic] = {"ann_return": po.get("ann_return", 0), "sharpe": po.get("sharpe", 0), "cum": cum, "ac": ac}

    for tic, info in sorted(oos_info.items(), key=lambda x: -x[1]['cum']):
        pct = info['cum'] / total_oos_cum * 100 if total_oos_cum != 0 else 0.0
        print(f"  {tic:<12} {info['ac']:<15} {info['ann_return']*100:>+11.2f}% {info['sharpe']:>+10.3f} {info['cum']*100:>+13.2f}%   {pct:>10.1f}%")

    print("\n  OOS ASSET CLASS ROLLUP:")
    print(f"  {'Class':<20} {'Cum Return %':>14} {'% of Total P&L':>16}")
    print("  " + "-"*55)
    oos_ac_totals = {}
    for tic, info in oos_info.items():
        oos_ac_totals.setdefault(info['ac'], 0.0)
        oos_ac_totals[info['ac']] += info['cum']
    for ac, cum in sorted(oos_ac_totals.items(), key=lambda x: -x[1]):
        pct = cum / total_oos_cum * 100 if total_oos_cum != 0 else 0.0
        print(f"  {ac:<20} {cum*100:>+13.2f}%   {pct:>10.1f}%")

    print("\n" + "="*110 + "\n")


if __name__ == "__main__":
    main()
