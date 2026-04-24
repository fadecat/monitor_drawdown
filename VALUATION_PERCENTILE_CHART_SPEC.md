# VALUATION_PERCENTILE_CHART_SPEC

> 架构师 ↔ Codex 协作文档。Codex 执行本任务时严格按本文件推进，有任何疑问写到文末"与架构师的问答"区，不要擅自扩展范围。

## 固定调用口令

`请读 VALUATION_PERCENTILE_CHART_SPEC.md 并严格按照执行`

---

## 0. 你（Codex）的第一步：切分支

在开始任何改动前，先在仓库根目录执行：

```bash
git switch -c feat/valuation-percentile-chart
```

后续所有改动都落在这个分支上，不要回到 `main` 或 `feat/equity-bond-chart-prototype`。

---

## 1. 任务目标

替换当前邮件中嵌入的 **股债性价比图（`generate_equity_bond_chart`）**，改为一张 **估值分位走势图**，视觉参考"估值中心 / 中证红利 PE 走势"卡片（架构师已附图在对话中）。

- 产物入口函数（新建，不改旧文件）：`generate_valuation_percentile_chart(target: Dict, output_dir: Path) -> Optional[Path]`
- 产物文件：`{output_dir}/valuation_percentile_{index_code}.png`
- 集成点：`monitor_drawdown.py` main 里填充 `chart_paths` 的那段（当前 ~1995–2012 行），把 `from prototype_equity_bond_chart import generate_equity_bond_chart` 换成新函数导入。同一个 dict key（`index_code`）填入新 PNG 路径。邮件模板层 **不需要** 改。
- 旧文件 `prototype_equity_bond_chart.py` **保留不动**，以便回滚或对照；只是不再被 `monitor_drawdown.py` 调用。

---

## 2. 必须复用的数据函数（禁止新增抓取器）

所有取数必须走下列现有入口。**不允许** 新增 `requests.get` / `akshare` / `tickflow` 调用；也不允许改动这些函数的签名。

| 用途 | 现有函数 | 备注 |
|---|---|---|
| 指数详情（名称、当前 PE/PB 等） | `fetch_index_detail(index_code, url)` | `monitor_drawdown.py` |
| 估值分位 JSON（PE 历史 + 分位切分） | `fetch_index_pe_history(index_code, url)` | 返回 `date`, `pe` |
| 估值百分位 & 当前值结构 | `fetch_index_valuation_percentile(index_code, url)` / `parse_index_valuation_percentile_rows` | 当前分位、百分位、分位临界值 |
| 指数股息率 | `fetch_index_dividend_yield(index_code, url)` | 供顶部"股息率"指标格使用 |
| 指数目标聚合 | `fetch_target_index_metrics(target)` | main 里已经调用过，`valuation_items` 里已含大部分字段；**优先从 target / valuation_item 里读，不要重复抓** |

调用方式：`generate_valuation_percentile_chart(target, output_dir)` 传入的 `target` 结构和当前 `generate_equity_bond_chart` 一致（见 `monitor_drawdown.py` 1998–2007 行），里面已带 `index_code` / `index_valuation_percentile_source` / `index_dividend_yield_source`。缺字段时回退到默认 URL 模板。

---

## 3. 视觉与布局规格

### 3.1 画布

- **尺寸：`1400 × 780`，`dpi=180`**（横向宽幅，替代旧图的竖卡片）
- 背景：纯白 `#ffffff`（参考图是白底浅灰分隔）
- 中文字体优先级：`Microsoft YaHei` → `Noto Sans CJK SC` → `SimHei`（Actions 已装 `fonts-noto-cjk`）
- 整图分为三条水平带：**顶部标题+结论带 / 中部指标格带 / 主图带**，主图占比 ≥ 60% 垂直高度

### 3.2 顶部标题+结论带（高度 ~140px）

> **已废弃（修订 6，2026-04-24）**：该带已从 PNG 中整体移除，相关 PE 当前值、PE百分位、档位等信息改由邮件表格层呈现。下列内容保留作历史参考。

从左到右：

1. 左上：**指数中文名**，字号 ~28pt 粗体（例：`中证红利`）
2. 左中小灰字：`比过去 {100 - pct_5y:.2f}% 的时间低`（其中 `pct_5y` = PE 5Y 百分位；若无 5Y 取可用窗口并在 tooltip 下方小字标注实际窗口）
3. 正下方大字档位标签（按 5Y PE 百分位映射颜色 & 文字）：

   | pct_5y | 文字 | 颜色 |
   |---|---|---|
   | <20 | 估值极低 | `#2f9e4f` |
   | 20–40 | 估值偏低 | `#6fbf73` |
   | 40–60 | 估值合理 | `#9aa0a6` |
   | 60–80 | 估值偏高 | `#e89b3b` |
   | ≥80 | 估值极高 | `#d94f3a` |

   档位大字 ~36pt 粗体，颜色按上表。

4. 右侧并排两个关键数字（用细竖分隔线隔开）：
   - `PE {MM-DD}` 小灰字 + 下行大数字（PE 当前值，2 位小数）
   - `PE百分位` 小灰字 + 下行大数字（pct_5y，2 位小数 + `%`）

### 3.3 中部指标格带（高度 ~90px，单行 3 格，左对齐）

> **已废弃（修订 6，2026-04-24）**：该带已从 PNG 中整体移除，PB / PB百分位 / 股息率 均改由邮件上方表格呈现。下列内容保留作历史参考。

