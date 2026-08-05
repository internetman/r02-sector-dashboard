window.M2_DATA = {
  asOf: "2026-08-04 15:00",
  market: {
    status: "🟡 震荡 / 分化",
    note: "风险边际改善，但权重与成长仍然分化；航运主线继续观察。",
    stats: [
      { label: "上证", value: "+0.33%" },
      { label: "深证", value: "+3.25%" },
      { label: "创业板", value: "+5.64%" },
      { label: "上涨 / 下跌", value: "1314 / 855" }
    ]
  },
  decision: {
    title: "今日没有 B1 / B2 触发",
    text: "候选正在积累形态证据。当前最接近买点的是亿联网络，但还需要有效站上 Pivot 并出现量能确认。",
    nextFocus: "亿联网络",
    pivot: "40.88 附近",
    distance: "3.01%"
  },
  changes: [],
  candidates: [
    {
      code: "300628", name: "亿联网络", sector: "通信 / 独立强势", state: "临近", stateClass: "near", stage: "阶段 2 候选",
      price: "39.65", change: "+1.04%", volume: "1.12×", volumeLabel: "温和放大", pivot: "40.88", distance: "3.01%",
      range: 78, action: "等待站上 40.88 附近并放量；未突破不追。", note: "均线多头，距离阶段高点较近。", baseAge: "待追踪", contractions: "未确认", correction: "待计算", chart: "m2-assets/亿联网络.jpg", priority: 1
    },
    {
      code: "601677", name: "明泰铝业", sector: "铝 / 有色", state: "临近复核", stateClass: "review", stage: "阶段 2 候选",
      price: "17.00", change: "+1.37%", volume: "0.74×", volumeLabel: "缩量整理", pivot: "未确认", distance: "—",
      range: 61, action: "继续观察平台上沿和突破量，不因上涨直接升级。", note: "平台相对紧凑，MACD 改善。", baseAge: "待追踪", contractions: "未确认", correction: "待计算", chart: "m2-assets/明泰铝业.jpg", priority: 2
    },
    {
      code: "002648", name: "卫星化学", sector: "化工材料 / 独立强势", state: "观察", stateClass: "watch", stage: "阶段 2 候选",
      price: "25.20", change: "−0.32%", volume: "0.93×", volumeLabel: "接近均量", pivot: "25.50", distance: "1.18%",
      range: 46, action: "等待 24.5–25.5 区间继续收窄，再观察突破。", note: "价格逐步抬高，平台仍未完全确认。", baseAge: "待追踪", contractions: "未确认", correction: "待计算", chart: "m2-assets/卫星化学.jpg", priority: 3
    },
    {
      code: "601872", name: "招商轮船", sector: "航运 / 主线共振", state: "主线观察", stateClass: "mainline", stage: "阶段 2 候选",
      price: "16.78", change: "−1.47%", volume: "1.19×", volumeLabel: "日内活跃", pivot: "16.90–17.00", distance: "—",
      range: 40, action: "航运主线未失效，但今天回落，不升级、不追跌。", note: "板块标签加分，形态仍需收紧。", baseAge: "待追踪", contractions: "未确认", correction: "待计算", chart: "m2-assets/招商轮船.jpg", priority: 4
    },
    {
      code: "300750", name: "宁德时代", sector: "电池新能源 / 独立强势", state: "观察", stateClass: "watch", stage: "阶段 2 候选",
      price: "395.10", change: "+0.18%", volume: "0.71×", volumeLabel: "缩量", pivot: "400–410 压力区", distance: "—",
      range: 31, action: "需要更紧的平台和放量突破，不能把压力区当买点。", note: "大市值、趋势尚在，但底部较宽。", baseAge: "待追踪", contractions: "未确认", correction: "待计算", chart: "m2-assets/宁德时代.jpg", priority: 5
    },
    {
      code: "000582", name: "北部湾港", sector: "港口航运 / 主线共振", state: "主线观察", stateClass: "mainline", stage: "阶段 2 候选",
      price: "12.63", change: "−1.17%", volume: "1.03×", volumeLabel: "接近均量", pivot: "近端平台待定", distance: "—",
      range: 27, action: "等待形成新平台，不能直接使用 15.46 前高作为买点。", note: "主线共振存在，但修复幅度仍较大。", baseAge: "待追踪", contractions: "未确认", correction: "待计算", chart: "m2-assets/北部湾港.jpg", priority: 6
    }
  ]
};
