# 给下一个 Codex Session 的接手提示

你现在接手维护 R02 盘面板块雷达的网站同步与部署。

请先阅读：

1. `/Users/leon/Library/Mobile Documents/iCloud~md~obsidian/Documents/投资/tools/r02-sector-dashboard/README.md`
2. `/Users/leon/Library/Mobile Documents/iCloud~md~obsidian/Documents/投资/tools/r02-sector-dashboard/handoff/website-sync/README.md`

关键路径：

- 源码目录：`/Users/leon/Library/Mobile Documents/iCloud~md~obsidian/Documents/投资/tools/r02-sector-dashboard`
- 源码仓库：`https://github.com/internetman/r02-sector-dashboard.git`
- Vercel 绑定仓库：`https://github.com/internetman/blackhorse-quant.git`
- 生产域名：`https://www.heimaq.com/`

同步规则：

- 先维护源码仓库，再同步到 `blackhorse-quant`。
- 数据源、刷新频率、缓存、R02 口径变更必须先写 README，再改代码。
- 不要提交 `.env`、真实 token、浏览器 cookie、`.vercel/`、`__pycache__/`。
- 当前没有项目 API key；GitHub/Vercel 权限依赖用户本机已登录的 Git 凭证和 Vercel GitHub 集成。
- 不输出买卖建议。盘中热度与正式 R02 宽度分层展示。

常用命令：

```bash
cd "/Users/leon/Library/Mobile Documents/iCloud~md~obsidian/Documents/投资/tools/r02-sector-dashboard"
python3 -m py_compile server.py api/dashboard.py
handoff/website-sync/sync-to-vercel-repo.sh "Sync R02 sector dashboard"
handoff/website-sync/verify-production.sh
```

