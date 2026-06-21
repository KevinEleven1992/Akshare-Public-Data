#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日宏观数据采集脚本
数据源: AkShare (https://akshare.akfamily.xyz/)
输出: docs/data/latest.json + 历史快照
"""

import akshare as ak
import pandas as pd
import json
import os
import time
import traceback
from datetime import datetime, timedelta

# ==================== 路径配置 ====================
# 脚本位于 scripts/ 目录，向上取一级得到项目根目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, 'docs', 'data')

os.makedirs(DATA_DIR, exist_ok=True)


def log(msg):
    """带时间戳的日志输出"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def safe_call(func, *args, retries=3, sleep_sec=2, **kwargs):
    """带重试的安全调用"""
    for i in range(retries):
        try:
            result = func(*args, **kwargs)
            if result is not None:
                return result
            log(f"  返回空值, 重试 {i+1}/{retries}")
        except Exception as e:
            log(f"  异常: {e}, 重试 {i+1}/{retries}")
            if i < retries - 1:
                time.sleep(sleep_sec)
    log(f"  {retries}次重试后仍失败")
    return None


def df_to_records(df, max_rows=30):
    """DataFrame 转 list[dict]，处理 NaN 和时间戳"""
    if df is None or len(df) == 0:
        return []
    df = df.head(max_rows).copy().fillna('')
    records = df.to_dict(orient='records')
    cleaned = []
    for r in records:
        row = {}
        for k, v in r.items():
            if isinstance(v, (pd.Timestamp, datetime)):
                row[k] = v.strftime('%Y-%m-%d')
            elif isinstance(v, float):
                row[k] = round(v, 4) if not pd.isna(v) else None
            elif hasattr(v, 'item'):
                try:
                    row[k] = v.item()
                except:
                    row[k] = str(v)
            else:
                row[k] = v
        cleaned.append(row)
    return cleaned


# ==================== 数据采集函数 ====================

def fetch_repo_calendar():
    """央行逆回购: 历史7天 + 未来14天到期日历"""
    log("采集央行逆回购日历...")
    today = datetime.now().date()
    calendar = []
    for i in range(-7, 15):
        d = today + timedelta(days=i)
        calendar.append({
            'date': d.strftime('%Y-%m-%d'),
            'weekday': ['一', '二', '三', '四', '五', '六', '日'][d.weekday()],
            'type': 'past' if i < 0 else ('today' if i == 0 else 'future'),
            'operation': None,
            'maturity': None,
            'note': '历史' if i < 0 else ('今日' if i == 0 else '未来到期'),
        })
    return calendar


def fetch_fx():
    """人民币汇率 (在岸/离岸)"""
    log("采集人民币汇率...")
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
    data = {}
    # 在岸 - 中行牌价
    df = safe_call(ak.currency_boc_sina, symbol="美元", start_date=start, end_date=end)
    if df is not None:
        data['onshore'] = df_to_records(df.tail(14))
        log(f"  在岸汇率: {len(data['onshore'])} 条")
    # 离岸
    try:
        df2 = safe_call(ak.fx_spot_quote)
        if df2 is not None:
            data['offshore'] = df_to_records(df2.head(20))
            log(f"  离岸汇率: {len(data.get('offshore', []))} 条")
    except Exception as e:
        log(f"  离岸汇率失败: {e}")
    return data


def fetch_margin():
    """A股两融余额"""
    log("采集两融余额...")
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=14)).strftime('%Y%m%d')
    data = {}
    df = safe_call(ak.stock_margin_sse, start_date=start, end_date=end)
    if df is not None:
        data['sse'] = df_to_records(df.tail(7))
        log(f"  上交所: {len(data['sse'])} 条")
    df = safe_call(ak.stock_margin_szse, start_date=start, end_date=end)
    if df is not None:
        data['szse'] = df_to_records(df.tail(7))
        log(f"  深交所: {len(data.get('szse', []))} 条")
    return data


def fetch_commodities():
    """大宗商品: 黄金/原油"""
    log("采集大宗商品价格...")
    data = {}
    df = safe_call(ak.futures_main_sina, symbol="AU0")
    if df is not None:
        data['gold'] = df_to_records(df.tail(30))
        log(f"  黄金: {len(data['gold'])} 条")
    df = safe_call(ak.futures_main_sina, symbol="SC0")
    if df is not None:
        data['oil'] = df_to_records(df.tail(30))
        log(f"  原油: {len(data.get('oil', []))} 条")
    return data


def fetch_rates():
    """中美国债收益率"""
    log("采集中美国债收益率...")
    start = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
    df = safe_call(ak.bond_zh_us_rate, start_date=start)
    if df is not None:
        records = df_to_records(df.tail(30))
        log(f"  收益率: {len(records)} 条")
        return records
    return []


