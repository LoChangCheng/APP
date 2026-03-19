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
LAMBDA_DECAY = 0.94      # RiskMetrics 指數衰減係數 (用於 VaR/CVaR/DownVol)
VAR_PERCENTILE = 0.05    # 95% 信心水準
LOOKBACK_YEARS = 5       # 總回測歷史長度
OUTPUT_FILE = "risk_lookup.json"

def get_ewma_weights(length):
    """產生 EWMA 指數衰減權重 (用於短期風險預測)"""
    days_ago = np.arange(length - 1, -1, -1)
    weights = np.power(LAMBDA_DECAY, days_ago)
    return weights / np.sum(weights)

def fetch_benchmark_prices(symbol):
    """抓取基準指數的 5 年『每日收盤價』"""
    print(f"📥 正在下載基準指數: {symbol}")
    bench = yf.download(symbol, period=f"{LOOKBACK_YEARS}y", progress=False)
    if bench.empty:
        return pd.Series(dtype=float)
    return bench['Adj Close'].squeeze()

def calculate_metrics(ticker, bench_prices):
    """核心演算法：計算單一標的之量化風險指標"""
    try:
        # 1. 抓取 5 年歷史價格數據
        stock = yf.download(ticker, period=f"{LOOKBACK_YEARS}y", progress=False)
        if stock.empty or len(stock) < 100: 
            return None 
            
        prices = stock['Adj Close'].squeeze()
        
        # 準備日頻率報酬 (給 VaR, CVaR, DownVol 使用)
        daily_returns = prices.pct_change().dropna()
        if daily_returns.empty:
            return None

        # 2. 歷史最大回撤 (MDD) - 看長線 5 年絕對值
        rolling_max = prices.cummax()
        drawdowns = (prices - rolling_max) / rolling_max
        mdd = drawdowns.min()

        # 3. 準備 EWMA 時間加權 (極度重視近期市況)
        T = len(daily_returns)
        weights = get_ewma_weights(T)
        df_sim = pd.DataFrame({'Return': daily_returns.values, 'Weight': weights})
        
        # 4. VaR & CVaR 95% (黑天鵝尾部風險預估)
        df_sorted = df_sim.sort_values(by='Return').reset_index(drop=True)
        df_sorted['CumWeight'] = df_sorted['Weight'].cumsum()
        
        var_idx = df_sorted[df_sorted['CumWeight'] >= VAR_PERCENTILE].index[0]
        var_95 = df_sorted.loc[var_idx, 'Return']
        
        tail_events = df_sorted.iloc[:var_idx]
        if len(tail_events) > 0:
            cvar_95 = np.average(tail_events['Return'], weights=tail_events['Weight'])
        else:
            cvar_95 = var_95
            
        # 5. DownVol (下行波動率)
        down_days = df_sim[df_sim['Return'] < 0]
        if len(down_days) > 0:
            down_weights = down_days['Weight'] / down_days['Weight'].sum()
            weighted_var = np.average((down_days['Return'])**2, weights=down_weights)
            down_vol = np.sqrt(weighted_var * 252) 
        else:
            down_vol = 0
            
        # ==========================================
        # 6. 業界標準 Beta (Bloomberg Methodology)
        # ==========================================
        # 對齊標的與大盤的價格資料
        aligned_prices = pd.concat([prices, bench_prices], axis=1, join='inner').dropna()
        aligned_prices.columns = ['Stock', 'Bench']
        
        # 鐵律一：截取近 2 年資料 (約 504 個交易日)
        aligned_2y = aligned_prices.tail(504)
        
        if len(aligned_2y) > 50:
            # 鐵律二：重採樣為每週末 (W-FRI) 收盤價，並計算週報酬率
            weekly_prices = aligned_2y.resample('W-FRI').last()
            weekly_returns = weekly_prices.pct_change().dropna()
            
            if len(weekly_returns) > 10:
                # 鐵律三：OLS 常態共變異數矩陣
                # 💡 防呆優化：加上 .values 確保傳入純 NumPy 陣列，避免 Pandas 索引報錯
                cov_matrix = np.cov(weekly_returns['Stock'].values, weekly_returns['Bench'].values)
                cov_sb = cov_matrix[0, 1] 
                var_b = cov_matrix[1, 1]  
                beta = cov_sb / var_b if var_b > 0 else 1.0
            else:
                beta = 1.0
        else:
            beta = 1.0

        # 封裝 JSON (加入 DB 所需的 name 欄位)
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

# 🌟 正式上線的寫法：讀取你辛苦抓下來的全市場清單
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
        # 開發測試期間如果需要強制重算，可將下方兩行註解掉
        # if ticker in risk_db and risk_db[ticker].get("last_updated") == today_str:
        #     continue
            
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
