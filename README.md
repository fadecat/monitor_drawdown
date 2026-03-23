# monitor_drawdown

用于监控 ETF / 指数回撤并通过企业微信 Webhook 发送告警。

## 当前监控标的

- 红利低波100ETF(博时) `159307`
- 价值100ETF `512040`

当前版本会优先使用 `tickflow` 获取日线数据，拿不到时再回退到 `akshare`。

## 当前已实现指标

- 回撤：在 `lookback_days` 窗口内，用历史最高价与当前价格计算回撤

当前代码核心逻辑在 `monitor_drawdown.py`，支持 ETF 与指数日线回撤监控。

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
$env:CONFIG_PATH=".\config.yaml"
python .\monitor_drawdown.py
```

安装依赖：

```powershell
python -m pip install --upgrade pip
pip install akshare pandas requests pyyaml tickflow pytest
```