**本期只展示 etf.com 估值中心接口真实返回的三项**（`PB`、`PB百分位`、`股息率`），ROE 和预测 PEG 不显示、不占位、不留 `-`。等宽 3 列：

1. `PB` + 值（2 位小数，来自 `index_valuation_metrics["PB(LF)"].current` 或等价字段）
2. `PB百分位` + 值（带 `%`，来自同一块的 5Y 百分位字段）
3. `股息率` + 值（带 `%`，来自 `index_dividend_yield`）

指标名小灰字（`#9aa0a6`），数值正常黑色 18pt。3 格之间细竖分隔线 `#eeeeee`。

（顶部标题+结论带右侧仍保留 `PE 当前 + PE百分位` 两格大数字，作为主图相关的核心指标，与本指标格不重复。）

### 3.4 主图带（高度占剩余空间）

- 标题行（主图正上方、左对齐）：
  - `PE走势` 加粗 18pt
  - 右侧图例三色小字：
    - 绿色 `30分位值 {q30:.2f}`
    - 灰色 `中位值 {q50:.2f}`
    - 红色 `70分位值 {q70:.2f}`
  - 分位值按**主图窗口内**（默认 5Y）的 PE 序列计算 `quantile([0.3, 0.5, 0.7])`，不要用接口返回的临界值（接口口径不一定与窗口一致）
- 折线：
  - 橙色 `#f07c2b`，线宽 1.8
  - 轻微透明填充（可选）到 x 轴，或不填色 —— 与参考图一致，**不填色**
- 三条水平虚线：
  - `q30` 绿色 `#2f9e4f` 虚线
  - `q50` 灰色 `#9aa0a6` 虚线
  - `q70` 红色 `#d94f3a` 虚线
- x 轴：左右两端各标一个日期（`YYYY-MM-DD`），不要中间刻度
- y 轴：5 档均匀刻度，显示 PE 值（2 位小数）
- 网格：仅横向浅灰 `#eeeeee`
- **最新点**：橙色实心圆点 + 旁边小字当前 PE

### 3.5 底部脚注（图最底部一行，小灰字 10pt）

`数据源：易方达估值中心 + 指数详情接口 · 生成时间 YYYY-MM-DD HH:MM`

**禁止**：底部 tab 条（近3年/近5年/近10年），邮件里是静态图，加了也没用。

---

## 4. 档位与分位口径（全图统一）

必须实现并全图复用下列函数（档位判定、顶部结论、颜色选择共用同一切分）：

```python
def classify_level_by_percentile(pct: float) -> tuple[str, str]:
    """返回 (文字, 颜色)。切分点 20/40/60/80。"""
```

窗口：默认 **近 5 年**。若 5Y 数据不足 20 条则退到全历史并在脚注里追加 `(使用全历史窗口，5Y 数据不足)`。

---

## 5. 约束

- 禁止新增数据源抓取器
- 禁止引入 `plotly` / `pyecharts` / `seaborn`，仅 `matplotlib`
- 禁止修改 `monitor_drawdown.py` 里既有函数签名（只允许替换 import + 调用点）
- 禁止修改 `prototype_equity_bond_chart.py`（保留原文件）
- 失败降级：若 PE 历史为空或连续 20 条以下，直接返回 `None`（main 里现有 try/except 会让邮件裸发无图）
- 代码风格：保持与 `prototype_equity_bond_chart.py` 一致的函数切分粒度（顶部块、指标格块、主图块各一个 `_draw_*` 辅助）

---

## 6. 数据缺失的降级策略（已由架构师决策，不要再问）

范围已收紧（2026-04-23 追加）：**本期只做 PE 走势主图 + PE/PB/股息率 指标展示**。ROE 与预测 PEG 完全不在本期范围内，不展示、不画图、不留位。

| 字段 | 方案 |
|---|---|
| PE 当前 / PE 5Y 百分位 | 必须有；缺失则函数返回 `None`，邮件不带图 |
| PE 历史 | 必须有 ≥20 条；不足退全历史窗口并脚注标注；再不足返回 `None` |
| PB 当前 / PB 百分位 | 从 `fetch_target_index_metrics` 返回的 `index_valuation_metrics` 里读 `PB(LF)` 块的 `current` 与 5Y 百分位字段。取不到：显示 `-`（仅该格） |
| 股息率 | 从 `index_dividend_yield` 读。取不到：显示 `-`（仅该格） |
| ROE、预测 PEG | **不在本期范围**。不抓、不算、不画、不占位 |
| PB 历史、ROE 历史 | **不在本期范围**。不画子图 |

即：主图 **只画 PE 走势一幅**。指标格只有 3 个（PB / PB百分位 / 股息率）。

---

## 7. 测试与验收

1. 在分支内新增 `tests/test_valuation_percentile_chart.py`，至少 1 条：
   - 给定一个 mock 过的 `fetch_index_pe_history`（20 条以上 PE 序列 + 单调变化）
   - 断言：输出 PNG 存在、大小 > 5KB、函数在缺 PB / 股息率时不抛异常（缺的格子显示 `-`）
2. 本地产出 6 张图手工目检（与 `config.yaml` 当前启用的 6 个 valuation 标的对应）：
   - 红利低波动100（930955）
   - 沪深300（000300）
   - 国证2000（399303）
   - 深证成长40指数（399326）
   - 港股通央企红利（931233）
   - 香港证券指数（930709）
3. 本地跑一次 `python preview_email_with_charts.py`（或等价预览脚本），确认邮件 HTML 的图区域：
   - 不再出现"股债性价比"图
   - 每个估值标的块下出现 1 张宽幅估值分位图
   - 不出现 404/裂图

