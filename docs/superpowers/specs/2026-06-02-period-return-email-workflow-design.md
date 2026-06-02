# 跨品种ETF区间收益日报设计

## 背景

当前仓库已有一套定时 GitHub Actions 和 `monitor_drawdown.py`，用于回撤监控、Webhook 推送和估值邮件发送。现需新增一套完全独立的收益率日报能力，用于定时发送“跨品种ETF区间收益日报”。

新增能力必须与现有回撤监控区分开：

- 新建独立 GitHub Actions workflow
- 沿用现有 workflow 的 4 个定时点
- 只发送这封收益率日报
- 不执行原回撤监控逻辑
- 不发送 webhook
- 收件人和 SMTP 凭据继续复用现有环境变量读取方式

## 目标

新增一条独立的自动化链路，按工作日固定时间发送一封“上图下表”的 HTML 邮件：

- 顶部为近 1 个月跨品种 ETF 收益率折线图 PNG
- 底部为区间收益率表格
- 邮件标题固定为 `跨品种ETF区间收益日报`

## 非目标

本次不做以下事项：

- 不修改现有 `monitor.yml` 的职责
- 不把新逻辑并入 `monitor_drawdown.py` 的 `main()`
- 不改变原回撤监控、原估值邮件、原 webhook 的行为
- 不新增新的收件人配置机制
- 不在本次引入最大回撤、Sharpe 等新指标

## 用户确认的约束

- 新 workflow 定时沿用旧 workflow 的 4 个时间点
- 新 workflow 只发这封收益率日报
- 收件邮箱读取方式参考之前邮件发送逻辑
- 标题使用 `跨品种ETF区间收益日报`

## 方案选择

### 方案 A：独立 workflow + 独立发送脚本

由新 workflow 直接执行独立发送脚本，脚本内部完成数据拉取、图片生成、HTML 组装和 SMTP 发送。

优点：

- 与旧监控链路彻底隔离
- GitHub Actions 页面中任务职责清晰
- 后续扩展标题、时间、配置、内容时影响面最小

缺点：

- 新增一个 workflow 和一个正式发送脚本

### 方案 B：独立 workflow + 复用预览脚本

让 workflow 直接调用当前预览脚本，再追加发信逻辑。

缺点：

- 预览脚本职责不纯，混入正式发信后边界变差
- 预览输出目录和正式发送逻辑耦合

### 方案 C：复用旧 workflow，在 `monitor_drawdown.py` 加分支

缺点：

- 与“跟之前区分开”的要求冲突
- 原主流程会继续膨胀
- 排查失败时日志定位不清晰

### 最终方案

采用方案 A：

- 新增独立 workflow：`.github/workflows/period_return_email.yml`
- 新增独立正式发送脚本：`send_period_return_email.py`
- 复用已有数据分析、图表生成和邮箱配置读取能力

## 文件边界

### 新增文件

- `.github/workflows/period_return_email.yml`
  - 独立调度收益率日报发送
  - 调度时间复制现有 `monitor.yml`
  - 执行 `python send_period_return_email.py`

- `send_period_return_email.py`
  - 收益率日报的正式发送入口
  - 读取配置、生成数据、构建邮件、执行 SMTP 发送

- `tests/test_send_period_return_email.py`
  - 覆盖新发送脚本的配置读取、邮件内容组装和发送行为

### 复用文件

- `period_return_email_config.yaml`
  - 只维护 ETF `codes`

- `analyze_etf_com_cn_period_returns.py`
  - 负责区间收益率计算
  - 负责近 1 个月曲线数据构建

- `prototype_period_return_chart.py`
  - 负责生成近 1 个月折线图 PNG

- `monitor_drawdown.py`
  - 只复用 `load_email_config_from_env()` 等邮件配置读取函数
  - 不复用其监控主流程

## 调度设计

新 workflow 的 cron 与现有 `monitor.yml` 保持一致，均按 GitHub Actions 的 UTC 配置：

- `37 1 * * 1-5`，北京时间 `09:37`
- `37 3 * * 1-5`，北京时间 `11:37`
- `7 7 * * 1-5`，北京时间 `15:07`
- `17 12 * * 1-5`，北京时间 `20:17`

同时保留 `workflow_dispatch`，便于手工触发验证。

## 配置与密钥设计

### 业务配置

收益率日报继续读取：

- `period_return_email_config.yaml`

结构保持最简：

```yaml
codes:
  - "159934"
  - "159941"
  - "159259"
  - "159263"
  - "511130"
  - "511380"
```

