# 集思录转债等权接入区间收益日报设计

## 背景

当前仓库已经具备一套独立的“跨品种ETF区间收益日报”链路：

- 通过 `.github/workflows/period_return_email.yml` 定时触发
- 读取 `period_return_email_config.yaml`
- 从 ETF.com 获取净值数据
- 计算区间收益率
- 生成近 1 个月收益率走势图和收益率表格
- 发送 HTML 邮件

现需在同一封邮件中加入一个新的非 ETF.com 品种：

- 名称：`集思录转债等权`
- 数据源：`https://www.jisilu.cn/data/cbnew/cb_index/`

同时，当前项目不能依赖另一个本地仓库的数据文件。当前仓库需要自己维护一套集思录 `cb_index` 历史归档，并将该品种与现有 ETF 一起出现在同一张图和同一张表中。

## 目标

在当前仓库中新增一套独立的集思录 `cb_index` 数据归档能力，并将“集思录转债等权”纳入现有收益率日报链路。

最终能力应满足：

- 当前仓库独立维护 `market_temperature_history.json`
- 归档解析集思录页面 `var __data` 中的所有字段
- 将 `price` 统一映射为长期收益率主字段 `index_value`
- 邮件发送前使用“本地多年归档 + 实时页面近一年窗口”的拼接结果
- “集思录转债等权”与现有 ETF 一起出现在同一张近 1 个月收益率图和同一张区间收益率表中

## 非目标

本次不做以下事项：

- 不修改现有回撤监控和估值告警主流程
- 不依赖旧仓库作为运行时数据源
- 不把集思录实时页直接当作唯一长期历史来源
- 不在本次引入最大回撤、波动率、夏普比率等新指标
- 不新增第二封独立的转债日报邮件

## 用户确认的约束

- 当前仓库自己维护 `market_temperature_history.json`
- 集思录实时页因为非会员限制，只能提供最近一年窗口
- 多年历史以已有归档为基础，发送前必须做“归档 + 实时页”拼接
- `price` 要统一映射到 `index_value`
- 新品种要和现有 ETF 混合在同一封邮件、同一张图、同一张表里
- 可直接复用旧仓库的 `cb_index` 归档逻辑，但要在当前仓库补齐遗漏字段解析

## 方案选择

### 方案 A：继续在现有 ETF.com 分析脚本上打补丁

做法：

- 在 `analyze_etf_com_cn_period_returns.py` 中新增对集思录数据的分支判断
- 配置仍然以 `codes` 为主，只对个别 code 特判

优点：

- 初期改动面看起来较小

缺点：

- 现有脚本强依赖 ETF.com 的 `trdDt + adjUnitNav` 结构
- 集思录 `date + index_value` 与 ETF.com 模型不同，继续堆分支会让脚本快速失控
- 后续若再增加其它指数、商品、债券等数据源，会继续恶化

### 方案 B：新增当前仓库自己的集思录归档 + 抽象多数据源收益率模型

做法：

- 在当前仓库落地独立的集思录 `cb_index` 归档模块与 workflow
- 将收益率分析层从“ETF.com 专用”升级为“统一时间序列收益率引擎”
- 不同 source 先转成标准序列，再统一计算区间收益与近 1 个月曲线

优点：

- 归档职责、实时拼接职责、收益率计算职责边界清晰
- 能兼容 ETF 与指数的不同字段口径
- 后续再接别的数据源时扩展成本更低

缺点：

- 需要做一次配置结构升级和分析层重构

### 方案 C：只在邮件发送前实时抓集思录页面，不做当前仓库归档

优点：

- 当前实现量最少

缺点：

- 无法保存每日窗口滚动前的数据
- 无法支持多年区间收益
- 与“当前仓库独立维护归档”的目标冲突

### 最终方案

采用方案 B。

设计原则：

- 归档与邮件发送分离
- 实时页只作为近一年窗口补丁，不作为长期历史唯一来源
- 收益率计算只依赖统一时间序列，不直接依赖某个上游接口字段名

## 总体架构

新增能力拆成三层：

### 1. 归档层

负责：

- 拉取 `https://www.jisilu.cn/data/cbnew/cb_index/`
- 解析 `var __date` 和 `var __data`
- 将所有字段按日期展开为日记录
- 将 `price` 映射为 `index_value`
- 增量合并进本地 `market_temperature_history.json`

这一层不负责收益率计算、画图和邮件发送。

### 2. 数据适配层

负责把不同数据源都转换为统一序列结构：

- `date`
- `value`

统一序列示例：

```json
[
  {"date": "2026-05-28", "value": 4870.231},
  {"date": "2026-05-29", "value": 4892.121}
]
```

映射规则：

