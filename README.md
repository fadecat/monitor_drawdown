# monitor_drawdown

用于监控 ETF / 指数回撤并通过企业微信 Webhook 发送告警。

## 当前监控标的

- 红利低波100ETF(博时) `159307`
- 价值100ETF `512040`

当前版本会优先使用 `tickflow` 获取日线数据，拿不到时再回退到 `akshare`。

如果配置了 `JISILU_USERNAME` / `JISILU_PASSWORD`，程序还会尝试用集思录 ETF 实时价格补齐当天数据：

- `etf`：直接用集思录 ETF 最新价格补今天这一条
- `index`：匹配对应指数 ETF，用 ETF 当日涨跌幅推算指数今天这一条

## 当前已实现指标

- 回撤：在 `lookback_days` 窗口内，用历史最高价与当前价格计算回撤

当前代码核心逻辑在 `monitor_drawdown.py`，支持 ETF 与指数日线回撤监控。

另外现在新增了一个独立脚本 `monitor_jisilu_calendar.py`，用于抓取集思录日历并推送指定标题关键词，不把这部分逻辑塞进回撤脚本里。

## 本次对话结论

### 1. 当前项目实际监控什么

当前只监控一个核心指标：`回撤`。

程序会：

1. 优先从 TickFlow 拉取 ETF / 指数日线，失败时回退到 AkShare
2. 归一化为 `date` 和 `close`
3. 在最近 `lookback_days` 内寻找高点
4. 计算当前回撤，并按 `threshold` 判断是否告警

### 2. 股息率是否支持

可以支持，但更适合作为“新增计算指标”，不是当前接口直接返回的稳定字段。

可行方案：

- 使用 `fund_etf_dividend_sina` 获取 ETF 分红历史
- 使用当前价格或实时行情价格作为分母
- 计算 `近12个月股息率(TTM) = 最近365天分红总额 / 当前价格`

这属于项目内自行推导，不是 ETF 接口原生直接返回“股息率”。

### 3. 额外可考虑的 ETF 指标

AkShare 的 `fund_etf_spot_em` 适合补充以下实时指标：

- 折溢价率
- 换手率
- 成交额
- 量比
- 主力净流入

其中优先级最高的是：

- `drawdown`
- `discount_rate`
- `dividend_yield_ttm`

### 4. PE-TTM / PB / 百分位

目前不建议作为 ETF 版本项目的首批指标。

原因：

- ETF 本体接口里暂未确认有稳定的 `PE-TTM`、`PB`、`PE/PB 百分位` 直出字段
- 这类指标更像“跟踪指数估值”，不属于 ETF 行情接口的标准输出
- 如果后续要做，可能需要切到指数估值数据源，或按 ETF 跟踪标的单独适配

## 下次继续时建议优先做的事

1. 新增 ETF 实时行情拉取
2. 新增 `dividend_yield_ttm` 计算
3. 新增 `discount_rate` 指标
4. 扩展告警文案，同时展示回撤、折溢价、近12个月股息率

## 运行方式

```powershell
$env:WEBHOOK_URL="你的企业微信 webhook"
$env:CALENDAR_WEBHOOK_URL="你的日历提醒 webhook"
$env:JISILU_USERNAME="你的集思录用户名"
$env:JISILU_PASSWORD="你的集思录密码"
$env:CONFIG_PATH=".\config.yaml"
python .\monitor_drawdown.py
python .\monitor_jisilu_calendar.py
```

本地只想预览日志和将要发送的消息、不实际推送 webhook 时，推荐用 `preview_webhook_message.py`。
它会优先读取系统环境变量；如果没有，再自动读取项目根目录下未跟踪的 `.env.local`。

## 集思录日历提醒

`config.yaml` 现在支持独立的 `calendar_monitors` 配置，例如：

```yaml
calendar_monitors:
  - name: "下修股东会提醒"
    qtype: "CNV"
    window: "next_month"
    webhook_env: "CALENDAR_WEBHOOK_URL"
    title_keywords:
      - "下修股东会"
    lookahead_days: 45
```

当前实现会：

- 调用 `https://www.jisilu.cn/data/calendar/get_calendar_data/`
- 默认按“下个月自然月”动态生成 `start/end`，每天抓下个月事件
- `window=current_to_lookahead` 时，才会按 `lookahead_days` 生成时间窗口
- 过滤 `title` 中包含 `title_keywords` 的项目
- 通过 `webhook_env` 指定的环境变量把结果推送到独立 webhook

先创建本地配置：

```powershell
Copy-Item .\.env.local.example .\.env.local
```

然后编辑 `.env.local`，至少填入：

```dotenv
JISILU_USERNAME=你的集思录用户名
JISILU_PASSWORD=你的集思录密码
CONFIG_PATH=./config.yaml
```

运行本地预览：

```powershell
python .\preview_webhook_message.py
```

如果你想模拟 `free-api.tickflow.org` 没有返回当天价格、改为观察“集思录补齐后的最终输出”，可以运行：

```powershell
python .\preview_webhook_message.py --simulate-missing-today
```

运行后会：

- 在终端打印预览日志
- 生成 [`preview_webhook_payload.json`](/C:/Users/han/桌面/code/monitor_drawdown/preview_webhook_payload.json)
- 生成 [`preview_webhook_message.md`](/C:/Users/han/桌面/code/monitor_drawdown/preview_webhook_message.md)
- 生成本地日志文件 `preview_webhook_run.log`

安装依赖：

```powershell
python -m pip install --upgrade pip
pip install akshare pandas requests pyyaml tickflow pytest pycryptodome
```
只测试“历史数据 + 集思录当天价格 + 最大回撤”时，可直接运行：

```powershell
python .\test_jisilu_index_patch.py
```
