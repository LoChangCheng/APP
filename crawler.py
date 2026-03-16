import yfinance as yf
from datetime import datetime, timedelta
import json
import os
import pandas as pd

# 設定時間範圍
end_date = datetime.today()
start_date = end_date - timedelta(days=7)

def get_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date).reset_index()
        
        if df.empty:
            return []

        # 強制轉換：先將所有資料轉成字串，再轉回字典
        # 這是最保險的做法，能解決所有 Timestamp 或特殊數值問題
        json_data = df.to_json(orient="records", date_format="iso")
        return json.loads(json_data)
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return []

# 彙整資料
output = {
    "SP500": get_data("^GSPC"),
    "0050.TW": get_data("0050.TW")
}

# 確保目錄存在
os.makedirs("data", exist_ok=True)

# 儲存檔案
with open("data/finance.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("✅ 檔案已成功存成 data/finance.json")
