"""
Multi-Asset Momentum Portfolio Engine (core/multi_asset_engine.py)

Supports 15 Instruments across 4 Asset Classes:
- Equities: SP500, NASDAQ, RUSSELL, DOW
- Fixed Income: US10Y, US30Y
- Commodities: GOLD, CRUDE_OIL, SILVER, NAT_GAS
- FX Majors: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD

Implements:
- Volatility targeting across multi-asset universe (10% target annual vol, equal-risk contribution)
- Continuous-contract return calculation (incorporating roll-yield / contango-backwardation)
- Monthly rebalancing
- Realizable transaction costs (1.0 pip / 0.01% spread) & daily carry/swap cost (0.002%/day)
- Asset-class & per-instrument attribution accounting
"""
import pandas as pd
import numpy as np

class MultiAssetConfig:
    TARGET_ANNUAL_VOL = 0.10       # 10% target annualized portfolio volatility
    VOL_ROLLING_DAYS = 60          # 60-day rolling volatility estimate
    REBALANCE_FREQ = "ME"          # Month End rebalance
    SPREAD_PCT = 0.0001            # 0.01% (1.0 pip equivalent) spread cost per rebalance
    DAILY_CARRY_PCT = 0.00002      # 0.002% per day (~0.7% per annum carry/swap cost)
    TRADING_DAYS_PER_YEAR = 252

    ASSET_CLASSES = {
        'SP500': 'Equities', 'NASDAQ': 'Equities', 'RUSSELL': 'Equities', 'DOW': 'Equities',
        'US10Y': 'Fixed Income', 'US30Y': 'Fixed Income',
        'GOLD': 'Commodities', 'CRUDE_OIL': 'Commodities', 'SILVER': 'Commodities', 'NAT_GAS': 'Commodities',
        'EURUSD': 'FX', 'GBPUSD': 'FX', 'USDJPY': 'FX', 'AUDUSD': 'FX', 'USDCAD': 'FX'
    }

class MultiAssetEngine:
    def __init__(self, prices_df: pd.DataFrame):
        self.prices = prices_df.copy()
        self.tickers = list(prices_df.columns)
        self.n_assets = len(self.tickers)

        # Calculate daily percentage returns per asset (incorporates continuous rolls)
        self.daily_returns = self.prices.pct_change().fillna(0.0)

        # Compute rolling annualized volatility per asset
        self.rolling_vol = (
            self.daily_returns.rolling(window=MultiAssetConfig.VOL_ROLLING_DAYS)
            .std()
            .fillna(0.01) * np.sqrt(MultiAssetConfig.TRADING_DAYS_PER_YEAR)
        )
        self.rolling_vol = self.rolling_vol.clip(lower=0.02)

    def run_simulation(self, formation_months: int = 12) -> dict:
        formation_days = int(formation_months * 21)

        # Compute formation return: R_{t-L -> t} = P_t / P_{t-L} - 1.0
        formation_returns = (self.prices / self.prices.shift(formation_days)) - 1.0
        raw_signals = np.sign(formation_returns).fillna(0.0)

        # Month-end rebalance dates
        month_ends = self.prices.groupby(pd.Grouper(freq=MultiAssetConfig.REBALANCE_FREQ)).apply(lambda x: x.index[-1] if len(x) > 0 else None)
        rebalance_dates = set(month_ends.dropna())

        # Target volatility per instrument: target_vol / sqrt(N)
        inst_target_vol = MultiAssetConfig.TARGET_ANNUAL_VOL / np.sqrt(self.n_assets)

        weights_history = pd.DataFrame(0.0, index=self.prices.index, columns=self.tickers)
        current_weights = pd.Series(0.0, index=self.tickers)

        for i in range(len(self.prices)):
            date = self.prices.index[i]
            if date in rebalance_dates and i >= max(formation_days, MultiAssetConfig.VOL_ROLLING_DAYS):
                sig = raw_signals.loc[date]
                vol = self.rolling_vol.loc[date]
                unscaled_weights = inst_target_vol / vol
                new_weights = sig * unscaled_weights
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
        if len(active_returns) == 0:
            return {"error": "No active trading days."}

        equity_curve = (1.0 + active_returns).cumprod()
        total_days = len(active_returns)
        years = total_days / MultiAssetConfig.TRADING_DAYS_PER_YEAR

        ann_return = (equity_curve.iloc[-1] ** (1.0 / years)) - 1.0 if years > 0 else 0.0
        ann_vol = active_returns.std() * np.sqrt(MultiAssetConfig.TRADING_DAYS_PER_YEAR)
        sharpe = (active_returns.mean() * MultiAssetConfig.TRADING_DAYS_PER_YEAR) / ann_vol if ann_vol > 0 else 0.0

        peak = equity_curve.cummax()
        drawdowns = (peak - equity_curve) / peak
        max_dd = drawdowns.max()
        calmar = ann_return / max_dd if max_dd > 0 else 0.0

        # Asset-Class & Instrument breakdown
        inst_breakdown = {}
        asset_class_daily_ret = {ac: pd.Series(0.0, index=active_returns.index) for ac in set(MultiAssetConfig.ASSET_CLASSES.values())}

        for ticker in self.tickers:
            inst_daily_ret = asset_contrib[ticker] - (weight_changes[ticker] * MultiAssetConfig.SPREAD_PCT) - (weights_history[ticker].abs() * MultiAssetConfig.DAILY_CARRY_PCT)
            inst_active = inst_daily_ret.loc[active_returns.index]
            ac = MultiAssetConfig.ASSET_CLASSES.get(ticker, 'Other')
            asset_class_daily_ret[ac] += inst_active

            inst_ann_ret = inst_active.mean() * MultiAssetConfig.TRADING_DAYS_PER_YEAR
            inst_ann_vol = inst_active.std() * np.sqrt(MultiAssetConfig.TRADING_DAYS_PER_YEAR)
            inst_sharpe = inst_ann_ret / inst_ann_vol if inst_ann_vol > 0 else 0.0
            
            inst_weights = weights_history[ticker].loc[active_returns.index]
            long_ret = inst_active[inst_weights > 0].sum()
            short_ret = inst_active[inst_weights < 0].sum()

            inst_breakdown[ticker] = {
                "asset_class": ac,
                "ann_return": inst_ann_ret,
                "ann_vol": inst_ann_vol,
                "sharpe": inst_sharpe,
                "long_cum_return": long_ret,
                "short_cum_return": short_ret,
                "net_cum_return": inst_active.sum()
            }

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
            "formation_months": formation_months,
            "years": years,
            "ann_return": ann_return,
            "ann_vol": ann_vol,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "calmar": calmar,
            "equity_curve": equity_curve,
            "daily_returns": active_returns,
            "weights_history": weights_history,
            "inst_breakdown": inst_breakdown,
            "asset_class_summary": asset_class_summary
        }
