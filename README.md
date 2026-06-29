# R02 盘面板块雷达

本地 / Vercel 可部署的网页仪表盘，用于同时观察：

- 盘面总览：上证指数、创业板指、科创50、纳斯达克、恒生指数。
- 全市场温度：涨跌幅中位数、上涨占比、P25/P75。
- 实时板块指数：东方财富行业板块指数按当日涨跌幅排序。
- Top 5 板块趋势：前 5 名板块最近 10 个交易日相对首日收盘的涨跌幅趋势。
- 板块归因分析：按上涨家数、龙头强度、10 日相对趋势、成交额拆解上涨来源。
- 板块领涨股：每个 Top 5 板块内按当日涨跌幅列出前 10 只股票。
- R02 宽度校验：大盘云图行业市场宽度，用于确认当前主线资格。

## 本地运行

```bash
python3 server.py
```

然后打开：

```text
http://127.0.0.1:8765/
```

也可以指定端口：

```bash
R02_DASHBOARD_PORT=8766 python3 server.py
```

## Vercel 部署

当前结构支持直接部署到 Vercel：

```text
index.html          # 静态页面
server.py           # 本地服务 + 共享数据抓取逻辑
api/dashboard.py    # Vercel Python Serverless Function
vercel.json         # Function 超时配置
```

Vercel 上的访问路径：

- `/`：静态页面
- `/api/dashboard`：实时数据 JSON

部署步骤：

1. 在本目录初始化独立 Git 仓库并提交文件。
2. 在 GitHub 创建一个新仓库，把本目录推送上去。
3. 在 Vercel 新建 Project，导入该 GitHub 仓库。
4. Framework Preset 选择 `Other` 或保持自动识别；不需要 Build Command。
5. 部署完成后打开 Vercel URL。

本项目没有 npm / pip 依赖，当前只使用 Python 标准库。

## 口径

- 实时板块排行：东方财富 `push2` 行业板块，`fs=m:90+t:2`，按 `f3` 当日涨跌幅排序。
- 10 日趋势：东方财富 `push2his` 板块日 K，`secid=90.BKxxxx`，前端按首日收盘归一化为相对涨跌幅。
- 领涨 10 股：东方财富 `push2` 板块成分股，`fs=b:BKxxxx`，按 `f3` 当日涨跌幅排序。
- 盘面指数：东方财富 `push2` 指数行情。
- 全市场涨跌分布：大盘云图 `mkt_idx.cur_chng_pct`。
- R02 宽度：大盘云图 `industry_ma20_analysis_range`。

## 交易系统边界

- 实时板块涨跌是盘中温度计。
- R02 宽度是交易系统里的板块资格证。
- 二者必须分层展示，不能互相替代。
- 本工具只做盘面监控和数据展示，不输出买卖建议。
- 正式交易分析必须回到 Vault 里的 R02 / R04 / R05 / R13 / R15 和账户状态完成预检。

## 注意事项

- 部署到 Vercel 后，页面会成为公网可访问页面；不要放入账号、持仓截图、API key 或任何私密数据。
- 东方财富和大盘云图接口是公开前端数据源，可能因为网络、限流、字段变化或跨境访问失败而返回空数据。
- `R02_CURRENT` 是 `server.py` 中的正式 R02 摘要；若正式 R02 口径变更，先更新本 README，再同步修改代码。