### 邮件环境变量

复用现有邮件配置方式：

- `RECEIVER_EMAIL`
- `SMTP_USER`
- `SMTP_PASS`

兼容现有备用变量逻辑：

- `EMAIL_TO`
- `EMAIL_USER`
- `EMAIL_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_SMTP_HOST`
- `EMAIL_SMTP_PORT`
- `EMAIL_SUBJECT`

其中 `EMAIL_SUBJECT` 在新脚本中会被强制覆盖为固定标题，避免行为漂移。

## 数据流

1. GitHub Actions 定时触发 `period_return_email.yml`
2. workflow 安装 Python 依赖和中文字体
3. 执行 `python send_period_return_email.py`
4. 脚本读取 `period_return_email_config.yaml`
5. 对配置中的每个 ETF code：
   - 读取/拉取历史净值
   - 计算近 1 月、近 3 月、近 6 月、近 1 年、年初至今、近 3 年、近 5 年、近 10 年、成立以来收益率
   - 生成近 1 月曲线数据
6. 聚合生成表格 JSON 和图表 PNG
7. 组装 HTML 邮件：
   - 顶部一张 PNG 图
   - 底部一张区间收益表
8. 读取邮箱环境变量配置
9. 构造 `EmailMessage`
10. 通过 SMTP SSL 发送邮件

## 邮件内容设计

### 标题

固定为：

`跨品种ETF区间收益日报`

### 正文结构

- 邮件头部标题
- 数据日期
- 近 1 月收益率折线图
- 区间收益率表格

### 表格列

- 名称
- 代码
- 近1月
- 近3月
- 近6月
- 近1年
- 年初至今
- 近3年
- 近5年
- 近10年
- 成立以来

### 图表要求

- 单张合并图
- 时间窗口：近 1 个月
- 每个品种尾部标注“名称 + 收益率”
- 自动避免尾部标签重叠
- 最终输出 PNG，可直接嵌入邮件

## 错误处理

### 缺少邮箱配置

如果 `RECEIVER_EMAIL` / `SMTP_USER` / `SMTP_PASS` 不完整：

- 直接抛出异常
- workflow 标红
- 不静默跳过

### 名称接口失败

如果简称接口失败或个别 code 未匹配：

- 优先降级为 code
- 不阻断整封邮件发送

### 历史不足

如果某品种缺少足够历史：

- 对应区间输出 `--`
- 不阻断整封邮件

### 图表生成失败

如果近 1 月图生成失败：

- 整个任务失败
- 不发送残缺邮件

### SMTP 发送失败

- 直接抛出异常
- 由 workflow 显式报错

## 测试设计

新增 `tests/test_send_period_return_email.py`，覆盖：

1. 标题固定为 `跨品种ETF区间收益日报`
2. 邮件 HTML 同时包含顶部图片与底部表格
3. 邮件发送逻辑正确调用 SMTP
4. 缺少邮箱配置时抛出错误
5. 生成消息时能正确挂载 PNG 为 related image

已有测试继续覆盖：

- `tests/test_analyze_etf_com_cn_period_returns.py`
- `tests/test_prototype_period_return_chart.py`
- `tests/test_preview_period_return_email.py`

## 实施顺序

1. 补正式发送脚本测试
2. 实现正式发送脚本
3. 新增独立 workflow
4. 本地运行脚本与测试
5. 提交后由 GitHub Actions 手工触发验证

## 风险与缓解

### 风险 1：现有预览代码与正式发信职责交叉

缓解：

- 保持 `preview_period_return_email.py` 继续只负责预览
- 新增 `send_period_return_email.py` 负责正式发送

### 风险 2：workflow 缺少中文字体导致图片中文字异常

缓解：

- 新 workflow 与现有邮件 workflow 一样安装 `fonts-noto-cjk`

### 风险 3：右侧尾部标签继续挤压

缓解：

- 保持当前“名称 + 收益率”尾标策略
- 若 GitHub Actions 产图仍存在显示问题，再针对图表布局做二次微调

## 验收标准

满足以下条件视为完成：

- 仓库中新增独立 workflow，且不影响原 workflow
- workflow 定时与旧监控保持一致
- 新 workflow 只发收益率日报，不执行原监控，不发 webhook
- 收件人和 SMTP 凭据继续读取现有环境变量
- 邮件标题为 `跨品种ETF区间收益日报`
- 邮件内容为“上图下表”
- 相关自动化测试通过
