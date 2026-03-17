import yfinance as yf
from datetime import datetime, timedelta
import os
import pandas as pd

# 設定時間
end_date = datetime.today()
start_date = end_date - timedelta(days=7)

def get_json_str(symbol):
    df = yf.Ticker(symbol).history(start=start_date, end=end_date).reset_index()
    # 使用 Pandas 內建轉換，徹底避開 Timestamp 序列化問題
    return df.to_json(orient="records", date_format="iso")

# 抓取資料
sp500_json = get_json_str("^GSPC")
tw0050_json = get_json_str("0050.TW")

# 強制寫入檔案
os.makedirs("data", exist_ok=True)
with open("data/finance.json", "w", encoding="utf-8") as f:
    # 直接用字串組合，不經過 json 套件檢查
    f.write(f'{{"SP500": {sp500_json}, "0050.TW": {tw0050_json}}}')

print("✅ 成功使用強制字串寫入！")
