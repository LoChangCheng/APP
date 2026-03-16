import yfinance as yf
from datetime import datetime, timedelta
import json
import os

# 設定時間範圍：過去一週
end_date = datetime.today()
start_date = end_date - timedelta(days=7)

# 抓 S&P 500 (^GSPC)
sp500 = yf.Ticker("^GSPC")
sp500_data = sp500.history(start=start_date, end=end_date)

# 抓台灣 0050 ETF (0050.TW)
tw0050 = yf.Ticker("0050.TW")
tw0050_data = tw0050.history(start=start_date, end=end_date)

# 整理成字典
output = {
    "SP500": sp500_data.reset_index().to_dict(orient="records"),
    "0050.TW": tw0050_data.reset_index().to_dict(orient="records")
}

# 存成 JSON 檔
os.makedirs("data", exist_ok=True)
with open("data/finance.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("已存成 data/finance.json")
