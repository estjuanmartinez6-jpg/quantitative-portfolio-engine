"""
Data Loader Module for fx_momentum_portfolio
Fetches and caches 15+ years of Daily OHLC data for the 7 major USD FX pairs:
EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD.
"""
import os
import pandas as pd
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")

TICKERS = {
    'EURUSD': 'EURUSD=X',
    'GBPUSD': 'GBPUSD=X',
    'USDJPY': 'JPY=X',
    'AUDUSD': 'AUDUSD=X',
    'USDCAD': 'CAD=X',
    'USDCHF': 'CHF=X',
    'NZDUSD': 'NZDUSD=X'
}

# Define quote structure: True if price is USD per 1 Foreign Currency (EURUSD, GBPUSD, AUDUSD, NZDUSD)
# False if price is Foreign Currency per 1 USD (USDJPY, USDCAD, USDCHF)
IS_USD_QUOTE = {
    'EURUSD': True,
    'GBPUSD': True,
    'USDJPY': False,
    'AUDUSD': True,
    'USDCAD': False,
    'USDCHF': False,
    'NZDUSD': True
}

def download_and_cache_data(start_date="2010-01-01", end_date="2026-01-01") -> pd.DataFrame:
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_path = os.path.join(DATA_DIR, "fx_majors_daily_2010_2025.csv")
    
    if os.path.exists(cache_path):
        print(f"Loading cached daily FX data from {cache_path}...")
        df_prices = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        return df_prices

    print(f"Downloading 15+ years of daily OHLC data for 7 major USD pairs via yfinance...")
    raw_data = yf.download(list(TICKERS.values()), start=start_date, end=end_date, interval="1d")
    
    close_df = raw_data['Close'].copy()
    
    # Rename columns to standard pair names
    inv_map = {v: k for k, v in TICKERS.items()}
    close_df = close_df.rename(columns=inv_map)

    # Sort index and drop empty rows
    close_df = close_df.sort_index().dropna(how='all')
    close_df.to_csv(cache_path)
    print(f"Successfully cached daily prices to {cache_path} ({len(close_df)} trading days).")
    
    return close_df

def load_split_datasets(dev_start="2010-01-01", dev_end="2020-01-01", oos_end="2025-12-31"):
    full_df = download_and_cache_data()
    
    dev_df = full_df[(full_df.index >= dev_start) & (full_df.index < dev_end)].copy()
    oos_df = full_df[(full_df.index >= dev_end) & (full_df.index <= oos_end)].copy()
    
    print(f"Data Split Loaded:")
    print(f"  Development Set: {dev_df.index.min().strftime('%Y-%m-%d')} to {dev_df.index.max().strftime('%Y-%m-%d')} ({len(dev_df)} days)")
    print(f"  Out-of-Sample Set: {oos_df.index.min().strftime('%Y-%m-%d')} to {oos_df.index.max().strftime('%Y-%m-%d')} ({len(oos_df)} days - SEALED)")
    
    return dev_df, oos_df

if __name__ == "__main__":
    dev, oos = load_split_datasets()
    print("\nSample Dev Set Prices:")
    print(dev.head())