---

## 8. 交付清单

在这个分支上：

- [ ] 新增 `prototype_valuation_percentile_chart.py`
- [ ] `monitor_drawdown.py` 改 import + 调用点（最小 diff，只替换 1 处）
- [ ] 新增 `tests/test_valuation_percentile_chart.py`
- [ ] `README.md` 末尾 1 段说明邮件图已改为估值分位图（不超过 5 行）
- [ ] 6 张目检 PNG（可放 `.test_artifacts/` 或不提交，但要在 PR 描述中附截图）
- [ ] PR 描述里贴 1 张 before/after 对比图

### 8.1 执行进度

- 2026-04-23 23:25 Codex：已按要求切到分支 `feat/valuation-percentile-chart`。
- 2026-04-23 23:25 Codex：已完成规格阅读、现有集成点排查，确认当前邮件图由 `monitor_drawdown.py` 与 `preview_email_with_charts.py` 分别引用 `generate_equity_bond_chart`。
- 2026-04-23 23:25 Codex：架构师已批准开工；后续关键进度、阻塞与约束确认将持续同步到本文。
- 2026-04-23 23:25 Codex：当前进入实现前准备阶段，先编写实现计划文档，再按 TDD 先写失败测试。
- 2026-04-23 23:26 Codex：实现计划已写入 `docs/superpowers/plans/2026-04-23-valuation-percentile-chart.md`。
- 2026-04-23 23:26 Codex：已新增 `tests/test_valuation_percentile_chart.py` 首条测试，并执行 `python -m pytest tests/test_valuation_percentile_chart.py -v`。
- 2026-04-23 23:26 Codex：测试按预期失败，失败原因为 `ModuleNotFoundError: No module named 'prototype_valuation_percentile_chart'`；当前进入最小实现阶段。
- 2026-04-23 23:27 Codex：已新增 `prototype_valuation_percentile_chart.py`，实现新入口 `generate_valuation_percentile_chart(target, output_dir)` 及顶部块/指标格/主图/脚注分块绘制。
- 2026-04-23 23:27 Codex：再次执行 `python -m pytest tests/test_valuation_percentile_chart.py -v`，结果 `1 passed`；当前准备切换主流程与预览脚本到新图函数。
- 2026-04-23 23:32 Codex：已完成 `monitor_drawdown.py` 与 `preview_email_with_charts.py` 的调用切换，邮件图改为调用 `generate_valuation_percentile_chart`。
- 2026-04-23 23:32 Codex：已更新 `README.md` 末尾说明，标注邮件估值图已切换为估值分位走势图。
- 2026-04-23 23:32 Codex：已执行 `python -m pytest tests/test_valuation_percentile_chart.py tests/test_monitor_drawdown.py -v`，结果 `16 passed`，当前进入本地预览验收阶段。
- 2026-04-23 23:36 Codex：架构师追加第 11 节《精细视觉复刻细则》与修订 3。已重新通读全文，确认当前实现仍属“功能跑通”，但未满足 `add_axes` 四区显式布局、`PALETTE/FONT_SIZES` 常量化、`_build_figure` 可测结构等像素级约束。
- 2026-04-23 23:36 Codex：本轮按 11.11 回修清单顺序执行：1）常量收敛；2）改四区布局；3）统一档位映射；4）对齐虚线/最新点/坐标轴；5）拆 `_build_figure` 并补结构断言；6）重绘 6 张图做目检。
- 2026-04-23 23:42 Codex：11.1–11.11 回修已落地到 `prototype_valuation_percentile_chart.py`，包含 `PALETTE` / `FONT_SIZES` 常量、`fig.add_axes` 四区显式布局、`_build_figure(target, data)` 拆分、档位映射统一、三条结构断言。
- 2026-04-23 23:42 Codex：已执行 `python -m pytest tests/test_valuation_percentile_chart.py -v`，结果 `4 passed`；新增结构断言通过。
- 2026-04-23 23:42 Codex：已执行 `python -m pytest -q`，结果 `40 passed`。
- 2026-04-23 23:46 Codex：已创建目录 `.test_artifacts/valuation_percentile/`，并对 `config.yaml` 当前启用的 6 个 `valuation` 标的真实联网调用 `generate_valuation_percentile_chart(target, Path(".test_artifacts/valuation_percentile"))` 生成 PNG。
- 2026-04-23 23:46 Codex：已再次执行 `python preview_email_with_charts.py`，生成 `C:\Users\han\桌面\code\monitor_drawdown\email_preview_with_charts.html`，当前产物路径如下，请架构师目检：
  - 红利低波100 930955: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_930955.png
  - 沪深300 000300: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_000300.png
  - 国证2000 399303: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_399303.png
  - 深证成长40指数 399326: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_399326.png
  - 港股通央企红利 931233: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_931233.png
  - 香港证券指数 930709: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_930709.png
  - 邮件预览 HTML: C:\Users\han\桌面\code\monitor_drawdown\email_preview_with_charts.html
  - 参考图：C:\Users\han\桌面\code\monitor_drawdown\image.png
