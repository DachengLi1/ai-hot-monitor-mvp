# AI Hot Monitor MVP

一个独立于 whiteboard 的 AI 热点 / 监管监控 MVP，面向 AI 公众号博主。

## Public repo note

This copy ships with **demo sample data** under `data/` and excludes local runtime logs/history.

## 现在已经有的能力

- **每 30 分钟自动抓取一次** AI / 监管 / 社区热帖
- **官方源 + 媒体源 + 社区源混合采集**
- **事件级聚合**：把相近热点聚成一个事件，不只是文章堆砌
- **监管相关度打分**：方便优先看 AI policy / compliance / governance
- **写作角度建议**：自动给公众号可写方向
- **选题池工作台**：支持「想写 / 在写 / 已发 / 忽略」四列管理
- **历史快照保存**：按天保存 dashboard 和 items 快照

## 当前数据源

### 官方 / 一手源
- OpenAI News
- Anthropic News
- Google AI Blog
- Google DeepMind
- Google Research
- Meta Engineering

### 媒体 / 行业源
- MIT Technology Review AI
- IEEE Spectrum AI
- TechCrunch AI

### 创业 / 公司 / 博客源
- a16z News & Content
- Y Combinator Blog
- TechCrunch Startups
- Datadog Blog + 指定 engineering 文章
- Databricks Blog
- Anyscale Blog
- Together AI Blog
- Physical Intelligence Watch

### 监管源
- NIST News
- EU Commission Press
- The Verge Policy

### 社区源
- Hacker News Top

### 人物 / Talk 观察
- Andrew Karpathy Watch
- Fei-Fei Li Watch
- Yann LeCun Watch
- Demis Hassabis Watch
- Jensen Huang Watch
- Sam Altman Watch
- Dario Amodei Watch
- Mustafa Suleyman Watch

## 目录说明

- `fetch_sources.py`：抓取、过滤、去重、事件聚合、生成 dashboard
- `run_fetch_loop.py`：每 30 分钟自动执行一次抓取
- `server.py`：本地 HTTP 服务，提供 dashboard API 和选题池 API
- `index.html`：前端 dashboard
- `sources.json`：可扩展的数据源配置
- `data/dashboard.json`：前端直接消费的聚合结果
- `data/items.json`：所有标准化后的热点条目 + 事件聚合结果
- `data/fetch_status.json`：每个 source 的抓取状态
- `data/board_state.json`：选题池状态
- `data/history/YYYY-MM-DD/`：每天的 dashboard / items 历史快照
- `data/board_history/YYYY-MM-DD/`：选题池保存历史

## 运行方式

在仓库目录里运行：

```bash
cd ai-hot-monitor-mvp
python3 server.py
```

如果你想启用定时抓取，再另外开一个终端运行：

```bash
cd ai-hot-monitor-mvp
python3 run_fetch_loop.py
```

或者直接使用脚本：

```bash
cd ai-hot-monitor-mvp
bash start_mvp.sh
```

这会：
- 启动本地 dashboard 服务
- 启动 30 分钟自动抓取循环
- 日志写到 `logs/`
- PID 写到 `run/`

停止：

```bash
cd ai-hot-monitor-mvp
bash stop_mvp.sh
```

## 默认地址 / 端口

```bash
http://127.0.0.1:8890
```

如果需要从外网访问，请开放：

- **TCP 8890**

## API

- `GET /api/dashboard`：dashboard 聚合数据
- `GET /api/items`：所有 item + events
- `GET /api/status`：抓取状态
- `GET /api/board`：读取选题池
- `POST /api/board`：保存选题池

## 后续可以继续加

- 更多官方源：xAI / Mistral / Microsoft AI / AWS AI
- 更强的语义级事件聚类
- 每个事件的一键导出 Markdown
- 日报 / 周报推送
- 更细的监管专题面板（版权、隐私、AI Act、平台治理）
