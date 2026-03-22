import yfinance as yf
import pandas as pd
import os
import time
from datetime import datetime

LOOKBACK_PERIOD = "5y"
OUTPUT_DIR = "raw_us_market_data"

def setup_environment():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"📁 建立資料夾: {OUTPUT_DIR}")

def fetch_us_data(tickers):
    today_str = datetime.now().strftime("%Y-%m-%d")
    success_count = 0
    
    print(f"🚀 啟動美股歷史數據爬蟲，預計掃描 {len(tickers)} 檔標的...")
    print("⚠️ 警告：美股數量龐大（約 10,000 檔），因設定 0.5 秒安全間隔，完整執行可能需時 1.5 ~ 2 小時。")
    print("-" * 50)

    for ticker in tickers:
        file_path = os.path.join(OUTPUT_DIR, f"{ticker}.csv")
        
        # 💡 【斷點續傳機制】檢查今日是否已經下載過了
        if os.path.exists(file_path):
            try:
                # 只讀取少量檔案末端資料，加速判定
                existing_data = pd.read_csv(file_path)
                if not existing_data.empty:
                    last_date = str(existing_data.iloc[-1]['Date'])[:10]
                    if last_date == today_str:
                        # 已經是今天抓過的資料，直接略過
                        continue
            except Exception:
                pass # 讀取錯誤視為損毀，重新下載

        print(f"📥 正在下載美股: {ticker:<8} ...", end=" ")
        
        try:
            data = yf.download(ticker, period=LOOKBACK_PERIOD, progress=False)
            
            if data.empty or len(data) < 10:
                print("⚠️ 查無數據或數據過少")
                continue
                
            # 簡化欄位，節省儲存空間與記憶體
            cols_to_keep = [col for col in ['Close', 'Adj Close', 'Volume'] if col in data.columns]
            clean_data = data[cols_to_keep]
            
            clean_data.to_csv(file_path)
            print(f"✅ 成功! 取得 {len(clean_data)} 筆")
            success_count += 1
            
            # 🛡️ 【防封鎖強制延遲】
            # 與台股相比，美股數量巨量，強制間隔 0.5 秒非常重要，避免被 Yahoo 防火牆永久 Ban IP
            time.sleep(0.5)
            
        except Exception as e:
            print(f"❌ 錯誤: {e}")
            # 若遭遇網路或遠端伺服器短暫拒絕連線，休眠長一點時間再繼續
            time.sleep(2)

    print("-" * 50)
    print(f"🎉 美股任務結束！本次成功抓取/更新了 {success_count} 檔標的。")

def load_tickers(filepath):
    if not os.path.exists(filepath):
        print(f"⚠️ 找不到 {filepath}，請先執行 get_us_tickers.py 建立代號清單。")
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines() if line.strip()]

if __name__ == "__main__":
    setup_environment()
    tickers_to_fetch = load_tickers("us_tickers.txt")
    if tickers_to_fetch:
        fetch_us_data(tickers_to_fetch)
