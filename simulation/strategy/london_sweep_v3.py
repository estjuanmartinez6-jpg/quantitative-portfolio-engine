from datetime import datetime, time
from typing import Dict, List, Optional, Any
from strategy.base_strategy import BaseStrategy
from core.execution_engine import ExecutionEngine


class Config:
    VERSION_TAG = "v3.0-london-sweep"

    # Time Windows (UTC)
    ASIAN_START_HOUR = 0
    ASIAN_END_HOUR = 7
    SESSION_START_HOUR = 7
    SESSION_END_HOUR = 9
    FORCE_CLOSE_HOUR = 17  # 17:00 UTC close

    # Strategy Parameters
    SL_BUFFER_PIPS = 1.0  # Buffer pips beyond sweep extreme
    RISK_REWARD_RATIO = 1.0  # Baseline TP 1.0R
    TP_MODE = "RR"  # Options: "RR" or "OPPOSITE_BOUNDARY"

    # Instrument parameters
    PIP = 0.0001


class LondonSweepV3(BaseStrategy):
    """
    London Liquidity Sweep Mean Reversion Strategy (v3.0-london-sweep)
    
    Causal Thesis:
    "Early London session volatility expansion often overshoots into resting 
    stop-loss liquidity above/below the Asian range, and because that initial move 
    lacks sustained institutional follow-through, price reverts back into the Asian range 
    before the session ends."
    """

    def __init__(self):
        super().__init__(name="LondonSweepV3")
        self.current_date = None
        self.asian_high: Optional[float] = None
        self.asian_low: Optional[float] = None

        # Sweep tracking variables
        self.upper_sweep_active = False
        self.upper_sweep_max: Optional[float] = None

        self.lower_sweep_active = False
        self.lower_sweep_min: Optional[float] = None

    def _reset_daily_state(self, date):
        self.current_date = date
        self.asian_high = None
        self.asian_low = None
        self.upper_sweep_active = False
        self.upper_sweep_max = None
        self.lower_sweep_active = False
        self.lower_sweep_min = None

    def on_tick(
        self,
        current_time: datetime,
        m1_candle: Dict[str, Any],
        m5_candles: List[Dict[str, Any]],
        m15_candles: List[Dict[str, Any]],
        h1_candles: List[Dict[str, Any]],
        engine: ExecutionEngine,
        in_session: bool = True
    ):
        tick_date = current_time.date()
        if tick_date != self.current_date:
            self._reset_daily_state(tick_date)

        # ── Step 1: Accumulate Asian Session Range (00:00 - 07:00 UTC) ──
        if Config.ASIAN_START_HOUR <= current_time.hour < Config.ASIAN_END_HOUR:
            c_high = m1_candle['high']
            c_low = m1_candle['low']
            if self.asian_high is None or c_high > self.asian_high:
                self.asian_high = c_high
            if self.asian_low is None or c_low < self.asian_low:
                self.asian_low = c_low
            return

        # ── Step 2: Session Window Evaluation (07:00 - 09:00 UTC Entry Window) ──
        if not in_session:
            return

        # Ensure Asian range was successfully recorded
        if self.asian_high is None or self.asian_low is None or self.asian_high <= self.asian_low:
            return

        c_high = m1_candle['high']
        c_low = m1_candle['low']
        c_close = m1_candle['close']

        # ── Step 3: Track Sweeps Beyond Asian Range ──
        # Upper Sweep Detection
        if c_high > self.asian_high:
            self.upper_sweep_active = True
            if self.upper_sweep_max is None or c_high > self.upper_sweep_max:
                self.upper_sweep_max = c_high

        # Lower Sweep Detection
        if c_low < self.asian_low:
            self.lower_sweep_active = True
            if self.lower_sweep_min is None or c_low < self.lower_sweep_min:
                self.lower_sweep_min = c_low

        # ── Step 4: Evaluate Reversal Entries ──
        spread_pips = engine.spread_pips
        spread_price = engine.spread_price

        # SHORT REVERSION ENTRY (after Upper Sweep)
        # Price must have swept above asian_high, and now closed back BELOW asian_high
        if self.upper_sweep_active and c_close < self.asian_high:
            sl_price = self.upper_sweep_max + (Config.SL_BUFFER_PIPS * Config.PIP)
            effective_entry = c_close - spread_price  # Short entry price after spread
            sl_pips = (sl_price - effective_entry) / Config.PIP

            if Config.TP_MODE == "OPPOSITE_BOUNDARY":
                tp_pips = (effective_entry - self.asian_low) / Config.PIP
            else:
                tp_pips = sl_pips * Config.RISK_REWARD_RATIO

            if sl_pips > 0 and tp_pips > 0:
                opened = engine.try_open_trade(
                    direction="SHORT",
                    current_time=current_time,
                    current_close=c_close,
                    sl_pips=sl_pips,
                    tp_pips=tp_pips
                )
                if opened:
                    self.upper_sweep_active = False
                    self.upper_sweep_max = None
                    return

        # LONG REVERSION ENTRY (after Lower Sweep)
        # Price must have swept below asian_low, and now closed back ABOVE asian_low
        if self.lower_sweep_active and c_close > self.asian_low:
            sl_price = self.lower_sweep_min - (Config.SL_BUFFER_PIPS * Config.PIP)
            effective_entry = c_close + spread_price  # Long entry price after spread
            sl_pips = (effective_entry - sl_price) / Config.PIP

            if Config.TP_MODE == "OPPOSITE_BOUNDARY":
                tp_pips = (self.asian_high - effective_entry) / Config.PIP
            else:
                tp_pips = sl_pips * Config.RISK_REWARD_RATIO

            if sl_pips > 0 and tp_pips > 0:
                opened = engine.try_open_trade(
                    direction="LONG",
                    current_time=current_time,
                    current_close=c_close,
                    sl_pips=sl_pips,
                    tp_pips=tp_pips
                )
                if opened:
                    self.lower_sweep_active = False
                    self.lower_sweep_min = None
                    return
