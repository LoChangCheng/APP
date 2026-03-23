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
    "mdd_delisted":      -99.0,
    "down_vol_max":       100.0,
    "cvar_var_ratio_max":   3.0,
}

# 靜態期貨 Beta
FUTURE_BETA_MAP = {
    "NQ":  1.3, "ES":  1.0, "RTY": 1.4, "YM":  1.0,
    "GC": -0.1, "CL":  0.3, "TX":  1.1,
}

# 💡 反向 ETF：(對應標的, 倍數)
INVERSE_ETF_MAP = {
    # 台股
    "00632R.TW": ("0050.TW", -1.0),
    # 美股
    "PSQ":       ("QQQ",     -1.0),
    "SH":        ("SPY",     -1.0),
    "DOG":       ("DIA",     -1.0),
    "RWM":       ("IWM",     -1.0),
}

# 💡 槓桿 ETF：(對應標的, 倍數)
LEVERAGED_ETF_MAP = {
    # 台股
    "00631L.TW": ("0050.TW",  2.0),
    # 美股 2x
    "QLD":       ("QQQ",      2.0),
    "SSO":       ("SPY",      2.0),
    "DDM":       ("DIA",      2.0),
    "UWM":       ("IWM",      2.0),
    # 美股 3x
    "TQQQ":      ("QQQ",      3.0),
    "SQQQ":      ("QQQ",     -3.0),
    "SPXL":      ("SPY",      3.0),
    "SPXS":      ("SPY",     -3.0),
    "UPRO":      ("SPY",      3.0),
    "SOXL":      ("SOXX",     3.0),
    "SOXS":      ("SOXX",    -3.0),
    "TNA":       ("IWM",      3.0),
    "TZA":       ("IWM",     -3.0),
    "LABU":      ("XBI",      3.0),
    "LABD":      ("XBI",     -3.0),
    "NUGT":      ("GDX",      2.0),
    "DUST":      ("GDX",     -2.0),
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
        
    prices = pd.to_numeric(prices, errors='coerce').dropna()
    
    # 🚀【核心修復】：無論從 CSV 還是 API 來，無腦強制轉為時間格式！
    prices.index = pd.to_datetime(prices.index, errors='coerce')
    
    # 剃除轉換失敗的爛行 (例如 CSV 的字串表頭)
    prices = prices[prices.index.notna()]
    
    # 強制移除時區並標準化時間
    if getattr(prices.index, 'tz', None) is not None:
        prices.index = prices.index.tz_localize(None)
    prices.index = prices.index.normalize()
        
    return prices

def fetch_benchmark_prices(symbol):
    print(f"📥 正在下載基準指數: {symbol}")
    bench = yf.download(symbol, period=f"{LOOKBACK_YEARS}y", progress=False)
    return extract_price_series(bench)

def assess_quality(mdd, down_vol, var_95, cvar_95):
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

def calculate_metrics(ticker, bench_prices, ticker_meta):
    # 處理靜態期貨
    if ticker.upper() in FUTURE_BETA_MAP:
        return {
            "beta": FUTURE_BETA_MAP[ticker.upper()],
            "data_quality": "ok",
            "sector": "Futures",
            "industry": "Commodities/Indices",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        }, True

    try:
        is_cached = False
        stock = pd.DataFrame()
        us_path = os.path.join("raw_us_market_data", f"{ticker}.csv")
        tw_path = os.path.join("raw_market_data", f"{ticker}.csv")
        
        if os.path.exists(us_path):
            stock = pd.read_csv(us_path, index_col=0, parse_dates=True)
            is_cached = True
            print("📁 [US快取]", end=" ")
        elif os.path.exists(tw_path):
            stock = pd.read_csv(tw_path, index_col=0, parse_dates=True)
            is_cached = True
            print("📁 [TW快取]", end=" ")

        # 🕵️ 防禦機制 1：檢查快取是否過期 (以 7 天為安全閥值)
        if is_cached and not stock.empty:
            last_date = pd.to_datetime(stock.index[-1])
            if (datetime.now() - last_date).days > 7:
                print("⚠️ [快取過期，轉為連線]", end=" ")
                is_cached = False
                stock = pd.DataFrame()
        
        # 🕵️ 防禦機制 2：若無快取或快取被認定無效/殘缺，強制觸發 Yahoo 連線
        if stock.empty or len(stock) < 100:
            if is_cached:
                print("⚠️ [資料殘缺，轉為連線]", end=" ")
                is_cached = False
            else:
                print("🌐 [線上抓取]", end=" ")
            
            stock = yf.download(ticker, period=f"{LOOKBACK_YEARS}y", progress=False)

        # 最終若還是抓不到或資料依然不夠，才會真的放棄此檔
        if stock.empty or len(stock) < 100: 
            return None, is_cached 
            
        prices = extract_price_series(stock)
        daily_returns = prices.pct_change().dropna()
        if daily_returns.empty: return None

        # 1. MDD
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
            
        # 4. Bloomberg Adjusted Beta：近 3 年週報酬
        aligned_prices = pd.concat([prices, bench_prices], axis=1, join='inner').dropna()

        if aligned_prices.empty:
            raw_beta = 1.0
        else:
            aligned_prices.columns = ['Stock', 'Bench']
            three_years_ago = aligned_prices.index[-1] - pd.DateOffset(years=3)
            aligned_3y = aligned_prices[aligned_prices.index >= three_years_ago]
            
            if len(aligned_3y) > 50:
                weekly_prices = aligned_3y.resample('W-FRI').last()
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
            
        adj_beta = ADJUST_ALPHA * raw_beta + (1 - ADJUST_ALPHA) * 1.0
        quality = assess_quality(mdd, down_vol, var_95, cvar_95)

        return {
            "mdd": mdd,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "down_vol": down_vol,
            "raw_beta": round(float(raw_beta), 2),
            "beta": round(float(adj_beta), 2),
            "sector": ticker_meta.get("sector", "Unknown"),
            "industry": ticker_meta.get("industry", "Unknown"),
            "data_quality": quality,
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        }, is_cached

    except Exception as e:
        print(f"⚠️ {ticker} 運算失敗: {e}")
        return None, False

# ────────────────────────────────────────
# 主程式
# ────────────────────────────────────────

def main():
    print("🚀 啟動 AP 雲端量化引擎 (Bloomberg Beta 3Y週報酬版 + 標籤整合)")
    
    # 讀取標籤快取
    meta_db = {}
    if os.path.exists("ticker_meta.json"):
        with open("ticker_meta.json", "r", encoding="utf-8") as f:
            try:
                meta_db = json.load(f)
                print(f"🏷️ 成功載入標籤資料庫，共 {len(meta_db)} 筆。")
            except:
                print("⚠️ ticker_meta.json 格式錯誤。")

    # 讀取風險快取
    risk_db = {}
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            try:
                risk_db = json.load(f)
                print(f"✅ 成功載入風險歷史斷點，已完成 {len(risk_db)} 檔標的。")
            except:
                print("⚠️ json 格式錯誤，重新建立。")

    bench_tw_prices = fetch_benchmark_prices('^TWII')
    bench_us_prices = fetch_benchmark_prices('^GSPC')

    target_tickers = []
    
    # 讀取台股清單
    if os.path.exists("my_tickers.txt"):
        with open("my_tickers.txt", "r", encoding="utf-8") as f:
            tw_tickers = [line.strip() for line in f.readlines() if line.strip()]
            target_tickers.extend(tw_tickers)
        print(f"📋 共讀取到 {len(tw_tickers)} 檔台股標的。")
    else:
        print("⚠️ 找不到 my_tickers.txt！")

    # 讀取美股清單
    if os.path.exists("us_tickers.txt"):
        with open("us_tickers.txt", "r", encoding="utf-8") as f:
            us_tickers = [line.strip() for line in f.readlines() if line.strip()]
            target_tickers.extend(us_tickers)
        print(f"📋 共讀取到 {len(us_tickers)} 檔美股標的。")
    else:
        print("⚠️ 找不到 us_tickers.txt，目前僅運算台股。")

    if not target_tickers:
        print("❌ 沒有讀取到任何標的，程式結束。")
        return

    print(f"✅ 總計準備處理 {len(target_tickers)} 檔標的。")

    target_tickers.extend(list(FUTURE_BETA_MAP.keys()))

    # 確保反向/槓桿 ETF 的對應標的一定在清單裡
    all_underlyings = set()
    for _, (underlying, _) in INVERSE_ETF_MAP.items():
        all_underlyings.add(underlying)
    for _, (underlying, _) in LEVERAGED_ETF_MAP.items():
        all_underlyings.add(underlying)
    for u in all_underlyings:
        if u not in target_tickers:
            target_tickers.append(u)
            print(f"📌 自動補入對應標的: {u}")

    today_str = datetime.now().strftime("%Y-%m-%d")
    count = 0

    for ticker in target_tickers:
        if ticker in risk_db and risk_db[ticker].get("last_updated") == today_str:
            continue
            
        print(f"🔍 正在運算: {ticker:<12} ...", end=" ")
        
        bench_p = bench_tw_prices if ticker.endswith((".TW", ".TWO")) or ticker == "TX" else bench_us_prices
        
        # 從標籤庫提取該檔股票的 meta (若無則預設 Unknown)
        ticker_meta = meta_db.get(ticker, {"sector": "Unknown", "industry": "Unknown"})
        
        # 解構出運算結果與是否命中快取的標示，並傳入 ticker_meta
        out = calculate_metrics(ticker, bench_p, ticker_meta)
        result, is_cached = out if out else (None, False)
        
        if result:
            risk_db[ticker] = result
            print(f"完成! (Adj Beta: {result['beta']}, 品質: {result.get('data_quality', 'N/A')})")
            count += 1
            
            # 🕵️ 防禦機制 3：降低 I/O 寫入頻率，從 10 改為 500，保護 SSD 與加快極速運算
            if count % 500 == 0:
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(risk_db, f, ensure_ascii=False, indent=2)

        # 🚀【極速運算關鍵】防 rate limit 僅限真實連線 (Yahoo)，讀取本地 CSV 時直接跳過休眠全速衝刺！
        if not is_cached:
            if count % 100 == 0 and count > 0:
                print("⏸️ 防 rate limit 休息 30 秒...")
                time.sleep(30)
            elif count % 10 == 0 and count > 0:
                time.sleep(2)
            else:
                time.sleep(0.5)

    # ────────────────────────────────────────
    # 💡 特殊標的聯動校正 (Post-processing)
    # ────────────────────────────────────────
    print("\n🔧 開始 Beta 聯動校正...")

    # 🌟 數學修正：必須先對「Raw Beta」乘上倍數，再套用 Bloomberg 平滑公式，這樣算出來的 Adjusted Beta 才會正確！
    def apply_proxy_logic(etf_map, label):
        for etf, (underlying, multiplier) in etf_map.items():
            if etf in risk_db and underlying in risk_db:
                # 取得母體的 Raw Beta (預設為 1.0 防呆)
                base_raw_beta = risk_db[underlying].get("raw_beta", 1.0)
                
                # 計算 ETF 的理論 Raw Beta
                derived_raw_beta = base_raw_beta * multiplier
                
                # 套用 Bloomberg 公式計算最終的 Adj Beta
                derived_adj_beta = ADJUST_ALPHA * derived_raw_beta + (1 - ADJUST_ALPHA) * 1.0
                
                # 寫回 JSON (保留它原本在上方迴圈被賦予的 sector 與 industry)
                risk_db[etf]["raw_beta"] = round(float(derived_raw_beta), 2)
                risk_db[etf]["beta"] = round(float(derived_adj_beta), 2)
                risk_db[etf]["data_quality"] = "ok (derived proxy)"
                
                print(f"🔧 [{label}] {etf} 校正完成 👉 Raw: {round(derived_raw_beta, 2)} | Adj Beta: {round(derived_adj_beta, 2)}")

    apply_proxy_logic(INVERSE_ETF_MAP, "反向校正")
    apply_proxy_logic(LEVERAGED_ETF_MAP, "槓桿校正")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(risk_db, f, ensure_ascii=False, indent=2)
        
    print(f"\n🎉 運算結束！本次新增/更新了 {count} 檔標的。")

if __name__ == "__main__":
    main()
