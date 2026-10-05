"""
London Bot V1 — FVG + Fibonacci + Ichimoku Strategy
=====================================================
Incremental build. Current phase layers:
  [x] Phase 1: FVG detection on M15 + Fibonacci retracement zones
  [x] Phase 2: Ichimoku H1 trend filter (binary)
  [x] Phase 3: M1 entry confirmation (rejection candle / minor structure shift)

All session/frequency constraints are delegated to execution_engine.py and session_manager.py.
"""

from strategy.base_strategy import BaseStrategy
from core.execution_engine import ExecutionEngine
from datetime import datetime
from typing import Dict, List, Optional


# ─────────────────────────────────────────────
# CONFIGURATION — Tunable parameters
# ─────────────────────────────────────────────
class Config:
    VERSION_TAG: str = "v1.0-fvg-standardized"  # Frozen reference version tag
    MIN_FVG_SIZE_PIPS: float = 1.5          # Minimum gap to register as FVG
    FIB_QUALITY_UPPER: float = 0.786        # FVG must sit within this retracement depth
    FIB_QUALITY_LOWER: float = 0.236        # FVG must sit above this retracement depth
    SL_BUFFER_PIPS: float = 5.0             # Extra pips beyond FVG boundary for SL
    TP_RISK_MULTIPLE: float = 1.5           # Risk/reward ratio
    BREAKEVEN_PIPS: float = 5.0             # Move SL to entry after this many pips in profit
    FVG_MAX_AGE_HOURS: float = 8.0          # FVGs older than this are expired (stale zones)
    SESSION_WARMUP_MINUTES: int = 15        # Skip entries for first N minutes of session
    MIN_IMPULSE_BODY_RATIO: float = 0.60    # Impulse candle body must be >= 60% of its range
    
    # --- PHASE 3 ABLATION TOGGLES ---
    ENABLE_SESSION_WARMUP: bool = False
    ENABLE_FVG_EXPIRY: bool = False
    ENABLE_STRICT_M1_CONFIRM: bool = False
    ENABLE_IMPULSE_FILTER: bool = False
    
    # Provisional — needs sensitivity testing once the extended dataset is available
    M1_CONFIRMATION_WINDOW_CANDLES: int = 10
    
    ICHIMOKU_CHIKOU_PERIOD: int = 26
    ICHIMOKU_TENKAN_PERIOD: int = 9
    ICHIMOKU_KIJUN_PERIOD: int = 26
    ICHIMOKU_SENKOU_B_PERIOD: int = 52
    PIP: float = 0.0001


# ─────────────────────────────────────────────
# FVG DATA STRUCTURE
# ─────────────────────────────────────────────
class FairValueGap:
    def __init__(self, direction: str, gap_high: float, gap_low: float,
                 formation_time: datetime, swing_high: float, swing_low: float,
                 impulse_quality: float = 0.0):
        self.direction = direction          # "BULLISH" or "BEARISH"
        self.gap_high = gap_high
        self.gap_low = gap_low
        self.formation_time = formation_time
        self.swing_high = swing_high        # High of the impulse leg that created this FVG
        self.swing_low = swing_low          # Low of the impulse leg
        self.impulse_quality = impulse_quality  # Body/range ratio of the impulse candle
        self.mitigated = False
        self.invalidated = False
        self.pending_m1_confirmation = False
        self.touched_at: Optional[datetime] = None

    def is_expired(self, current_time: datetime) -> bool:
        """Returns True if the FVG is too old to be tradeable."""
        if not Config.ENABLE_FVG_EXPIRY:
            return False
            
        if self.formation_time is None:
            return True
        from datetime import timedelta
        age = current_time - self.formation_time
        return age > timedelta(hours=Config.FVG_MAX_AGE_HOURS)

    @property
    def is_active(self) -> bool:
        return not self.mitigated and not self.invalidated

    @property
    def size_pips(self) -> float:
        return (self.gap_high - self.gap_low) / Config.PIP

    def passes_fib_quality_filter(self) -> bool:
        """
        Quality filter: checks that the FVG midpoint falls within a reasonable
        Fibonacci retracement zone (0.236–0.786) of the originating swing.
        This ensures we're trading at a discount/premium, not at extremes.
        """
        swing_range = self.swing_high - self.swing_low
        if swing_range <= 0:
            return False

        fvg_midpoint = (self.gap_high + self.gap_low) / 2.0

        if self.direction == "BULLISH":
            # Bullish: how deep has price retraced from swing_high?
            retrace_ratio = (self.swing_high - fvg_midpoint) / swing_range
        else:
            # Bearish: how high has price bounced from swing_low?
            retrace_ratio = (fvg_midpoint - self.swing_low) / swing_range

        return Config.FIB_QUALITY_LOWER <= retrace_ratio <= Config.FIB_QUALITY_UPPER


