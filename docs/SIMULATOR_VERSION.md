# VERSION IDENTIFIER & CHANGELOG

**Version Tag:** `v3.0-london-sweep` — **DECOMMISSIONED**  
**Date:** August 12, 2026  
**Status:** Rejected at Pre-Flight Gate (1 configuration tested). Full-population expectancy was negative across all 3 chronological sub-periods (-0.93, -0.57, -0.42 pips/trade). Process validation: rejected in 1 run vs. 8 in v1.0 and 9 in v2.0.

---

## Version History

| Version | Status | Date | Summary |
|:---|:---|:---|:---|
| `v1.0-fvg-standardized` | Decommissioned | Aug 3, 2026 | FVG + Fibonacci + Ichimoku. Rejected after ~8 configs: OOS validation confirmed trend-correlation artifact. |
| `v2.0-london-orb` | Decommissioned | Aug 12, 2026 | London Opening Range Breakout. Rejected after 9 configs: chronological stability failed in P3 (-4.27 pips/trade). |
| `v3.0-london-sweep` | Decommissioned | Aug 12, 2026 | London Liquidity Sweep Mean Reversion. Rejected after 1 config (pre-flight gate failure: all 3 sub-periods negative). |

---

## Codebase Versioning Policy
- All future ablation studies, sensitivity analyses, and out-of-sample (OOS) validations must explicitly reference the active version tag.
- Any future modification to shared infrastructure (SessionManager, ExecutionEngine, DataFeeder) **MUST** bump this version tag before generating comparison results.
- The 6-month OOS set (`eurusd_m1_oos_6m.csv`) has never been touched. It remains reserved for a single-shot validation of a future architecture that first passes in-sample chronological stability testing.
