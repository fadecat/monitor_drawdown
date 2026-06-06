# ETF 轮动策略 V3 / V3.1 研究交接

更新时间：`2026-06-06`

---

## 1. 这份文档解决什么问题

这份文档是本轮 V3 / V3.1 研究的阶段性交接，目标不是介绍项目背景，而是把下面几件事固定下来：

1. 当前已经落地了哪些实验版本
2. 每个版本到底改了哪一条规则
3. 回测结果分别如何
4. 已经验证清楚了哪些结论
5. 下一步最值得继续研究的方向是什么

一句话概括：

**V3 证明了“横截面中位数短期确认”会带来结构性偏差；V3.1 证明了加绝对底线只能部分修复弱市保护，不能解决 2025 年的问题。**

---

## 2. 当前分支与主要文件

本轮研究代码位于分支：

- `feat/etf-rotation-v3-research-handoff`

主要文件：

- V3 策略：[etf_rotation_v3_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/etf_rotation_v3_strategy.py:1)
- V3 运行器：[run_etf_rotation_v3_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/run_etf_rotation_v3_strategy.py:1)
- V3 回测：[backtest_etf_rotation_v3_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/backtest_etf_rotation_v3_strategy.py:1)
- V3 配置：[etf_rotation_v3_config.yaml](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/etf_rotation_v3_config.yaml:1)
- V3 测试：
  - [tests/test_etf_rotation_v3_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/tests/test_etf_rotation_v3_strategy.py:1)
  - [tests/test_run_etf_rotation_v3_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/tests/test_run_etf_rotation_v3_strategy.py:1)
  - [tests/test_backtest_etf_rotation_v3_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/tests/test_backtest_etf_rotation_v3_strategy.py:1)

- V3.1 策略：[etf_rotation_v3_1_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/etf_rotation_v3_1_strategy.py:1)
- V3.1 运行器：[run_etf_rotation_v3_1_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/run_etf_rotation_v3_1_strategy.py:1)
- V3.1 回测：[backtest_etf_rotation_v3_1_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/backtest_etf_rotation_v3_1_strategy.py:1)
- V3.1 配置：[etf_rotation_v3_1_config.yaml](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/etf_rotation_v3_1_config.yaml:1)
- V3.1 测试：
  - [tests/test_etf_rotation_v3_1_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/tests/test_etf_rotation_v3_1_strategy.py:1)
  - [tests/test_run_etf_rotation_v3_1_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/tests/test_run_etf_rotation_v3_1_strategy.py:1)
  - [tests/test_backtest_etf_rotation_v3_1_strategy.py](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/tests/test_backtest_etf_rotation_v3_1_strategy.py:1)

相关既有文档：

- V2 决策文档：[docs/etf_rotation_v2_stage1_decisions.md](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/docs/etf_rotation_v2_stage1_decisions.md:1)
- V1 -> V2 对比文档：[docs/etf_rotation_v1_vs_v2_analysis.md](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/docs/etf_rotation_v1_vs_v2_analysis.md:1)

---

## 3. 当前统一不变的策略骨架

V2、V3、V3.1 这几版有一套共同骨架，下面这些内容当前都没有改：

- 中期门槛：`score_25 > 0`
- 排名方式：按 `score_25` 从高到低
- 持仓方式：只持有 `Top1`
- 执行时序：`T` 日收盘信号，`T+1` 持有
- 防守逻辑：风险资产候选池为空时切 `511880`

因此，本轮讨论聚焦的不是“大框架”，而是：

**短期确认规则应该如何定义。**

---

## 4. 三个版本的规则差异

### 4.1 V2

短期确认：

- `return_10d > 0`

含义：

- 过去 10 个交易日必须上涨，才允许参与排名

优点：

- 有明确的绝对保护线
- 整体下跌时会自动把风险资产全部踢出

缺点：

- 容易错杀“中期趋势仍然很好，但短期有小回踩”的标的

### 4.2 V3

短期确认：

- `return_10d >= 当日 score_25 > 0 候选的 return_10d 中位数`

含义：

- 最近 10 天不要求必须上涨
- 只要求不显著弱于当天其他中期合格的风险资产

初衷：

- 解决 V2 在强势市场回踩阶段过早切防守的问题

### 4.3 V3.1

短期确认：

- `return_10d >= 当日 score_25 > 0 候选的 return_10d 中位数`
- 且 `return_10d >= -3%`

含义：

- 在 V3 的相对确认上，再补回一条绝对底线

初衷：

- 先只验证一个变量：绝对底线能不能把 V3 的弱市保护修回来

---

## 5. 回测结果对比

本次对比使用同一份真实数据缓存、同一标的池、同一交易区间。

摘要文件：

