from datetime import datetime
from typing import Dict, List
from core.execution_engine import ExecutionEngine

class BaseStrategy:
    """
    Abstract template for London Session bots.
    Forces implementation of the per-tick evaluation logic.
    """
    def __init__(self, name: str):
        self.name = name

    def on_tick(self, current_time: datetime, m1_candle: Dict, m5_candles: List[Dict], m15_candles: List[Dict], h1_candles: List[Dict], engine: ExecutionEngine, in_session: bool = True):
        """
        Called every M1 tick (24/7, not just during session).
        :param current_time: The current simulation timestamp.
        :param m1_candle: The current M1 candle forming (can be used for current close price).
        :param m5_candles: 100% closed historical M5 candles (No Look-Ahead!).
        :param m15_candles: 100% closed historical M15 candles.
        :param h1_candles: 100% closed historical H1 candles.
        :param engine: The pipeline to open positions.
        :param in_session: True if we are inside the active trading session window.
        """
        raise NotImplementedError("Strategy must implement on_tick")