- 2026-04-23 23:58 Codex：已按修订 5 回修邮件容器与顶部带布局。新增回归测试覆盖 `780px` 邮件容器/full-bleed 图片行，以及顶部带 11.4 坐标落位；已执行 `python -m pytest tests/test_monitor_drawdown.py tests/test_valuation_percentile_chart.py -v`，结果 `21 passed`。
- 2026-04-23 23:58 Codex：已按 11.12 / 12.3 覆盖重绘 6 张 PNG，并重新生成邮件预览 HTML。当前产物路径如下，请架构师第 2 轮目检：
  - 红利低波100 930955: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_930955.png
  - 沪深300 000300: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_000300.png
  - 国证2000 399303: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_399303.png
  - 深证成长40指数 399326: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_399326.png
  - 港股通央企红利 931233: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_931233.png
  - 香港证券指数 930709: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_930709.png
  - 邮件预览 HTML: C:\Users\han\桌面\code\monitor_drawdown\email_preview_with_charts.html
  - 参考图：C:\Users\han\桌面\code\monitor_drawdown\image.png
- 2026-04-24 00:16 Codex：收到用户目检反馈：图形左侧上方无需显示指数名；档位大字（如“估值极高”）需缩小，避免覆盖“比过去 X% 的时间低”描述。本轮只回修顶部标题带，不扩展 ROE / 预测 PEG / tab 条 / PB 子图 / ROE 子图。
- 2026-04-24 00:16 Codex：已在 `prototype_valuation_percentile_chart.py` 中移除顶部带左上指数名渲染，并将 `FONT_SIZES["level"]` 调整为 26；已在 `tests/test_valuation_percentile_chart.py` 增加/更新结构断言，确认顶部带不出现指数名、档位字号不大于 26。
- 2026-04-24 00:16 Codex：已执行 `python -m pytest tests/test_monitor_drawdown.py tests/test_valuation_percentile_chart.py -v`，结果 `21 passed, 3 warnings`。
- 2026-04-24 00:16 Codex：已重新执行 `python preview_email_with_charts.py` 覆盖生成 6 张 PNG 与邮件预览 HTML。当前产物路径如下，请架构师继续目检：
  - 红利低波100 930955: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_930955.png
  - 沪深300 000300: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_000300.png
  - 国证2000 399303: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_399303.png
  - 深证成长40指数 399326: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_399326.png
  - 港股通央企红利 931233: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_931233.png
  - 香港证券指数 930709: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_930709.png
  - 邮件预览 HTML: C:\Users\han\桌面\code\monitor_drawdown\email_preview_with_charts.html
  - 参考图：C:\Users\han\桌面\code\monitor_drawdown\image.png
- 2026-04-24 00:25 Codex：已按用户要求用中文提交信息在 `feat/valuation-percentile-chart` 创建提交 `df03807 新增估值分位走势图邮件展示`。
- 2026-04-24 00:25 Codex：已创建见名知意的 main 备份分支 `backup/main-before-valuation-percentile-20260424`，指向旧 `main` 提交 `0d16f7b`，并已推送到远程。
- 2026-04-24 00:25 Codex：已将本地 `main` 通过 `git merge --ff-only feat/valuation-percentile-chart` 快进到估值分位图提交；已在 `main` 上执行 `python -m pytest tests/test_monitor_drawdown.py tests/test_valuation_percentile_chart.py -v`，结果 `21 passed, 3 warnings`。下一步推送 `main` 到远程。
- 2026-04-24 00:29 Codex：收到 GitHub Actions 中文字体告警：新估值图模块固定传入 `Microsoft YaHei` / `Noto Sans CJK SC` / `SimHei`，Actions 中未命中的字体会触发 findfont 并回落到 DejaVu Sans。已按旧图模块 `fix: 修复Actions中文字体缺失告警` 的策略，在 `prototype_valuation_percentile_chart.py` 中改为从 Matplotlib 当前可见字体里选择可用 CJK 字体；`.github/workflows/monitor.yml` 保持直接安装 `fonts-noto-cjk`。按用户要求，本轮不新增/运行测试。
- 2026-04-24 Codex：用户反馈图片区域上方的 PE/PB 百分位与档位信息与邮件表格重复，已按修订 6 精简 PNG：移除顶部标题+结论带与中部指标格带，只保留 `PE走势` 主图（含 30/中/70 分位值标签）与底部脚注；画布由 `14×7.8` 缩至 `14×5.2`。已同步更新 `tests/test_valuation_percentile_chart.py`：移除涉及档位分类与顶部带文字的断言，新增两条断言验证分位值标签渲染且 `PE百分位 / PB / PB百分位 / 股息率 / 比过去` 不再出现。`python -m pytest tests/test_valuation_percentile_chart.py` 结果 `4 passed`；重跑 `python preview_email_with_charts.py`，6 张 PNG 与邮件预览 HTML 已覆盖生成。

---

## 9. 与架构师的问答

Codex 有任何阻塞问题写到本节，不要边写代码边猜。架构师看到后补充回复到同一处。

### Q1:
所有与本任务相关的交互回复，是否都需要同步记录在本文件中，并且以本文件作为架构师约束与指导的唯一落点？

### A1:
是。Codex 后续所有与本任务相关的关键交互回复、约束确认、阻塞说明，都要同步体现在 `VALUATION_PERCENTILE_CHART_SPEC.md` 中，并严格遵循本文件已有范围、限制与架构师后续补充指导，不得脱离本文自行扩展。

### Q2:
6 张预览图与参考图对比，请架构师目检验收。

### Q3:
修订 5 已完成，请架构师第 2 轮目检。

### Q4:
已按用户反馈隐藏顶部带左上指数名并缩小档位文字，请架构师继续目检。

---

## 11. 精细视觉复刻细则（架构师补，Codex 在集成前必须对齐）