- V2 摘要：[.test_artifacts/etf_rotation_v2_backtest/backtest_summary.md](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/.test_artifacts/etf_rotation_v2_backtest/backtest_summary.md:1)
- V3 摘要：[.test_artifacts/etf_rotation_v3_backtest/backtest_summary.md](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/.test_artifacts/etf_rotation_v3_backtest/backtest_summary.md:1)
- V3.1 摘要：[.test_artifacts/etf_rotation_v3_1_backtest/backtest_summary.md](/D:/gitub_codes/monitor_drawdown/.worktrees/etf-rotation-v2/.test_artifacts/etf_rotation_v3_1_backtest/backtest_summary.md:1)

### 5.1 全周期指标

| 指标 | V2 | V3 | V3.1 |
| --- | ---: | ---: | ---: |
| 最终净值 | 38.4813 | 14.2260 | 19.9617 |
| 总收益 | 3748.13% | 1322.60% | 1896.17% |
| 年化收益 | 35.55% | 24.76% | 28.34% |
| 最大回撤 | -21.60% | -30.04% | -27.43% |
| 交易次数 | 466 | 562 | 564 |
| 胜率 | 57.94% | 50.53% | 51.95% |
| 防守天数 | 364 | 129 | 175 |

### 5.2 关键年份

| 年份 | V2 | V3 | V3.1 |
| --- | ---: | ---: | ---: |
| 2018 | 5.36% | -8.13% | -1.69% |
| 2020 | 29.11% | 22.90% | 28.42% |
| 2024 | 8.75% | 16.48% | 19.88% |
| 2025 | 50.19% | 39.34% | 39.34% |
| 2026 | 23.73% | 27.03% | 26.93% |

### 5.3 结论

- V3 相比 V2 明显失败
- V3.1 相比 V3 明显改善
- 但 V3.1 仍然明显弱于 V2
- 特别重要的是：
  - **V3.1 没有修复 2025**
  - `2025` 年 V3 和 V3.1 收益完全一样，都是 `39.34%`

这说明：

**`-3%` 绝对底线只能部分修复 V3 的问题，但不是 2025 差异的根因。**

---

## 6. 已经验证清楚的两条结论

### 6.1 结论一：V3 会削弱弱市保护

这个结论已经确认，不再是假设。

原因很直接：

- 当天所有 `score_25 > 0` 标的都在跌时
- 横截面中位数本身也会是负数
- V3 仍然会放行“跌得少一点”的风险资产
- 结果是本该切防守时，继续持有风险资产

这就是 V3 相比 V2：

- 防守天数 `364 -> 129`
- 回撤 `-21.60% -> -30.04%`

的主要原因之一。

### 6.2 结论二：2025 的主问题不在排名层，在过滤层

我们已经把 `2025` 年 V2 与 V3 的风险资产差异日拆开。

结果：

- `27` 天存在“V2 和 V3 都持风险资产，但持仓不同”
- 这 `27` 天里：
  - `0` 天是“候选池相同，只是排序不同”
  - `27` 天全都是“候选池不同”

也就是说：

**2025 的主问题不是 score 排名错了，而是过滤规则先把候选池改坏了。**

---

## 7. 2025 年 27 个差异日的归因结论

### 7.1 差异日总体特征

在 `2025` 年：

- V2 和 V3 相同持仓：`204` 天
- V2 防守 / V3 风险：`12` 天
- 两者都持风险资产但标的不同：`27` 天

真正决定 `2025` 相对强弱的，不是那 `12` 天防守差异，而是这 `27` 天风险资产差异。

### 7.2 27 天里到底发生了什么

统计结果：

- V3 主要不是“多放进来一个新标的”
- 而是“把 V2 原本会保留的标的踢掉了”

出现频次：

- `V3新增` 只发生 `3` 天
- `V3缺少` 发生 `24` 天

被 V3 踢掉最多的标的：

- `黄金ETF易方达`：`15` 天
- `国证价值100指数`：`7` 天
- `国证石油天然气指数`：`7` 天
- `纳指ETF国泰`：`2` 天
- `国证成长100指数`：`1` 天

### 7.3 这些被踢掉的标的是边缘标的吗

不是。

相反，很多被 V3 踢掉的标的，在当天全市场 `score_25` 排名里非常靠前，甚至就是 `rank1`。

典型模式：

- `黄金ETF易方达` 当天是 `score_25 rank1`
- 但因为 `return_10d` 低于横截面中位数，被 V3 过滤掉
- 然后 V3 只能去持有 `rank2` 或更后面的标的

这说明问题不是：

- 某个标的本身有 bug
- 或者排序公式错了

而是：

**横截面中位数短期确认，会系统性错杀“中期最强，但短期涨得不够快”的标的。**

### 7.4 这 27 天谁更赚钱

这 `27` 天逐日比较结果：

- V2 胜：`16` 天
- V3 胜：`11` 天

单日收益简单求和：

- V2：`+6.51%`
- V3：`-3.79%`

这就是 `2025` 年 V2 比 V3 高出一截的核心来源之一。

---

## 8. 过滤规则到底是在歧视什么

这是本轮研究最重要的判断之一。

### 8.1 不是“只对某几个特定标的有问题”

如果只是某几个特定标的有问题，现象应该是：

- 只有 1 到 2 个标的总出问题
- 其他标的几乎不受影响

