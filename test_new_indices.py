"""
快速验证新增指数的数据通路:
  - 沪深300  000300
  - 中证800  000906
  - 1000成长创新 931591 (对应ETF: 159505 中证1000成长ETF华夏)
  - 国证2000  399303 (对应ETF: 国证2000ETF博时)
  - 中证红利  000922
  - 红利低波100 930955 (已有)

运行: python test_new_indices.py
需要 JISILU_USERNAME / JISILU_PASSWORD 环境变量
"""

import os
from datetime import datetime, timedelta, timezone

import monitor_drawdown as md

BEIJING_TZ = timezone(timedelta(hours=8))

TARGETS = [
    {"name": "沪深300", "code": "000300", "type": "index"},
    {"name": "中证800", "code": "000906", "type": "index"},
    {"name": "1000成长创新", "code": "931591", "type": "index", "jisilu_etf_code": "562520"},
    {"name": "国证2000", "code": "399303", "type": "index", "jisilu_etf_code": "159505"},
    {"name": "中证红利", "code": "000922", "type": "index", "jisilu_etf_code": "159581"},
    {"name": "红利低波100", "code": "930955", "type": "index"},
]

END = datetime.now(BEIJING_TZ)
START = END - timedelta(days=30)
start_str = START.strftime("%Y%m%d")
end_str = END.strftime("%Y%m%d")

SEP = "-" * 60


def check_price_data():
    print(f"\n{'='*60}")
    print("1. 历史价格数据 (fetch_index_data)")
    print(f"{'='*60}")
    for t in TARGETS:
        code, name = t["code"], t["name"]
        try:
            df = md.fetch_index_data(code, start_str, end_str)
            if df.empty:
                print(f"  [WARN] {name}({code}): 空数据")
            else:
                latest = df.iloc[-1]
                print(f"  [OK]   {name}({code}): {len(df)} 条, 最新 {latest['date'].strftime('%Y-%m-%d')} close={latest['close']:.4f}")
        except Exception as e:
            print(f"  [FAIL] {name}({code}): {e}")


def check_jisilu_patch(jisilu_rows):
    print(f"\n{'='*60}")
    print("2. 集思录当日价格补齐 (patch_index_dataframe_with_jisilu)")
    print(f"{'='*60}")
    for t in TARGETS:
        code, name = t["code"], t["name"]
        fallback = t.get("jisilu_etf_code")

        candidates = md.find_jisilu_index_etf_candidates(jisilu_rows, code)
        selected = md.select_best_jisilu_index_etf(candidates)
        via = "index_id"

        if selected is None and fallback:
            selected = md.find_jisilu_etf_by_fund_id(jisilu_rows, fallback)
            via = f"fallback({fallback})"

        if selected is None:
            print(f"  [FAIL] {name}({code}): 集思录无对应ETF (index_id={code}, fallback={fallback})")
            continue

        fund_id = selected.get("fund_id", "?")
        fund_nm = selected.get("fund_nm", "?")
        price = selected.get("price", "?")
        print(f"  [OK]   {name}({code}): via={via} -> {fund_nm}({fund_id}), 现价={price}, 共{len(candidates)}个index_id候选")


def check_index_metrics():
    print(f"\n{'='*60}")
    print("3. 指数股息率 + 估值分位 (fetch_target_index_metrics)")
    print(f"{'='*60}")
    for t in TARGETS:
        code, name = t["code"], t["name"]
        try:
            metrics = md.fetch_target_index_metrics(t)
            if not metrics:
                print(f"  [WARN] {name}({code}): 无估值数据 (efunds 可能不支持此指数)")
                continue
            dy = metrics.get("index_dividend_yield")
            dy_date = metrics.get("index_dividend_yield_date", "")
            val_date = metrics.get("index_valuation_date", "")
            val_metrics = metrics.get("index_valuation_metrics", {})
            pe_pct = val_metrics.get("PE(TTM)", {}).get("percentiles", {})
            print(
                f"  [OK]   {name}({code}): "
                f"股息率={dy}%({dy_date}), "
                f"估值日期={val_date}, "
                f"PE分位={pe_pct}"
            )
        except Exception as e:
            print(f"  [FAIL] {name}({code}): {e}")


if __name__ == "__main__":
    check_price_data()

    jisilu_user = os.getenv("JISILU_USERNAME", "").strip()
    jisilu_pass = os.getenv("JISILU_PASSWORD", "").strip()
    if jisilu_user and jisilu_pass:
        print(f"\n{'='*60}")
        print("集思录登录中...")
        try:
            jisilu_rows = md.fetch_jisilu_etf_rows(jisilu_user, jisilu_pass)
            print(f"  登录成功，获取 {len(jisilu_rows)} 条 ETF 数据")
            check_jisilu_patch(jisilu_rows)
        except Exception as e:
            print(f"  [FAIL] 集思录登录失败: {e}")
    else:
        print("\n[SKIP] 未配置 JISILU_USERNAME/JISILU_PASSWORD，跳过集思录补价测试")

    check_index_metrics()

    print(f"\n{'='*60}")
    print("验证完成")