此节把 3.x 的方向性描述**收紧为像素级规范**。Codex 如果已实现但对不上下列任何一条，视为偏差，必须回修；不要解释"差不多"。

### 11.1 figure / 坐标系

- `fig = plt.figure(figsize=(14, 7.8), dpi=180, facecolor="#ffffff")`
- **全部 sub-axes 用 `fig.add_axes([left, bottom, width, height])` 显式放置**，禁止用 `subplots` 自动布局（自动布局无法精确复刻三带结构）
- 画面划分（左右留边 4%，即 `left=0.04, right=0.96`）：

  | 区块 | add_axes 坐标 | 作用 |
  |---|---|---|
  | 顶部标题+结论带 | `[0.04, 0.80, 0.92, 0.17]` | 指数名、档位标签、PE 当前 / PE百分位 |
  | 中部指标格带 | `[0.04, 0.68, 0.92, 0.09]` | PB / PB百分位 / 股息率 三格 |
  | 主图带 | `[0.07, 0.10, 0.90, 0.52]` | PE 折线 + 三条分位虚线 |
  | 脚注带 | `[0.04, 0.02, 0.92, 0.04]` | 数据源 / 生成时间 |

- 顶部带、指标格带、脚注带的 axes 调用：`ax.set_axis_off()`（只做文字层），用 `ax.text(x, y, ..., transform=ax.transAxes)` 定位
- 两条水平分隔线用 `fig.add_artist(Line2D([...], [...], transform=fig.transFigure))`，不要画到 ax 里：
  - `y=0.78` 一条（顶部带与指标格带之间）
  - `y=0.66` 一条（指标格带与主图带之间）
  - 颜色 `#ececec`，lw=0.8

### 11.2 色板（唯一真源，代码里定义 `PALETTE` 常量）

```python
PALETTE = {
    "orange":       "#ed7c2b",   # 主线 / 档位强调 / "15.72%" 数字
    "orange_soft":  "#ef8a3f",   # 备用（如需减淡）
    "text_primary": "#1f1f1f",   # 指数名、大数字
    "text_metric":  "#242424",   # 指标值
    "text_muted":   "#8a8a8a",   # 指标名、轴标签、脚注、"比过去...的时间低"
    "divider":      "#ececec",   # 带间分隔线
    "grid":         "#f0f0f0",   # 主图横向网格
    "spine":        "#d0d0d0",   # 主图 x/y 轴 spine
    "pct_low":      "#2f9e4f",   # 30 分位 / 估值极低
    "pct_mid":      "#9aa0a6",   # 中位 / 合理
    "pct_high":     "#d94f3a",   # 70 分位 / 估值极高
    "level_low":    "#2f9e4f",
    "level_belowmid":"#6fbf73",
    "level_mid":    "#9aa0a6",
    "level_abovemid":"#e89b3b",
    "level_high":   "#d94f3a",
}
```

严格使用十六进制常量，不允许在绘制函数里硬编码散落色值。

### 11.3 字体

```python
plt.rcParams["font.family"] = ["Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
```

字号表（全部用 `fontsize=` 传入，不要依赖 rcParams 默认）：

| 用途 | size | weight |
|---|---|---|
| 指数名（左上） | 26 | bold |
| "比过去 X% 的时间低"（含橙色数字） | 13 | normal |
| 档位大字（估值偏高等） | 34 | bold |
| PE 日期小标签 `PE MM-DD` | 12 | normal（`text_muted`） |
| PE 当前 / PE百分位 大数字 | 22 | semibold |
| 指标格名（PB / PB百分位 / 股息率） | 12 | normal（`text_muted`） |
| 指标格值 | 18 | normal（`text_metric`） |
| 主图图例（三色分位值） | 12 | normal（各自颜色） |
| 主图 y 轴刻度 | 10 | normal（`text_muted`） |
| 主图 x 轴首末日期 | 11 | normal（`text_muted`） |
| 最新点旁的 PE 值标签 | 11 | bold（`orange`） |
| 脚注 | 9 | normal（`text_muted`） |

### 11.4 顶部带排版（add_axes `[0.04, 0.80, 0.92, 0.17]` 内 `transAxes` 坐标）

> **已废弃（修订 6，2026-04-24）**：顶部带已整体移除，本节坐标表不再生效。

| 元素 | (x, y) | anchor | 文案 |
|---|---|---|---|
| 指数名 | (0.00, 0.90) | left, top | `中证红利` |
| "比过去 X% 的时间低"（混排） | (0.00, 0.55) | left, center | `"比过去"` + 橙色 `"{100-pct_5y:.2f}%"` + `"的时间低"` |
| 档位大字 | (0.00, 0.18) | left, bottom | 例 `估值偏高`，颜色取 `level_*` |
| 竖分隔线 | x=0.30，y=0.12→0.88 | — | 色 `divider`，lw=1 |
| PE 日期小标签 | (0.35, 0.72) | left, center | `PE {MM-DD}`（MM-DD 取 PE 历史最后一条日期） |
| PE 当前值大字 | (0.35, 0.30) | left, center | `"{pe_now:.2f}"` |
| PE百分位小标签 | (0.60, 0.72) | left, center | `PE百分位` |
| PE百分位大字 | (0.60, 0.30) | left, center | `"{pct_5y:.2f}"` + 上标小一号 `%` |

混排文字用多次 `ax.text` 拼接，不要手算字宽；第二段的橙色百分数单独一次 `ax.text` 再用 `transform=ax.transAxes` 位移 —— 或直接整行用 `matplotlib.text` 的 `usetex=False` + 分多段绘制。

