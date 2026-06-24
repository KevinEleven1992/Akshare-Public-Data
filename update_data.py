import akshare as ak
import pandas as pd
import json
import traceback
from datetime import datetime, timedelta

# 忽略Pandas链式赋值警告
pd.options.mode.chained_assignment = None

def safe_call_ak(func_name, *args, **kwargs):
    """
    【核心防崩引擎】动态调用 AkShare 接口。
    若接口更名、不存在或请求超时，返回 None 并继续执行后续任务，确保看板坚挺。
    """
    if not hasattr(ak, func_name):
        print(f"[-] 警告: 当前 AkShare 版本未发现接口 [{func_name}]，已安全跳过。")
        return None
    try:
        func = getattr(ak, func_name)
        df = func(*args, **kwargs)
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return None
        return df
    except Exception as e:
        print(f"[-] 接口 [{func_name}] 运行时获取失败: {e}")
        return None

def get_pboc_omo():
    """1. 央行逆回购操作量与到期推算 (使用东财最新公开市场业务提示接口)"""
    df = safe_call_ak("repo_open_market_info_em")
    if df is None: return None
    
    try:
        # 兼容处理列名
        df.columns = [str(c) for c in df.columns]
        date_col = '发布日期' if '发布日期' in df.columns else df.columns[0]
        
        df[date_col] = pd.to_datetime(df[date_col])
        today = pd.to_datetime(datetime.today().date())
        
        # 历史7天与未来14天过滤
        hist_df = df[(df[date_col] <= today) & (df[date_col] >= today - timedelta(days=7))]
        future_df = df[(df[date_col] > today) & (df[date_col] <= today + timedelta(days=14))]
        
        hist_data = hist_df.head(10).fillna("-").to_dict(orient='records')
        future_data = future_df.head(15).fillna("-").to_dict(orient='records')
        
        for item in hist_data: item[date_col] = item[date_col].strftime('%Y-%m-%d')
        for item in future_data: item[date_col] = item[date_col].strftime('%Y-%m-%d')
        
        return {"history_7d": hist_data, "future_14d": future_data}
    except Exception as e:
        print(f"OMO 数据清洗失败: {e}")
        return None

def get_unlock_calendar():
    """2. A股非ST主板解禁日历表"""
    df = safe_call_ak("stock_restricted_release_queue_em")
    if df is None: return None
    try:
        df = df[~df['股票简称'].str.contains('ST|退|st', na=False)]
        df['解禁时间'] = pd.to_datetime(df['解禁时间'])
        today = pd.to_datetime(datetime.today().date())
        # 筛选近期解禁
        df_future = df[df['解禁时间'] >= today].sort_values(by='解禁时间')
        df_future['解禁时间'] = df_future['解禁时间'].dt.strftime('%Y-%m-%d')
        return df_future.head(20).fillna("-").to_dict(orient='records')
    except Exception:
        return None

def get_exchange_rate():
    """3. 人民币离岸和在岸汇率"""
    df = safe_call_ak("fx_spot_quote")
    if df is None:
        # 备用方案：新浪外汇
        df = safe_call_ak("currency_boc_sina")
        if df is None: return None
        try:
            cny = df[df['外币名称'] == '美元']['现汇卖出价'].values[0]
            return {"USDCNY_Onshore": cny, "USDCNH_Offshore": "-"}
        except: return None
    try:
        usd_cny = df[df['货币对'] == 'USDCNY']['最新价'].values[0]
        usd_cnh = df[df['货币对'] == 'USDCNH']['最新价'].values[0]
        return {"USDCNY_Onshore": float(usd_cny), "USDCNH_Offshore": float(usd_cnh)}
    except:
        return None

def get_citic_futures():
    """4. 机构和中信每天成交的多单空单数据 (以沪深300 IF合约为例)"""
    today_str = datetime.today().strftime('%Y%m%d')
    df = safe_call_ak("futures_holding_manager", symbol="IF", date=today_str)
    if df is None:
        # 周末或未收盘时向前推一天
        yesterday_str = (datetime.today() - timedelta(days=1)).strftime('%Y%m%d')
        df = safe_call_ak("futures_holding_manager", symbol="IF", date=yesterday_str)
    
    if df is None: return None
    try:
        citic = df[df['机构名称'].str.contains('中信期货', na=False)]
        return citic.fillna("-").to_dict(orient='records')
    except:
        return None

def get_macro_and_sentiment():
    """整合获取第 5 至 14 项核心情绪及海内外宏观指标"""
    hub = {}

    # 5. 情绪指标 / 贪婪指标
    df_greed = safe_call_ak("index_fear_greed_funddb")
    hub['fear_greed'] = df_greed.iloc[-1].fillna("-").to_dict() if df_greed is not None else None

    # 6. 大宗品价格 (黄金、石油 - 订阅国内核心主力连续合约更具A股投研价值)
    # AU0为黄金连续，SC0为原油连续
    df_gold = safe_call_ak("futures_zh_spot", symbol="AU0")
    df_oil = safe_call_ak("futures_zh_spot", symbol="SC0")
    hub['commodity'] = {
        "gold": df_gold.iloc[0]['current_price'] if df_gold is not None else "-",
        "oil": df_oil.iloc[0]['current_price'] if df_oil is not None else "-"
    }

    # 7. 中/美最新5年期以上利率
    df_lpr = safe_call_ak("macro_china_lpr")
    df_us_bond = safe_call_ak("bond_zh_us_rate")
    hub['interest_rate'] = {
        "china_lpr_5y": df_lpr.iloc[0]['5年期LPR'] if df_lpr is not None else "-",
        "us_bond_10y": df_us_bond.iloc[-1]['美国国债收益率10年'] if df_us_bond is not None else "-"
    }

    # 13. A股两融余额
    df_margin = safe_call_ak("stock_margin_detail")
    hub['margin_balance'] = df_margin.iloc[0][['日期', '融资融券余额']].fillna("-").to_dict() if df_margin is not None else None

    # 8-12, 14. 中美核心宏观指标映射表 (采用全动态字符串反射，规避编译期AttributeError)
    macro_mappings = {
        "china_cpi": "macro_china_cpi",
        "china_ppi": "macro_china_ppi",
        "china_pmi": "macro_china_pmi",
        "china_m1_m2": "macro_china_money_supply",
        "china_unemployment": "macro_china_urban_unemployment",
        "usa_cpi": "macro_usa_cpi_monthly",      # 已修正接口名
        "usa_ppi": "macro_usa_ppi_monthly",      # 已修正接口名
        "usa_pmi": "macro_usa_pmi_monthly",      # 已修正接口名
        "usa_non_farm": "macro_usa_non_farm"     # 美国就业核心指标
    }

    for key, api_name in macro_mappings.items():
        df_m = safe_call_ak(api_name)
        if df_m is not None:
            try:
                latest_row = df_m.iloc[0].to_dict()
                hub[key] = {str(k): str(v) for k, v in latest_row.items()}
            except:
                hub[key] = None
        else:
            hub[key] = None

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

    # 写入规范的 JSON 文件供前端拉取
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_hub, f, ensure_ascii=False, indent=4)
        
    print(f"[{datetime.now()}] 核心数据全量捕获完成，顺利写入 data.json。")

if __name__ == "__main__":
    build_dashboard()
