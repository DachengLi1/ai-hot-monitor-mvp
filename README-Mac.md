# AI Hot Monitor MVP

这是一个独立于 whiteboard 的 AI 热点 / 监管监控服务，面向 AI 公众号博主。

## 在 Mac 上怎么打开
1. 下载并解压整个 `ai-hot-monitor-mvp` 文件夹
2. 把整个文件夹放到桌面或任意位置
3. 双击 `open-ai-hot-monitor.command`
4. 浏览器会自动打开 dashboard

如果双击 `.command` 第一次被 macOS 拦住：
- 右键 `open-ai-hot-monitor.command`
- 选择“打开”
- 再确认一次

## 它会自动做什么
- 启动本地 HTTP 服务
- 启动 30 分钟自动抓取循环
- 浏览器打开 `http://127.0.0.1:8890`
- 数据保存在当前文件夹的 `data/` 目录

## 默认端口
- `8890`

如果想换端口，可以在终端里这样启动：

```bash
cd ai-hot-monitor-mvp
PORT=8891 bash start_mvp.sh
```

## 停止服务

```bash
cd ai-hot-monitor-mvp
bash stop_mvp.sh
```

## 文件说明
- `index.html`：dashboard 前端
- `server.py`：本地服务
- `fetch_sources.py`：抓取和聚合逻辑
- `run_fetch_loop.py`：30 分钟自动抓取循环
- `open-ai-hot-monitor.command`：Mac 一键打开脚本
- `start_mvp.sh`：通用启动脚本
- `stop_mvp.sh`：停止脚本

## 数据保存位置
- `data/dashboard.json`：首页聚合结果
- `data/items.json`：所有热点与事件聚合结果
- `data/fetch_status.json`：抓取状态
- `data/board_state.json`：选题池状态
- `data/history/`：每天的热点历史快照
- `data/board_history/`：选题池修改历史