### 11.5 指标格带（`[0.04, 0.68, 0.92, 0.09]`）

> **已废弃（修订 6，2026-04-24）**：指标格带已整体移除，本节不再生效。

- 3 列等宽，每列中心 x = 0.167、0.500、0.833（`transAxes`）
- 两条竖分隔线：x=0.333 与 x=0.667，y=0.15→0.85，色 `divider`，lw=1
- 每格内部（上下两行）：
  - 指标名，(cx, 0.75)，center+center，`text_muted` 12pt
  - 指标值，(cx, 0.30)，center+center，`text_metric` 18pt（缺失显示 `-`）

### 11.6 主图带（`[0.07, 0.10, 0.90, 0.52]`）

**标题行 + 图例**（画在该 ax 上方 outside，用 `ax.text` + `transform=ax.transAxes`）：

- `PE走势` 在 (0.00, 1.08)，left/baseline，14pt bold
- 三色分位值并排在 (0.00, 1.00) 起：
  - `30分位值{q30:.2f}` 绿
  - `中位值{q50:.2f}` 灰
  - `70分位值{q70:.2f}` 红
  - 用三次 `ax.text`，手动 x 偏移（简单方式：第一个 x=0.00，第二个 x=0.14，第三个 x=0.28；若字符数导致挤压，允许各加 0.02 缓冲）

**折线**：

```python
ax.plot(dates, pes, color=PALETTE["orange"], linewidth=1.8,
        solid_joinstyle="round", solid_capstyle="round")
```

**三条水平虚线**（用计算出的 q30/q50/q70）：

```python
ax.axhline(q30, color=PALETTE["pct_low"],  linestyle=(0, (5, 4)), linewidth=1.0, alpha=0.95, zorder=1)
ax.axhline(q50, color=PALETTE["pct_mid"],  linestyle=(0, (5, 4)), linewidth=1.0, alpha=0.95, zorder=1)
ax.axhline(q70, color=PALETTE["pct_high"], linestyle=(0, (5, 4)), linewidth=1.0, alpha=0.95, zorder=1)
```

**网格与 spine**：

- 只开横向网格：`ax.yaxis.grid(True, color=PALETTE["grid"], linewidth=0.8, alpha=1.0)`；`ax.xaxis.grid(False)`
- 四边 spine：顶/右不显示（`set_visible(False)`），左/底保留，色 `spine`，lw=0.8
- `ax.tick_params(axis="both", which="both", length=0, colors=PALETTE["text_muted"])`（不要 tick 短线，只保留文字）

**y 轴**：

- 5 档刻度：`ax.set_yticks(np.linspace(pes.min(), pes.max(), 5))`
- 格式化：`ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))`
- y 范围：`ax.set_ylim(pes.min()*0.985, pes.max()*1.015)`（给上下留一点）

**x 轴**：

- 仅首末日期：`ax.set_xticks([dates[0], dates[-1]])`
- `ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))`
- 不要 minor ticks

**最新点**：

```python
ax.scatter([dates[-1]], [pes[-1]], s=36, color=PALETTE["orange"], zorder=5)
ax.annotate(f"{pes[-1]:.2f}",
            xy=(dates[-1], pes[-1]),
            xytext=(6, 6), textcoords="offset points",
            color=PALETTE["orange"], fontsize=11, fontweight="bold")
```

### 11.7 脚注（`[0.04, 0.02, 0.92, 0.04]`）

- 一行小字居左：`数据源：易方达估值中心 + 指数详情接口 · 生成时间 YYYY-MM-DD HH:MM`
- 若窗口回退到全历史，追加 ` · 使用全历史窗口（5Y 数据不足）`
- 字号 9，色 `text_muted`

### 11.8 保存

```python
fig.savefig(
    out_path,
    dpi=180,
    facecolor="#ffffff",
    edgecolor="none",
    # 不要使用 bbox_inches="tight"，会破坏本节定义的 add_axes 布局
)
plt.close(fig)
```

### 11.9 档位 x 文字映射（覆盖 3.2 的粗略表，口径不变但文字措辞以此为准）

| pct_5y | 档位文字 | 颜色 key |
|---|---|---|
| <20 | 估值极低 | `level_low` |
| 20–40 | 估值偏低 | `level_belowmid` |
| 40–60 | 估值合理 | `level_mid` |
| 60–80 | 估值偏高 | `level_abovemid` |
| ≥80 | 估值极高 | `level_high` |

### 11.10 可测断言（补充到 `tests/test_valuation_percentile_chart.py`）

除现有 PNG 存在/>5KB 断言外，追加：

1. 产出的 `fig` 上 `ax.get_children()` 中恰好能找到 3 个 `Line2D` 是 axhline（可以查 `get_xdata()` 返回 `[0, 1]` 或其 `get_linestyle()`）
2. 档位文字 in {`估值极低`, `估值偏低`, `估值合理`, `估值偏高`, `估值极高`}
3. 给 pct_5y 传 10 / 30 / 50 / 70 / 90 五次，断言返回的档位颜色 hex 分别落在 `level_low/belowmid/mid/abovemid/high`

为了让前 2 条可断言，建议把绘制函数拆成 `_build_figure(target, data) -> Figure` + `generate_valuation_percentile_chart(...)` 薄壳调用 `_build_figure` 再存盘；测试对 `_build_figure` 的返回值做结构断言。

### 11.11 回修清单（给 Codex 当前已实现代码的 diff 指引）

