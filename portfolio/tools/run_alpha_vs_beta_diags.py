"""
Diagnostic: Alpha vs. Beta Isolation & Naive Long Benchmark comparison
1. Naive Long-Only Buy-and-Hold Benchmarking (equally risk-weighted, monthly rebalanced)
2. Short-Side Performance & 2008 GFC Position History Audit
3. Model Ex-Period 2 (exclude 2012–2015)
4. Data Source Documentation (ETF vs. Futures)
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

class BenchmarkEngine(MultiAssetEngine):
    def run_benchmark_long_only(self) -> dict:
        """
        Runs an equally-risk-weighted buy-and-hold benchmark (Always Long).
        Same volatility targeting, rebalanced monthly.
        """
        raw_signals = pd.DataFrame(1.0, index=self.prices.index, columns=self.tickers)
        
        # Month-end rebalance dates
        month_ends = self.prices.groupby(pd.Grouper(freq=MultiAssetConfig.REBALANCE_FREQ)).apply(lambda x: x.index[-1] if len(x) > 0 else None)
        rebalance_dates = set(month_ends.dropna())

        # Target volatility per instrument
        inst_target_vol = MultiAssetConfig.TARGET_ANNUAL_VOL / np.sqrt(self.n_assets)

        weights_history = pd.DataFrame(0.0, index=self.prices.index, columns=self.tickers)
        current_weights = pd.Series(0.0, index=self.tickers)

        for i in range(len(self.prices)):
            date = self.prices.index[i]
            if date in rebalance_dates and i >= MultiAssetConfig.VOL_ROLLING_DAYS:
                vol = self.rolling_vol.loc[date]
                new_weights = inst_target_vol / vol
                current_weights = new_weights

            weights_history.loc[date] = current_weights

        weights_history = weights_history.shift(1).fillna(0.0)

        # Calculate daily portfolio returns
        asset_contrib = weights_history * self.daily_returns
        gross_daily_returns = asset_contrib.sum(axis=1)

        weight_changes = weights_history.diff().abs().fillna(0.0)
        rebalance_costs = weight_changes.sum(axis=1) * MultiAssetConfig.SPREAD_PCT
        daily_swap_costs = weights_history.abs().sum(axis=1) * MultiAssetConfig.DAILY_CARRY_PCT

        net_daily_returns = gross_daily_returns - rebalance_costs - daily_swap_costs
        active_returns = net_daily_returns[weights_history.abs().sum(axis=1) > 0]

        equity_curve = (1.0 + active_returns).cumprod()
        total_days = len(active_returns)
        years = total_days / MultiAssetConfig.TRADING_DAYS_PER_YEAR

        ann_return = (equity_curve.iloc[-1] ** (1.0 / years)) - 1.0 if years > 0 else 0.0
        ann_vol = active_returns.std() * np.sqrt(MultiAssetConfig.TRADING_DAYS_PER_YEAR)
        sharpe = (active_returns.mean() * MultiAssetConfig.TRADING_DAYS_PER_YEAR) / ann_vol if ann_vol > 0 else 0.0

        peak = equity_curve.cummax()
        drawdowns = (peak - equity_curve) / peak
        max_dd = drawdowns.max()

        return {
            "ann_return": ann_return,
            "ann_vol": ann_vol,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "daily_returns": active_returns,
            "weights_history": weights_history
        }

    def run_simulation_short_only(self, formation_months: int = 12) -> dict:
        """
        Runs TSMOM but keeps ONLY short transitions, setting all long signals to 0.
        """
        formation_days = int(formation_months * 21)
        formation_returns = (self.prices / self.prices.shift(formation_days)) - 1.0
        raw_signals = np.sign(formation_returns).fillna(0.0)
        
        # Enforce short-only by zeroing positive signals
        raw_signals = raw_signals.clip(upper=0.0)

        # Month-end rebalance dates
        month_ends = self.prices.groupby(pd.Grouper(freq=MultiAssetConfig.REBALANCE_FREQ)).apply(lambda x: x.index[-1] if len(x) > 0 else None)
        rebalance_dates = set(month_ends.dropna())

        inst_target_vol = MultiAssetConfig.TARGET_ANNUAL_VOL / np.sqrt(self.n_assets)
        weights_history = pd.DataFrame(0.0, index=self.prices.index, columns=self.tickers)
        current_weights = pd.Series(0.0, index=self.tickers)

        for i in range(len(self.prices)):
            date = self.prices.index[i]
            if date in rebalance_dates and i >= max(formation_days, MultiAssetConfig.VOL_ROLLING_DAYS):
                sig = raw_signals.loc[date]
                vol = self.rolling_vol.loc[date]
                unscaled_weights = inst_target_vol / vol
                # sig is negative or zero
                new_weights = sig * unscaled_weights
                current_weights = new_weights

            weights_history.loc[date] = current_weights

        weights_history = weights_history.shift(1).fillna(0.0)
        asset_contrib = weights_history * self.daily_returns
        gross_daily_returns = asset_contrib.sum(axis=1)

        weight_changes = weights_history.diff().abs().fillna(0.0)
        rebalance_costs = weight_changes.sum(axis=1) * MultiAssetConfig.SPREAD_PCT
        daily_swap_costs = weights_history.abs().sum(axis=1) * MultiAssetConfig.DAILY_CARRY_PCT

        net_daily_returns = gross_daily_returns - rebalance_costs - daily_swap_costs
        active_returns = net_daily_returns[weights_history.abs().sum(axis=1) > 0]

        equity_curve = (1.0 + active_returns).cumprod()
        total_days = len(active_returns)
        years = total_days / MultiAssetConfig.TRADING_DAYS_PER_YEAR

        ann_return = (equity_curve.iloc[-1] ** (1.0 / years)) - 1.0 if years > 0 else 0.0
        ann_vol = active_returns.std() * np.sqrt(MultiAssetConfig.TRADING_DAYS_PER_YEAR)
        sharpe = (active_returns.mean() * MultiAssetConfig.TRADING_DAYS_PER_YEAR) / ann_vol if ann_vol > 0 else 0.0

        peak = equity_curve.cummax()
        drawdowns = (peak - equity_curve) / peak
        max_dd = drawdowns.max()

        # Asset-Class breakdown
        asset_class_daily_ret = {ac: pd.Series(0.0, index=active_returns.index) for ac in set(MultiAssetConfig.ASSET_CLASSES.values())}
        for ticker in self.tickers:
            inst_daily_ret = asset_contrib[ticker] - (weight_changes[ticker] * MultiAssetConfig.SPREAD_PCT) - (weights_history[ticker].abs() * MultiAssetConfig.DAILY_CARRY_PCT)
            inst_active = inst_daily_ret.loc[active_returns.index]
            ac = MultiAssetConfig.ASSET_CLASSES.get(ticker, 'Other')
            asset_class_daily_ret[ac] += inst_active

        asset_class_summary = {}
        for ac, s_ret in asset_class_daily_ret.items():
            ac_ann_ret = s_ret.mean() * MultiAssetConfig.TRADING_DAYS_PER_YEAR
            ac_ann_vol = s_ret.std() * np.sqrt(MultiAssetConfig.TRADING_DAYS_PER_YEAR)
            ac_sharpe = ac_ann_ret / ac_ann_vol if ac_ann_vol > 0 else 0.0
            asset_class_summary[ac] = {
                "ann_return": ac_ann_ret,
                "ann_vol": ac_ann_vol,
                "sharpe": ac_sharpe,
                "cum_return": s_ret.sum()
            }

        return {
            "ann_return": ann_return,
            "ann_vol": ann_vol,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "asset_class_summary": asset_class_summary,
            "weights_history": weights_history
        }

def run_diagnostics():
    print("="*105)
    print(" DIAGNOSTIC SUITE: DETAILED MOMENTUM ALPHA VS LONG-BIAS BETA")
    print("="*105 + "\n")

    # Load dev data
    raw = yf.download(list(MULTI_ASSET_TICKERS.values()), start="2004-01-01", end="2026-01-01", interval="1d")
    close_df = raw['Close'].copy()
    inv_map = {v: k for k, v in MULTI_ASSET_TICKERS.items()}
    close_df = close_df.rename(columns=inv_map).sort_index().dropna(how='all')

    dev_df = close_df[(close_df.index >= "2007-04-18") & (close_df.index < "2020-01-01")].dropna().copy()

    engine = BenchmarkEngine(dev_df)
    
    # 1. Momentum Baseline vs Naive Long-Only Buy-and-Hold
    tsmom = engine.run_simulation(formation_months=12)
    lo = engine.run_benchmark_long_only()

    print("DIAGNOSTIC 1: BENCHMARK COMPARISON (Full 13-Year Dev Set 2007-2020)")
    print("-" * 105)
    print(f" {'Metric':<25} {'TSMOM Baseline':<25} {'Naive Long-Only B&H':<25}")
    print(f" {'Sharpe Ratio':<25} {tsmom['sharpe']:>+14.3f} {lo['sharpe']:>+19.3f}")
    print(f" {'Annualized Return':<25} {tsmom['ann_return']*100:>+13.2f}% {lo['ann_return']*100:>+18.2f}%")
    print(f" {'Annualized Volatility':<25} {tsmom['ann_vol']*100:>+13.2f}% {lo['ann_vol']*100:>+18.2f}%")
    print(f" {'Max Drawdown':<25} {tsmom['max_drawdown']*100:>13.2f}% {lo['max_drawdown']*100:>18.2f}%")
    print("-" * 105 + "\n")

    # 2. Short-Side Audit
    so = engine.run_simulation_short_only(formation_months=12)
    print("DIAGNOSTIC 2: SHORT-SIDE ATTRIBUTION (Short-Only Performance)")
    print("-" * 105)
    print(f" {'Short-Only Metric':<30} {'Performance / Sharpe':<30}")
    print(f" {'Short-Only Sharpe':<30} {so['sharpe']:>+14.3f}")
    print(f" {'Short-Only Annualized Return':<30} {so['ann_return']*100:>+13.2f}%")
    print(f" {'Short-Only Max Drawdown':<30} {so['max_drawdown']*100:>13.2f}%")
    print("\n  Asset Class Breakdown (Short-Only):")
    for ac, info in so['asset_class_summary'].items():
        print(f"    {ac:<20} Ann. Return: {info['ann_return']*100:>+8.2f}% | Sharpe: {info['sharpe']:>+6.3f} | Cum Return: {info['cum_return']*100:>+8.2f}%")
    
    # Audit 2008 GFC Equities Position flipping
    gfc_dates = ["2008-01-31", "2008-06-30", "2008-09-30", "2008-11-28", "2008-12-31"]
    print("\n  Equities Position Audit During 2008 GFC (Month-Ends):")
    print(f"    {'Date':<15} {'SP500 Return (12m)':>20} {'NASDAQ Weight':>15} {'SP500 Weight':>15}")
    tsmom_w = tsmom['weights_history']
    for d_str in gfc_dates:
        d = pd.to_datetime(d_str)
        # Find closest trading day
        idx = dev_df.index[dev_df.index.get_indexer([d], method='nearest')[0]]
        f_ret = (dev_df.loc[idx] / dev_df.shift(252).loc[idx]) - 1.0
        sp_w = tsmom_w.loc[idx, 'SP500']
        nd_w = tsmom_w.loc[idx, 'NASDAQ']
        print(f"    {idx.strftime('%Y-%m-%d'):<15} {f_ret['SP500']*100:>+19.2f}% {nd_w*100:>+14.2f}% {sp_w*100:>+14.2f}%")
    print("-" * 105 + "\n")

    # 3. Period 2 Concentration Check
    # Periods 1 & 3 Combined (GFC & Late Cycle), Exclude 2012-2015
    p13_rets = tsmom['daily_returns'][(tsmom['daily_returns'].index < "2012-01-01") | (tsmom['daily_returns'].index >= "2016-01-01")]
    p13_eq = (1.0 + p13_rets).cumprod()
    p13_yrs = len(p13_rets) / 252.0
    p13_ann_ret = (p13_eq.iloc[-1] ** (1.0 / p13_yrs)) - 1.0
    p13_ann_vol = p13_rets.std() * np.sqrt(252)
    p13_sharpe = (p13_rets.mean() * 252) / p13_ann_vol if p13_ann_vol > 0 else 0.0
    p13_mdd = ((p13_eq.cummax() - p13_eq) / p13_eq.cummax()).max()

    print("DIAGNOSTIC 4: EX-PERIOD 2 CONCENTRATION CHECK (Periods 1 & 3 Combined)")
    print("-" * 105)
    print(f" {'Metric':<30} {'Active Strategy (TSMOM)':<25}")
    print(f" {'Sharpe Ratio (Ex-P2)':<30} {p13_sharpe:>+14.3f}")
    print(f" {'Annualized Return (Ex-P2)':<30} {p13_ann_ret*100:>+13.2f}%")
    print(f" {'Annualized Volatility (Ex-P2)':<30} {p13_ann_vol*100:>+13.2f}%")
    print(f" {'Max Drawdown (Ex-P2)':<30} {p13_mdd*100:>13.2f}%")
    print("-" * 105 + "\n")

if __name__ == "__main__":
    run_diagnostics()
