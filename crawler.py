import yfinance as yf
from datetime import datetime, timedelta
import json
import os

# 設定時間範圍
end_date = datetime.today()
start_date = end_date - timedelta(days=7)

# 抓取資料
def get_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    df = ticker.history(start=start_date, end=end_date).reset_index()
    # 關鍵修正：將日期轉為字串格式，否則 JSON 會報錯
    df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
    return df.to_dict(orient="records")

output = {
    "SP500": get_data("^GSPC"),
    "0050.TW": get_data("0050.TW")
}

# 存成 JSON
os.makedirs("data", exist_ok=True)
with open("data/finance.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("已成功存成 data/finance.json")