# ─────────────────────────────────────────────
# ICHIMOKU HELPERS
# ─────────────────────────────────────────────
def _donchian_mid(candles: List[Dict], period: int) -> Optional[float]:
    """Donchian channel midpoint over the last `period` candles."""
    if len(candles) < period:
        return None
    subset = candles[-period:]
    highest = max(c['high'] for c in subset)
    lowest = min(c['low'] for c in subset)
    return (highest + lowest) / 2.0


def compute_ichimoku(h1_candles: List[Dict]) -> Optional[Dict]:
    """
    Computes the current Ichimoku values from closed H1 candles.
    Returns None if there isn't enough history.
    Requires at least max(52, 26+26) = 52 candles for Senkou B,
    plus 26 candles for Chikou comparison -> 52 candles minimum for the
    indicator lines, and we need candle[-26] for the Chikou check.
    """
    needed = Config.ICHIMOKU_SENKOU_B_PERIOD + Config.ICHIMOKU_CHIKOU_PERIOD
    if len(h1_candles) < needed:
        return None

    tenkan = _donchian_mid(h1_candles, Config.ICHIMOKU_TENKAN_PERIOD)
    kijun = _donchian_mid(h1_candles, Config.ICHIMOKU_KIJUN_PERIOD)

    # Senkou Span A = midpoint of Tenkan + Kijun (projected 26 periods ahead,
    # but for a current-state filter we use the value plotted at the current bar,
    # which was calculated 26 bars ago).
    # To get the Senkou A value plotted on the CURRENT bar, we compute tenkan/kijun
    # as of 26 bars ago.
    past_candles = h1_candles[:-Config.ICHIMOKU_CHIKOU_PERIOD]
    tenkan_past = _donchian_mid(past_candles, Config.ICHIMOKU_TENKAN_PERIOD)
    kijun_past = _donchian_mid(past_candles, Config.ICHIMOKU_KIJUN_PERIOD)
    senkou_b_past = _donchian_mid(past_candles, Config.ICHIMOKU_SENKOU_B_PERIOD)

    if any(v is None for v in [tenkan, kijun, tenkan_past, kijun_past, senkou_b_past]):
        return None

    senkou_a = (tenkan_past + kijun_past) / 2.0
    senkou_b = senkou_b_past

    current_close = h1_candles[-1]['close']
    chikou_compare = h1_candles[-Config.ICHIMOKU_CHIKOU_PERIOD]['close']

    return {
        'tenkan': tenkan,
        'kijun': kijun,
        'senkou_a': senkou_a,
        'senkou_b': senkou_b,
        'current_close': current_close,
        'chikou_compare': chikou_compare,
    }


def ichimoku_trend(ichi: Optional[Dict]) -> Optional[str]:
    """Returns 'BULLISH', 'BEARISH', or None (no clear trend)."""
    if ichi is None:
        return None

    c = ichi['current_close']
    sa = ichi['senkou_a']
    sb = ichi['senkou_b']
    ts = ichi['tenkan']
    ks = ichi['kijun']
    chk = ichi['chikou_compare']

    if c > sa and c > sb and ts > ks and c > chk:
        return "BULLISH"
    if c < sa and c < sb and ts < ks and c < chk:
        return "BEARISH"
    return None


