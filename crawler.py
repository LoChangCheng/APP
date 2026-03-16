import yfinance as yf
from datetime import datetime, timedelta
import json
import os
import pandas as pd

# 設定時間範圍：過去一週
end_date = datetime.today()
start_date = end_date - timedelta(days=7)

def get_clean_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(start=start_date, end=end_date).reset_index()
        
        if df.empty:
            print(f"警告: {ticker_symbol} 沒有抓到資料")
            return []

        # 【核心修正】將 Date 欄位轉換為 ISO 格式字串 (例如 "2024-05-20")
        # 這樣 json.dump 才能處理它
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        
        # 轉成字典列表
        return df.to_dict(orient="records")
    except Exception as e:
        print(f"抓取 {ticker_symbol} 時發生錯誤: {e}")
        return []

# 整理成字典
output = {
    "SP500": get_clean_data("^GSPC"),
    "0050.TW": get_clean_data("0050.TW")
}

# 存成 JSON 檔
os.makedirs("data", exist_ok=True)
with open("data/finance.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("已成功修正日期格式並存成 data/finance.json")
