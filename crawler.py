import yfinance as yf
import pandas as pd
import os
import time
from datetime import datetime

# 💡 爬蟲參數設定
LOOKBACK_PERIOD = "5y"  # 抓取過去 5 年的日 K 線
OUTPUT_DIR = "raw_market_data"  # 存放原始數據的資料夾

def setup_environment():
    """建立存放歷史數據的資料夾"""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"📁 建立資料夾: {OUTPUT_DIR}")

def fetch_historical_data(tickers):
    """
    強健型 Yahoo Finance 爬蟲：
    1. 抓取量化必備的 5 年數據
    2. 內建實體檔案斷點續傳 (今天載過的直接跳過)
    3. 禮貌性延遲 (防封鎖)
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    success_count = 0
    
    print(f"🚀 啟動雅虎財經爬蟲，預計掃描 {len(tickers)} 檔標的...")
    print("-" * 50)

    for ticker in tickers:
        file_path = os.path.join(OUTPUT_DIR, f"{ticker}.csv")
        
# 💡 【改進版：斷點續傳機制】
        # 讀取 CSV 確認最後一筆資料的日期，這在 GitHub Actions 環境才有效
        if os.path.exists(file_path):
            try:
                # 讀取現有檔案的最後幾行來檢查日期 (節省記憶體)
                existing_data = pd.read_csv(file_path)
                if not existing_data.empty:
                    last_date = str(existing_data.iloc[-1]['Date'])[:10] # 取 YYYY-MM-DD
                    if last_date == today_str:
                        # print(f"⏭️ {ticker} 今日已有最新數據，跳過。") 
                        continue
            except Exception as e:
                pass # 如果檔案損毀或讀取失敗，就忽視並重新下載

        print(f"📥 正在下載: {ticker:<10} ...", end=" ")
        
        try:
            # 呼叫 yfinance 抓取 5 年數據 (progress=False 關閉擾人的進度條)
            data = yf.download(ticker, period=LOOKBACK_PERIOD, progress=False)
            
            # 檢查是否抓到空包彈 (下市股票或代號打錯)
            if data.empty or len(data) < 10:
                print("⚠️ 查無數據或數據過少 (可能已下市)")
                continue
                
            # 💡 量化資料清洗：我們只需要 Date(Index), Close, Adj Close, Volume
            # 確保欄位存在，避免有些冷門股缺少某些數據
            cols_to_keep = [col for col in ['Close', 'Adj Close', 'Volume'] if col in data.columns]
            clean_data = data[cols_to_keep]
            
            # 將數據存成 CSV 檔，方便後續量化引擎隨時讀取
            clean_data.to_csv(file_path)
            
            print(f"✅ 成功! 取得 {len(clean_data)} 個交易日")
            success_count += 1
            
            # 🛡️ 【防封鎖機制】
            # 每抓一檔停頓 0.3 秒，避免被 Yahoo 視為惡意攻擊直接 Ban IP
            time.sleep(0.3)
            
        except Exception as e:
            print(f"❌ 錯誤: {e}")
            time.sleep(1) # 遇到錯誤稍微停久一點再繼續

    print("-" * 50)
    print(f"🎉 爬蟲任務結束！本次成功抓取/更新了 {success_count} 檔標的。")

if __name__ == "__main__":
    setup_environment()
    
    # 📝 測試用清單：台股大盤、美股大盤、幾檔權值股與高波動股
    # 實務上，您可以讓程式去讀取一個包含 6000 檔代號的 txt 或 csv 檔
    sample_tickers = [
        "^TWII", "^GSPC",   # 大盤基準指數 (必備)
        "2330.TW", "2317.TW", "2603.TW", # 台股 (後綴 .TW)
        "AAPL", "TSLA", "NVDA", "MSTR"   # 美股
    ]
    
    fetch_historical_data(sample_tickers)