如果现有 `prototype_valuation_percentile_chart.py` 不满足上述任何一条，请按以下顺序回修（避免一次大 diff）：

1. 先把色值、字号全提取到 `PALETTE` / `FONT_SIZES` 常量
2. 把布局改成 `fig.add_axes(...)` 四区
3. 档位文字、映射表统一到 11.9
4. 最新点、分位虚线、y 轴 5 档、x 轴首末日期
5. 加 `_build_figure` 拆分，补 11.10 的断言
6. 本地重绘 6 张目检图，与参考图逐项对比（档位文字 / PE 数字对齐 / 虚线色 / 轴留白 / 脚注）

### 11.12 视觉目检产出要求（架构师必须能亲自看图）

架构师目前只能通过 `Read` 工具查看仓库内磁盘上的 PNG 文件才能做视觉评估。只写"已通过测试 / 已产出预览"不够，必须把图真的落到磁盘上，并在本文登记绝对路径供架构师逐张查看。

**硬要求**：

1. 在分支根目录创建 `.test_artifacts/valuation_percentile/` 目录（该目录可以加入 `.gitignore`，不要求提交，但要真实存在）。
2. 写一个一次性脚本（例如 `scripts/render_valuation_previews.py` 或临时脚本）或在本机 REPL 手动跑，对 `config.yaml` 当前启用的 6 个 `valuation` 标的依次调用 `generate_valuation_percentile_chart(target, Path(".test_artifacts/valuation_percentile"))`。要求：
   - 允许真实联网抓数据（不走 mock），要和生产实际一致
   - 缺数据的标的也要产出一张，缺哪格就 `-`，不要整张略过；无法产出的在 8.1 节注明原因
3. 同时调用 `python preview_email_with_charts.py`（或等效脚本）产出 `email_preview_with_charts.html`，里面必须把这些 PNG 内联引用到位，不出现 404 / 裂图。
4. 把下列 **所有** 路径以 **绝对路径** 形式追加到第 8.1 节"执行进度"里，一行一个；架构师会用 `Read` 逐个打开：

   - 6 张目检 PNG 的绝对路径（每个标的一行，标注标的名 + 指数代码）
   - 邮件预览 HTML 的绝对路径
   - 参考图的绝对路径（已存在，一起列上方便对比）

5. 不要在问答区（第 9 节）或聊天里描述"图应该是什么样"，架构师只认磁盘上能打开的 PNG。

**输出示例**（Codex 在 8.1 节追加时照此格式）：

```
- 2026-04-23 HH:MM Codex：已重绘 6 张目检图，产出路径如下，请架构师目检：
  - 红利低波100 930955: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_930955.png
  - 沪深300 000300:     C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_000300.png
  - 国证2000 399303:    C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_399303.png
  - 深证成长40 399326:  C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_399326.png
  - 港股通央企红利 931233: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_931233.png
  - 香港证券指数 930709: C:\Users\han\桌面\code\monitor_drawdown\.test_artifacts\valuation_percentile\valuation_percentile_930709.png
  - 邮件预览 HTML:       C:\Users\han\桌面\code\monitor_drawdown\email_preview_with_charts.html
  - 参考图：             C:\Users\han\桌面\code\monitor_drawdown\tests\4a04c44ef9ee7babd4b390d5ac36fef3.jpg （如有）
```

登记完成后，在问答区写一条 `Q: 6 张预览图与参考图对比，请架构师目检验收`，等架构师回复 `A` 再进入下一轮回修或封板，不要自行判断"看起来不错"继续推进。

---

## 12. 邮件容器扩宽 + 顶部带布局回修（架构师补，修订 5，阻塞第 1 轮目检）

> **部分已废弃（修订 6，2026-04-24）**：12.2-C（顶部标题带落位）随顶部带整体移除而失效；12.1 / 12.2-A / 12.2-B / 12.2-D（邮件容器 780px、图片单元格去 padding、PNG 画布保留）仍然生效。12.3 的验收口径中涉及指数名与档位大字的条款已不再适用。

### 12.1 现象（架构师读 `valuation_percentile_930955.png` 后定位）

- 邮件 HTML 外层写死 `width="640" max-width:640px`（见 `monitor_drawdown.py` 约 1728–1731 行），1400×780 的 PNG 在邮件里被缩到 ~46% 显示，架构师"再放大一点"的诉求无法满足
- 当前 PNG 顶部标题带的实现是平铺/默认排版，**没有按 11.4 的 (x, y, anchor) 表落位**。表现：指数中文名（"中证红利低波动100指数"）与档位大字（"估值极高"）**同一区域重叠**；"比过去 X% 的时间低"那行被盖住几乎看不见；右侧 PE / PE百分位 的 "PE 04-22" 与数字 "9.19" 上下间距太小，百分号 "%" 跑到下一行

### 12.2 必须做的修复

#### A. 邮件容器扩宽（`monitor_drawdown.py`）

- 把外层 table 的 `width="640"` 与 `max-width:640px` **全部替换为 `780`**（单位为 px）
- 搜索整个文件把 `640` 作为邮件容器宽度使用的地方一并改掉，不要漏。涉及的典型位置是 `build_email_html_content` 里的两处 `width="640"` + `max-width:640px`；如还有其它子卡片/子表格引用 640px 的硬编码，按比例放大（例如 600→730，620→760），使它们在新容器内仍有相对留白
- **把图片所在的 `<td>` 的水平 padding 改为 0**（让 PNG full-bleed 撑满卡片宽度），图片本身 `<img style="width:100%;max-width:100%;height:auto;display:block">`。不要再留 28px 左右 padding 夹住图
- 其余文字段（标题、指标、脚注等）的 padding 保持 28px 不变

