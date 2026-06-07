# ETF 轮动 V2 策略计算逻辑说明

这份文档解释 V2 每日邮件和回测里的核心变量是怎么产生的，目标是让看到邮件的人能理解并复现这套信号逻辑。

V2 的核心思想不是“找最近涨幅最大的标的”，而是：

```text
先判断风险资产里有没有涨得快、涨得稳、短期没有转弱的标的。
如果有，就只持有 score_25 最高的 Top1。
如果没有，就切换到防守资产 511880。
```

当前 V2 只做“入场筛选 + 防守切换”，不包含固定止损、ATR 跟踪止损、RSI 过滤、手续费、滑点和换仓缓冲。

## 资产池

当前配置文件是 `etf_rotation_v2_config.yaml`。

风险资产池：

| 标的 | 代码 | 类型 | 角色 |
|---|---|---|---|
| 国证成长100指数 | `980080.CN` | index | 风险资产 |
| 国证价值100指数 | `980081.CNI` | index | 风险资产 |
| 国证石油天然气指数 | `399439.SZ` | index | 风险资产 |
| 纳指ETF国泰 | `NDX` | index | 风险资产 |
| 黄金ETF易方达 | `159934` | etf | 风险资产 |

防守资产：

| 标的 | 代码 | 类型 | 角色 |
|---|---|---|---|
| 银华日利ETF | `511880` | etf | 防守资产 |

防守资产不参与风险资产排名。它只在所有风险资产都不合格时接管持仓。

其中“纳指ETF国泰”使用 `NDX` 指数作为风险暴露代理。这样做是为了避免 QDII ETF 净值 T-2 更新拖慢统一信号日；实盘执行时仍可参考对应场内 ETF 完成交易。

## 数据日期

ETF 日轮动会遇到数据滞后问题，例如：

- 国内 ETF 净值通常是 T-1 更新；
- 跨境 ETF 可能是 T-2 更新；
- 指数和 ETF 净值的更新日期也可能不同。

所以 V2 不混用各自最新日期，而是先统一信号日：

```text
signal_date = 所有标的 latest_date 的最小值
```

也就是说，如果某一天 A 股标的已经更新到 2026-06-05，但纳指ETF只更新到 2026-06-04，那么本次信号统一使用 2026-06-04 及以前的数据。

对应代码逻辑：

- `run_etf_rotation_v2_strategy.build_data_status`
- `run_etf_rotation_v2_strategy.trim_series_records_to_signal_date`

大白话：

```text
宁可所有标的都退回同一天，也不让一部分标的多看一天数据。
```

## 参数

当前 V2 策略参数：

| 参数 | 当前值 | 含义 |
|---|---:|---|
| `lookback_days` | 25 | 用最近 25 个收盘价判断中期趋势质量 |
| `short_lookback_days` | 10 | 用最近 10 个交易日收益判断短期是否转弱 |
| `annualization_days` | 250 | 趋势斜率年化时使用 250 个交易日 |
| `weight_start` | 1.0 | 25 日趋势窗口第一天的权重 |
| `weight_end` | 2.0 | 25 日趋势窗口最后一天的权重 |
| `holdings_num` | 1 | 只持有排名第 1 的风险资产 |

## return_25 与 annualized_return_25

这里最容易混淆。

当前 V2 代码里没有直接用“简单 25 日涨幅”作为排名指标，也没有在输出里保存 `return_25` 字段。

如果有人口头说 `return_25`，大白话上可以理解成“最近 25 日窗口的中期表现”。但 V2 真正用于 `score_25` 的不是：

```text
简单 return_25 = close[t] / close[t-25] - 1
```

而是：

```text
最近 25 个收盘价的加权对数趋势回归
```

也就是说，V2 关心的不是“头尾两个价格相差多少”，而是“这 25 个点整体是不是沿着一条稳定向上的趋势线在走”。

邮件里的“年化收益”对应代码字段：

```text
annualized_return_25
```

它不是简单 25 日收益直接年化，而是由 25 日趋势回归斜率年化得到。

