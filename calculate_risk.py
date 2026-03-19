import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import time
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

# ==========================================
# ⚙️ 系統參數設定
# ==========================================
LAMBDA_DECAY = 0.94      
VAR_PERCENTILE = 0.05    
LOOKBACK_YEARS = 5       
OUTPUT_FILE = "risk_lookup.json"

def get_ewma_weights(length):
    days_ago = np.arange(length - 1, -1, -1)
    weights = np.power(LAMBDA_DECAY, days_ago)
    return weights / np.sum(weights)

def extract_price_series(df):
    """🛡️ 強健提取價格序列，抵抗 yfinance 新版 MultiIndex 與欄位缺失問題"""
    if df.empty:
        return pd.Series(dtype=float)
    
    # 1. 處理 yfinance 新版的 MultiIndex (把 Ticker 層級拔掉)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    # 2. 尋找收盤價欄位 (優先找 Adj Close，沒有就找 Close)
    if 'Adj Close' in df.columns:
        target_col = 'Adj Close'
    elif 'Close' in df.columns:
        target_col = 'Close'
    else:
        target_col = df.columns[0] # 真找不到就拿第一欄
        
    prices = df[target_col]
    
    # 3. 如果拔掉層級後變成 DataFrame (欄位名重複)，強制取第一欄
    if isinstance(prices, pd.DataFrame):
        prices = prices.iloc[:, 0]
        
    return pd.to_numeric(prices, errors='coerce').dropna()

def fetch_benchmark_prices(symbol):
    print(f"📥 正在下載基準指數: {symbol}")
    bench = yf.download(symbol, period=f"{LOOKBACK_YEARS}y", progress=False)
    return extract_price_series(bench)

def calculate_metrics(ticker, bench_prices):
    try:
        stock = yf.download(ticker, period=f"{LOOKBACK_YEARS}y", progress=False)
        if stock.empty or len(stock) < 100: 
            return None 
            
        prices = extract_price_series(stock)
        
        daily_returns = prices.pct_change().dropna()
        if daily_returns.empty:
            return None

        # MDD
        rolling_max = prices.cummax()
        drawdowns = (prices - rolling_max) / rolling_max
        mdd = drawdowns.min()

        # EWMA
        T = len(daily_returns)
        weights = get_ewma_weights(T)
        df_sim = pd.DataFrame({'Return': daily_returns.values, 'Weight': weights})
        
        # VaR & CVaR 
        df_sorted = df_sim.sort_values(by='Return').reset_index(drop=True)
        df_sorted['CumWeight'] = df_sorted['Weight'].cumsum()
        
        var_idx = df_sorted[df_sorted['CumWeight'] >= VAR_PERCENTILE].index[0]
        var_95 = df_sorted.loc[var_idx, 'Return']
        
        tail_events = df_sorted.iloc[:var_idx]
        if len(tail_events) > 0:
            cvar_95 = np.average(tail_events['Return'], weights=tail_events['Weight'])
        else:
            cvar_95 = var_95
            
        # DownVol 
        down_days = df_sim[df_sim['Return'] < 0]
        if len(down_days) > 0:
            down_weights = down_days['Weight'] / down_days['Weight'].sum()
            weighted_var = np.average((down_days['Return'])**2, weights=down_weights)
            down_vol = np.sqrt(weighted_var * 252) 
        else:
            down_vol = 0
            
        # Beta (Bloomberg Methodology)
        aligned_prices = pd.concat([prices, bench_prices], axis=1, join='inner').dropna()
        aligned_prices.columns = ['Stock', 'Bench']
        
        aligned_2y = aligned_prices.tail(504)
        
        if len(aligned_2y) > 50:
            weekly_prices = aligned_2y.resample('W-FRI').last()
            weekly_returns = weekly_prices.pct_change().dropna()
            
            if len(weekly_returns) > 10:
                cov_matrix = np.cov(weekly_returns['Stock'].values, weekly_returns['Bench'].values)
                cov_sb = cov_matrix[0, 1] 
                var_b = cov_matrix[1, 1]  
                beta = cov_sb / var_b if var_b > 0 else 1.0
            else:
                beta = 1.0
        else:
            beta = 1.0

        custom_name = ""
        if "2330.TW" in ticker: custom_name = "台積電"
        elif "0050.TW" in ticker: custom_name = "元大台灣50"
        elif "00632R.TW" in ticker: custom_name = "元大台灣50反1"

        return {
            "name": custom_name,
            "mdd": round(float(mdd) * 100, 2),
            "var_95": round(float(var_95) * 100, 2),
            "cvar_95": round(float(cvar_95) * 100, 2),
            "down_vol": round(float(down_vol) * 100, 2),
            "beta": round(float(beta), 2),
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        }

    except Exception as e:
        print(f"⚠️ {ticker} 運算失敗: {e}")
        return None

def main():
    print("🚀 啟動 AP 雲端量化引擎 (Bloomberg Beta 升級版)")
    
    risk_db = {}
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            try:
                risk_db = json.load(f)
                print(f"✅ 成功載入歷史斷點，已完成 {len(risk_db)} 檔標的。")
            except:
                print("⚠️ json 格式錯誤，重新建立。")
    
    bench_tw_prices = fetch_benchmark_prices('^TWII')
    bench_us_prices = fetch_benchmark_prices('^GSPC')

    target_tickers = []
    if os.path.exists("my_tickers.txt"):
        with open("my_tickers.txt", "r", encoding="utf-8") as f:
            target_tickers = [line.strip() for line in f.readlines() if line.strip()]
        print(f"📋 共讀取到 {len(target_tickers)} 檔標的準備處理。")
    else:
        print("⚠️ 找不到 my_tickers.txt，請先執行清單抓取程式！")
        return
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    count = 0
    
    for ticker in target_tickers:
        if ticker in risk_db and risk_db[ticker].get("last_updated") == today_str:
            continue
            
        print(f"🔍 正在運算: {ticker:<10} ...", end=" ")
        
        bench_p = bench_tw_prices if ticker.endswith((".TW", ".TWO")) else bench_us_prices
        result = calculate_metrics(ticker, bench_p)
        
        if result:
            risk_db[ticker] = result
            print(f"完成! (Beta: {result['beta']}, CVaR: {result['cvar_95']}%)")
            count += 1
            
            if count % 5 == 0:
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(risk_db, f, ensure_ascii=False, indent=2)
                    
        time.sleep(0.2)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(risk_db, f, ensure_ascii=False, indent=2)
        
    print(f"🎉 運算結束！本次新增/更新了 {count} 檔標的。")

if __name__ == "__main__":
    main()
