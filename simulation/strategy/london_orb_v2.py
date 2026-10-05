from datetime import datetime, time
from typing import Dict, List, Optional, Any
from strategy.base_strategy import BaseStrategy
from core.execution_engine import ExecutionEngine


class Config:
    VERSION_TAG = "v2.0-london-orb"

    # Time Windows (UTC)
    ASIAN_START_HOUR = 0
    ASIAN_END_HOUR = 7
    SESSION_START_HOUR = 7
    SESSION_END_HOUR = 9

    # Trigger & Confirmation
    ORB_CONFIRMATION_CANDLES = 2  # Number of M1 closes required beyond Asian boundary

    # Regime / Quality Filter (Toggleable)
    ENABLE_RANGE_FILTER = False  # False for Run A (baseline), True for Run B
    ORB_MIN_RANGE_ATR_MULT = 0.5
    ORB_MAX_RANGE_ATR_MULT = 1.5
    ATR_PERIOD = 14

    # Risk Management
    SL_MODE = "OPPOSITE"  # Options: "OPPOSITE" (opposite Asian range boundary) or "MIDPOINT" (50% of Asian range)
    SL_BUFFER_PIPS = 1.0  # Buffer pips beyond opposite or midpoint
    RISK_REWARD_RATIO = 2.0  # Default 2.0R for TP
    TP_MODE = "RR"  # Options: "RR" (risk-reward multiple) or "MEASURED_MOVE" (Asian range pips)

    # Early Time Exit Invalidation
    ENABLE_EARLY_EXIT = False
    EARLY_EXIT_WINDOW_MINUTES = 45.0
    EARLY_EXIT_MFE_R = 0.2

    # Instrument parameters
    PIP = 0.0001


def calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    """
    Calculates Average True Range (ATR) in pips over N closed candles.
    """
    if len(candles) < period + 1:
        return 0.0

    tr_list = []
    for i in range(1, len(candles)):
        high = candles[i]['high']
        low = candles[i]['low']
        prev_close = candles[i - 1]['close']

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        tr_list.append(tr)

    if len(tr_list) < period:
        return 0.0

    atr = sum(tr_list[-period:]) / period
    return atr / Config.PIP


