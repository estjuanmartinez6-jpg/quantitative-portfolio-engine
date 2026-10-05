# VERSION IDENTIFIER & CHANGELOG — FX MOMENTUM PORTFOLIO

**Version Tag:** `v3.0-passive-long-only` — **OOS SHOT CONSUMED**
**Date:** August 12, 2026
**Status:** All 3 in-sample gates passed (Dev Set Sharpe +0.588, all sub-periods positive, N_eff = 5.53). OOS validation consumed on 2020–2025: Sharpe **+1.103**, Ann. Return **+17.58%**, Max DD **26.84%**. See [passive_portfolio_validation_report.md](file:///C:/Users/juanm/.gemini/antigravity/brain/d15b9c87-15e0-43fa-bc2c-fc166aaf18f2/passive_portfolio_validation_report.md) for full audit.

---

## Version History

| Version | Status | Date | Summary |
|:---|:---|:---|:---|
| `v1.0-tsmom-baseline` | Decommissioned | Aug 12, 2026 | FX-Only TSMOM. Rejected (Sharpe -0.130, N_eff = 3.20). |
| `v2.0-multi-asset-baseline` | Decommissioned | Aug 12, 2026 | Multi-Asset TSMOM (15 instruments). Rejected — passive benchmark outperformed (+0.588 vs +0.451), Ex-P2 Sharpe collapsed to +0.136. |
| `v3.0-passive-long-only` | **OOS Shot Consumed** | Aug 12, 2026 | Passive vol-targeted Buy-and-Hold (15 instruments, 4 asset classes). All in-sample gates passed. OOS: Sharpe **+1.103**, Ann. Return **+17.58%**, Max DD **26.84%**. |

---

## Codebase Versioning & Inherited Policy

- This project inherits all validation discipline, single-shot OOS rules, and search-depth tracking from the `london_session_simulator` project.
- All performance evaluation uses portfolio-level metrics (% returns, Sharpe ratio, Max Drawdown, Calmar Ratio, Volatility Target) rather than pips/trade.
- The 15-year dataset (2010–2025) is divided into a 10-year Development set (2010–2020) and a 5-year Out-of-Sample set (2020–2025). The OOS set remains sealed until an in-sample configuration passes rolling walk-forward stability gates.
