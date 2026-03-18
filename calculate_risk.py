import pandas as pd
import numpy as np
import json
import os
import glob
from datetime import datetime
import warnings

# 關閉煩人的日期格式警告
warnings.filterwarnings('ignore')

# ==========================================
# ⚙️ 系統參數設定
# ==========================================
LAMBDA_DECAY = 0.94
VAR_PERCENTILE = 0.05
INPUT_DIR = "raw_market_data"
OUTPUT_FILE = "risk_lookup.json"

def get_ewma_weights(length):
    days_ago = np.arange(length - 1, -1, -1)
    weights = np.power(LAMBDA_DECAY, days_ago)
    return weights / np.sum(weights)

def safe_read_csv(file_path):
    """🛡️ 終極防呆機制：自動清除 yfinance 產生的髒資料"""
    try:
        df = pd.read_csv(file_path, low_memory=False)
        if df.empty: return df
        
        date_col = None
        for col in ['Date', 'Datetime', 'date', 'Unnamed: 0', 'Price']:
            if col in df.columns:
                date_col = col
                break
                
        if not date_col:
            date_col = df.columns[0]
            
        # 轉換日期，無法轉換的字串（例如 'Ticker'）會變成 NaT (Not a Time)
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df.set_index(date_col, inplace=True)
        
        # 🌟 核心修正 1：把 index 是 NaT 的髒資料整列砍掉！
        df = df[df.index.notna()]
            
        return df
    except Exception as e:
        print(f"讀取 {file_path} 發生錯誤: {e}")
        return pd.DataFrame()

def load_benchmark(symbol):
    """讀取大盤數據"""
    file_path = os.path.join(INPUT_DIR, f"{symbol}.csv")
    if os.path.exists(file_path):
        bench = safe_read_csv(file_path)
        if bench.empty: return pd.Series(dtype=float)
        
        col = 'Adj Close' if 'Adj Close' in bench.columns else ('Close' if 'Close' in bench.columns else bench.columns[0])
        
        # 🌟 核心修正 2：強制把欄位轉成數值，如果遇到字串就變成 NaN，然後丟棄
        prices = pd.to_numeric(bench[col], errors='coerce').dropna()
        return prices.pct_change().dropna()
    else:
        print(f"⚠️ 找不到基準指數檔案: {symbol}.csv")
        return pd.Series(dtype=float)

def calculate_metrics(ticker, file_path, bench_returns):
    """計算風險指標"""
    try:
        stock = safe_read_csv(file_path)
        if stock.empty or len(stock) < 50: 
            return None
            
        col = 'Adj Close' if 'Adj Close' in stock.columns else ('Close' if 'Close' in stock.columns else stock.columns[0])
        
        # 🌟 核心修正 3：強制數值轉換
        prices = pd.to_numeric(stock[col], errors='coerce').dropna()
        returns = prices.pct_change().dropna()
        
        if returns.empty: return None

        # 1. MDD
        rolling_max = prices.cummax()
        drawdowns = (prices - rolling_max) / rolling_max
        mdd = drawdowns.min()

        # 2. EWMA
        T = len(returns)
        weights = get_ewma_weights(T)
        df_sim = pd.DataFrame({'Return': returns.values, 'Weight': weights})
        
        # 3. VaR & CVaR
        df_sorted = df_sim.sort_values(by='Return').reset_index(drop=True)
        df_sorted['CumWeight'] = df_sorted['Weight'].cumsum()
        var_idx = df_sorted[df_sorted['CumWeight'] >= VAR_PERCENTILE].index[0]
        var_95 = df_sorted.loc[var_idx, 'Return']
        
        tail_events = df_sorted.iloc[:var_idx]
        cvar_95 = np.average(tail_events['Return'], weights=tail_events['Weight']) if len(tail_events) > 0 else var_95
            
        # 4. DownVol
        down_days = df_sim[df_sim['Return'] < 0]
        if len(down_days) > 0:
            down_weights = down_days['Weight'] / down_days['Weight'].sum()
            weighted_var = np.average((down_days['Return'])**2, weights=down_weights)
            down_vol = np.sqrt(weighted_var * 252)
        else:
            down_vol = 0
            
        # 5. Beta
        bench_ret_series = bench_returns.squeeze()
        aligned = pd.concat([returns, bench_ret_series], axis=1, join='inner').dropna()
        aligned.columns = ['Stock', 'Bench']
        T_align = len(aligned)
        
        if T_align > 50:
            w_align = get_ewma_weights(T_align)
            stock_rets = aligned['Stock'].values
            bench_rets = aligned['Bench'].values
            cov = np.sum(w_align * stock_rets * bench_rets)
            var_bench = np.sum(w_align * bench_rets**2)
            beta = cov / var_bench if var_bench > 0 else 1.0
        else:
            beta = 1.0

        return {
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
    print("🚀 啟動 AP 本地端量化引擎 (直接讀取 CSV)")
    
    bench_tw = load_benchmark('^TWII')
    bench_us = load_benchmark('^GSPC')

    risk_db = {}
    csv_files = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    print(f"📂 找到 {len(csv_files)} 個 CSV 檔案，準備運算...")
    
    for file_path in csv_files:
        ticker = os.path.basename(file_path).replace(".csv", "")
        # 如果是大盤本身就不算自己的風險指標
        if ticker in ["^TWII", "^GSPC"]:
            continue
            
        print(f"🔍 正在運算: {ticker:<10} ...", end=" ")
        
        bench_ret = bench_tw if ticker.endswith((".TW", ".TWO")) else bench_us
        result = calculate_metrics(ticker, file_path, bench_ret)
        
        if result:
            risk_db[ticker] = result
            print("✅ 完成!")
        else:
            print("⏭️ 略過 (資料不足或錯誤)")

    # 一次性存檔
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(risk_db, f, ensure_ascii=False, indent=2)
        
    print(f"🎉 運算結束！已將 {len(risk_db)} 檔標的風險數據存入 {OUTPUT_FILE}。")

if __name__ == "__main__":
    main()
