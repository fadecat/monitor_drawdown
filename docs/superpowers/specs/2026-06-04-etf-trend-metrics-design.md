# ETF Trend Metrics Design

## Goal

在现有 ETF.com.cn 搜索与 K 线抓取链路已经稳定的前提下，新增一层独立、可测试、可复核的趋势指标分析模块，用统一口径计算以下 3 项研究指标：

- `偏离度`
- `综合趋势`
- `转变日`

本期目标不是把指标直接接入主监控流程，而是先形成一套稳定、可落盘、可拿截图做误差对比的第一版研究口径。

## Confirmed Scope

本期会完成：

1. 新增一个独立指标模块，对标准化 K 线序列做趋势分析
2. 基于真实 ETF.com.cn K 线计算 `bias20_raw`、`bias20`、`direction5`
3. 生成四象限 `综合趋势` 标签
4. 生成“连续 2 个交易日确认”的 `转变日`
5. 将逐日分析结果与最新摘要写入本地产物
6. 预留人工 benchmark 对比入口，用于后续和截图结果做误差验证
7. 新增确定性的单元测试，覆盖指标计算与状态切换逻辑

## Explicit Non-Goals

本期不会：

- 修改 `monitor_drawdown.py` 的主告警流程
- 做 OCR、自动读图或自动从截图提取基准值
- 做前端页面、图表页面或浏览器展示
- 做参数可配置化
- 并行计算多套均线窗口
- 引入更复杂的趋势评分、打分卡或机器学习模型
- 混入 TickFlow、AkShare 作为本研究脚本的趋势数据源

## Confirmed Metric Definitions

### 1. 偏离度

第一版 `偏离度` 口径固定为“价格相对 20 日均线的平滑偏离”。

定义如下：

- `ma20[t] = close` 的 20 日简单移动平均
- `bias20_raw[t] = close[t] / ma20[t] - 1`
- `bias20[t] = MA5(bias20_raw)[t]`

解释：

- `bias20_raw` 是原始偏离率
- `bias20` 是对 `bias20_raw` 再做一次 5 日简单平滑后的研究主指标

后续和截图做误差对比时，默认对比的是 `bias20`，不是 `bias20_raw`。

### 2. 综合趋势

第一版 `综合趋势` 由两个维度共同决定：

- 位置：`bias20` 在 `0` 上方还是下方
- 方向：`direction5[t] = bias20[t] - bias20[t-5]`

方向判断规则固定为：

- `direction5 > 0` 视为上升
- `direction5 <= 0` 视为下降

四象限状态标签固定为：

- `bias20 > 0` 且 `direction5 > 0` -> `强势上行`
- `bias20 > 0` 且 `direction5 <= 0` -> `强势回落`
- `bias20 <= 0` 且 `direction5 > 0` -> `弱势修复`
- `bias20 <= 0` 且 `direction5 <= 0` -> `弱势下行`

### 3. 转变日

`转变日` 定义为“综合趋势状态切换后，被连续 2 个交易日确认成立时的第一个新状态日”。

确认规则固定为：

1. 先按每天的 `trend_state` 生成状态序列
2. 如果某一天状态和前一有效状态不同，则这一天记为“候选转变日”
3. 只有下一交易日状态仍然等于该新状态，才确认这次转变成立
4. 一旦确认：
   - 当天行的 `transition_confirmed = true`
   - `transition_date` 记为“候选转变日”
5. 如果候选后的下一交易日又切回旧状态，或切到第三种状态，则本次候选作废
6. 同一段连续状态只确认一次，不重复记转变日

例子：

- `2026-06-01` -> `强势回落`
- `2026-06-02` -> `弱势修复`
- `2026-06-03` -> `弱势修复`

则 `2026-06-02` 为本次确认后的 `transition_date`。

## Warm-Up Rules

由于指标链条是逐层依赖的，前期数据不足时允许字段为空。

按当前口径：

- `ma20` 至少需要 `20` 个交易日
- `bias20` 还需要再多 `4` 个交易日
- `direction5` 还需要再多 `5` 个交易日

因此最早能够得到完整 `trend_state` 的位置，大约在第 `29` 个交易日附近。

在暖机期内：

- `ma20`、`bias20_raw`、`bias20`、`direction5` 允许为空
- `trend_state` 允许为空
- 不进行 `转变日` 判断

这不是异常，而是设计预期。

## Implementation Shape

采用“独立指标模块 + 现有脚本调用”的结构。

### New Module

新增：

- `etf_trend_analysis.py`

职责：

- 只负责趋势指标计算
- 不负责关键词搜索
- 不负责网络请求
- 不负责 ETF / 指数候选解析

输入：

- 升序标准化 K 线序列：`[{date, close}]`

输出：

- 完整逐日分析结果
- 最新一日摘要

### Existing Entry Script

修改：

- `inspect_etf_trend_sources.py`

职责保持为：

1. `keyword -> 候选 -> 主标的`
2. 从 ETF.com.cn 拉取真实 K 线
3. 把标准化后的序列交给 `etf_trend_analysis.py`
4. 将分析结果落盘到 `.test_artifacts/etf_trend_sources`

### Main Monitoring Flow

`monitor_drawdown.py` 本期不接入这些新指标。

原因：

- 当前仍处于口径探索和截图对比阶段
- 过早并入主监控流程会把试验逻辑和生产告警逻辑耦合在一起

## Module API

