import yfinance as yf
from datetime import datetime, timedelta
import json
import os

# 設定時間範圍
end_date = datetime.today()
start_date = end_date - timedelta(days=7)

def get_data(symbol):
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date, end=end_date).reset_index()
    # 關鍵修正：將日期欄位轉為字串格式 (YYYY-MM-DD)
    if not df.empty:
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
    return df.to_dict(orient="records")

# 抓取資料
output = {
    "SP500": get_data("^GSPC"),
    "0050.TW": get_data("0050.TW")
}

# 存成 JSON 檔
os.makedirs("data", exist_ok=True)
with open("data/finance.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("已存成 data/finance.json")
