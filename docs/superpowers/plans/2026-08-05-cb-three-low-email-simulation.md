# 可转债三低轮动 · 模拟净值 + 邮件推送

## 目标
在 monitor_drawdown 仓库新建一套可转债三低轮动**模拟盘**：每日收盘后拉集思录全市场转债，跑三低选债（从 `v2_cb_rotation` 移植），以 **10 只等权、日频再平衡、无盘中止盈** 跟踪模拟净值，记录持仓历史，邮件推送净值曲线 + 选债排名。整体流程对标 `etf_rotation_20d`。

## 已确认的设计决策
- **模拟盘**：NAV 从 1.0 起，不发真实委托
- **仅向前记录**：不回填历史（三低因子是每日快照，集思录不存历史）
- **target_count=10，hold_tolerance=5（可配）**，10 只等权，日频再平衡
- **只做日频收盘**：不建模盘中 5% 止盈/回落
- 选债参数（因子 / 排除规则 / 强赎过滤 / 上市天数 / 7 只手动排除清单）**原样从实盘 `factors.json` 移植**

## 无未来函数的净值机制
- `entry[T].holdings` = T 收盘选出的 10 只（即次日 T+1 持仓），记录 T 收盘价
- `entry[T].daily_return` = T 组合收益 = mean(prev_holdings 各只 T-1收盘→T收盘 涨幅)；`prev_holdings` = 上一条 entry 的 holdings
- `entry[T].nav` = `prev_nav × (1 + daily_return)`
- **首次运行**：无 prev，`nav=1.0`，`daily_return=0`，`holdings=top10`
- `apply_tolerance`：已持有且仍在 keep_pool(`target+tol`) 内的保留，空缺按排名补到 10 只 → 降低换手

## 文件清单（新增）
1. `cb_three_low.py` — 核心策略模块（选债移植 + 净值跟踪 + 状态 + 报告）
2. `cb_three_low_config.yaml` — 配置
3. `cb_three_low_email_chart.py` — 净值曲线图（照搬 `etf_rotation_20d_email_chart.py`，改标题/CID）
4. `send_cb_three_low_email.py` — 邮件发送（照搬 `send_etf_rotation_20d_email.py` 结构）
5. `.github/workflows/cb_three_low.yml` — 每日 workflow（照搬 `etf_rotation_20d.yml`，去 akshare）
6. `tests/test_cb_three_low.py` — 单元测试（无网络，照搬 etf 测试结构）
7. `data_state/cb_three_low_state.json` — 运行时状态（首次运行自动生成）

## 选债逻辑移植（来自 `v2_cb_rotation/src/services/jisilu_service.py`）
- `fetch_cb_list`：POST `cb_list_new`（`CB_FORM_DATA` + `___jsl`）→ 复用 `jisilu_login.login_jisilu` 的 cookie（同一套 AES-ECB 登录，cookie 通用）
- `fetch_redeem_list`：POST `redeem_list` → `remain_days_map`（`redeem_safe_days` 过滤）+ 强赎状态展示
- `filter_cb`：ST + 强赎 icons(R/O/B) + 排除规则 + `redeem_safe_days=2` + `min_listing_days=3` + 手动排除清单
- `three_low_strategy`：`dblow` / `premium_rt` / `curr_iss_amt` 各权重 1 打分求和，降序，同分按双低升序
- `normalize_bond_code` / `build_bond_code_match_set`：代码归一化（`.SH/.SZ` ↔ 6 位）
- 存储用 6 位 `bond_id` 作为 canonical code（与 etf 一致）

