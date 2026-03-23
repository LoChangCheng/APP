import yfinance as yf
import json
import os
import time

META_FILE = "ticker_meta.json"

def main():
    print("🗂️ 啟動標籤資料庫更新程式 (Metadata Updater)")
    
    # 1. 讀取現有的標籤快取
    meta_db = {}
    if os.path.exists(META_FILE):
        with open(META_FILE, 'r', encoding='utf-8') as f:
            meta_db = json.load(f)
            print(f"✅ 已載入本地標籤庫，現有 {len(meta_db)} 筆資料。")

    # 2. 收集所有需要處理的代號
    target_tickers = set()
    for filename in ["my_tickers.txt", "us_tickers.txt"]:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                tickers = [line.strip() for line in f.readlines() if line.strip()]
                target_tickers.update(tickers)
                
    target_tickers = sorted(list(target_tickers))
    print(f"📋 清單總計 {len(target_tickers)} 檔標的準備檢查。")

    count = 0
    new_added = 0
    
    # 3. 只針對「不在標籤庫」裡的新股票發送 Yahoo API 請求
    for ticker in target_tickers:
        if ticker in meta_db:
            continue  # 💡 已經有標籤了，直接跳過！零 API 請求！
            
        print(f"🔍 正在獲取新標的標籤: {ticker:<12} ...", end=" ")
        
        sector_val = "Unknown"
        industry_val = "Unknown"
        
        try:
            info = yf.Ticker(ticker).info
            if info:
                if info.get("quoteType", "") == "ETF":
                    sector_val = "ETF"
                    industry_val = info.get("category", "Index Fund")
                else:
                    sector_val = info.get("sector", "Unknown")
                    industry_val = info.get("industry", "Unknown")
        except Exception as e:
            print(f"⚠️ 失敗 ({e})", end=" ")
            
        meta_db[ticker] = {
            "sector": sector_val,
            "industry": industry_val
        }
        
        print(f"完成! ({sector_val} / {industry_val})")
        new_added += 1
        count += 1
        
        # 每抓 50 檔新標的就存檔並休息，極度安全
        if count % 50 == 0:
            with open(META_FILE, 'w', encoding='utf-8') as f:
                json.dump(meta_db, f, ensure_ascii=False, indent=2)
            time.sleep(5)
        else:
            time.sleep(0.5)

    # 最終存檔
    if new_added > 0:
        with open(META_FILE, 'w', encoding='utf-8') as f:
            json.dump(meta_db, f, ensure_ascii=False, indent=2)
            
    print(f"🎉 標籤庫更新結束！本次新增了 {new_added} 檔新標籤。")

if __name__ == "__main__":
    main()
