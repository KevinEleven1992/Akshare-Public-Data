import akshare as ak
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import time
import traceback

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'docs', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

def safe_call(func, *args, retries=2, **kwargs):
    for i in range(retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"  retry {i}: {e}")
            time.sleep(3)
    return None

def fetch_macro_china():
    """中国宏观：CPI/PPI/PMI/M1/M2/LPR"""
    data = {}
    # CPI
    df = safe_call(ak.macro_china_cpi)
    if df is not None:
        data['cpi'] = df.head(12).to_dict(orient='records')
    # PPI
    df = safe_call(ak.macro_china_ppi)
    if df is not None:
        data['ppi'] = df.head(12).to_dict(orient='records')
    # PMI
    df = safe_call(ak.macro_china_pmi)
    if df is not None:
        data['pmi'] = df.head(12).to_dict(orient='records')
    # 货币供应量 M1/M2
    df = safe_call(ak.macro_china_money_supply)
    if df is not None:
        data['money_supply'] = df.head(12).to_dict(orient='records')
    # LPR
    df = safe_call(ak.macro_china_lpr)
    if df is not None:
        data['lpr'] = df.head(24).to_dict(orient='records')
    return data

def fetch_macro_usa():
    """美国宏观：CPI/PPI/PMI/非农/失业率"""
    data = {}
    for name, func in [
        ('cpi', ak.macro_usa_cpi_monthly),
        ('non_farm', ak.macro_usa_non_farm),
        ('unemployment', ak.macro_usa_unemployment_rate),
    ]:
        df = safe_call(func)
        if df is not None:
            data[name] = df.head(12).to_dict(orient='records')
    return data

def fetch_rates():
    """中美国债收益率"""
    start = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
    df = safe_call(ak.bond_zh_us_rate, start_date=start)
    if df is not None:
        return df.tail(30).to_dict(orient='records')
    return []

def fetch_fx():
    """在岸人民币（中行牌价）"""
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
    df = safe_call(ak.currency_boc_sina, symbol="美元", start_date=start, end_date=end)
    if df is not None:
        return df.tail(14).to_dict(orient='records')
    return []

def fetch_margin():
    """沪深两融余额（历史7天）"""
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=14)).strftime('%Y%m%d')
    data = {}
    df = safe_call(ak.stock_margin_sse, start_date=start, end_date=end)
    if df is not None:
        data['sse'] = df.tail(7).to_dict(orient='records')
    df = safe_call(ak.stock_margin_szse, start_date=start, end_date=end)
    if df is not None:
        data['szse'] = df.tail(7).to_dict(orient='records')
    return data

def fetch_commodities():
    """黄金、原油主力"""
    data = {}
    df = safe_call(ak.futures_main_sina, symbol="AU0")
    if df is not None:
        data['gold'] = df.tail(30).to_dict(orient='records')
    df = safe_call(ak.futures_main_sina, symbol="SC0")  # 原油(INE)
    if df is not None:
        data['oil'] = df.tail(30).to_dict(orient='records')
    return data

def fetch_if_cot():
    """股指期货 IF 持仓（中信等多空单）"""
    data = {}
    for sym in ['IF', 'IH', 'IC']:
        df = safe_call(ak.futures_cot_cffex, symbol=sym, indicator="持仓量")
        if df is not None:
            # 筛选中信期货
            df['会员简称'] = df.get('会员简称', df.iloc[:,0]).astype(str)
            citic = df[df['会员简称'].str.contains('中信')]
            data[sym] = {
                'all': df.head(20).to_dict(orient='records'),
                'citic': citic.to_dict(orient='records'),
            }
    return data

def fetch_repo_calendar():
    """
    央行逆回购：历史7天 + 未来14天到期日历
    AkShare 无直接接口，预留自爬人民银行OMO公告位置
    此处给出7天期逆回购到期推算逻辑框架
    """
    today = datetime.now().date()
    calendar = []
    # 假设已有历史操作记录 repo_history: [{date, amount, term_days}]
    # 未来到期 = date + term_days
    # 此处需结合自爬数据填充，示例留空结构
    for i in range(-7, 15):
        d = today + timedelta(days=i)
        calendar.append({
            'date': d.strftime('%Y-%m-%d'),
            'type': 'past' if i < 0 else ('today' if i == 0 else 'future'),
            'operation': None,   # 操作量（亿元），自爬填充
            'maturity': None,    # 到期量（亿元），按 term 推算
        })
    return calendar

def main():
    print(f"=== 数据采集开始 {datetime.now()} ===")
    snapshot = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'macro_china': fetch_macro_china(),
        'macro_usa': fetch_macro_usa(),
        'rates': fetch_rates(),
        'fx': fetch_fx(),
        'margin': fetch_margin(),
        'commodities': fetch_commodities(),
        'if_cot': fetch_if_cot(),
        'repo_calendar': fetch_repo_calendar(),
    }

    # 写入最新快照
    latest_path = os.path.join(DATA_DIR, 'latest.json')
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, default=str, indent=2)
    print(f"已写入 {latest_path}")

    # 写入历史归档（按日期）
    hist_path = os.path.join(DATA_DIR, f"snapshot_{datetime.now().strftime('%Y%m%d')}.json")
    with open(hist_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, default=str, indent=2)

    print("=== 采集完成 ===")

if __name__ == '__main__':
    main()