但真实情况不是这样。

`2025` 年里，`V2有资格但V3没有资格` 的次数：

- 国证价值100指数：`53`
- 国证石油天然气指数：`40`
- 纳指ETF国泰：`33`
- 黄金ETF易方达：`33`
- 国证成长100指数：`10`

这说明：

- 问题不是单个品种特有
- 而是规则本身存在偏置

### 8.2 也不能简单概括成“只歧视低波动”

确实，低波动品种受害更明显。

比如：

- `黄金ETF易方达`
- `国证价值100指数`

都属于更容易出现“中期趋势很好，但 10 日涨幅没那么炸”的标的。

但这不是全部。

`国证石油天然气指数`、`纳指ETF国泰` 也有大量 `V2通过 / V3不过` 的情况。

所以更准确的说法是：

**V3 不是单纯歧视“低波动”，而是系统性打压“中期趋势好、短期也在涨、但涨得不够快”的标的。**

低波动品种只是这个偏置里最显眼的一类受害者。

### 8.3 问题的本质

V3 比较的是：

- 原始 `return_10d`

而不是：

- 按波动调整后的短期强度
- 或者资产自身相对历史的短期状态

这会带来一个结构性问题：

- 波动更大的资产，短期更容易出现更高的绝对涨幅
- 波动更小、走势更稳的资产，即使中期趋势很健康，也容易在横截面比较中落后

所以当前最该被质疑的，不是某个阈值数值，而是：

**“拿原始 10 日涨幅做横截面比较”这个基准本身。**

---

## 9. V3.1 告诉了我们什么

V3.1 只做了一件事：

- 在 V3 上增加 `return_10d >= -3%`

这个实验的价值不在于它是否最终可用，而在于它帮助排除了一个方向。

验证结果：

- V3.1 比 V3 好
- 说明“绝对底线”确实能部分修复弱市保护
- 但 V3.1 在 `2025` 与 V3 完全一样

已经确认：

- `2025` 年 V3 与 V3.1 的持仓没有一天不同

这说明：

- `-3%` 底线没有触发到 2025 的核心差异日
- 所以 `2025` 的问题不是“跌太多没拦住”
- 而是“明明还在涨、或者只是涨得没那么快，却被横截面比较错杀”

这使下一步方向变得很清楚：

**V4 如果要继续研究，重点不该是再调绝对底线参数，而该是替换短期比较基准。**

---

## 10. 当前最值得继续研究的方向

### 10.1 不建议优先继续做的事情

当前不建议优先做：

- 继续细调 `short_confirmation_absolute_floor`
- 直接去修 score 排名层
- 针对某几个标的做特调

原因：

- V3.1 已经证明绝对底线不是 2025 的主因
- 2025 的 `27` 个差异日里没有“同池重排”
- 对单个标的做修补容易过拟合

### 10.2 建议优先继续做的事情

V4 更合理的方向是：

- 不再直接比较原始 `return_10d`
- 改成一个更公平的短期确认基准

候选方向可以考虑：

1. 波动调整后的短期收益
2. 资产自身相对历史的短期状态
3. 横截面排序不再用绝对收益，而用标准化收益

当前不在这份文档里拍板 V4 规则，只固定一个共识：

**下一轮研究重点是“替换比较基准”，不是“继续调当前基准的参数”。**

---

## 11. 本地复现实验命令

### 11.1 运行 V3 定向测试

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_etf_rotation_v3_strategy.py tests/test_run_etf_rotation_v3_strategy.py tests/test_backtest_etf_rotation_v3_strategy.py -q
```

### 11.2 运行 V3.1 定向测试

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_etf_rotation_v3_1_strategy.py tests/test_run_etf_rotation_v3_1_strategy.py tests/test_backtest_etf_rotation_v3_1_strategy.py -q
```

### 11.3 运行回测

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python backtest_etf_rotation_v2_strategy.py
python backtest_etf_rotation_v3_strategy.py
python backtest_etf_rotation_v3_1_strategy.py
```

### 11.4 当前不建议使用的验证口径

```powershell
python -m pytest -q
```

原因不是 V3 / V3.1 有问题，而是当前仓库存在大量既有失败和权限问题：

- `tmp_path` 相关权限错误
- `prototype_fx_chart` 相关既有失败
- `inspect_etf_trend_sources` 相关既有失败

所以本轮研究只使用 V3 / V3.1 的定向测试作为验收口径。

---

## 12. 交接结论

到当前为止，已经可以明确说：

1. V3 这条“横截面中位数短期确认”不适合作为最终方案直接使用
2. V3.1 证明了绝对底线有一定价值，但不是 2025 问题的核心修复手段
3. 2025 年的主问题不在排名层，而在过滤层
4. 过滤层的问题不是某几个特定标的有 bug，而是比较基准本身存在结构性偏置
5. 下一步最值得研究的，是替换短期确认的比较基准

如果回家继续研究，最建议的起点不是回头再调 V3.1 参数，而是直接开始设计 V4 的候选过滤层方案。
