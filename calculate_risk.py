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

# Bloomberg Beta 設定
ADJUST_ALPHA = 0.67

# 數據品質過濾閾值
QUALITY_RULES = {
    "mdd_delisted":      -99.0,    # MDD <= -99% → 視為下市或極端壁紙
    "down_vol_max":       100.0,   # 年化下行波動率上限
    "cvar_var_ratio_max":   3.0,   # CVaR / VaR 比值上限 (放寬一點避免誤殺)
}

# 靜態期貨 Beta (若遇到這些代號直接給定)
FUTURE_BETA_MAP = {
    "NQ":  1.3, "ES":  1.0, "RTY": 1.4, "YM":  1.0,
    "GC": -0.1, "CL":  0.3, "TX":  1.1,
}

# ────────────────────────────────────────
# 工具函數
# ────────────────────────────────────────

def get_ewma_weights(length):
    days_ago = np.arange(length - 1, -1, -1)
    weights = np.power(LAMBDA_DECAY, days_ago)
    return weights / np.sum(weights)

def extract_price_series(df):
    """🛡️ 強健提取價格序列，抵抗 yfinance 新版 MultiIndex 與欄位缺失問題"""
    if df.empty: return pd.Series(dtype=float)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    if 'Adj Close' in df.columns: target_col = 'Adj Close'
    elif 'Close' in df.columns: target_col = 'Close'
    else: target_col = df.columns[0]
        
    prices = df[target_col]
    if isinstance(prices, pd.DataFrame):
        prices = prices.iloc[:, 0]
        
    return pd.to_numeric(prices, errors='coerce').dropna()

def fetch_benchmark_prices(symbol):
    print(f"📥 正在下載基準指數: {symbol}")
    bench = yf.download(symbol, period=f"{LOOKBACK_YEARS}y", progress=False)
    return extract_price_series(bench)

def assess_quality(mdd, down_vol, var_95, cvar_95):
    """評估數據品質，供前端顯示警示用"""
    if mdd <= QUALITY_RULES["mdd_delisted"]:
        return "delisted"
    if abs(down_vol) > QUALITY_RULES["down_vol_max"]:
        return "unreliable"
    if abs(var_95) > 0:
        ratio = abs(cvar_95) / abs(var_95)
        if ratio > QUALITY_RULES["cvar_var_ratio_max"]:
            return "fat_tail"
    return "ok"

# ────────────────────────────────────────
# 核心演算法
# ────────────────────────────────────────