- ETF.com：`trdDt -> date`，`adjUnitNav -> value`
- 集思录转债等权：`date -> date`，`index_value -> value`

### 3. 收益率邮件层

负责：

- 读取配置中的目标列表
- 针对不同 `source` 加载统一序列
- 统一计算区间收益率和近 1 个月曲线
- 生成图表 PNG 与表格
- 发送邮件

## 文件边界

### 新增文件

- `cb_index_history.py`
  - 集思录 `cb_index` 页面抓取、解析、合并逻辑

- `refresh_cb_index_history.py`
  - 当前仓库的集思录 `cb_index` 归档入口脚本

- `.github/workflows/refresh_cb_index_history.yml`
  - 独立调度集思录 `cb_index` 归档刷新

- `tests/test_cb_index_history.py`
  - 覆盖页面解析、字段映射、merge 行为

### 复用并改造的文件

- `market_temperature_history.json`
  - 当前仓库自己的初始多年归档底库

- `period_return_email_config.yaml`
  - 从 `codes` 升级为 `targets`

- `analyze_etf_com_cn_period_returns.py`
  - 不再只服务 ETF.com；建议演进为通用收益率分析模块
  - 可以保留文件名先做内部重构，或拆出通用模块后由旧文件调用

- `preview_period_return_email.py`
  - 读取新配置结构

- `send_period_return_email.py`
  - 读取新配置结构
  - 对集思录标的执行“归档 + 实时页”拼接

- `prototype_period_return_chart.py`
  - 无需理解 source，只继续渲染统一曲线数据

## 配置设计

现有配置：

```yaml
codes:
  - "159934"
  - "159941"
```

升级后配置：

```yaml
targets:
  - id: "159934"
    source: "etf_com_cn"

  - id: "159941"
    source: "etf_com_cn"

  - id: "159259"
    source: "etf_com_cn"

  - id: "159263"
    source: "etf_com_cn"

  - id: "511130"
    source: "etf_com_cn"

  - id: "511380"
    source: "etf_com_cn"

  - id: "cb_equal_weight"
    name: "集思录转债等权"
    source: "jisilu_cb_index"
```

字段含义：

- `id`
  - ETF.com 标的使用基金代码
  - 集思录转债等权使用稳定业务 ID，例如 `cb_equal_weight`

- `name`
  - ETF.com 标的可省略，由接口补齐
  - 非 ETF.com 标的在配置中显式提供

- `source`
  - 决定使用哪个 loader

## 集思录归档字段策略

### 主收益率字段

`price` 必须映射为：

- `index_value`

原因：

- 旧多年历史已经使用 `index_value`
- 多年收益率计算必须依赖单一稳定主字段
- 新增归档不能让主字段从 `index_value` 漂移到 `price` 或 `idx_price`

### 其余字段

`__data` 中的其它字段全部保留归档，至少包含：

- `volume`
- `amount`
- `temperature`
- `count`
- `avg_price`
- `mid_price`
- `mid_convert_value`
- `avg_dblow`
- `premium_temp`
- `avg_premium_rt`
- `mid_premium_rt`
- `avg_ytm_rt`
- `increase_val`
- `increase_rt`
- `turnover_rt`
- `price_90`
- `price_90_100`
- `price_100_110`
- `price_110_120`
- `price_120_130`
- `price_130`
- `increase_rt_90`
- `increase_rt_90_100`
- `increase_rt_100_110`
- `increase_rt_110_120`
- `increase_rt_120_130`
- `increase_rt_130`
- `idx_price`
- `idx_increase_rt`
- `volume_arr`

设计要求：

- 归档尽量保留上游原始字段
- 仅对 `price -> index_value` 做必要标准化
- 如需兼容分析或回看，也可以同时保留原始 `price`
- 收益率计算层只认 `index_value`

## 历史 merge 策略

### 输入

- 现有当前仓库中的 `market_temperature_history.json`
- 实时解析得到的最近一年窗口记录

### merge key

- `date`

### merge 规则

1. 读入本地历史记录
2. 拉取并解析集思录最近一年窗口
3. 按 `date` 建立映射
4. 若日期已存在：
   - 用新记录补充/覆盖同日期字段
   - 保留旧记录中实时页不再提供的历史字段
5. 若日期不存在：
   - 直接新增记录
6. 最终按 `date` 升序写回

### 设计目的

- 保留旧多年历史
- 使用新窗口补齐近一年字段
- 允许同日数据因上游修正而被覆盖
- 避免重复记录

## 归档 workflow 设计

新增：

- `.github/workflows/refresh_cb_index_history.yml`

### 触发方式

- 定时触发
- `workflow_dispatch`

### 职责

