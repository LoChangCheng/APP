import pandas as pd
import requests

def get_taiwan_tickers():
    print("🌐 正在連接台灣證交所獲取最新代號...")
    tickers = []

    # 1. 抓取【上市】股票與 ETF (後綴為 .TW)
    url_twse = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    res_twse = requests.get(url_twse)
    df_twse = pd.read_html(res_twse.text)[0]

    for val in df_twse[0]:
        val = str(val)
        if '　' in val:
            code = val.split('　')[0]
            
            # 💡 修正邏輯：
            # 條件 A: 一般股票 (4碼純數字，如 2330)
            is_normal_stock = (len(code) == 4 and code.isdigit())
            # 條件 B: ETF (以 00 開頭，長度 4~6 碼，包含 L/R/B 等字母，如 0050, 00878, 00632R)
            is_etf = (code.startswith('00') and 4 <= len(code) <= 6)
            
            if is_normal_stock or is_etf:
                tickers.append(f"{code}.TW")

    # 2. 抓取【上櫃】股票與 ETF (後綴為 .TWO)
    url_tpex = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    res_tpex = requests.get(url_tpex)
    df_tpex = pd.read_html(res_tpex.text)[0]

    for val in df_tpex[0]:
        val = str(val)
        if '　' in val:
            code = val.split('　')[0]
            
            is_normal_stock = (len(code) == 4 and code.isdigit())
            is_etf = (code.startswith('00') and 4 <= len(code) <= 6)
            
            if is_normal_stock or is_etf:
                tickers.append(f"{code}.TWO")

    return tickers

if __name__ == "__main__":
    tw_tickers = get_taiwan_tickers()
    print(f"✅ 共找到 {len(tw_tickers)} 檔台股標的 (包含股票與 ETF)。")

    # 存成 my_tickers.txt 給爬蟲讀取
    with open("my_tickers.txt", "w", encoding="utf-8") as f:
        for t in tw_tickers:
            f.write(t + "\n")
            
    print("✅ 已成功更新 my_tickers.txt 清單！")
