import ftplib
import io
import pandas as pd

def get_us_tickers():
    print("🌐 正在連線至 NASDAQ 官方結算 FTP 伺服器...")
    
    try:
        # 1. 連線至 NASDAQ 公開 FTP (不需要密碼，匿名登入即可)
        ftp = ftplib.FTP('ftp.nasdaqtrader.com')
        ftp.login() 
        
        # 2. 下載全市場清單檔案到記憶體中
        print("📥 正在下載 nasdaqtraded.txt ...")
        bio = io.BytesIO()
        ftp.retrbinary('RETR SymbolDirectory/nasdaqtraded.txt', bio.write)
        bio.seek(0)
        ftp.quit()
        
        # 3. 使用 pandas 解析 (分隔符號為 |)
        df = pd.read_csv(bio, sep='|')
        
        # 排除最後一行的檔案建立時間標記 (File Creation Time)
        df = df[:-1] 
        
        # 🛡️ 核心過濾邏輯：
        # 排除測試用代碼 (Test Issue == 'N')，只保留真實交易的標的
        df = df[df['Test Issue'] == 'N']
        
        # 4. 取得代號並進行 yfinance 格式清理
        raw_tickers = df['Symbol'].dropna().tolist()
        tickers = []
        for t in raw_tickers:
            # NASDAQ FTP 會用 "$" 來標示特別股或 Class A/B (例如 BRK$B)
            # 但 Yahoo Finance 認得的格式是 "-" (例如 BRK-B)
            t = str(t).strip().replace('$', '-').replace('.', '-')
            
            # 過濾掉長度異常的奇怪債券或憑證
            if len(t) <= 5:
                tickers.append(t)
                
        # 去除重複項並按英文字母排序
        tickers = sorted(list(set(tickers)))
        
        print(f"✅ 成功獲取 {len(tickers)} 檔美股全市場代號 (包含所有股票與 ETF)。")
        return tickers

    except Exception as e:
        print(f"❌ 抓取失敗: {e}")
        return []

if __name__ == "__main__":
    us_tickers = get_us_tickers()
    if us_tickers:
        with open("us_tickers.txt", "w", encoding="utf-8") as f:
            for t in us_tickers:
                f.write(t + "\n")
        print("✅ 已成功儲存全市場清單至 us_tickers.txt")