`etf_trend_analysis.py` 第一版只暴露 2 个对外函数：

### `analyze_trend_series(records: list[dict[str, Any]]) -> dict[str, Any]`

输入：

- 升序 `[{date, close}]`

输出包含：

- `records`: 带全部中间列和最终标签的逐日序列
- `latest_transition_date`
- `latest_valid_state`
- `latest_valid_date`

### `build_latest_trend_snapshot(analysis: dict[str, Any]) -> dict[str, Any]`

输入：

- `analyze_trend_series` 的结果

输出：

- 只保留最新一日分析结论，供汇总文件使用

## Daily Output Fields

每个交易日保留以下字段：

- `date`
- `close`
- `ma20`
- `bias20_raw`
- `bias20`
- `direction5`
- `trend_state`
- `state_candidate_changed`
- `transition_confirmed`
- `transition_date`

字段含义：

- `state_candidate_changed`: 当天相对前一有效状态是否发生了候选切换
- `transition_confirmed`: 该候选是否在下一交易日被确认成立
- `transition_date`: 被确认的“第一个新状态日”；无确认则为 `null`

## Artifact Layout

继续沿用现有目录：

- `.test_artifacts/etf_trend_sources/`

本期新增以下产物。

### 1. `series_analysis/<kind>_<code>.json`

作用：

- 保存逐日分析序列
- 保留全部中间列，方便后续和截图逐项核对误差

示例：

```json
[
  {
    "date": "2026-06-01",
    "close": 1.0234,
    "ma20": 1.0112,
    "bias20_raw": 0.012064,
    "bias20": 0.008531,
    "direction5": -0.001923,
    "trend_state": "强势回落",
    "state_candidate_changed": false,
    "transition_confirmed": false,
    "transition_date": null
  }
]
```

### 2. `trend_metrics_summary.json`

作用：

- 每个标的只保留最新快照

固定字段：

- `label`
- `selected_primary`
- `latest_date`
- `close`
- `bias20_raw`
- `bias20`
- `direction5`
- `trend_state`
- `latest_transition_date`

### 3. `summary.md`

在现有解析与 K 线汇总基础上，追加简短趋势摘要：

- `selected=...`
- `trend=...`
- `bias20=...`
- `transition=...`

## Manual Benchmark Comparison

本期不做 OCR，也不自动读图。

为了后续和截图做误差验证，增加一个可选人工 benchmark 文件入口：

- `manual_trend_benchmarks.json`

固定结构：

```json
[
  {
    "label": "煤炭ETF",
    "as_of_date": "2026-06-04",
    "expected_bias20": 0.0248,
    "expected_trend_state": "强势回落",
    "expected_transition_date": "2026-05-27"
  }
]
```

如果该文件存在，脚本额外输出：

- `trend_benchmark_diff.json`

对比只做三项：

1. `bias20` 数值误差
2. `trend_state` 是否一致
3. `transition_date` 是否一致

这能把“截图口径验证”与“主分析逻辑”解耦，避免为了做人工对照而污染算法主流程。

## Testing Strategy

新增：

- `tests/test_etf_trend_analysis.py`

测试必须完全使用本地构造数据，不依赖实时网络。

第一版至少覆盖以下行为：

1. `ma20 / bias20_raw / bias20 / direction5` 的基础数值计算
2. 暖机期字段为空，不提前产出 `trend_state`
3. 四象限状态分类正确
4. 状态切换后连续 2 天保持时，正确确认 `transition_date`
5. 候选切换后又反转时，不误报 `transition_date`

最少测试样例：

- 单调上涨序列 -> 最终应为 `强势上行`
- 负偏离但修复中的序列 -> 最终应为 `弱势修复`
- 切换后连续两天保持 -> 应确认 `transition_date`
- 切换一天后打回原状态 -> 不确认 `transition_date`
- 数据不足 29 天 -> 只出部分中间列，不出最终状态

## Error Handling

本期分析模块面对异常输入时应保持保守：

- 空序列 -> 返回空分析结果，不抛业务外异常
- 缺失 `date` / `close` 的行 -> 在进入分析前过滤掉
- 非数值 `close` -> 在进入分析前过滤掉
- 序列长度不足 -> 返回带暖机空字段的结果，而不是报错

`inspect_etf_trend_sources.py` 只负责把分析失败记为显式错误，不应悄悄吞掉指标计算异常。

## Why This Shape

选择独立模块而不是继续把逻辑堆进 `inspect_etf_trend_sources.py`，理由是：

- 指标口径仍在探索期，后续很可能要和截图反复比对
- 单独模块更容易写确定性测试
- 单独模块更容易替换公式或补充中间列
- 不会把“搜索解析”和“趋势计算”混成一个大脚本

## Acceptance Criteria

本期完成后，应满足：

1. 任何已成功拉到真实 K 线的标的，都能产出逐日趋势分析序列
2. 汇总文件能给出每个标的最新的 `bias20`、`trend_state`、最近一次 `transition_date`
3. 单元测试能稳定覆盖暖机、趋势分类、转变日确认三类核心规则
4. 后续只需手工录入截图中的对照值，就可以生成算法口径与截图口径的误差文件

## Deferred Work

明确延后到后续阶段的内容：

- 参数外置到配置文件
- 计算多套 `MA20/60/120` 偏离度并比较
- 更复杂的趋势评分或综合打分
- 自动从截图识别 benchmark
- 直接将该指标链路接入 `monitor_drawdown.py`