## 配置（cb_three_low_config.yaml）
```yaml
strategy:
  target_count: 10
  hold_tolerance: 5
  initial_nav: 1.0
  factors:
    - {field: dblow,        weight: 1.0, ascending: true}
    - {field: premium_rt,   weight: 1.0, ascending: true}
    - {field: curr_iss_amt, weight: 1.0, ascending: true}
  exclusion_rules:
    - {field: pb,                op: lt, threshold: 1,  label: "市净率<1"}
    - {field: year_left,        op: lt, threshold: 1,  label: "剩余年限<1年"}
    - {field: curr_iss_amt,     op: lt, threshold: 1,  label: "剩余规模<1亿"}
    - {field: curr_iss_amt,     op: gt, threshold: 20, label: "剩余规模>20亿"}
    - {field: convert_amt_ratio,op: gt, threshold: 20, label: "转债市占比>20%"}
    - {field: sprice,           op: lt, threshold: 5,  label: "正股<5元"}
    - {field: convert_value,    op: gt, threshold: 127,label: "转股价值>127"}
  excluded_redeem_icons: ["R", "O", "B"]
  redeem_safe_days: 2
  min_listing_days: 3
  excluded_bond_codes:
    - "118027.SH"  # 宏图转债
    - "110092.SH"  # 三房转债
    - "110081.SH"  # 闻泰转债
    - "128119.SZ"  # 龙大转债
    - "123157.SZ"  # 科蓝转债
    - "110093.SH"  # 神马转债
    - "127061.SZ"
state_path: data_state/cb_three_low_state.json
```

## 状态结构（cb_three_low_state.json）
```json
{
  "strategy": "cb_three_low",
  "last_run_date": "2026-08-05",
  "portfolio_nav": 1.0234,
  "initial_nav": 1.0,
  "target_count": 10,
  "hold_tolerance": 5,
  "updated_at": "2026-08-05 15:35:00",
  "holdings_history": [
    {
      "date": "2026-08-05",
      "holdings": [{"code":"128xxx","name":"..","price":121.0,"rank":1}, "...10只"],
      "nav": 1.0234, "prev_nav": 1.0200, "daily_return": 0.0033,
      "selection": [{"code","name","price","dblow","premium_rt","curr_iss_amt","total_score","rank","selected"}, "...keep_pool"]
    }
  ]
}
```
> `prev_holdings` 不单独存——下一条 entry 的 `daily_return` 用上一条 entry 的 `holdings`（含 T-1 收盘价）对比当日快照 T 收盘价算出。

## 邮件内容（照搬 etf 版式）
- 标题：`可转债三低轮动日报 {date}`
- 次日持仓（10 只表：名称/代码/价格/排名）
- 组合净值 / 累计收益 / 最大回撤 / 当前回撤（A 股配色：涨红跌绿）
- 三低排名（keep_pool 表：名称/代码/价格/双低/溢价率/规模/得分/排名，选中的 10 只高亮）
- 净值曲线图（CID 内嵌）
- 历史持仓（近 20 日：日期/净值/日收益/持仓只数）
- 规则说明脚注

## GitHub Actions（cb_three_low.yml）
- `cron: "30 7 * * 1-5"`（UTC 07:30 = 北京 15:30，A股收盘后）
- 依赖：`requests pyyaml pandas pycryptodome matplotlib`（去掉 akshare；CB 数据全来自集思录）
- secrets：`JISILU_USERNAME/PASSWORD`、`RECEIVER_EMAIL`、`SMTP_USER/SMTP_PASS`
- 流程：`python send_cb_three_low_email.py` → 检测 `data_state/cb_three_low_state.json` 变化 → commit + push

## 测试（无网络，tests/test_cb_three_low.py）
- `filter_cb`：ST / 强赎 icon / 各排除规则分别命中
- `three_low_strategy` 打分：确定性输入 → 排名正确，同分按双低升序
- `apply_tolerance`：保留已持有 + 补仓 + 换手三种情形
- `compute_portfolio_return`：等权均值正确，缺失价按 0 收益兜底
- `run_strategy`：首次运行（nav=1.0, top10）+ 第二次运行（净值更新 + tolerance 生效），mock `fetch_cb_list`/`fetch_redeem_list`
- `compute_drawdown_stats` + `save/load` roundtrip + 配置读取

## 集成风险与验证
- **cb_list_new 能否用 jl 的 cookie 访问**：jl 与 v2 同一套 AES 登录，cookie 应通用。实现时**优先本地跑一次 `fetch_cb_list` 确认返回 >30 条**（v2 有 ≤30 视为未登录的校验）。
- **cb_list `price` 收盘后是否为当日收盘价**：用 `last_dt` 校验 == 当日，否则告警。
- 持仓中某只当日无价（停牌/退市）：按 0 收益兜底 + 日志告警，不中断。

## 明确不做
- 不回填历史净值
- 不建模盘中止盈/回落
- 不接 QMT 实盘
- 不计交易成本/手续费（与 etf 版一致）
