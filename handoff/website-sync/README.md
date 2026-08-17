# R02 网站同步交接包

更新时间：2026-08-05

## 当前项目

生产网站的首页已经切换为 Mark Minervini 2 看板，导入表格保留为 `/m2-table`，原 R02 板块雷达保留为 `/radar`。

- 源码目录：`/Users/leon/Library/Mobile Documents/iCloud~md~obsidian/Documents/投资/tools/r02-sector-dashboard`
- 源码仓库：`https://github.com/internetman/r02-sector-dashboard.git`
- Vercel 绑定仓库：`https://github.com/internetman/blackhorse-quant.git`
- 生产域名：`https://www.heimaq.com/`
- Vercel 默认域名：`https://blackhorse-quant.vercel.app/`
- API：`/api/dashboard`、`/api/m2-watchlist`、`/api/m2-history`
- M2 展示快照：`m2-snapshot.json`

当前部署方式是：先维护源码仓库，再同步同一套文件到 `internetman/blackhorse-quant` 的 `main` 分支；Vercel 已绑定 `blackhorse-quant`，push 后会自动生产部署。

## 权限和密钥

本项目代码本身没有业务 API key，也没有需要写入仓库的密钥。行情接口都是公开前端数据源。

正常同步需要的是本机已有的 GitHub 推送权限：

- 能 push `internetman/r02-sector-dashboard`
- 能 push `internetman/blackhorse-quant`

Vercel 不需要单独 token；生产部署由 Vercel 的 GitHub 集成自动触发。如果 Git push 要求登录，让用户在 Chrome/GitHub 或本机 Git Credential Manager 中完成授权，不要把 token 明文写进代码、README、截图或聊天消息。

可参考 `secrets.env.example`。它只是占位说明，不含真实密钥。

## 同步步骤

1. 在源码目录改代码。
2. 若改了数据源、R02 口径、刷新频率或缓存口径，先改项目 `README.md`，再改代码。
3. 本地验证：

```bash
python3 -m py_compile server.py api/dashboard.py
node - <<'NODE'
const fs = require('fs');
const html = fs.readFileSync('index.html', 'utf8');
const match = html.match(/<script>([\s\S]*)<\/script>/);
if (!match) throw new Error('script tag not found');
new Function(match[1]);
console.log('index script syntax ok');
NODE
python3 - <<'PY'
from server import build_dashboard_payload
p = build_dashboard_payload(force=True)
print(p["generatedAt"], len(p.get("indices") or []), len(p.get("sectors") or []), len(p.get("top5") or []), len(p.get("warnings") or []))
PY
```

4. 提交并推送源码仓库：

```bash
git add README.md server.py index.html api/dashboard.py vercel.json .gitignore .vercelignore
git commit -m "你的提交信息"
git push origin main
```

5. 同步到 Vercel 绑定仓库：

```bash
handoff/website-sync/sync-to-vercel-repo.sh "你的提交信息"
```

日常收盘后把最新的 `*收盘.xlsx` 放入 M2 项目的 `导入/` 根目录，然后直接运行：

```bash
bash handoff/website-sync/refresh-m2-site.sh
```

脚本会自动选择根目录中修改时间最新的收盘表，使用归档目录里最新的上一份收盘表计算新进/退出，依次生成收盘分析、网站数据、行业映射和历史 K 线快照，提交源码仓库，再同步到 Vercel 生产仓库。可用 `M2_CLOSE_XLSX` 和 `M2_PRIOR_CLOSE_XLSX` 显式覆盖这两个文件。

6. 验证生产：

```bash
handoff/website-sync/verify-production.sh
```

## 当前部署口径

- 静态首页：`index.html`（Mark Minervini 2）
- M2 导入表格页：`m2-table.html`（当前 8-5 早盘 i问财快照，含关键数据表、均线距离推演和摘要图形）
- R02 雷达页：`/radar`（源码文件：`radar.html`）
- M2 静态资源：`m2-styles.css`、`m2-data.js`、`m2-app.js`、`m2-assets/`
- Vercel Python Serverless Function：`api/dashboard.py`
- M2 行情 Serverless Function：`api/m2-watchlist.py`（默认读已发布收盘报价，`dynamic=1` 才实时抓取）
- M2 快照 Serverless Function：`api/m2-history.py`（默认读 `m2-snapshot.json`，`dynamic=1` 才动态抓取日K）
- M2 本地快照脚本：`handoff/website-sync/capture-m2-snapshot.py`
- M2 一键抓取并发布：`handoff/website-sync/refresh-m2-site.sh`
- 共享抓取逻辑：`server.py`
- Vercel 配置：`vercel.json`
- 无 npm / pip 依赖；当前只用 Python 标准库。

M2 建议只提供候选分层，不替用户下单：`突破确认后考虑`、`不追当日大涨`、`等待平台/突破`、`暂不建议买入`。导入表的建议基于带时间的快照；Pivot、收缩次数、底部时间和突破量仍需历史 OHLCV 与图形复核。

首页候选卡正常读取 `m2-snapshot.json`，不再依赖截图或打开网页时临时抓取六只股票；点击“动态 VCP 图”会查看由复权日K、成交量、MA50/150/200、候选 Pivot 和算法收缩区绘制的图形。`m2-assets/` 中的旧图片仅保留为历史存档。

行情源：

- 指数：东方财富 `push2` / `push2delay`
- 板块排行：东方财富 `push2` / `push2delay`，`fs=m:90+t:2`，按 `f3` 当日涨跌幅排序
- 10 日趋势：东方财富 `push2his` / `push2delay` 板块日 K
- 领涨股：东方财富 `push2` / `push2delay`，`fs=b:BKxxxx`
- 全市场涨跌分布：大盘云图 `mkt_idx.cur_chng_pct`
- R02 宽度：大盘云图 `industry_ma20_analysis_range`
- M2 候选股行情：东方财富 `push2` / `push2delay` `ulist.np`

刷新与缓存：

- M2 选股快照：建议收盘后 15:30–16:00 由本地 Session 生成并推送
- M2 快照有效期：36 小时；网页过期后明确标注
- 网页检查新快照：30 分钟
- API 候选股行情：`/api/m2-watchlist` 默认读已发布收盘报价；`dynamic=1` 才实时抓取
- API 动态日K：`/api/m2-history` 默认读已发布快照；`dynamic=1` 仅作为本地排障和快照首次生成兜底
- R02 雷达页面自动刷新：30 分钟
- 手动按钮：强制刷新
- 服务端短缓存：45 秒
- 趋势缓存：30 分钟
- 板块排行成功快照：24 小时
- 若新数据失败，页面优先沿用上一次成功快照，并标注快照时间。

## 交易系统边界

- 盘中板块排行只是温度计。
- 正式 R02 宽度是交易系统里的板块资格证。
- 二者必须分层展示，不能混成交易结论。
- 只输出规则化购买建议，不执行交易；“均线通过”不等于立即买入，仍需结合 Pivot、收缩、突破量和止损计划复核。

## 常见故障

- `push2.eastmoney.com` 502 / empty reply：这是上游或出口网络问题，先看是否已走 `push2delay` 兜底。
- API 返回 `warnings` 但主排行不空：可继续展示，提醒这是公开源不稳定。
- 板块排行不空但趋势为空：趋势 K 线接口可能失败，页面会尝试服务器和浏览器趋势缓存。
- Vercel 没更新：先确认 `blackhorse-quant` 的 `main` 分支是否收到新 commit，再去 Vercel 看 deployment。
