import akshare as ak
import pandas as pd
import json
import traceback
from datetime import datetime, timedelta

# 配置Pandas防警告
pd.options.mode.chained_assignment = None

def get_pboc_omo():
    """1. 央行逆回购操作量与到期推算 (历史7天，未来14天到期)"""
    try:
        df = ak.macro_china_pebc_omo()
        df['日期'] = pd.to_datetime(df['日期'])
        today = pd.to_datetime(datetime.today().date())
        
        # 提取历史7天操作
        hist_7d = df[(df['日期'] <= today) & (df['日期'] >= today - timedelta(days=7))]
        
        # 推算到期量：将历史操作的 日期 + 期限 = 到期日
        df['期限天数'] = df['期限'].str.extract('(\d+)').astype(float)
        df['到期日'] = df['日期'] + pd.to_timedelta(df['期限天数'], unit='d')
        
        # 获取未来14天到期量
        future_14d = df[(df['到期日'] > today) & (df['到期日'] <= today + timedelta(days=14))]
        
        # 数据清洗
        hist_7d_clean = hist_7d[['日期', '交易方向', '交易量(亿)', '期限', '利率(%)']].fillna("").to_dict(orient='records')
        future_14d_clean = future_14d[['到期日', '交易量(亿)', '期限']].rename(columns={'交易量(亿)': '到期量(亿)'}).fillna("").to_dict(orient='records')
        
        # 转换 datetime 为字符串
        for item in hist_7d_clean: item['日期'] = item['日期'].strftime('%Y-%m-%d')
        for item in future_14d_clean: item['到期日'] = item['到期日'].strftime('%Y-%m-%d')
            
        return {"history_7d": hist_7d_clean, "future_14d_maturity": future_14d_clean}
    except Exception:
        print(f"央行OMO抓取失败: {traceback.format_exc()}")
        return None

def get_unlock_calendar():
    """2. A股非ST主板解禁日历"""
    try:
        df = ak.stock_restricted_release_queue_em()
        # 过滤ST和退市股
        df = df[~df['股票简称'].str.contains('ST|退')]
        df['解禁时间'] = pd.to_datetime(df['解禁时间'])
        today = pd.to_datetime(datetime.today().date())
        # 取未来7天解禁
        df_future = df[(df['解禁时间'] >= today) & (df['解禁时间'] <= today + timedelta(days=7))]
        df_future['解禁时间'] = df_future['解禁时间'].dt.strftime('%Y-%m-%d')
        return df_future[['解禁时间', '股票代码', '股票简称', '解禁数量(股)']].head(20).to_dict(orient='records')
    except Exception:
        return None

def get_exchange_rate():
    """3. 离岸/在岸汇率"""
    try:
        df = ak.fx_spot_quote()
        usd_cny = df[df['货币对'] == 'USDCNY']['最新价'].values[0] # 在岸
        usd_cnh = df[df['货币对'] == 'USDCNH']['最新价'].values[0] # 离岸
        return {"USDCNY_Onshore": float(usd_cny), "USDCNH_Offshore": float(usd_cnh)}
    except Exception:
        return None

def get_citic_futures():
    """4. 中信期货多空单 (以沪深300 IF合约为例)"""
    try:
        # 获取沪深300最新主力合约的机构持仓
        df = ak.futures_holding_manager(symbol="IF", date=datetime.today().strftime('%Y%m%d'))
        if df is empty:
            # 如果今天周末或没更新，取前一天
            last_workday = (datetime.today() - timedelta(days=1)).strftime('%Y%m%d')
            df = ak.futures_holding_manager(symbol="IF", date=last_workday)
            
        citic = df[df['机构名称'] == '中信期货']
        return citic.fillna("").to_dict(orient='records')
    except Exception:
        return None

def get_macro_data():
    """整合获取 5-14项 所有宏观与情绪数据"""
    macro_hub = {}
    
    # 5. 情绪指标
    try:
        df_greed = ak.index_fear_greed_funddb()
        macro_hub['fear_greed'] = df_greed.iloc[-1].to_dict()
    except: macro_hub['fear_greed'] = None

    # 6. 大宗商品 (最新价)
    try:
        gold = ak.futures_global_commodity_hist(sector="外盘贵金属", symbol="伦敦金")
        oil = ak.futures_global_commodity_hist(sector="外盘能源", symbol="WTI原油")
        macro_hub['gold'] = gold.iloc[-1]['收盘']
        macro_hub['oil'] = oil.iloc[-1]['收盘']
    except: macro_hub['gold'], macro_hub['oil'] = None, None

    # 7. 利率 (中 LPR 5Y, 美 10Y)
    try:
        lpr = ak.macro_china_lpr()
        us_bond = ak.bond_zh_us_rate()
        macro_hub['china_lpr_5y'] = lpr.iloc[0]['5年期LPR']
        macro_hub['us_bond_10y'] = us_bond.iloc[-1]['美国国债收益率10年']
    except: macro_hub['china_lpr_5y'], macro_hub['us_bond_10y'] = None, None

    # 8-12, 14. 宏观经济指标
    funcs = {
        "china_cpi": ak.macro_china_cpi,
        "china_ppi": ak.macro_china_ppi,
        "china_pmi": ak.macro_china_pmi,
        "china_unemployment": ak.macro_china_urban_unemployment,
        "china_m1_m2": ak.macro_china_money_supply,
        "usa_cpi": ak.macro_usa_cpi,
        "usa_non_farm": ak.macro_usa_non_farm
    }
    
    for key, func in funcs.items():
        try:
            df = func()
            # 取最新一期数据
            latest = df.iloc[0].to_dict() if len(df) > 0 else None
            # 处理所有值类型，转为 string 或 float 防止 JSON 报错
            if latest:
                macro_hub[key] = {str(k): str(v) for k, v in latest.items()}
        except Exception as e:
            macro_hub[key] = None

    # 13. 两融余额
    try:
        margin = ak.stock_margin_detail()
        latest_margin = margin.iloc[0]
        macro_hub['margin_balance'] = {
            "日期": str(latest_margin['日期']),
            "融资融券余额": float(latest_margin['融资融券余额'])
        }
    except: macro_hub['margin_balance'] = None

    return macro_hub


def build_dashboard():
    """主控函数：组装数据并保存"""
    print(f"[{datetime.now()}] 开始抓取全景宏观数据...")
    
    final_data = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "1_pboc_omo": get_pboc_omo(),
        "2_unlock_queue": get_unlock_calendar(),
        "3_exchange_rate": get_exchange_rate(),
        "4_citic_futures": get_citic_futures(),
        "macro_metrics": get_macro_data()
    }

    # 存入 JSON
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=4)
    print(f"[{datetime.now()}] 数据抓取完成，已保存至 data.json")

if __name__ == "__main__":
    build_dashboard()
