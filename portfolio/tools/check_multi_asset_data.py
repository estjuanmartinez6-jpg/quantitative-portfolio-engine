"""
Verify Data Availability for Multi-Asset-Class Momentum Universe
Spans 4 Asset Classes across 15 Instruments:
1. Equities: S&P 500 (ES=F / SPY), Nasdaq-100 (NQ=F / QQQ), Russell 2000 (RTY=F / IWM), Dow Jones (YM=F / DIA)
2. Fixed Income / Bonds: 10Y Treasury (ZN=F / IEF), 30Y Treasury (ZB=F / TLT)
3. Commodities: Gold (GC=F / GLD), WTI Crude (CL=F / USO), Silver (SI=F / SLV), Natural Gas (NG=F / UNG)
4. FX Majors: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, NZD/USD
"""
import os, sys
import pandas as pd
import yfinance as yf

# Map 15 Multi-Asset Tickers
MULTI_ASSET_TICKERS = {
    # Equities
    'SP500': 'SPY',
    'NASDAQ': 'QQQ',
    'RUSSELL': 'IWM',
    'DOW': 'DIA',
    # Fixed Income
    'US10Y': 'IEF',
    'US30Y': 'TLT',
    # Commodities
    'GOLD': 'GLD',
    'CRUDE_OIL': 'USO',
    'SILVER': 'SLV',
    'NAT_GAS': 'UNG',
    # FX Majors
    'EURUSD': 'EURUSD=X',
    'GBPUSD': 'GBPUSD=X',
    'USDJPY': 'JPY=X',
    'AUDUSD': 'AUDUSD=X',
    'USDCAD': 'CAD=X'
}

ASSET_CLASS_MAP = {
    'SP500': 'Equities', 'NASDAQ': 'Equities', 'RUSSELL': 'Equities', 'DOW': 'Equities',
    'US10Y': 'Fixed Income', 'US30Y': 'Fixed Income',
    'GOLD': 'Commodities', 'CRUDE_OIL': 'Commodities', 'SILVER': 'Commodities', 'NAT_GAS': 'Commodities',
    'EURUSD': 'FX', 'GBPUSD': 'FX', 'USDJPY': 'FX', 'AUDUSD': 'FX', 'USDCAD': 'FX'
}

def check_multi_asset_data():
    print("Fetching 15+ years of continuous daily data for 15 Multi-Asset Instruments...", flush=True)
    raw = yf.download(list(MULTI_ASSET_TICKERS.values()), start="2004-01-01", end="2026-01-01", interval="1d")
    
    close_df = raw['Close'].copy()
    inv_map = {v: k for k, v in MULTI_ASSET_TICKERS.items()}
    close_df = close_df.rename(columns=inv_map).sort_index().dropna(how='all')

    print(f"\nDownloaded Data Summary ({len(close_df)} trading days):")
    print(f"{'Asset Class':<15} {'Instrument':<12} {'Ticker':<10} {'Data Rows':>10} {'Start Date':>12} {'End Date':>12}")
    print("-" * 75)
    
    for name, ticker in MULTI_ASSET_TICKERS.items():
        if name in close_df.columns:
            s = close_df[name].dropna()
            count = len(s)
            start_d = s.index.min().strftime('%Y-%m-%d')
            end_d = s.index.max().strftime('%Y-%m-%d')
            ac = ASSET_CLASS_MAP[name]
            print(f"{ac:<15} {name:<12} {ticker:<10} {count:>10} {start_d:>12} {end_d:>12}")
            
    return close_df

if __name__ == "__main__":
    check_multi_asset_data()
