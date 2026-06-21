import akshare as ak
import yfinance as yf
import json
import datetime
import os
import traceback

def fetch_all_data():
    data = {
        "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pbc": [], "fx": {}, "futures_rank": [], "sentiment": {},
        "commodities": {}, "rates": {}, "macro_cn": {}, "macro_us": {},
        "margin": {}, "money_supply": []
    }
    
    print("开始抓取数据...")
    
    # 1. 央行逆回购 (历史与未来)
    try:
        df = ak.macro_china_pbc_open_market_operation()
        data['pbc'] = df.tail(21).to_dict(orient='records') # 取近21条覆盖7天历史+14天到期
    except Exception as e: print(f"PBC Error: {e}")
        
    # 2. 汇率 (在岸 CNY, 离岸 CNH)
    try:
        cny = yf.Ticker("CNY=X").history(period="5d")['Close'].dropna().iloc[-1]
        cnh = yf.Ticker("CNH=X").history(period="5d")['Close'].dropna().iloc[-1]
        data['fx'] = {"CNY": round(cny, 4), "CNH": round(cnh, 4)}
    except Exception as e: print(f"FX Error: {e}")

    # 3. 机构多单空单 (以中金所沪深300股指期货为例)
    try:
        end_date = datetime.datetime.now().strftime("%Y%m%d")
        df = ak.get_rank_sum_daily(start_day="20230101", end_day=end_date, market="中金所", symbol="沪深300股指期货")
        data['futures_rank'] = df.tail(5).to_dict(orient='records')
    except Exception as e: print(f"Futures Error: {e}")

    # 4. 情绪指标 (北向资金)
    try:
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        data['sentiment'] = {"north_flow": df.tail(10).to_dict(orient='records')}
    except Exception as e: print(f"Sentiment Error: {e}")

    # 5. 大宗商品 (黄金, 原油)
    try:
        gold = yf.Ticker("GC=F").history(period="5d")['Close'].dropna().iloc[-1]
        oil = yf.Ticker("CL=F").history(period="5d")['Close'].dropna().iloc[-1]
        data['commodities'] = {"Gold": round(gold, 2), "Oil": round(oil, 2)}
    except Exception as e: print(f"Commodities Error: {e}")

    # 6. 中美5年期利率
    try:
        cn_bond = ak.bond_china_yield(date=datetime.datetime.now().strftime("%Y%m%d"))
        cn_5y = cn_bond[cn_bond['曲线名称'].str.contains('5年')]['收益率'].iloc[0]
        us_5y = yf.Ticker("^FVX").history(period="5d")['Close'].dropna().iloc[-1] / 10 # 美债单位转换
        data['rates'] = {"CN_5Y": cn_5y, "US_5Y": round(us_5y, 3)}
    except Exception as e: print(f"Rates Error: {e}")

    # 7. 宏观数据 (CPI, PPI, PMI, 就业)
    try:
        cn_cpi = ak.macro_china_cpi_yearly().iloc[-1]['全国-当月-同比']
        cn_ppi = ak.macro_china_ppi_yearly().iloc[-1]['当月-同比']
        cn_pmi = ak.macro_china_pmi_yearly().iloc[-1]['制造业-指数']
        
        us_cpi = ak.macro_usa_cpi().iloc[-1]['当月-同比'] 
        us_pmi = ak.macro_usa_ism_pmi().iloc[-1]['制造业-指数']
        us_nonfarm = ak.macro_usa_non_farm().iloc[-1]['季调后非农就业人口']
        
        data['macro_cn'] = {"CPI": cn_cpi, "PPI": cn_ppi, "PMI": cn_pmi}
        data['macro_us'] = {"CPI": us_cpi, "PMI": us_pmi, "NonFarm": us_nonfarm}
    except Exception as e: print(f"Macro Error: {e}")

    # 8. A股两融余额
    try:
        sse = ak.stock_margin_sse().iloc[-1]['融资融券余额']
        szse = ak.stock_margin_szse().iloc[-1]['融资融券余额']
        data['margin'] = {"Total": sse + szse}
    except Exception as e: print(f"Margin Error: {e}")

    # 9. M1, M2
    try:
        m2_df = ak.macro_china_money_supply()
        data['money_supply'] = m2_df.tail(12).to_dict(orient='records')
    except Exception as e: print(f"Money Supply Error: {e}")

    return data

if __name__ == "__main__":
    data = fetch_all_data()
    os.makedirs("docs", exist_ok=True) # 创建 docs 文件夹用于 GitHub Pages 部署
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print("✅ 数据抓取完成，已保存至 docs/data.json")
