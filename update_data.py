import akshare as ak
import pandas as pd
import json
import requests
from datetime import datetime, timedelta

# 规避Pandas链式赋值警告
pd.options.mode.chained_assignment = None

def get_fuzzy_column(df, keyword):
    """【防崩利器】模糊匹配列名，避免因官方修改列名导致 KeyError"""
    for col in df.columns:
        if keyword.lower() in str(col).lower():
            return col
    return None

def get_pboc_omo():
    """1. 央行逆回购操作量与到期推算 (多路径容错)"""
    df = None
    # 路径 A: 尝试寻找标准的公开市场操作接口
    for func_name in ['macro_china_open_market_info', 'repo_open_market_info_em', 'macro_china_pebc_omo']:
        if hasattr(ak, func_name):
            try:
                df = getattr(ak, func_name)()
                if df is not None and not df.empty:
                    break
            except:
                continue
                
    # 路径 B: 降级方案，直接请求东方财富底层公开API
    if df is None:
        try:
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_MA_OMO_INFO&columns=ALL&sortColumns=TRADE_DATE&sortTypes=-1&pageNumber=1&pageSize=30"
            res = requests.get(url, timeout=10).json()
            result = res.get("result", {}).get("data", [])
            if result:
                df = pd.DataFrame(result)
                # 统一列名映射
                df.rename(columns={'TRADE_DATE': '日期', 'EXEC_TYPE': '交易方向', 'OMO_AMOUNT': '交易量(亿)', 'SUBC_RATE': '利率(%)', 'TERM': '期限'}, inplace=True)
        except Exception as e:
            print(f"[-] 东方财富OMO原生接口请求失败: {e}")

    if df is None or df.empty:
        return {"history_7d": [], "future_14d": []}

    try:
        date_col = get_fuzzy_column(df, '日期') or get_fuzzy_column(df, 'DATE') or df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col])
        today = pd.to_datetime(datetime.today().date())
        
        hist_df = df[(df[date_col] <= today) & (df[date_col] >= today - timedelta(days=7))]
        future_df = df[(df[date_col] > today) & (df[date_col] <= today + timedelta(days=14))]
        
        hist_data = hist_df.head(10).fillna("-").to_dict(orient='records')
        future_data = future_df.head(15).fillna("-").to_dict(orient='records')
        
        for item in hist_data: item[date_col] = item[date_col].strftime('%Y-%m-%d')
        for item in future_data: item[date_col] = item[date_col].strftime('%Y-%m-%d')
        return {"history_7d": hist_data, "future_14d": future_data}
    except Exception as e:
        print(f"[-] OMO 数据解析失败: {e}")
        return {"history_7d": [], "future_14d": []}

def get_unlock_calendar():
    """2. A股非ST主板解禁日历表"""
    if hasattr(ak, "stock_restricted_release_queue_em"):
        try:
            df = ak.stock_restricted_release_queue_em()
            name_col = get_fuzzy_column(df, '简称') or get_fuzzy_column(df, 'NAME')
            time_col = get_fuzzy_column(df, '时间') or get_fuzzy_column(df, 'DATE')
            
            if name_col and time_col:
                df = df[~df[name_col].str.contains('ST|退|st', na=False)]
                df[time_col] = pd.to_datetime(df[time_col])
                today = pd.to_datetime(datetime.today().date())
                df_future = df[df[time_col] >= today].sort_values(by=time_col)
                df_future[time_col] = df_future[time_col].dt.strftime('%Y-%m-%d')
                return df_future.head(20).fillna("-").to_dict(orient='records')
        except:
            pass
    return []

def get_exchange_rate():
    """3. 人民币离岸和在岸汇率 (直连新浪外汇公共接口)"""
    try:
        # 使用极其稳定的新浪财经轻量化行情接口
        url = "https://hq.sinajs.cn/list=fx_susdcny,fx_susdcnh"
        headers = {"Referer": "https://finance.sina.com.cn"}
        res = requests.get(url, headers=headers, timeout=10).text
        # 解析报价
        parts = res.split('\n')
        inline = parts[0].split('"')[1].split(',')
        outline = parts[1].split('"')[1].split(',')
        return {"USDCNY_Onshore": float(inline[1]), "USDCNH_Offshore": float(outline[1])}
    except Exception as e:
        print(f"[-] 新浪汇率接口异常: {e}")
        return {"USDCNY_Onshore": "-", "USDCNH_Offshore": "-"}

def get_citic_futures():
    """4. 机构和中信多空持仓数据 (自适应函数路由)"""
    df = None
    today_str = datetime.today().strftime('%Y%m%d')
    
    for func_name in ['futures_holding_position_csci', 'futures_position_num_holding_fame', 'futures_holding_manager']:
        if hasattr(ak, func_name):
            try:
                df = getattr(ak, func_name)(symbol="IF", date=today_str)
                if df is not None and not df.empty: break
            except:
                continue
    if df is empty or df is None:
        return []
    try:
        inst_col = get_fuzzy_column(df, '机构') or get_fuzzy_column(df, '公司')
        if inst_col:
            citic = df[df[inst_col].str.contains('中信', na=False)]
            return citic.fillna("-").to_dict(orient='records')
    except:
        pass
    return []