# ─────────────────────────────────────────────
# STRATEGY CLASS
# ─────────────────────────────────────────────
class LondonBotV1(BaseStrategy):
    """
    FVG + Fibonacci + Ichimoku + M1 Confirmation strategy for the London session.
    """

    def __init__(self):
        super().__init__("London FVG-Fib-Ichimoku V1")
        self.active_fvgs: List[FairValueGap] = []
        self._last_m15_time = None      # Track last processed M15 candle timestamp
        self._last_m5_time = None       # Track last processed M5 candle timestamp
        self._m1_buffer: List[Dict] = []
        self._M1_BUFFER_SIZE = 10
        # Session tracking for warmup logic
        self._session_start_time = None
        self._was_in_session = False

    # ─── FVG DETECTION (M15 + M5) ──────────────────
    def _detect_fvgs_from(self, candles: List[Dict], lookback: int = 5):
        """
        Scan for FVGs using TWO detection modes:
          1. Classic: true wick gap (c3.low > c1.high or c3.high < c1.low)
          2. Body Imbalance: the middle candle's body creates an imbalance zone
             that the surrounding candle bodies don't overlap. This catches the
             majority of real-world FVGs in liquid pairs like EURUSD where pure
             wick gaps almost never form.
        """
        if len(candles) < 3:
            return

        c1 = candles[-3]
        c2 = candles[-2]  # The impulse candle
        c3 = candles[-1]

        # ── Impulse quality check ──
        # The middle candle (c2) must be a strong directional candle
        c2_range = c2['high'] - c2['low']
        c2_body = abs(c2['close'] - c2['open'])
        impulse_quality = c2_body / c2_range if c2_range > 0 else 0
        if Config.ENABLE_IMPULSE_FILTER:
            if impulse_quality < Config.MIN_IMPULSE_BODY_RATIO:
                return  # Weak/indecisive impulse = unreliable FVG

        detected = False

        # ── Mode 1: Classic wick-gap FVG ──
        if c3['low'] > c1['high']:
            gap_size = (c3['low'] - c1['high']) / Config.PIP
            if gap_size >= Config.MIN_FVG_SIZE_PIPS:
                self._register_fvg("BULLISH", c1['high'], c3['low'], c3, candles, lookback, impulse_quality)
                detected = True

        if c3['high'] < c1['low']:
            gap_size = (c1['low'] - c3['high']) / Config.PIP
            if gap_size >= Config.MIN_FVG_SIZE_PIPS:
                self._register_fvg("BEARISH", c3['high'], c1['low'], c3, candles, lookback, impulse_quality)
                detected = True

        # ── Mode 2: Body imbalance FVG ──
        if not detected:
            c1_body_high = max(c1['open'], c1['close'])
            c3_body_low = min(c3['open'], c3['close'])
            c1_body_low = min(c1['open'], c1['close'])
            c3_body_high = max(c3['open'], c3['close'])

            if c2['close'] > c2['open']:  # c2 is bullish
                imbalance_low = c1_body_high
                imbalance_high = c3_body_low
                if imbalance_high > imbalance_low:
                    gap_size = (imbalance_high - imbalance_low) / Config.PIP
                    if gap_size >= Config.MIN_FVG_SIZE_PIPS:
                        self._register_fvg("BULLISH", imbalance_low, imbalance_high, c3, candles, lookback, impulse_quality)

            if c2['close'] < c2['open']:  # c2 is bearish
                imbalance_high = c1_body_low
                imbalance_low = c3_body_high
                if imbalance_high > imbalance_low:
                    gap_size = (imbalance_high - imbalance_low) / Config.PIP
                    if gap_size >= Config.MIN_FVG_SIZE_PIPS:
                        self._register_fvg("BEARISH", imbalance_low, imbalance_high, c3, candles, lookback, impulse_quality)

    def _register_fvg(self, direction: str, gap_low: float, gap_high: float,
                      anchor_candle: Dict, candles: List[Dict], lookback: int,
                      impulse_quality: float = 0.0):
        """Helper to create and store a FVG with proper swing identification."""
        if direction == "BULLISH":
            swing_low = min(c['low'] for c in candles[-lookback:]) if len(candles) >= lookback else candles[-3]['low']
            swing_high = anchor_candle['high']
        else:
            swing_high = max(c['high'] for c in candles[-lookback:]) if len(candles) >= lookback else candles[-3]['high']
            swing_low = anchor_candle['low']

        fvg = FairValueGap(
            direction=direction,
            gap_high=gap_high,
            gap_low=gap_low,
            formation_time=anchor_candle['time'],
            swing_high=swing_high,
            swing_low=swing_low,
            impulse_quality=impulse_quality
        )
        self.active_fvgs.append(fvg)

    def _detect_fvgs(self, m5_candles: List[Dict], m15_candles: List[Dict]):
        """Scan for FVGs on both M5 and M15 (only when new candles arrive)."""
        if len(m15_candles) >= 3:
            last_m15_time = m15_candles[-1]['time']
            if last_m15_time != self._last_m15_time:
                self._last_m15_time = last_m15_time
                self._detect_fvgs_from(m15_candles, lookback=5)

        if len(m5_candles) >= 3:
            last_m5_time = m5_candles[-1]['time']
            if last_m5_time != self._last_m5_time:
                self._last_m5_time = last_m5_time
                self._detect_fvgs_from(m5_candles, lookback=5)

    # ─── FVG STATE MAINTENANCE ─────────────────────
    def _update_fvg_states(self, current_close: float, current_high: float, current_low: float):
        """Mark FVGs as mitigated or invalidated based on current price action."""
        for fvg in self.active_fvgs:
            if fvg.invalidated:
                continue

            if fvg.direction == "BULLISH":
                if not fvg.mitigated:
                    # Mitigated: price retraced INTO the gap (touched it)
                    if current_low <= fvg.gap_high:
                        fvg.mitigated = True
                        # Don't invalidate on the same tick we mitigate — give it a chance
                        continue
                # Invalidated: price closed completely below the FVG (no reaction)
                if current_close < fvg.gap_low:
                    fvg.invalidated = True

            else:  # BEARISH
                if not fvg.mitigated:
                    if current_high >= fvg.gap_low:
                        fvg.mitigated = True
                        continue
                if current_close > fvg.gap_high:
                    fvg.invalidated = True

        # Prune: keep active or mitigated-but-not-invalidated
        self.active_fvgs = [f for f in self.active_fvgs if f.is_active or (f.mitigated and not f.invalidated)]
        # Cap total tracked FVGs
        if len(self.active_fvgs) > 100:
            self.active_fvgs = self.active_fvgs[-60:]

    # ─── M1 CONFIRMATION LOGIC ────────────────────
    def _check_m1_confirmation(self, direction: str) -> bool:
        """
        Stricter M1 confirmation:
          1. Strong rejection candle: wick >= 2x body, wick >= 50% of range,
             candle MUST close in trade direction.
          2. Double structure shift: TWO consecutive higher-lows (bullish) or
             lower-highs (bearish) in the last 4 candles — confirms sustained reaction.
        """
        if not Config.ENABLE_STRICT_M1_CONFIRM:
            return self._check_m1_confirmation_phase_1(direction)
            
        if len(self._m1_buffer) < 4:
            return False

        last = self._m1_buffer[-1]
        body = abs(last['close'] - last['open'])
        full_range = last['high'] - last['low']

        if full_range == 0:
            return False

        if direction == "BULLISH":
            # Strong rejection: long lower wick, closed bullish
            lower_wick = min(last['open'], last['close']) - last['low']
            if (lower_wick > body * 2.0 and lower_wick > full_range * 0.5
                    and last['close'] > last['open']):
                return True

            # Double structure shift: 2 consecutive higher-lows in last 4 candles
            lows = [c['low'] for c in self._m1_buffer[-4:]]
            if lows[-1] > lows[-2] > lows[-3] and lows[-3] < lows[-4]:
                # Also require last candle closed bullish
                if last['close'] > last['open']:
                    return True

        elif direction == "BEARISH":
            # Strong rejection: long upper wick, closed bearish
            upper_wick = last['high'] - max(last['open'], last['close'])
            if (upper_wick > body * 2.0 and upper_wick > full_range * 0.5
                    and last['close'] < last['open']):
                return True

            # Double structure shift: 2 consecutive lower-highs in last 4 candles
            highs = [c['high'] for c in self._m1_buffer[-4:]]
            if highs[-1] < highs[-2] < highs[-3] and highs[-3] > highs[-4]:
                # Also require last candle closed bearish
                if last['close'] < last['open']:
                    return True

        return False

    def _check_m1_confirmation_phase_1(self, direction: str) -> bool:
        """Original Phase 1 M1 confirmation logic."""
        if len(self._m1_buffer) < 3:
            return False

        last = self._m1_buffer[-1]
        body = abs(last['close'] - last['open'])
        full_range = last['high'] - last['low']

        if full_range == 0:
            return False

        if direction == "BULLISH":
            lower_wick = min(last['open'], last['close']) - last['low']
            if lower_wick > body * 1.5 and lower_wick > full_range * 0.5 and last['close'] > last['open']:
                return True
            lows = [c['low'] for c in self._m1_buffer[-3:]]
            if lows[-1] > lows[-2] and lows[-2] < lows[-3]:
                return True

        elif direction == "BEARISH":
            upper_wick = last['high'] - max(last['open'], last['close'])
            if upper_wick > body * 1.5 and upper_wick > full_range * 0.5 and last['close'] < last['open']:
                return True
            highs = [c['high'] for c in self._m1_buffer[-3:]]
            if highs[-1] < highs[-2] and highs[-2] > highs[-3]:
                return True

        return False

    # ─── MAIN TICK HANDLER ─────────────────────────
    def on_tick(self, current_time: datetime, m1_candle: Dict,
                m5_candles: List[Dict], m15_candles: List[Dict],
                h1_candles: List[Dict], engine: ExecutionEngine,
                in_session: bool = True):

        current_close = m1_candle['close']
        current_high = m1_candle['high']
        current_low = m1_candle['low']

        # ── Step 0: Trade Management (Breakeven) ──
        if engine.open_position:
            pos = engine.open_position
            if not pos['breakeven_triggered']:
                if pos['direction'] == "LONG":
                    # If high reached +5 pips, move SL
                    if (current_high - pos['entry_price']) / Config.PIP >= Config.BREAKEVEN_PIPS:
                        engine.move_to_breakeven()
                else: 
                    # If low reached +5 pips (down), move SL
                    if (pos['entry_price'] - current_low) / Config.PIP >= Config.BREAKEVEN_PIPS:
                        engine.move_to_breakeven()
            # If in a trade, skip new setup detection and entries for performance, 
            # or just continue detecting but skip entries. We must detect FVGs 24/7!
        
        # Maintain M1 buffer (always, for confirmation scanning)
        self._m1_buffer.append(m1_candle)
        if len(self._m1_buffer) > self._M1_BUFFER_SIZE:
            self._m1_buffer.pop(0)

        # ── Step 1: Detect new FVGs on M5 + M15 (ALWAYS — 24/7) ──
        self._detect_fvgs(m5_candles, m15_candles)

        # ── Step 2: Update FVG states (ALWAYS — mitigation / invalidation) ──
        self._update_fvg_states(current_close, current_high, current_low)

        # ── Only attempt entries during the active session window ──
        if not in_session:
            self._was_in_session = False
            return

        # ── Session warmup: detect new session start ──
        if not self._was_in_session:
            # Just entered a new session — record start time
            self._session_start_time = current_time
            self._was_in_session = True

        if Config.ENABLE_SESSION_WARMUP:
            from datetime import timedelta
            elapsed = (current_time - self._session_start_time).total_seconds() / 60
            if elapsed < Config.SESSION_WARMUP_MINUTES:
                return

        # ── Step 3: Compute Ichimoku trend from H1 ──
        ichi = compute_ichimoku(h1_candles)
        trend = ichimoku_trend(ichi)

        # If no clear Ichimoku trend, skip all entries
        if trend is None:
            return

        # ── Step 4: Check mitigated FVGs that align with the trend ──
        for fvg in self.active_fvgs:
            if not fvg.mitigated or fvg.invalidated:
                continue

            # Age check: expire stale FVGs
            if fvg.is_expired(current_time):
                fvg.invalidated = True
                continue

            # Trend alignment gate
            if fvg.direction == "BULLISH" and trend != "BULLISH":
                continue
            if fvg.direction == "BEARISH" and trend != "BEARISH":
                continue

            # Fibonacci quality filter: FVG must sit in a reasonable retracement zone
            if not fvg.passes_fib_quality_filter():
                continue

            # Price interaction gating / State Machine
            if not fvg.pending_m1_confirmation:
                # ── STATE 1: Waiting for first touch ──
                touched = False
                if fvg.direction == "BULLISH":
                    if current_low <= fvg.gap_high and current_close >= fvg.gap_low:
                        touched = True
                else:
                    if current_high >= fvg.gap_low and current_close <= fvg.gap_high:
                        touched = True
                
                if touched:
                    fvg.pending_m1_confirmation = True
                    fvg.touched_at = current_time
                else:
                    continue  # Not touched yet, skip M1 check

            else:
                # ── STATE 2: Pending M1 Confirmation ──
                # Check if we exceeded the confirmation window (in minutes)
                elapsed_minutes = (current_time - fvg.touched_at).total_seconds() / 60.0
                if elapsed_minutes > Config.M1_CONFIRMATION_WINDOW_CANDLES:
                    fvg.pending_m1_confirmation = False
                    fvg.invalidated = True  # Failed to confirm in time, invalidate zone
                    continue

            # ── Step 5: M1 Confirmation ──
            trade_direction = "LONG" if fvg.direction == "BULLISH" else "SHORT"
            if not self._check_m1_confirmation(fvg.direction):
                continue
            
            # If confirmed, reset the pending state so we don't accidentally re-trigger
            fvg.pending_m1_confirmation = False

            # ── Step 6: Calculate SL / TP ──
            if fvg.direction == "BULLISH":
                sl_price = fvg.gap_low - (Config.SL_BUFFER_PIPS * Config.PIP)
                sl_pips = (current_close - sl_price) / Config.PIP
                tp_pips = sl_pips * Config.TP_RISK_MULTIPLE
            else:
                sl_price = fvg.gap_high + (Config.SL_BUFFER_PIPS * Config.PIP)
                sl_pips = (sl_price - current_close) / Config.PIP
                tp_pips = sl_pips * Config.TP_RISK_MULTIPLE

            if sl_pips <= 0:
                continue

            # ── Step 7: Submit to engine (it handles 1-trade-per-session) ──
            opened = engine.try_open_trade(
                direction=trade_direction,
                current_time=current_time,
                current_close=current_close,
                sl_pips=sl_pips,
                tp_pips=tp_pips
            )

            if opened:
                # Invalidate this FVG so we don't re-enter on the same zone
                fvg.invalidated = True
                return  # Done for this tick