def fetch_macro_china():
    """中国宏观: CPI/PPI/PMI/M1/M2/LPR"""
    log("采集中国宏观数据...")
    data = {}
    # CPI
    df = safe_call(ak.macro_china_cpi)
    if df is not None:
        data['cpi'] = df_to_records(df, 12)
        log(f"  CPI: {len(data['cpi'])} 条")
    # PPI
    df = safe_call(ak.macro_china_ppi)
    if df is not None:
        data['ppi'] = df_to_records(df, 12)
        log(f"  PPI: {len(data['ppi'])} 条")
    # PMI
    df = safe_call(ak.macro_china_pmi)
    if df is not None:
        data['pmi'] = df_to_records(df, 12)
        log(f"  PMI: {len(data['pmi'])} 条")
    # M1/M2
    df = safe_call(ak.macro_china_money_supply)
    if df is not None:
        data['money_supply'] = df_to_records(df, 12)
        log(f"  M1/M2: {len(data['money_supply'])} 条")
    # LPR
    df = safe_call(ak.macro_china_lpr)
    if df is not None:
        data['lpr'] = df_to_records(df, 24)
        log(f"  LPR: {len(data['lpr'])} 条")
    return data


def fetch_macro_usa():
    """美国宏观: CPI/非农/失业率"""
    log("采集美国宏观数据...")
    data = {}
    df = safe_call(ak.macro_usa_cpi_monthly)
    if df is not None:
        data['cpi'] = df_to_records(df, 12)
        log(f"  CPI: {len(data['cpi'])} 条")
    df = safe_call(ak.macro_usa_non_farm)
    if df is not None:
        data['non_farm'] = df_to_records(df, 12)
        log(f"  非农: {len(data['non_farm'])} 条")
    df = safe_call(ak.macro_usa_unemployment_rate)
    if df is not None:
        data['unemployment'] = df_to_records(df, 12)
        log(f"  失业率: {len(data['unemployment'])} 条")
    return data


def fetch_if_cot():
    """股指期货持仓 (中信等多空单)"""
    log("采集股指期货持仓...")
    data = {}
    for sym in ['IF', 'IH', 'IC']:
        df = safe_call(ak.futures_cot_cffex, symbol=sym, indicator="持仓量")
        if df is not None:
            records = df_to_records(df, 20)
            citic = []
            for r in records:
                for v in r.values():
                    if isinstance(v, str) and '中信' in v:
                        citic.append(r)
                        break
            data[sym] = {'all': records, 'citic': citic}
            log(f"  {sym}: {len(records)} 条, 中信: {len(citic)} 条")
        else:
            data[sym] = {'all': [], 'citic': []}
    return data


def fetch_sentiment():
    """沪深情绪指标 (自建)"""
    log("采集市场情绪指标...")
    data = {}
    try:
        df = safe_call(ak.stock_zh_a_spot_em)
        if df is not None:
            total = len(df)
            if '涨跌幅' in df.columns:
                up = int((df['涨跌幅'] > 0).sum())
                down = int((df['涨跌幅'] < 0).sum())
                data['breadth'] = {
                    'total': total, 'up': up, 'down': down,
                    'up_ratio': round(up / total * 100, 2) if total > 0 else 0
                }
                log(f"  涨{up} 跌{down} 共{total}")
            if '换手率' in df.columns:
                t = df['换手率'].dropna()
                if len(t) > 0:
                    data['turnover_median'] = round(float(t.median()), 2)
                    log(f"  换手率中位数: {data['turnover_median']}%")
    except Exception as e:
        log(f"  情绪指标失败: {e}")
    return data


# ==================== 主函数 ====================

def main():
    log("=" * 50)
    log("每日宏观数据采集开始")
    log(f"项目根目录: {PROJECT_ROOT}")
    log(f"数据输出目录: {DATA_DIR}")
    log(f"数据目录是否存在: {os.path.isdir(DATA_DIR)}")
    log("=" * 50)

    snapshot = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'update_timestamp': int(datetime.now().timestamp()),
        'status': 'running',
    }

    sections = [
        ('repo_calendar', fetch_repo_calendar),
        ('fx', fetch_fx),
        ('margin', fetch_margin),
        ('commodities', fetch_commodities),
        ('rates', fetch_rates),
        ('macro_china', fetch_macro_china),
        ('macro_usa', fetch_macro_usa),
        ('if_cot', fetch_if_cot),
        ('sentiment', fetch_sentiment),
    ]

    for key, func in sections:
        try:
            log(f"--- 开始: {key} ---")
            snapshot[key] = func()
            log(f"--- 完成: {key} ---")
        except Exception as e:
            log(f"❌ {key} 采集失败: {e}")
            traceback.print_exc()
            snapshot[key] = None
        time.sleep(0.5)

    snapshot['status'] = 'completed'

    # 写入 latest.json
    latest_path = os.path.join(DATA_DIR, 'latest.json')
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, default=str, indent=2)
    log(f"✅ 已写入: {latest_path}")

    # 写入历史归档
    today_str = datetime.now().strftime('%Y%m%d')
    hist_path = os.path.join(DATA_DIR, f'snapshot_{today_str}.json')
    with open(hist_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, default=str, indent=2)
    log(f"✅ 已归档: {hist_path}")

    # 统计
    log("=" * 50)
    log("采集完成! 数据概览:")
    for key, val in snapshot.items():
        if key in ('update_time', 'update_timestamp', 'status'):
            continue
        if val is None:
            log(f"  {key}: ❌ 失败")
        elif isinstance(val, dict):
            log(f"  {key}: ✅ ({len(val)} 项)")
        elif isinstance(val, list):
            log(f"  {key}: ✅ ({len(val)} 条)")
        else:
            log(f"  {key}: ✅")
    log("=" * 50)


if __name__ == '__main__':
    main()