该改动不得扩到"换一套 email 模板"，只允许改这几处 width / padding 数字。

#### B. PNG 画布尺寸保留

- `prototype_valuation_percentile_chart.py` 里的 `figsize=(14, 7.8), dpi=180` **不变**。1400×780 px 作为 @~1.8x 超采样，在 780px 的容器里以 1:1 显示时细节清晰。
- 不要改成 780×435，会糊
- 不要改宽高比

#### C. 顶部标题带严格按 11.4 落位

- 完全按 11.4 表的 8 行 (x, y, anchor, 文案) 落到 `transAxes` 坐标，逐元素用 `ax.text()` 调用
- 禁止使用 `ax.set_title()` / `fig.suptitle()` / 默认 matplotlib 布局器
- 指数名字数过多时（如"中证红利低波动100指数"有 10 字），允许把 fontsize 从 26 **自动缩到 22 或 20** 以避免越界，但**绝对不能和档位大字同行**。档位大字永远在 y≈0.18 底部，指数名永远在 y≈0.90 顶部，中间是 y≈0.55 的"比过去 X% 的时间低"。三行上下分离
- 右侧 PE / PE百分位 区的垂直间距：标签 y=0.72、数字 y=0.30，数字与标签相差 ≥ 0.30 `transAxes`，不允许粘一起。百分号 `%` 与数字必须同行（用 text 里的 `rf"{pct:.2f}%"`，不要分两次 `ax.text` 叠加位置）

#### D. 指标格带与主图带不动

11.5 / 11.6 的规格本轮看渲染正常，维持现状，不要动

### 12.3 验收口径（架构师第 2 轮目检）

Codex 完成 A + B + C 后，按 11.12 节流程重新产出：

1. 重新落盘 6 张 PNG 到 `.test_artifacts/valuation_percentile/`（覆盖旧文件）
2. 重新生成 `email_preview_with_charts.html`
3. 在 8.1 节追加一条新的进度记录，列同一批路径（可以是同名覆盖）
4. 在第 9 节追加 Q3："修订 5 已完成，请架构师第 2 轮目检"，停下等 A3

目检通过标准：

- 邮件里 PNG 实际渲染宽度 ≥ 720px（中间内容区有 28px padding 就 780-56=724）
- 指数名与档位大字 **不重叠**，"比过去 X% 的时间低"整行可读
- 右侧 PE 数字与百分位数字 **不压字、不换行**
- 三条分位虚线颜色区分明显（绿/灰/红）
- 最新点圆点 + PE 值标签紧贴但不遮挡折线

---

## 10. 变更记录

- 2026-04-23 初版：架构师交付规格；Codex 尚未开工。
- 2026-04-23 修订 1（同日，架构师补）：范围收紧。本期只做 PE 走势主图；顶部指标格从 5 个缩减为 3 个（PB / PB百分位 / 股息率），ROE 与预测 PEG 完全不在范围内。数据源口径：etf.com 估值中心接口真实返回的字段。
- 2026-04-23 修订 2（同日，架构师补）：所有与本任务相关的关键交互回复、约束确认、阻塞说明，都需同步记录到本文，并以本文作为架构师指导与约束的落点。
- 2026-04-23 修订 3（同日，架构师补）：追加第 11 节《精细视觉复刻细则》。把 3.x 的方向性描述钉到像素：figure 坐标、色板常量、字号表、顶部/指标格/主图/脚注四区 `add_axes` 布局、分位虚线样式、最新点、保存参数、档位文字表、测试断言、回修清单。Codex 在主流程集成前必须对齐，不满足的逐条回修。
- 2026-04-23 修订 4（同日，架构师补）：追加 11.12《视觉目检产出要求》。规定 Codex 必须把 6 张目检 PNG 与邮件预览 HTML 真实落盘到 `.test_artifacts/valuation_percentile/`，并将绝对路径登记到 8.1 节，架构师用 `Read` 工具逐张目检。未完成目检前不得自行封板。
- 2026-04-23 修订 5（同日，架构师补）：第 1 轮目检不通过。追加第 12 节《邮件容器扩宽 + 顶部带布局回修》，解决两个问题：(a) 邮件外层容器 640px → 780px，图片单元格去水平 padding 让 PNG 全宽显示；(b) 顶部标题带当前实现是平铺排版，必须严格按 11.4 表的 (x, y, anchor) 坐标落位，现在指数名与档位大字重叠、"比过去 X% 的时间低"行被盖住。
- 2026-04-24 修订 6（用户反馈驱动）：PNG 图内的顶部标题+结论带与中部指标格带整体移除（PE 当前值 / PE百分位 / 档位 / PB / PB百分位 / 股息率 / 比过去 X% 的时间低 / 估值窗口脚注等全部不再渲染），原因是这些信息已在邮件上方表格重复展示。画布 `figsize` 由 `(14, 7.8)` 缩至 `(14, 5.2)`，只保留主图带（`PE走势` 标题 + 30/中/70 分位值标签 + 折线 + 三条分位虚线 + 最新点）与底部脚注。章节 3.2 / 3.3 / 11.4 / 11.5 已标记废弃，章节 12.2-C 随之失效，其他 12.x 条款（邮件容器 780px、图片单元格去 padding、PNG 超采样策略）继续生效。配套测试替换为断言分位值标签出现且旧顶部带文案不再出现。