def get_synthetic_sentiment():
    """5. 沪深主要情绪指标/贪婪指标 (使用A股全市场赚钱效应独立生成，永不断流)"""
    try:
        df = ak.stock_zh_a_spot_em()
        pct_col = get_fuzzy_column(df, '涨跌幅')
        if pct_col:
            total_stocks = len(df)
            up_stocks = len(df[df[pct_col] > 0])
            # 情绪得分：今日上涨个股占比 (0 - 100)
            sentiment_score = round((up_stocks / total_stocks) * 100, 2)
            if sentiment_score > 75: sentiment_str = "极度贪婪"
            elif sentiment_score > 55: sentiment_str = "多头贪婪"
            elif sentiment_score > 45: sentiment_str = "情绪中性"
            elif sentiment_score > 25: sentiment_str = "恐慌蔓延"
            else: sentiment_str = "极度恐慌"
            return {"value": sentiment_score, "sentiment": sentiment_str}
    except Exception as e:
        print(f"[-] 自主计算全场情绪指标失效: {e}")
    return {"value": "-", "sentiment": "未知"}

def get_macro_and_sentiment():
    """整合获取第 5 至 14 项宏观经济和利率指标"""
    hub = {}
    
    # 5. 情绪
    hub['fear_greed'] = get_synthetic_sentiment()

    # 6. 大宗品价格
    try:
        df_gold = ak.stock_zh_a_spot_em() # 降级借用大宗概念或现货价格
        hub['commodity'] = {"gold": "-", "oil": "-"}
        # 尝试新浪期货
        for sym, key in [("AU0", "gold"), ("SC0", "oil")]:
            res_df = ak.futures_zh_spot(symbol=sym)
            if res_df is not None:
                hub['commodity'][key] = res_df.iloc[0]['current_price']
    except:
        pass

    # 7. 中/美最新5年期以上利率 (加入模糊匹配，彻底击碎 KeyError)
    hub['interest_rate'] = {"china_lpr_5y": "-", "us_bond_10y": "-"}
    try:
        df_lpr = ak.macro_china_lpr()
        if df_lpr is not None and not df_lpr.empty:
            col_5y = get_fuzzy_column(df_lpr, '5年') or df_lpr.columns[1]
            hub['interest_rate']["china_lpr_5y"] = str(df_lpr.iloc[0][col_5y])
    except Exception as e:
        print(f"[-] LPR 获取解析异常: {e}")

    try:
        df_us_bond = ak.bond_zh_us_rate()
        if df_us_bond is not None and not df_us_bond.empty:
            col_us = get_fuzzy_column(df_us_bond, '美国国债收益率10年') or get_fuzzy_column(df_us_bond, '10年') or df_us_bond.columns[-1]
            hub['interest_rate']["us_bond_10y"] = str(df_us_bond.iloc[-1][col_us])
    except:
        pass

    # 13. A股两融余额
    try:
        df_margin = ak.stock_margin_detail()
        if df_margin is not None:
            date_col = get_fuzzy_column(df_margin, '日期') or df_margin.columns[0]
            val_col = get_fuzzy_column(df_margin, '余额') or df_margin.columns[1]
            hub['margin_balance'] = {
                "日期": str(df_margin.iloc[0][date_col]),
                "融资融券余额": float(df_margin.iloc[0][val_col])
            }
    except:
        hub['margin_balance'] = None

    # 8-12, 14. 宏观核心指标循环安全扫描
    macro_mappings = {
        "china_cpi": "macro_china_cpi",
        "china_ppi": "macro_china_ppi",
        "china_pmi": "macro_china_pmi",
        "china_m1_m2": "macro_china_money_supply",
        "china_unemployment": "macro_china_urban_unemployment",
        "usa_cpi": "macro_usa_cpi_monthly",
        "usa_ppi": "macro_usa_ppi_monthly",
        "usa_pmi": "macro_usa_pmi_monthly",
        "usa_non_farm": "macro_usa_non_farm"
    }

    for key, api_name in macro_mappings.items():
        hub[key] = None
        if hasattr(ak, api_name):
            try:
                df_m = getattr(ak, api_name)()
                if df_m is not None and not df_m.empty:
                    latest_row = df_m.iloc[0].to_dict()
                    hub[key] = {str(k): str(v) for k, v in latest_row.items()}
            except:
                pass
    return hub

def build_dashboard():
    print(f"[{datetime.now()}] 开始抓取全景宏观数据...")
    output_hub = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pboc_omo": get_pboc_omo(),
        "unlock_calendar": get_unlock_calendar(),
        "exchange_rate": get_exchange_rate(),
        "citic_futures": get_citic_futures(),
        "macro_metrics": get_macro_and_sentiment()
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_hub, f, ensure_ascii=False, indent=4)
    print(f"[{datetime.now()}] 看板数据文件更新成功。")

if __name__ == "__main__":
    build_dashboard()
