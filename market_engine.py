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
LOOKBACK_PERIOD = "5y"
OUTPUT_JSON = "risk_lookup.json"
TICKER_LIST = "my_tickers.txt"
CSV_BACKUP_DIR = "raw_market_data" # 可選：保留 CSV 備份以供其他用途

def get_ewma_weights(length):
    days_ago = np.arange(length - 1, -1, -1)
    weights = np.power(LAMBDA_DECAY, days_ago)
    return weights / np.sum(weights)

def fetch_benchmark(symbol):
    print(f"📥 正在下載基準指數: {symbol}")
    try:
        bench = yf.download(symbol, period=LOOKBACK_PERIOD, progress=False)
        if bench.empty: return pd.Series(dtype=float)
        
        col = 'Adj Close' if 'Adj Close' in bench.columns else 'Close'
        prices = pd.to_numeric(bench[col].squeeze(), errors='coerce').dropna()
        return prices.pct_change().dropna()
    except Exception as e:
        print(f"基準指數 {symbol} 下載失敗: {e}")
        return pd.Series(dtype=float)

def process_ticker(ticker, bench_returns):
    """抓取資料並立即計算風險指標"""
    try:
        # 1. 抓取資料 (直接在記憶體處理，避開 CSV 髒資料問題)
        stock = yf.download(ticker, period=LOOKBACK_PERIOD, progress=False)
        if stock.empty or len(stock) < 100:
            return None
            
        # 備份為 CSV (讓你有歷史資料可以查)
        os.makedirs(CSV_BACKUP_DIR, exist_ok=True)
        stock.to_csv(os.path.join(CSV_BACKUP_DIR, f"{ticker}.csv"))

        # 2. 取出收盤價計算報酬率
        col = 'Adj Close' if 'Adj Close' in stock.columns else 'Close'
        prices = pd.to_numeric(stock[col].squeeze(), errors='coerce').dropna()
        returns = prices.pct_change().dropna()
        
        if returns.empty: return None

        # --- 開始計算風險指標 ---
        # MDD
        rolling_max = prices.cummax()
        drawdowns = (prices - rolling_max) / rolling_max
        mdd = drawdowns.min()

        # EWMA VaR & CVaR
        T = len(returns)
        weights = get_ewma_weights(T)
        df_sim = pd.DataFrame({'Return': returns.values, 'Weight': weights})
        
        df_sorted = df_sim.sort_values(by='Return').reset_index(drop=True)
        df_sorted['CumWeight'] = df_sorted['Weight'].cumsum()
        var_idx = df_sorted[df_sorted['CumWeight'] >= VAR_PERCENTILE].index[0]
        var_95 = df_sorted.loc[var_idx, 'Return']
        
        tail_events = df_sorted.iloc[:var_idx]
        cvar_95 = np.average(tail_events['Return'], weights=tail_events['Weight']) if len(tail_events) > 0 else var_95
            
        # DownVol
        down_days = df_sim[df_sim['Return'] < 0]
        if len(down_days) > 0:
            down_weights = down_days['Weight'] / down_days['Weight'].sum()
            weighted_var = np.average((down_days['Return'])**2, weights=down_weights)
            down_vol = np.sqrt(weighted_var * 252)
        else:
            down_vol = 0
            
        # Beta
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
        print(f"⚠️ {ticker} 處理失敗: {e}")
        return None

def main():
    print("🚀 啟動 AP 雲端量化引擎 (抓取 + 計算 + 產 JSON)")
    
    # 1. 讀取清單
    if not os.path.exists(TICKER_LIST):
        print(f"❌ 找不到 {TICKER_LIST}，請先執行台股清單爬蟲！")
        return
        
    with open(TICKER_LIST, "r", encoding="utf-8") as f:
        target_tickers = [line.strip() for line in f.readlines() if line.strip()]
    print(f"📋 共讀取到 {len(target_tickers)} 檔標的準備處理。")

    # 2. 載入斷點續傳紀錄
    risk_db = {}
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
                risk_db = json.load(f)
            print(f"✅ 成功載入歷史紀錄，已有 {len(risk_db)} 檔資料。")
        except:
            print("⚠️ JSON 格式損毀，將重新建立。")

    # 3. 下載大盤基準
    bench_tw = fetch_benchmark('^TWII')
    bench_us = fetch_benchmark('^GSPC')

    today_str = datetime.now().strftime("%Y-%m-%d")
    count = 0

    # 4. 開始迴圈處理
    for ticker in target_tickers:
        # 🛡️ 斷點續傳：今天已經成功算過的，直接跳過！
        if ticker in risk_db and risk_db[ticker].get("last_updated") == today_str:
            continue
            
        print(f"🔍 處理中: {ticker:<10} ...", end=" ")
        
        bench_ret = bench_tw if ticker.endswith((".TW", ".TWO")) else bench_us
        result = process_ticker(ticker, bench_ret)
        
        if result:
            risk_db[ticker] = result
            print(f"✅ 完成 (Beta: {result['beta']})")
            count += 1
            
            # 🛡️ 每成功 10 檔就強制存檔一次 JSON，避免 GitHub Action 逾時導致心血白費
            if count % 10 == 0:
                with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
                    json.dump(risk_db, f, ensure_ascii=False, indent=2)
                    
        else:
            print("⏭️ 略過 (資料不足或錯誤)")
            
        time.sleep(0.3) # 禮貌延遲，防 Yahoo 封鎖

    # 5. 最終存檔
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(risk_db, f, ensure_ascii=False, indent=2)
        
    print(f"🎉 引擎運作結束！本次共更新了 {count} 檔標的風險數據。")

if __name__ == "__main__":
    main()
