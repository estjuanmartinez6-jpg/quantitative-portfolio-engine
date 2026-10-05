from datetime import datetime
from typing import Dict, List, Optional
import pytz

class ExecutionEngine:
    """
    Pip-based simulated execution engine.
    Ignores balance/equity, tracks Pure Pips, enforces simulated spread and '1 Trade Per Session'.
    """
    def __init__(self, spread_pips: float = 0.8, target_tz: str = 'America/Bogota'):
        self.spread_pips = spread_pips
        # Multiplier for EURUSD to convert pips to price offset
        self.pip_multiplier = 0.0001 
        self.spread_price = spread_pips * self.pip_multiplier
        
        self.target_timezone = pytz.timezone(target_tz)
        
        self.open_position: Optional[Dict] = None
        self.trade_history: List[Dict] = []
        
        # Guardrail: 1 trade per session day
        self.last_trade_date: Optional[datetime.date] = None

    def _get_colombia_date(self, broker_time: datetime) -> datetime.date:
        """Converts broker datetime into the target local date."""
        if broker_time.tzinfo is None:
            # Re-localize MT5 naive timestamp to Broker Time (typically EET/EEST)
            broker_time = pytz.timezone('Europe/Bucharest').localize(broker_time)
        return broker_time.astimezone(self.target_timezone).date()

    def try_open_trade(self, direction: str, current_time: datetime, current_close: float, sl_pips: float, tp_pips: float) -> bool:
        """
        Attempts to open a trade. Returns True if successful, False if rejected.
        Includes simulated spread penalization directly on the entry price.
        """
        if self.open_position is not None:
            return False # Already in a position
            
        colombia_date = self._get_colombia_date(current_time)
        if self.last_trade_date == colombia_date:
            return False # ONE TRADE PER SESSION GUARDRAIL TRIGGERED
            
        entry_price = current_close
        
        # Apply Spread (Worsens the entry price against the direction)
        if direction == "LONG":
            entry_price += self.spread_price
            sl_price = entry_price - (sl_pips * self.pip_multiplier)
            tp_price = entry_price + (tp_pips * self.pip_multiplier)
        elif direction == "SHORT":
            entry_price -= self.spread_price
            # SL for short is UP, TP is DOWN
            sl_price = entry_price + (sl_pips * self.pip_multiplier)
            tp_price = entry_price - (tp_pips * self.pip_multiplier)
        else:
            return False
            
        self.open_position = {
            'direction': direction,
            'entry_time': current_time,
            'entry_price': entry_price,
            'base_sl': sl_price,  # Keep original SL just in case we need it
            'sl': sl_price,
            'tp': tp_price,
            'breakeven_triggered': False
        }
        
        self.last_trade_date = colombia_date
        return True
        
    def move_to_breakeven(self):
        """Moves the stop loss to the exact entry price, ensuring a risk-free trade."""
        if self.open_position and not self.open_position['breakeven_triggered']:
            # Move SL to entry price
            self.open_position['sl'] = self.open_position['entry_price']
            self.open_position['breakeven_triggered'] = True

    def check_position(self, current_time: datetime, high: float, low: float):
        """
        Evaluates the open position against the current M1 high/low for SL/TP hits.
        Uses pessimistic execution: if both SL and TP are triggered in the same minute, SL is assumed.
        """
        if not self.open_position:
            return
            
        pos = self.open_position
        closed = False
        pips_profit = 0.0
        
        if pos['direction'] == "LONG":
            if low <= pos['sl']:
                pips_profit = (pos['sl'] - pos['entry_price']) / self.pip_multiplier
                closed = True
            elif high >= pos['tp']:
                pips_profit = (pos['tp'] - pos['entry_price']) / self.pip_multiplier
                closed = True
                
        elif pos['direction'] == "SHORT":
            if high >= pos['sl']:
                # Short loses money when price goes up
                pips_profit = (pos['entry_price'] - pos['sl']) / self.pip_multiplier
                closed = True
            elif low <= pos['tp']:
                pips_profit = (pos['entry_price'] - pos['tp']) / self.pip_multiplier
                closed = True
                
        if closed:
            self._record_trade_exit(pos, current_time, pips_profit)
            
    def force_close(self, current_time: datetime, current_close: float):
        """
        Called when session strictly ends (04:00). Forces closure of the open position.
        """
        if not self.open_position:
            return
            
        pos = self.open_position
        if pos['direction'] == "LONG":
            pips_profit = (current_close - pos['entry_price']) / self.pip_multiplier
        else:
            pips_profit = (pos['entry_price'] - current_close) / self.pip_multiplier
            
        self._record_trade_exit(pos, current_time, pips_profit, note='Forced Close (Session End)')

    def _record_trade_exit(self, pos: Dict, exit_time: datetime, pips_profit: float, note: str = ""):
        self.trade_history.append({
            'direction': pos['direction'],
            'entry_time': pos['entry_time'],
            'exit_time': exit_time,
            'pips_profit': round(pips_profit, 2),
            'is_win': pips_profit > 0,
            'note': note
        })
        self.open_position = None
