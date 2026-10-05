import pandas as pd
from typing import Dict, List, Any

class DataFeeder:
    """
    Simulates real-time market ticks by iterating row-by-row on M1 data.
    Synthesizes higher timeframes strictly without look-ahead bias and elegantly handles gaps.
    """
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        print(f"Loading data from {data_path}...")
        self.df = pd.read_csv(self.data_path)
        self.df['time'] = pd.to_datetime(self.df['time'])
        
        # MTF intervals mapping (keys -> minutes)
        self.timeframes = {
            'M5': 5,
            'M15': 15,
            'H1': 60
        }
        
        self.historical_data: Dict[str, List[Dict[str, Any]]] = {tf: [] for tf in self.timeframes.keys()}
        self.historical_data['M1'] = []
        
        self._wip_candles = {tf: None for tf in self.timeframes.keys()}

    def _sync_higher_timeframes(self, m1_row: pd.Series):
        current_time = m1_row['time']
        
        for tf, minutes in self.timeframes.items():
            # Calculate the mathematical anchor boundary for the current timeframe.
            # Example: current 02:17 mapped to M15 gives an anchor of 02:15.
            if minutes == 60:
                anchor_time = current_time.replace(minute=0, second=0, microsecond=0)
            else:
                anchor_minute = (current_time.minute // minutes) * minutes
                anchor_time = current_time.replace(minute=anchor_minute, second=0, microsecond=0)
            
            wip = self._wip_candles[tf]
            
            # Look-Ahead Bias / Gap Handling Magic:
            # If the M1 timestamp crosses into a NEW anchor boundary, the previous WIP candle
            # is declared perfectly closed and appended to the historical record.
            if wip and wip['time'] < anchor_time:
                self.historical_data[tf].append(wip.copy())
                wip = None # Reset for the new boundary
                
            # If WIP is None, start a new one
            if wip is None:
                wip = {
                    'time': anchor_time,
                    'open': m1_row['open'],
                    'high': m1_row['high'],
                    'low': m1_row['low'],
                    'close': m1_row['close'],
                    'tick_volume': m1_row.get('tick_volume', 0)
                }
            else:
                # Update WIP candle as M1 evolves inside the boundary
                wip['high'] = max(wip['high'], m1_row['high'])
                wip['low'] = min(wip['low'], m1_row['low'])
                wip['close'] = m1_row['close']
                wip['tick_volume'] += m1_row.get('tick_volume', 0)
                
            self._wip_candles[tf] = wip

    def yield_ticks(self):
        """
        Generator yielding the next M1 tick while managing MTF history.
        """
        for _, row in self.df.iterrows():
            self._sync_higher_timeframes(row)
            row_dict = row.to_dict()
            self.historical_data['M1'].append(row_dict)
            
            # The yield occurs AFTER the higher TFs have potentially closed.
            # Work-in-progress (WIP) candles are hidden in self._wip_candles and NOT exposed.
            yield row_dict
            
    def get_closed_candles(self, tf: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Returns only the FULLY CLOSED historical candles for a timeframe.
        Look-ahead bias is structurally impossible here.
        """
        if tf not in self.historical_data:
            return []
        # Return the most recent N closed candles
        return self.historical_data[tf][-limit:]

if __name__ == "__main__":
    print("DataFeeder structural design is ready.")
