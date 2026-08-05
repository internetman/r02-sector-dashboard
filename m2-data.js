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
      range: 78, pivotPrice: 40.88, pivotStatus: "候选", pivotReason: "最近整理平台上沿 40.88；需收盘站上并有量能确认。", stageReason: "阶段 2 候选：均线多头结构待每日重算。", volumeRule: "突破日需明显放量", advice: "突破确认后考虑", adviceClass: "priority", adviceReason: "站上 40.88 并放量后才进入买点复核；当前不追。", action: "等待站上 40.88 附近并放量；未突破不追。", note: "均线多头，距离阶段高点较近。", baseAge: "未接入历史统计", contractions: "未确认", contractionDetail: "需历史 OHLCV 扫描", correction: "未接入历史统计", chart: "m2-assets/亿联网络.jpg", priority: 1
    },
    {
      code: "601677", name: "明泰铝业", sector: "铝 / 有色", state: "临近复核", stateClass: "review", stage: "阶段 2 候选",
      price: "17.00", change: "+1.37%", volume: "0.74×", volumeLabel: "缩量整理", pivot: "未确认", distance: "—",
      range: 61, pivotPrice: null, pivotStatus: "待确认", pivotReason: "当前平台上沿尚未确认；不能把当天高点直接当 Pivot。", stageReason: "阶段 2 候选：需确认均线顺序和平台持续性。", volumeRule: "突破日需明显放量", advice: "等待平台 / 突破", adviceClass: "wait", adviceReason: "先确认平台上沿、收缩和突破量，再判断是否进入买点。", action: "继续观察平台上沿和突破量，不因上涨直接升级。", note: "平台相对紧凑，MACD 改善。", baseAge: "未接入历史统计", contractions: "未确认", contractionDetail: "需历史 OHLCV 扫描", correction: "未接入历史统计", chart: "m2-assets/明泰铝业.jpg", priority: 2
    },
    {
      code: "002648", name: "卫星化学", sector: "化工材料 / 独立强势", state: "观察", stateClass: "watch", stage: "阶段 2 候选",
      price: "25.20", change: "−0.32%", volume: "0.93×", volumeLabel: "接近均量", pivot: "25.50", distance: "1.18%",
      range: 46, pivotPrice: 25.50, pivotStatus: "候选", pivotReason: "近端平台上沿 25.50；需要继续收窄后再验证突破。", stageReason: "阶段 2 候选：价格抬高，但均线与底部仍需复核。", volumeRule: "突破日需明显放量", advice: "等待平台 / 突破", adviceClass: "wait", adviceReason: "25.50 只是候选上沿；先等收窄和量能确认，不把压力位当买点。", action: "等待 24.5–25.5 区间继续收窄，再观察突破。", note: "价格逐步抬高，平台仍未完全确认。", baseAge: "未接入历史统计", contractions: "未确认", contractionDetail: "需历史 OHLCV 扫描", correction: "未接入历史统计", chart: "m2-assets/卫星化学.jpg", priority: 3
    },
    {
      code: "601872", name: "招商轮船", sector: "航运 / 主线共振", state: "主线观察", stateClass: "mainline", stage: "阶段 2 候选",
      price: "16.78", change: "−1.47%", volume: "1.19×", volumeLabel: "日内活跃", pivot: "16.90–17.00", distance: "—",
      range: 40, pivotPrice: 17.00, pivotStatus: "候选", pivotReason: "16.90–17.00 近端平台上沿；回落中不把压力区当买点。", stageReason: "阶段 2 候选：主线共振加分，但个股形态尚未收紧。", volumeRule: "突破日需明显放量", advice: "等待平台 / 突破", adviceClass: "wait", adviceReason: "主线共振只能加分；先等个股收紧并有效突破 16.90–17.00。", action: "航运主线未失效，但今天回落，不升级、不追跌。", note: "板块标签加分，形态仍需收紧。", baseAge: "未接入历史统计", contractions: "未确认", contractionDetail: "需历史 OHLCV 扫描", correction: "未接入历史统计", chart: "m2-assets/招商轮船.jpg", priority: 4
    },
    {
      code: "300750", name: "宁德时代", sector: "电池新能源 / 独立强势", state: "观察", stateClass: "watch", stage: "阶段 2 候选",
      price: "395.10", change: "+0.18%", volume: "0.71×", volumeLabel: "缩量", pivot: "400–410 压力区", distance: "—",
      range: 31, pivotPrice: null, pivotStatus: "压力区", pivotReason: "400–410 只是压力区，不是已经确认的 Pivot。", stageReason: "阶段 2 候选：趋势尚在，但底部较宽，需重新定义平台。", volumeRule: "突破日需明显放量", advice: "等待平台 / 突破", adviceClass: "wait", adviceReason: "趋势尚在但底部较宽；先重新定义紧平台，不把 400–410 当现成买点。", action: "需要更紧的平台和放量突破，不能把压力区当买点。", note: "大市值、趋势尚在，但底部较宽。", baseAge: "未接入历史统计", contractions: "未确认", contractionDetail: "需历史 OHLCV 扫描", correction: "未接入历史统计", chart: "m2-assets/宁德时代.jpg", priority: 5
    },
    {
      code: "000582", name: "北部湾港", sector: "港口航运 / 主线共振", state: "主线观察", stateClass: "mainline", stage: "阶段 2 候选",
      price: "12.63", change: "−1.17%", volume: "1.03×", volumeLabel: "接近均量", pivot: "近端平台待定", distance: "—",
      range: 27, pivotPrice: null, pivotStatus: "待形成", pivotReason: "新平台尚未形成；15.46 前高只能作参考，不能直接作为买点。", stageReason: "阶段 2 候选：主线共振存在，但修复幅度仍较大。", volumeRule: "突破日需明显放量", advice: "暂不建议买入", adviceClass: "avoid", adviceReason: "新平台和 Pivot 尚未形成；主线共振不能替代个股买点。", action: "等待形成新平台，不能直接使用 15.46 前高作为买点。", note: "主线共振存在，但修复幅度仍较大。", baseAge: "未接入历史统计", contractions: "未确认", contractionDetail: "需历史 OHLCV 扫描", correction: "未接入历史统计", chart: "m2-assets/北部湾港.jpg", priority: 6
    }
  ]
};