## 25 日趋势回归

对每个风险资产，在统一信号日 `t`，取最近 25 个有效收盘价：

```text
close[0], close[1], ..., close[24]
```

其中：

- `close[24]` 是 `signal_date` 当天或之前的最新收盘价；
- `close[0]` 是这个 25 日窗口里最早的收盘价。

先取对数：

```text
y[i] = ln(close[i])
x[i] = i
i = 0, 1, ..., 24
```

再设置线性递增权重：

```text
weight[0]  = 1.0
weight[24] = 2.0
```

中间权重从 1.0 到 2.0 均匀递增。

大白话：

```text
越新的价格越重要，但旧价格不会被完全忽略。
```

然后对 `y = slope * x + intercept` 做加权一元线性回归。

对应代码：

```text
etf_rotation_v2_strategy.calculate_weighted_trend_metrics
```

## annualized_return_25

回归得到 `slope` 后，计算趋势年化收益：

```text
annualized_return_25 = exp(slope * 250) - 1
```

大白话：

```text
如果最近 25 个交易日的趋势斜率持续一年，大概对应多少年化收益。
```

注意：

- `slope > 0` 时，`annualized_return_25` 为正；
- `slope < 0` 时，`annualized_return_25` 为负；
- 它来自趋势线斜率，不等于简单 25 日收益。

## r_squared_25

`r_squared_25` 表示最近 25 日价格走势和趋势线的贴合程度。

公式：

```text
ss_res = sum(weight[i] * (y[i] - y_hat[i])^2)
ss_tot = sum(weight[i] * (y[i] - mean(y))^2)
r_squared_25 = 1 - ss_res / ss_tot
```

其中：

- `y[i]` 是实际对数价格；
- `y_hat[i]` 是回归趋势线上的拟合值；
- `weight[i]` 是从 1.0 到 2.0 递增的权重。

大白话：

```text
R² 越接近 1，说明这 25 日走势越像一条顺滑趋势线。
R² 越低，说明走势越杂乱，即使涨了也不稳定。
```

边界处理：

- 如果价格完全横盘，`ss_tot <= 0`，则 `r_squared_25 = 0`；
- 如果算出来的 R² 不是有限数，或小于 0，也按 0 处理。

## score_25

`score_25` 是 V2 的核心排名分数。

公式：

```text
score_25 = annualized_return_25 * r_squared_25
```

大白话：

```text
score_25 同时奖励“涨得快”和“涨得稳”。
```

几个典型情况：

| 情况 | annualized_return_25 | r_squared_25 | score_25 | 解释 |
|---|---:|---:|---:|---|
| 稳定上涨 | 正 | 高 | 高 | 强趋势 |
| 暴涨暴跌 | 正 | 低 | 被打折 | 涨得不稳 |
| 稳定下跌 | 负 | 高 | 负 | 稳定走弱 |
| 横盘 | 接近 0 | 低或 0 | 接近 0 | 没有趋势 |

V2 第一层过滤要求：

```text
score_25 > 0
```

如果 `score_25 <= 0`，该标的不合格，拒绝原因是：

```text
score_25_not_positive
```

邮件里可以理解为：

```text
中期趋势为负或趋势质量不足。
```

## return_10d

`return_10d` 是短期确认指标。

公式：

```text
return_10d = close[t] / close[t-10] - 1
```

这里的 `t` 是统一信号日对应的最新可用收盘价。

大白话：

```text
最近 10 个交易日还在不在上涨。
```

V2 第二层过滤要求：

```text
return_10d > 0
```

如果 `score_25 > 0`，但 `return_10d <= 0`，该标的不合格，拒绝原因是：

```text
return_10d_not_positive
```

邮件里可以理解为：

```text
中期趋势还可以，但短期已经转弱。
```

## 合格条件

一个风险资产要进入最终排名，必须同时满足：

```text
score_25 > 0
return_10d > 0
```

过滤顺序：

1. 先检查 `score_25 > 0`；
2. 再检查 `return_10d > 0`；
3. 两个条件都通过，才算合格。