class LondonORBV2(BaseStrategy):
    """
    London Opening Range Breakout Strategy (v2.0-london-orb)
    Reuses core SessionManager (UTC), ExecutionEngine, and DataFeeder.
    """

    def __init__(self):
        super().__init__(name="LondonORBV2")
        self.current_date = None
        self.asian_high: Optional[float] = None
        self.asian_low: Optional[float] = None

        self.bullish_closes_count = 0
        self.bearish_closes_count = 0
        self.range_filter_passed: Optional[bool] = None

        self.current_trade_mfe = 0.0
        self.mfe_initialized = False

    def _reset_daily_state(self, date):
        self.current_date = date
        self.asian_high = None
        self.asian_low = None
        self.bullish_closes_count = 0
        self.bearish_closes_count = 0
        self.range_filter_passed = None
        self.current_trade_mfe = 0.0
        self.mfe_initialized = False

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

        # ── Step 0: Open Position MFE Tracker & Early Time Invalidation Exit ──
        if engine.open_position is None:
            self.current_trade_mfe = 0.0
            self.mfe_initialized = False
        else:
            pos = engine.open_position
            if pos['direction'] == 'LONG':
                sl_pips = (pos['entry_price'] - pos['sl']) / Config.PIP
                fav_pips = (m1_candle['high'] - pos['entry_price']) / Config.PIP
            else:
                sl_pips = (pos['sl'] - pos['entry_price']) / Config.PIP
                fav_pips = (pos['entry_price'] - m1_candle['low']) / Config.PIP
            
            if not self.mfe_initialized:
                self.current_trade_mfe = max(0.0, fav_pips)
                self.mfe_initialized = True
            else:
                self.current_trade_mfe = max(self.current_trade_mfe, fav_pips)
                
            # Perform Early Time Exit Check
            if Config.ENABLE_EARLY_EXIT:
                elapsed_minutes = (current_time - pos['entry_time']).total_seconds() / 60.0
                mfe_r = self.current_trade_mfe / sl_pips if sl_pips > 0 else 0.0
                
                if elapsed_minutes >= Config.EARLY_EXIT_WINDOW_MINUTES and mfe_r < Config.EARLY_EXIT_MFE_R:
                    engine.force_close(current_time, current_close=m1_candle['close'])
                    if len(engine.trade_history) > 0:
                        engine.trade_history[-1]['note'] = 'Early Exit (Time Invalidation)'
                    self.current_trade_mfe = 0.0
                    self.mfe_initialized = False

        # ── Step 1: Accumulate Asian Session Range (00:00 - 07:00 UTC) ──
        if Config.ASIAN_START_HOUR <= current_time.hour < Config.ASIAN_END_HOUR:
            c_high = m1_candle['high']
            c_low = m1_candle['low']
            if self.asian_high is None or c_high > self.asian_high:
                self.asian_high = c_high
            if self.asian_low is None or c_low < self.asian_low:
                self.asian_low = c_low
            return

        # ── Step 2: Session Window Evaluation (07:00 - 09:00 UTC) ──
        if not in_session:
            return

        # Ensure Asian range was successfully recorded
        if self.asian_high is None or self.asian_low is None or self.asian_high <= self.asian_low:
            return

        # ── Step 3: Evaluate Regime / Range Filter (if enabled) ──
        if self.range_filter_passed is None:
            if Config.ENABLE_RANGE_FILTER:
                range_pips = (self.asian_high - self.asian_low) / Config.PIP
                atr_pips = calculate_atr(m15_candles, period=Config.ATR_PERIOD)

                if atr_pips > 0:
                    min_range = Config.ORB_MIN_RANGE_ATR_MULT * atr_pips
                    max_range = Config.ORB_MAX_RANGE_ATR_MULT * atr_pips
                    self.range_filter_passed = (min_range <= range_pips <= max_range)
                else:
                    self.range_filter_passed = False
            else:
                self.range_filter_passed = True

        if not self.range_filter_passed:
            return

        # ── Step 4: Track Breakout Confirmation Closes ──
        c_close = m1_candle['close']

        if c_close > self.asian_high:
            self.bullish_closes_count += 1
            self.bearish_closes_count = 0
        elif c_close < self.asian_low:
            self.bearish_closes_count += 1
            self.bullish_closes_count = 0
        else:
            self.bullish_closes_count = 0
            self.bearish_closes_count = 0

        # ── Step 5: Execute Signal if Confirmation Met ──
        asian_range_pips = (self.asian_high - self.asian_low) / Config.PIP

        # LONG Signal
        if self.bullish_closes_count >= Config.ORB_CONFIRMATION_CANDLES:
            if Config.SL_MODE == "MIDPOINT":
                midpoint = (self.asian_high + self.asian_low) / 2.0
                sl_price = midpoint - (Config.SL_BUFFER_PIPS * Config.PIP)
            else:
                sl_price = self.asian_low - (Config.SL_BUFFER_PIPS * Config.PIP)
                
            sl_pips = (c_close - sl_price) / Config.PIP

            if Config.TP_MODE == "MEASURED_MOVE":
                tp_pips = asian_range_pips
            else:
                tp_pips = sl_pips * Config.RISK_REWARD_RATIO

            if sl_pips > 0:
                opened = engine.try_open_trade(
                    direction="LONG",
                    current_time=current_time,
                    current_close=c_close,
                    sl_pips=sl_pips,
                    tp_pips=tp_pips
                )
                if opened:
                    self.bullish_closes_count = 0
                    self.bearish_closes_count = 0
                    return

        # SHORT Signal
        if self.bearish_closes_count >= Config.ORB_CONFIRMATION_CANDLES:
            if Config.SL_MODE == "MIDPOINT":
                midpoint = (self.asian_high + self.asian_low) / 2.0
                sl_price = midpoint + (Config.SL_BUFFER_PIPS * Config.PIP)
            else:
                sl_price = self.asian_high + (Config.SL_BUFFER_PIPS * Config.PIP)
                
            sl_pips = (sl_price - c_close) / Config.PIP

            if Config.TP_MODE == "MEASURED_MOVE":
                tp_pips = asian_range_pips
            else:
                tp_pips = sl_pips * Config.RISK_REWARD_RATIO

            if sl_pips > 0:
                opened = engine.try_open_trade(
                    direction="SHORT",
                    current_time=current_time,
                    current_close=c_close,
                    sl_pips=sl_pips,
                    tp_pips=tp_pips
                )
                if opened:
                    self.bullish_closes_count = 0
                    self.bearish_closes_count = 0
                    return
