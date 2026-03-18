import pandas as pd
import requests

def is_target_ticker(code):
    """🛡️ 全市場精準過濾器：只抓取有價值的標的，過濾掉幾萬檔權證"""
    if not code: return False
    
    # 1. 普通股、KY股、TDR、創新板 (剛好 4 碼純數字，例如 2330, 2939)
    if len(code) == 4 and code.isdigit():
        return True
        
    # 2. 特別股 (4 碼數字 + 1 碼英文，例如 2881A)
    if len(code) == 5 and code[:4].isdigit() and code[4].isalpha():
        return True
        
    # 3. ETF (00 開頭，4~6 碼，包含 L/R/U/B，例如 0050, 00632R)
    if code.startswith('00') and 4 <= len(code) <= 6:
        return True
        
    # 4. REITs 不動產投資信託 (01 開頭，通常以 T 結尾，例如 01001T)
    if code.startswith('01') and code.endswith('T'):
        return True
        
    # 5. ETN 指數投資證券 (02 開頭，例如 020000)
    if code.startswith('02') and 4 <= len(code) <= 6:
        return True
        
    # 其他諸如 03~08 開頭的權證，或是牛熊證，全部擋掉回傳 False
    return False

def get_taiwan_tickers():
    print("🌐 正在連接台灣證交所獲取最新代號...")
    tickers = []

    # 1. 抓取【上市】 (後綴為 .TW)
    url_twse = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    res_twse = requests.get(url_twse)
    df_twse = pd.read_html(res_twse.text)[0]

    for val in df_twse[0]:
        val = str(val)
        if '　' in val:  # 注意這是全形空白
            code = val.split('　')[0]
            if is_target_ticker(code):
                tickers.append(f"{code}.TW")

    # 2. 抓取【上櫃】 (後綴為 .TWO)
    url_tpex = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    res_tpex = requests.get(url_tpex)
    df_tpex = pd.read_html(res_tpex.text)[0]

    for val in df_tpex[0]:
        val = str(val)
        if '　' in val:
            code = val.split('　')[0]
            if is_target_ticker(code):
                tickers.append(f"{code}.TWO")

    return tickers

if __name__ == "__main__":
    tw_tickers = get_taiwan_tickers()
    print(f"✅ 共找到 {len(tw_tickers)} 檔台股標的 (包含股票、ETF、特別股、REITs、ETN)。")

    # 存成 my_tickers.txt 給爬蟲讀取
    with open("my_tickers.txt", "w", encoding="utf-8") as f:
        for t in tw_tickers:
            f.write(t + "\n")
            
    print("✅ 已成功更新 my_tickers.txt 清單！")