def calculate_metrics(ticker, bench_prices):
    # 處理靜態期貨
    if ticker.upper() in FUTURE_BETA_MAP:
        return {
            "beta": FUTURE_BETA_MAP[ticker.upper()],
            "data_quality": "ok",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        }

    try:
        stock = yf.download(ticker, period=f"{LOOKBACK_YEARS}y", progress=False)
        if stock.empty or len(stock) < 100: 
            return None 
            
        prices = extract_price_series(stock)
        daily_returns = prices.pct_change().dropna()
        if daily_returns.empty: return None

        # 1. MDD (換算成百分比整數)
        rolling_max = prices.cummax()
        drawdowns = (prices - rolling_max) / rolling_max
        mdd_raw = drawdowns.min()
        mdd = round(float(mdd_raw) * 100, 2)

        # 2. EWMA VaR & CVaR
        T = len(daily_returns)
        weights = get_ewma_weights(T)
        df_sim = pd.DataFrame({'Return': daily_returns.values, 'Weight': weights})
        
        df_sorted = df_sim.sort_values(by='Return').reset_index(drop=True)
        df_sorted['CumWeight'] = df_sorted['Weight'].cumsum()
        
        var_idx = df_sorted[df_sorted['CumWeight'] >= VAR_PERCENTILE].index[0]
        var_raw = df_sorted.loc[var_idx, 'Return']
        var_95 = round(float(var_raw) * 100, 2)
        
        tail_events = df_sorted.iloc[:var_idx]
        if len(tail_events) > 0:
            cvar_raw = np.average(tail_events['Return'], weights=tail_events['Weight'])
        else:
            cvar_raw = var_raw
        cvar_95 = round(float(cvar_raw) * 100, 2)
            
        # 3. DownVol
        down_days = df_sim[df_sim['Return'] < 0]
        if len(down_days) > 0:
            down_weights = down_days['Weight'] / down_days['Weight'].sum()
            weighted_var = np.average((down_days['Return'])**2, weights=down_weights)
            down_vol_raw = np.sqrt(weighted_var * 252) 
        else:
            down_vol_raw = 0
        down_vol = round(float(down_vol_raw) * 100, 2)
            
        # 4. Bloomberg Adjusted Beta
        aligned_prices = pd.concat([prices, bench_prices], axis=1, join='inner').dropna()
        aligned_prices.columns = ['Stock', 'Bench']
        aligned_2y = aligned_prices.tail(504) # 取近兩年
        
        if len(aligned_2y) > 50:
            weekly_prices = aligned_2y.resample('W-FRI').last()
            weekly_returns = weekly_prices.pct_change().dropna()
            
            if len(weekly_returns) > 10:
                cov_matrix = np.cov(weekly_returns['Stock'].values, weekly_returns['Bench'].values)
                cov_sb = cov_matrix[0, 1] 
                var_b = cov_matrix[1, 1]  
                raw_beta = cov_sb / var_b if var_b > 0 else 1.0
            else:
                raw_beta = 1.0
        else:
            raw_beta = 1.0
            
        # 🌟 套用 Bloomberg 調整公式
        adj_beta = ADJUST_ALPHA * raw_beta + (1 - ADJUST_ALPHA) * 1.0

        # 5. 評估數據品質
        quality = assess_quality(mdd, down_vol, var_95, cvar_95)

        # 封裝 JSON
        return {
            "mdd": mdd,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "down_vol": down_vol,
            "raw_beta": round(float(raw_beta), 2),
            "beta": round(float(adj_beta), 2), # APP 預設讀取這個 Adjusted Beta
            "data_quality": quality,
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        }

    except Exception as e:
        print(f"⚠️ {ticker} 運算失敗: {e}")
        return None

# ────────────────────────────────────────
# 主程式
# ────────────────────────────────────────

def main():
    print("🚀 啟動 AP 雲端量化引擎 (Bloomberg Beta + 品質過濾版)")
    
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
    
    target_tickers.extend(list(FUTURE_BETA_MAP.keys()))
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    count = 0
    
    for ticker in target_tickers:
        if ticker in risk_db and risk_db[ticker].get("last_updated") == today_str:
            continue
            
        print(f"🔍 正在運算: {ticker:<10} ...", end=" ")
        
        bench_p = bench_tw_prices if ticker.endswith((".TW", ".TWO")) or ticker == "TX" else bench_us_prices
        result = calculate_metrics(ticker, bench_p)
        
        if result:
            risk_db[ticker] = result
            print(f"完成! (Adj Beta: {result['beta']}, 品質: {result.get('data_quality', 'N/A')})")
            count += 1
            
            if count % 10 == 0:
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(risk_db, f, ensure_ascii=False, indent=2)
                    
        time.sleep(0.2)

    # ────────────────────────────────────────
    # 🌟 特殊標的聯動校正 (Post-processing)
    # ────────────────────────────────────────
    if "0050.TW" in risk_db:
        # 🛡️ 防呆機制：相容舊版 JSON，若無 raw_beta 則取 beta，再沒有就預設 1.0
        raw_0050 = risk_db["0050.TW"].get("raw_beta", risk_db["0050.TW"].get("beta", 1.0))
        
        # 1. 校正 00632R (元大台灣50反1)
        if "00632R.TW" in risk_db:
            raw_inv = -raw_0050
            adj_inv = ADJUST_ALPHA * raw_inv + (1 - ADJUST_ALPHA) * 1.0
            risk_db["00632R.TW"]["raw_beta"] = round(float(raw_inv), 2)
            risk_db["00632R.TW"]["beta"] = round(float(adj_inv), 2)
            risk_db["00632R.TW"]["data_quality"] = "ok (derived proxy)"
            print(f"\n🔧 [自動校正] 00632R.TW Beta 已校正為 0050 反向: {round(adj_inv, 2)}")


    # 最終存檔
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(risk_db, f, ensure_ascii=False, indent=2)
        
    print(f"🎉 運算結束！本次新增/更新了 {count} 檔標的。")

if __name__ == "__main__":
    main()
