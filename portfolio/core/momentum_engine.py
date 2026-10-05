"""
Momentum Portfolio Execution & Accounting Engine (core/momentum_engine.py)

Implements Time Series Momentum (TSMOM) portfolio simulation:
- Volatility-targeted position sizing (inversely proportional to 60-day rolling daily volatility)
- Monthly rebalancing
- Daily swap costs and rebalance spread costs
- Portfolio performance accounting (% returns, Sharpe, Max DD, Calmar)
"""
import pandas as pd
import numpy as np

class Config:
    TARGET_ANNUAL_VOL = 0.10      # 10% target annualized portfolio volatility
    VOL_ROLLING_DAYS = 60         # 60-day rolling volatility estimate
    REBALANCE_FREQ = "ME"         # Month End rebalance
    SPREAD_PIPS = 1.0             # 1.0 pip spread cost at rebalance
    DAILY_SWAP_PCT = 0.00002      # 0.002% per day (~0.7% per annum swap cost)
    TRADING_DAYS_PER_YEAR = 252

class MomentumEngine:
    def __init__(self, prices_df: pd.DataFrame):
        self.prices = prices_df.copy()
        self.tickers = list(prices_df.columns)
        self.n_assets = len(self.tickers)

        # Calculate daily percentage returns per asset
        self.daily_returns = self.prices.pct_change().fillna(0.0)

        # Compute rolling annualized volatility per asset
        self.rolling_vol = (
            self.daily_returns.rolling(window=Config.VOL_ROLLING_DAYS)
            .std()
            .fillna(0.01) * np.sqrt(Config.TRADING_DAYS_PER_YEAR)
        )
        # Avoid zero or near-zero vol division
        self.rolling_vol = self.rolling_vol.clip(lower=0.02)

    def run_simulation(self, formation_months: int = 12) -> dict:
        """
        Runs Time Series Momentum simulation for a given formation window (in months).
        12 months = 252 trading days.
        """
        formation_days = int(formation_months * 21)

        # Compute formation return: R_{t-L -> t} = P_t / P_{t-L} - 1.0
        formation_returns = (self.prices / self.prices.shift(formation_days)) - 1.0

        # Raw Signal: +1 if trailing return > 0, -1 if trailing return < 0
        raw_signals = np.sign(formation_returns).fillna(0.0)

        # Identify month-end rebalance dates
        month_ends = self.prices.groupby(pd.Grouper(freq=Config.REBALANCE_FREQ)).apply(lambda x: x.index[-1] if len(x) > 0 else None)
        rebalance_dates = set(month_ends.dropna())

        # Target volatility per instrument: target_vol / sqrt(N)
        inst_target_vol = Config.TARGET_ANNUAL_VOL / np.sqrt(self.n_assets)

        # Initialize portfolio weight history
        weights_history = pd.DataFrame(0.0, index=self.prices.index, columns=self.tickers)
        
        current_weights = pd.Series(0.0, index=self.tickers)

        # Simulation loop over daily index
        for i in range(len(self.prices)):
            date = self.prices.index[i]

            # Rebalance on month-end dates (only if we have enough history for formation & vol)
            if date in rebalance_dates and i >= max(formation_days, Config.VOL_ROLLING_DAYS):
                sig = raw_signals.loc[date]
                vol = self.rolling_vol.loc[date]
                
                # Volatility-targeted weight: w_i = (target_vol / sqrt(N)) / vol_i
                unscaled_weights = inst_target_vol / vol
                new_weights = sig * unscaled_weights
                
                current_weights = new_weights

            weights_history.loc[date] = current_weights

        # Forward fill weights between rebalances (holding positions)
        weights_history = weights_history.shift(1).fillna(0.0)  # Shift by 1 day to avoid lookahead bias

        # Calculate daily portfolio returns
        asset_contrib = weights_history * self.daily_returns
        gross_daily_returns = asset_contrib.sum(axis=1)

        # Calculate Costs:
        # 1. Turnover / Rebalance spread cost: |w_t - w_{t-1}| * (spread_pips * 0.0001)
        weight_changes = weights_history.diff().abs().fillna(0.0)
        rebalance_costs = weight_changes.sum(axis=1) * (Config.SPREAD_PIPS * 0.0001)

        # 2. Daily swap cost on held positions
        daily_swap_costs = weights_history.abs().sum(axis=1) * Config.DAILY_SWAP_PCT

        # Net daily portfolio returns
        net_daily_returns = gross_daily_returns - rebalance_costs - daily_swap_costs

        # Compute Performance Metrics
        # Trim warmup period (where weights were 0)
        active_returns = net_daily_returns[weights_history.abs().sum(axis=1) > 0]
        
        if len(active_returns) == 0:
            return {"error": "No active trading days."}

        equity_curve = (1.0 + active_returns).cumprod()
        total_days = len(active_returns)
        years = total_days / Config.TRADING_DAYS_PER_YEAR

        ann_return = (equity_curve.iloc[-1] ** (1.0 / years)) - 1.0 if years > 0 else 0.0
        ann_vol = active_returns.std() * np.sqrt(Config.TRADING_DAYS_PER_YEAR)
        sharpe = (active_returns.mean() * Config.TRADING_DAYS_PER_YEAR) / ann_vol if ann_vol > 0 else 0.0

        # Drawdown calculation
        peak = equity_curve.cummax()
        drawdowns = (peak - equity_curve) / peak
        max_dd = drawdowns.max()
        calmar = ann_return / max_dd if max_dd > 0 else 0.0

        # Per-instrument performance breakdown
        inst_breakdown = {}
        for ticker in self.tickers:
            inst_daily_ret = asset_contrib[ticker] - (weight_changes[ticker] * Config.SPREAD_PIPS * 0.0001) - (weights_history[ticker].abs() * Config.DAILY_SWAP_PCT)
            inst_active = inst_daily_ret.loc[active_returns.index]
            inst_ann_ret = inst_active.mean() * Config.TRADING_DAYS_PER_YEAR
            inst_ann_vol = inst_active.std() * np.sqrt(Config.TRADING_DAYS_PER_YEAR)
            inst_sharpe = inst_ann_ret / inst_ann_vol if inst_ann_vol > 0 else 0.0
            
            # Long vs Short split for this instrument
            inst_weights = weights_history[ticker].loc[active_returns.index]
            long_mask = inst_weights > 0
            short_mask = inst_weights < 0
            
            long_ret = inst_active[long_mask].sum()
            short_ret = inst_active[short_mask].sum()

            inst_breakdown[ticker] = {
                "ann_return": inst_ann_ret,
                "ann_vol": inst_ann_vol,
                "sharpe": inst_sharpe,
                "long_cum_return": long_ret,
                "short_cum_return": short_ret,
                "net_cum_return": inst_active.sum()
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
            "inst_breakdown": inst_breakdown
        }
