import requests
import json

def get_us_tickers():
    print("🌐 正在從美國 SEC (美國證券交易委員會) 抓取官方公司標的清單...")
    
    # 💡 SEC API 強制要求 User-Agent 必須帶有識別資訊 (如信箱)，否則會阻擋並回傳 403 Forbidden
    headers = {
        "User-Agent": "QuantResearchBot/1.0 (quant@example.com)"
    }
    
    # SEC 官方 JSON 檔案，包含所有向 SEC 註冊的公司與對應股票代號
    url = "https://www.sec.gov/files/company_tickers.json"
    
    try:
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        data = res.json()
        
        # 解析 JSON，格式如: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        # ⚠️ 注意：有些美股代號在 SEC 用 "." 分隔 (如 BRK.B)，但 yfinance 偏好使用 "-" (如 BRK-B)
        dirty_tickers = [info["ticker"] for info in data.values()]
        tickers = [t.replace(".", "-") for t in dirty_tickers]
        
        # 去除重複項並按英文字母排序
        tickers = sorted(list(set(tickers)))
        
        print(f"✅ 成功獲取 {len(tickers)} 檔美股代號。")
        return tickers

    except Exception as e:
        print(f"❌ 抓取美股清單失敗: {e}")
        return []

if __name__ == "__main__":
    us_tickers = get_us_tickers()
    if us_tickers:
        with open("us_tickers.txt", "w", encoding="utf-8") as f:
            for t in us_tickers:
                f.write(t + "\n")
        print("✅ 已成功儲存清單至 us_tickers.txt")
