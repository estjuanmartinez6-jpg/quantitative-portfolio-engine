import pandas as pd
from typing import List, Dict

def calculate_metrics(trade_history: List[Dict]) -> Dict:
    """
    Computes professional strategy metrics strictly based on pip data.
    """
    if not trade_history:
        return {}
        
    df = pd.DataFrame(trade_history)
    
    total_trades = len(df)
    wins = df[df['is_win'] == True]
    losses = df[df['is_win'] == False]
    
    win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
    
    gross_profit = wins['pips_profit'].sum() if not wins.empty else 0.0
    # Losses are stored as negative (e.g. -5.0 pips)
    gross_loss = abs(losses['pips_profit'].sum()) if not losses.empty else 0.0
    
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    
    avg_win = wins['pips_profit'].mean() if not wins.empty else 0.0
    avg_loss = abs(losses['pips_profit'].mean()) if not losses.empty else 0.0
    
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    
    # Max Drawdown (in pips)
    df['cumulative_pips'] = df['pips_profit'].cumsum()
    df['peak'] = df['cumulative_pips'].cummax()
    df['drawdown'] = df['peak'] - df['cumulative_pips']
    max_drawdown = df['drawdown'].max() if not df.empty else 0.0
    
    # Trade frequency
    start_time = pd.to_datetime(df['entry_time'].min())
    end_time = pd.to_datetime(df['exit_time'].max())
    days_diff = (end_time - start_time).days
    trades_per_day = total_trades / days_diff if days_diff > 0 else total_trades
    
    return {
        'total_trades': total_trades,
        'win_rate': round(win_rate * 100, 2),
        'gross_profit_pips': round(gross_profit, 2),
        'gross_loss_pips': round(gross_loss, 2),
        'net_profit_pips': round(gross_profit - gross_loss, 2),
        'profit_factor': round(profit_factor, 2),
        'avg_win_pips': round(avg_win, 2),
        'avg_loss_pips': round(avg_loss, 2),
        'expectancy_pips': round(expectancy, 2),
        'max_drawdown_pips': round(max_drawdown, 2),
        'trades_per_day': round(trades_per_day, 2)
    }

def print_metrics_report(metrics: Dict):
    print("\n" + "="*50)
    print("      LONDON SESSION SIMULATOR: METRICS REPORT")
    print("="*50)
    if not metrics:
        print("No trades were taken during the simulation period.")
        return
        
    for key, value in metrics.items():
        # Formatting nicely for the console
        friendly_key = key.replace('_', ' ').title()
        if 'Rate' in friendly_key:
            print(f"{friendly_key:<25}: {value}%")
        else:
            print(f"{friendly_key:<25}: {value}")
    print("="*50 + "\n")
    
def export_history_to_csv(trade_history: List[Dict], filepath: str = "trade_history.csv"):
    if not trade_history:
        return
    df = pd.DataFrame(trade_history)
    df.to_csv(filepath, index=False)
    print(f"Trade history exported to: {filepath}")