如果历史数据不足、价格为空、价格小于等于 0、无法形成有效回归，则该标的不合格，拒绝原因是：

```text
insufficient_history_or_invalid_series
```

## 排名规则

只有合格风险资产才会进入排名。

排序规则：

```text
按 score_25 从高到低排序
如果 score_25 相同，再按 return_10d 从高到低排序
如果还相同，再按标的名称排序
```

对应代码：

```text
etf_rotation_v2_strategy.rank_candidates
```

注意：

```text
return_10d 只作为过滤条件和极少数并列时的辅助排序。
正常情况下，最终 Top1 主要由 score_25 决定。
```

## 选仓逻辑

V2 只持有一个标的：

```text
holdings_num = 1
```

如果至少有一个风险资产合格：

```text
持有 score_25 排名第 1 的风险资产
selection_reason = top_ranked_risk_asset
```

如果没有任何风险资产合格：

```text
持有防守资产：银华日利ETF（511880）
selection_reason = fallback_defensive_asset
```

## 执行时序

V2 使用 T 日收盘信号、T+1 日记账的研究口径。

如果：

```text
signal_date = T
position_date = T+1
```

则：

1. 用 `T` 日及以前的数据计算信号；
2. 决定 `T+1` 持有什么；
3. 回测里用选中标的从 `T` 收盘到 `T+1` 收盘的涨跌幅记为单日收益。

公式：

```text
daily_return = close[T+1] / close[T] - 1
```

这个口径是研究记账口径，不是严格实盘成交模型。当前没有使用开盘价、盘口、滑点、手续费或申赎冲击。

## 输出字段对应关系

邮件和回测文件中常见字段含义如下：

| 字段 | 来源 | 含义 |
|---|---|---|
| `data_date` | runner | 该标的实际用于计算的最新数据日期 |
| `annualized_return_25` | 25 日加权对数趋势回归 | 趋势斜率年化后的收益 |
| `r_squared_25` | 25 日加权对数趋势回归 | 趋势线拟合稳定度 |
| `score_25` | `annualized_return_25 * r_squared_25` | 趋势质量分数 |
| `return_10d` | `close[t] / close[t-10] - 1` | 短期确认收益 |
| `qualified` | 过滤结果 | 是否同时通过 `score_25 > 0` 和 `return_10d > 0` |
| `rejection_reason` | 过滤结果 | 不合格原因 |
| `selection_reason` | 组合决策 | 风险 Top1 入选或防守接管 |

常见拒绝原因：

| rejection_reason | 中文解释 |
|---|---|
| `score_25_not_positive` | 中期趋势分数不为正 |
| `return_10d_not_positive` | 短期 10 日收益不为正 |
| `insufficient_history_or_invalid_series` | 历史数据不足或价格序列无效 |
| `no_signal_date_close` | 信号日没有可用收盘价 |

## 复现步骤

如果要手工复现某一天的 V2 信号，按这个顺序做：

1. 读取配置里的全部风险资产和防守资产。
2. 找到每个标的最新数据日期。
3. 取所有最新数据日期的最小值作为统一 `signal_date`。
4. 每个标的只保留 `signal_date` 及以前的数据。
5. 对每个风险资产取最近 25 个收盘价。
6. 对这 25 个收盘价取对数，做权重从 1.0 到 2.0 的加权线性回归。
7. 计算 `annualized_return_25 = exp(slope * 250) - 1`。
8. 计算加权 `r_squared_25`。
9. 计算 `score_25 = annualized_return_25 * r_squared_25`。
10. 计算 `return_10d = close[t] / close[t-10] - 1`。
11. 只保留 `score_25 > 0` 且 `return_10d > 0` 的风险资产。
12. 对合格风险资产按 `score_25` 从高到低排序。
13. 如果有合格风险资产，选择排名第 1 的标的。
14. 如果没有合格风险资产，选择防守资产 `511880`。

一句话总结：

```text
V2 = 统一信号日 + 25日趋势质量评分 + 10日短期确认 + Top1 集中持仓 + 511880 防守切换。
```
