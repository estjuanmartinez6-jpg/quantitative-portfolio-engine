# Design Rules for Multi-Currency Momentum Portfolio (v1+)

**Purpose**: Standing checklist and inherited validation discipline transferred from `london_session_simulator`. These constraints apply to any momentum hypothesis *before* parameter exploration begins.

**Status**: Active. Must be reviewed before modifying formation windows, volatility targets, or universe rules.

---

## Inherited Project Context & Lessons Learned

This project builds directly on the rigorous empirical lessons of the prior `london_session_simulator` project, where 18 configurations across 3 intraday architectures were systematically tested:

1. **Intraday HFT/Microstructure Arbitrage**: 3 distinct intraday price-action theses (`v1.0` FVG, `v2.0` ORB, `v3.0` Sweep Reversion) failed to produce a chronologically stable edge on M1 bars. Statistical analysis proved intraday efficiency ratios across all sessions are indistinguishable from noise ($p > 0.14$).
2. **Pivot to Medium-Term Macro Momentum**: This project shifts from machine-speed intraday microstructure to **medium-term Time Series Momentum (TSMOM)** operating on daily/weekly horizons, grounded in slow institutional information diffusion and portfolio rebalancing.
3. **Inherited Validation Gate**: The strict pre-flight checklist (Rule 7) that successfully rejected `v3.0` in a single run is transferred here as mandatory protocol.

---

## Rule 1: Causal, Falsifiable Thesis

> *"Currency pairs that have trended over the past 1–12 months tend to continue trending over the subsequent 1 month, because macro participants (central bank policy shifts, corporate hedging flows, institutional trend-following capital) adjust positioning gradually rather than instantaneously, creating serial correlation in medium-term returns — as documented empirically across 58 liquid futures including currencies in Moskowitz, Ooi & Pedersen (2012)."*

---

## Rule 2: Multi-Year Rolling Walk-Forward Stability

Any momentum model must pass a rolling walk-forward test (or multi-period split) across the 10-year Development set (2010–2020) before evaluating candidate parameters.

- **Protocol**: Evaluate portfolio Sharpe ratio, Max Drawdown, and Calmar Ratio across sub-periods (e.g. 2010–2013, 2013–2016, 2016–2020).
- **Gate**: If performance collapses or turns negative in sub-periods, the hypothesis fails.

---

## Rule 3: Instrument Contribution & Long/Short Symmetry Check

- **Instrument Diversity**: No single pair (e.g., EUR/USD or USD/JPY) may account for more than 40% of net portfolio profits.
- **Directional Symmetry**: Long signals and Short signals must both contribute positively (or be structurally explainable by macro interest rate differentials).

---

## Rule 4: Volatility Targeting & Realistic Cost Accounting

- **Position Sizing**: Inverse volatility scaling ($w_i \propto 1/\sigma_i$) ensures equal risk contribution per instrument.
- **Transaction & Swap Costs**:
  - Rebalance execution spread: 1.0 pip per position change.
  - Daily rollover/swap cost: 0.002% per day (~0.7% annualized) applied daily on open positions.

---

## Rule 5: Track Cumulative Search Depth Ledger

### Ledger

| # | Project | Architecture | Configuration | Portfolio Sharpe | Stable? |
|---|:---|:---|:---|:---:|:---:|
| 1–17 | `london_session_simulator` | v1.0–v2.0 (Intraday) | 17 intraday configs | Various | Rejected |
| 18 | `london_session_simulator` | v3.0-sweep (Intraday) | 1 untuned sweep config | -0.64 pips | Rejected |
| 19 | `fx_momentum_portfolio` | v1.0-tsmom-baseline | Untuned FX Baseline (12m formation, 2010–2020) | -0.114 | Failed Gate (P1 & P3 negative; USDJPY dominated) |
| 20 | `fx_momentum_portfolio` | Diagnostic 1: N_eff Check | FX Pairwise Correlation Matrix (2010–2020) | N_eff = 3.20 | Structural limitation (high USD co-movement) |
| 21 | `fx_momentum_portfolio` | Diagnostic 2: Extended History | FX Extended Baseline (12m formation, 2006–2019) | -0.130 | REJECTED per Stopping Rule (3 of 4 sub-periods negative) |
| 22 | `fx_momentum_portfolio` | v2.0-multi-asset-baseline | Untuned Multi-Asset Baseline (15 assets, 4 classes, 2007–2020) | +0.451 | Evaluated via Pre-Flight Gate (N_eff = 5.53) |
| 23 | `fx_momentum_portfolio` | Naive B&H & Ex-P2 Diagnostics | Benchmarking & Period 2 exclusion audit | +0.588 / +0.136 | REJECTED: TSMOM underperformed static long B&H (+0.588) and collapsed without P2 (+0.136) |

**Running total: 23 configurations/diagnostics tested across project history, 0 with stable positive Sharpe ratio and genuine alpha.**
*Process validation: Multi-asset TSMOM rejected after benchmarking proved returns are dominated by passive beta (+0.588 Sharpe for naive B&H) and highly sensitive to Period 2 QE expansion (+0.136 Sharpe Ex-P2).*

---

## Pre-Flight Checklist (Gate Before Parameter Search)

- [ ] **Thesis stated**: Moskowitz et al. (2012) TSMOM thesis documented
- [ ] **Baseline run complete**: Single untuned 12m formation window on 7 USD pairs (2010–2020 Dev set)
- [ ] **Walk-Forward / Sub-period stability checked**: Sub-period performance evaluated
- [ ] **Instrument breakdown & directional symmetry reported**: Per-pair and Long/Short split reviewed
- [ ] **Scale & Unit verification complete**: Manual spot-check of % return & vol-scaling math
- [ ] **Ledger updated**: Entry added to search depth ledger
