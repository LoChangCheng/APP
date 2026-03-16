import yfinance as yf
from datetime import datetime, timedelta
import os
import pandas as pd

# 設定時間
end_date = datetime.today()
start_date = end_date - timedelta(days=7)

# 抓取資料並直接處理成 JSON 字串
def get_json_str(symbol):
    df = yf.Ticker(symbol).history(start=start_date, end=end_date).reset_index()
    # 使用 Pandas 內建的 to_json，它能完美處理 Timestamp
    return df.to_json(orient="records", date_format="iso")

# 組合資料
sp500_json = get_json_str("^GSPC")
tw0050_json = get_json_str("0050.TW")

# 存檔
os.makedirs("data", exist_ok=True)
with open("data/finance.json", "w", encoding="utf-8") as f:
    # 這裡用字串拼接，完全避開 json.dump 的型別檢查問題
    f.write(f'{{"SP500": {sp500_json}, "0050.TW": {tw0050_json}}}')

print("✅ 檔案已成功強制寫入 data/finance.json")