1. checkout 仓库
2. setup Python
3. 安装最小依赖
4. 运行 `python refresh_cb_index_history.py`
5. `git add market_temperature_history.json`
6. 若无变化则退出
7. 若有变化则自动 commit 并 push

### 触发频率

由于实时页只有近一年窗口，归档不能太稀疏。建议至少工作日每日运行一次；若希望更稳，可与收益率邮件发送频率保持接近，避免窗口滚动期间遗漏。

本次设计不强行锁死具体 cron，实施时以“晚于日内数据更新、早于长期窗口滚动风险”为准配置。

## 邮件发送前拼接策略

对于 `jisilu_cb_index` 标的，邮件发送前必须执行：

1. 读取当前仓库 `market_temperature_history.json`
2. 再实时抓一次集思录 `cb_index` 页面
3. 对实时窗口数据执行同样的解析与标准化
4. 在内存中按 `date` merge
5. 从 merge 后结果中提取 `date + index_value` 统一序列

原因：

- 归档 workflow 与发邮件 workflow 可能存在时间差
- 即使归档未先跑完，邮件也应尽量反映当天最新值
- 多年历史仍然依赖本地归档

## 多数据源收益率模型

### 统一序列

所有标的最终转为：

- `date`
- `value`

### 统一分析能力

统一序列进入同一套逻辑，产出：

- 近 1 月收益率
- 近 3 月收益率
- 近 6 月收益率
- 近 1 年收益率
- 年初至今收益率
- 近 3 年收益率
- 近 5 年收益率
- 近 10 年收益率
- 成立以来收益率
- 近 1 个月收益率曲线

### 命名补齐

- `etf_com_cn`：继续通过 ETF.com 接口补齐名称
- `jisilu_cb_index`：直接使用配置里的 `name`

## 向后兼容要求

- 现有 ETF 收益率行为保持不变
- 图表与表格模板不改变结构，只增加一个新标的
- SMTP 配置读取不变
- 原独立收益率邮件 workflow 不并回 `monitor.yml`
- 原 ETF 样本缓存、图表生成、预览能力继续可用

## 测试设计

至少新增或更新以下测试：

### 1. 集思录页面解析

- 能正确解析 `var __date`
- 能正确解析 `var __data`
- `price` 正确映射到 `index_value`
- 其它字段按日期展开

### 2. 历史 merge

- 同日期覆盖更新
- 新日期追加
- 旧字段保留
- 最终结果按日期升序

### 3. 多数据源收益率计算

- ETF.com 标的仍能按原口径计算
- `jisilu_cb_index` 标的能基于 `index_value` 计算
- 近 1 月曲线与区间收益率口径一致

### 4. 配置解析

- 新 `targets` 结构可读
- 支持混合 `etf_com_cn` 与 `jisilu_cb_index`
- 去重和空值处理稳定

### 5. 邮件链路

- 混合多 source 的表格可正常生成
- 图表曲线可包含集思录转债等权
- 邮件 HTML 结构不回退

## 实施顺序

推荐按以下顺序落地：

1. 复制并改造旧仓库 `cb_index` 归档逻辑到当前仓库
2. 导入当前项目自己的 `market_temperature_history.json` 初始多年底库
3. 新增 `refresh_cb_index_history.yml` 并打通自动 commit
4. 抽象收益率分析层为统一时间序列模型
5. 升级 `period_return_email_config.yaml` 为 `targets`
6. 接入 `jisilu_cb_index` loader
7. 在邮件发送前加入“归档 + 实时页”拼接
8. 更新预览、发送脚本与测试

## 风险与对应策略

### 风险 1：集思录页面变量结构变动

策略：

- 解析逻辑集中封装
- 用最小 HTML 样本测试锁定结构假设
- 解析失败时明确报错，避免静默空数据

### 风险 2：归档字段口径不一致

策略：

- 强制使用 `index_value` 作为长期主字段
- 实时页和历史归档都走同一标准化逻辑

### 风险 3：配置迁移影响现有 ETF 邮件

策略：

- 先补配置解析测试
- 保持 ETF 标的原行为完全一致

### 风险 4：归档与邮件发送时序错位

策略：

- 发邮件前始终做一次实时页补丁 merge
- 不把归档 workflow 是否先完成作为发送前提

## 结论

本次改造的核心不是“给 ETF 邮件里插入一个特殊品种”，而是把当前收益率日报从“ETF.com 单数据源”升级为“统一时间序列、多数据源收益率日报”。

第一批支持两类 source：

- `etf_com_cn`
- `jisilu_cb_index`

其中“集思录转债等权”通过当前仓库自己的 `market_temperature_history.json` 多年归档，加上发送前实时页近一年窗口拼接，稳定进入现有收益率图表和表格。
