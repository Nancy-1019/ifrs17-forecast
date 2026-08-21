// ===== 新准则预测模型 v5.4.0 =====
// 技术栈: Python + Django + SQLite + openpyxl (全栈) | 前端仅渲染和交互

// 压力情景参数中英对照（来源：paa_engine/field_names.py）
// 在前端展示时把 CALC_SCENARIOS / stressParams 中的英文 key 转中文
const SCENARIO_PARAM_CN = {
  gross_premium_growth: '原保险保费增长',
  expected_claim_ratio_increase: '预期赔付率上升',
  expected_expense_ratio_increase: '预期费用率上升',
  spot_rate_change: '即期利率变动',
};

// 全局计算结果状态
let CALC_RESULT = null;
let CALC_SCENARIOS = [];
let CALC_RUNNING = false;

// 多场景结果存储 (Task #111)
let CALC_RESULTS_MAP = {};  // {scenario: result, ...}

// ===== 计算进度轮询控制器（模块级，跨页面存活，保证切导航不中断进度显示）=====
let CALC_PROGRESS_TIMER = null;     // 轮询定时器（仅一个，避免重复）
let CALC_PROGRESS_TIMEOUT = null;   // 安全超时（10 分钟）
let CALC_ACTIVE_RESOLVE = null;     // 当前情景 Promise 的 resolve
let CALC_ACTIVE_REJECT = null;      // 当前情景 Promise 的 reject
let CALC_SAFE_TIMEOUT_MS = 600000;  // 10 分钟

// 全局显示单位 (Task #113)
// 1=元, 10000=万元, 1000000=百万元, 100000000=亿元
let DISPLAY_UNIT = 10000;  // 默认万元
const UNIT_OPTIONS = [
  { value: 1, label: '元' },
  { value: 10000, label: '万元' },
  { value: 1000000, label: '百万元' },
  { value: 100000000, label: '亿元' },
];

const MODEL_DATA = {
  basicInfo: { updateDate: '2026/6/18', updater: 'NW', evalDate: '2025/12/31', forecastPeriods: 16, totalAssets: 300000, selectedScenario: '情景6 - 压力情景3' },
  contracts: [
    { group: '新合同组A', subGroup: '子合同组合1', portfolio: '合同组合1', cls: '36', type: '直保或分入' },
    { group: '新合同组B', subGroup: '子合同组合2', portfolio: '合同组合2', cls: '36', type: '分出' },
    { group: '新合同组C', subGroup: '子合同组合3', portfolio: '合同组合1', cls: '37', type: '直保或分入' },
    { group: '新合同组D', subGroup: '子合同组合4', portfolio: '合同组合2', cls: '37', type: '分出' },
    { group: '新合同组E', subGroup: '子合同组合5', portfolio: '合同组合5', cls: '301', type: '直保或分入' },
    { group: '新合同组F', subGroup: '子合同组合6', portfolio: '合同组合6', cls: '301', type: '分出' },
  ],
  existingContracts: [
    { id: '现有合同组A_0', name: '现有合同组A', subGroup: '子合同组合1', portfolio: '合同组合1', cls: '32', type: '直保或分入', premRec: 1800, iacfPay: -500 },
    { id: '现有合同组B_0', name: '现有合同组B', subGroup: '子合同组合1', portfolio: '合同组合1', cls: '32', type: '直保或分入', premRec: 1800, iacfPay: 0 },
    { id: '现有合同组C_0', name: '现有合同组C', subGroup: '子合同组合2', portfolio: '合同组合2', cls: '301', type: '直保或分入', premRec: 1800, iacfPay: 0 },
    { id: '现有合同组D_0', name: '现有合同组D', subGroup: '子合同组合2', portfolio: '合同组合2', cls: '301', type: '直保或分入', premRec: 1800, iacfPay: 0 },
    { id: '现有合同组E_0', name: '现有合同组E', subGroup: '子合同组合3', portfolio: '合同组合3', cls: '32', type: '分出', premRec: -200, iacfPay: 0 },
    { id: '现有合同组F_0', name: '现有合同组F', subGroup: '子合同组合4', portfolio: '合同组合4', cls: '301', type: '分出', premRec: -250, iacfPay: 0 },
  ],
  scenarios: [
    { name: '情景0', desc: '基础情景', p: { pg: 0, lr: 0, er: 0, rc: 0, ed: 0, rd: 0, bd: 0, obd: 0, fx: 0, cd: 0 } },
    { name: '情景1', desc: '沉淀资金情景1', p: { pg: -0.05, lr: 0, er: 0, rc: 0, ed: 0, rd: 0, bd: 0, obd: 0, fx: 0, cd: 0 } },
    { name: '情景2', desc: '沉淀资金情景2', p: { pg: 0, lr: 0.10, er: 0, rc: 0, ed: 0, rd: 0, bd: 0, obd: 0, fx: 0, cd: 0 } },
    { name: '情景3', desc: '沉淀资金情景3', p: { pg: 0, lr: 0, er: 0.02, rc: 0, ed: 0, rd: 0, bd: 0, obd: 0, fx: 0, cd: 0 } },
    { name: '情景4', desc: '压力情景1', p: { pg: 0, lr: 0, er: 0, rc: 0.01, ed: 0, rd: 0, bd: 0, obd: 0, fx: 0, cd: 0 } },
    { name: '情景5', desc: '压力情景2', p: { pg: 0, lr: 0, er: 0, rc: 0, ed: 0.10, rd: 0.20, bd: 0.30, obd: 0.40, fx: 0.50, cd: 0.60 } },
    { name: '情景6', desc: '压力情景3', p: { pg: 0.02, lr: 0.05, er: 0.05, rc: 0.02, ed: 0.05, rd: 0, bd: 0.05, obd: 0, fx: 0, cd: 0 } },
  ],
  selectedScenario: {
    name: '情景6', desc: '压力情景3',
    y1: { pg: 0.02, lr: 0.05, er: 0.05, rc: 0.02, ed: 0.05, bd: 0.05 },
    y2: { pg: 0.02, lr: 0.05, er: 0.05, rc: 0, ed: 0.05, bd: 0.05 },
    y3: { pg: 0.02, lr: 0.05, er: 0.05, rc: 0, ed: 0.05, bd: 0.05 },
  },
  incomeStatement: {
    actual: { rev: 56459, premInc: 52000, invInc: 5000, othInc: -541, exp: 62953, insSvcExp: 51036, cededPrem: 26052, reinsRec: 15000, undFin: 200, reinsFin: 105, premRes: 100, taxExp: 20, mgmtExp: 650, opProfit: -6494, nonOpInc: -21, totalProfit: -6515, netProfit: -6515, compInc: -6515 },
    forecast: [
      { year: '未来第一年', rev: 34235, premInc: 32843, invInc: 1933, othInc: -541, exp: 48139, insSvcExp: 51213, cededPrem: 6506, reinsRec: 9745, undFin: 152, reinsFin: 77, premRes: 0, taxExp: 72, mgmtExp: 18, opProfit: -13904, nonOpInc: -21, totalProfit: -13925, netProfit: -13925, compInc: -13925 },
      { year: '未来第二年', rev: 27092, premInc: 25427, invInc: 2026, othInc: -361, exp: 31745, insSvcExp: 30690, cededPrem: 4503, reinsRec: 3849, undFin: 553, reinsFin: 218, premRes: 0, taxExp: 52, mgmtExp: 13, opProfit: -4652, nonOpInc: -19, totalProfit: -4672, netProfit: -4672, compInc: -4672 },
      { year: '未来第三年', rev: 27409, premInc: 26052, invInc: 1553, othInc: -196, exp: 32730, insSvcExp: 32107, cededPrem: 4496, reinsRec: 4122, undFin: 360, reinsFin: 182, premRes: 0, taxExp: 57, mgmtExp: 14, opProfit: -5321, nonOpInc: -21, totalProfit: -5341, netProfit: -5341, compInc: -5341 }
    ]
  },
  balanceSheet: {
    actual: { a: { cash: 43589, reins: 17026, oth: 172251, total: 232866 }, l: { insLiab: 39787, premRes: 150, total: 39937 }, e: { paid: 150000, surplus: 50000, retained: -7071, total: 192929 } },
    forecast: [
      { year: '未来第一年末', a: { cash: 305305, reins: 3756, oth: -108404, total: 200656 }, l: { insLiab: 21502, premRes: 150, total: 21652 }, e: { paid: 150000, surplus: 50000, retained: -20996, total: 179004 } },
      { year: '未来第二年末', a: { cash: 310513, reins: 3115, oth: -115001, total: 198626 }, l: { insLiab: 24144, premRes: 150, total: 24294 }, e: { paid: 150000, surplus: 50000, retained: -25668, total: 174332 } },
      { year: '未来第三年末', a: { cash: 311156, reins: 2858, oth: -120302, total: 193712 }, l: { insLiab: 24572, premRes: 150, total: 24722 }, e: { paid: 150000, surplus: 50000, retained: -31009, total: 168991 } }
    ]
  },
  paaNew: {
    y1: { uln: 4596, ull: 2470, ullr: -741, icl: 4647, idcl: 139, insRev: 13129, lcl: -2470, lrg: 741, cashClaim: -7954, cashMgmt: -1380, cashPrem: 20000, cashIACF: -4400, ifie: -45 },
    y2: { uln: 6704, ull: 2651, ullr: -682, icl: 10120, idcl: 304, insRev: 23183, lcl: -181, lrg: -59, cashClaim: -16781, cashMgmt: -2424, cashPrem: 26083, cashIACF: -4067, ifie: -116 },
    y3: { uln: 7455, ull: 2945, ullr: -732, icl: 13089, idcl: 393, insRev: 26052, lcl: -294, lrg: 50, cashClaim: -22966, cashMgmt: -2810, cashPrem: 29000, cashIACF: -4817, ifie: -134 }
  },
  inv: {
    totalAssets: 300000,
    alloc: [
      { cat: '现金及流动性管理工具', r: 0.02, y1: 0.02, y2: 0.02, y3: 0.02 },
      { cat: '固定收益类投资资产', r: 0.60, y1: 0.62, y2: 0.64, y3: 0.66 },
      { cat: '权益类投资资产', r: 0.31, y1: 0.31, y2: 0.31, y3: 0.30 },
      { cat: '投资性房地产', r: 0.03, y1: 0.02, y2: 0.01, y3: 0.01 },
      { cat: '黄金等大宗商品', r: 0.05, y1: 0.04, y2: 0.03, y3: 0.02 },
    ],
    yield: [
      { cat: '现金及流动性管理工具', y1: 0.0018, y2: 0.0933, y3: 0.0054 },
      { cat: '境内固定收益类', y1: 0.0274, y2: 0.0276, y3: 0.0228 },
      { cat: '权益类投资资产', y1: 0.0222, y2: 0.0181, y3: 0.0132 },
      { cat: '投资性房地产', y1: 0.0391, y2: 0.0535, y3: 0.0524 },
      { cat: '黄金等大宗商品', y1: 0.03, y2: 0.03, y3: 0.03 },
    ],
    duration: { dom: 7.4138, ovs: 7.4138 },
    expRatio: { mgmt: 0.02, tax: 0.01 },
  },
  rateCurve: [
    { m: 1, fwd: 0.001000, rate: 0.034315 }, { m: 2, fwd: 0.001005, rate: 0.034315 },
    { m: 3, fwd: 0.001010, rate: 0.034315 }, { m: 6, fwd: 0.001025, rate: 0.034315 },
    { m: 12, fwd: 0.001050, rate: 0.034315 }, { m: 24, fwd: 0.001100, rate: 0.034315 },
    { m: 36, fwd: 0.001150, rate: 0.034315 }, { m: 60, fwd: 0.001250, rate: 0.034315 },
  ],
  cfPattern: { premium: [0.17,0.22,0.22,0.22,0.17,0,0,0,0,0,0,0] },
  calcSteps: [
    { id: 1, name: '选定场景', status: 'pending', desc: '选择压力情景参数' },
    { id: 2, name: '合同组拼接', status: 'pending', desc: '合并现有+新业务' },
    { id: 3, name: '关键假设整理', status: 'pending', desc: '整理合同组假设' },
    { id: 4, name: '利率曲线加工', status: 'pending', desc: '初始确认+即期利率' },
    { id: 5, name: '现金流模式整理', status: 'pending', desc: '保费/IACF/赚取/赔付' },
    { id: 6, name: '新业务预期现金流', status: 'pending', desc: '计算新业务现金流' },
    { id: 7, name: 'PAA计算_新业务', status: 'pending', desc: 'PAA计量新业务' },
    { id: 8, name: '现有业务预期现金流', status: 'pending', desc: '计算现有业务现金流' },
    { id: 9, name: 'PAA计算_现有业务', status: 'pending', desc: 'PAA计量现有业务' },
    { id: 10, name: 'PAA结果汇总', status: 'pending', desc: '汇总新旧业务' },
    { id: 11, name: '输出财务报表', status: 'pending', desc: '生成CAS25报表' },
  ]
};

const C = { blue:'#1677FF', blueL:'#4096FF', green:'#52C41A', greenL:'#73D13D', orange:'#FAAD14', orangeL:'#FFC53D', purple:'#722ED1', purpleL:'#9254DE', red:'#FF4D4F', redL:'#FF7875', gray:'#8C8C8C' };

// 中华保险品牌浅色系配色（多情景对比统一使用，减少颜色混乱、降低视觉压迫）
const CCI_COLORS = [
  '#F08A9A', // 浅红（中华红浅化）
  '#F2D06B', // 浅金（金色浅化）
  '#8FB8E0', // 浅蓝（深蓝浅化）
  '#C9A0A8', // 浅紫红（深红浅化）
  '#A9C4E8', // 浅中蓝（中蓝浅化）
  '#E6C97A', // 浅暗金（暗金浅化）
  '#B9C0CC', // 浅灰
];

// ===== Task #253 全局数据标签插件：在所有结果展示面板的图表上直接绘制数值 =====
// 注意：图表数据在传入时已按显示单位做过除法，因此标签格式化不再二次除单位，
// 直接格式化像素对应的数值，保证与坐标轴一致。
function fmtChartVal(v, d = 2) {
  if (v === null || v === undefined) return '';
  const num = typeof v === 'number' ? v : parseFloat(v);
  if (isNaN(num)) return '';
  return num.toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d });
}
const ifrsDataLabelPlugin = {
  id: 'ifrsDataLabels',
  afterDatasetsDraw(chart, args, opts) {
    if (opts && opts.enabled === false) return;
    const { ctx } = chart;
    const isHorizontal = chart.options.indexAxis === 'y';
    const isStackedBar = chart.options.scales && chart.options.scales.x && chart.options.scales.x.stacked;
    const allLabels = [];
    chart.data.datasets.forEach((dataset, di) => {
      const meta = chart.getDatasetMeta(di);
      if (meta.hidden) return;
      const dsType = dataset.type || chart.config.type;
      const isLine = dsType === 'line';
      const data = dataset.data || [];
      const len = data.length;
      // 折线数据点过多时稀疏标注，避免重叠不可读
      let step = 1;
      if (isLine && len > 16) step = Math.ceil(len / 16);
      for (let i = 0; i < len; i++) {
        if (isLine && step > 1 && i % step !== 0 && i !== len - 1) continue;
        const rawVal = data[i];
        if (rawVal === null || rawVal === undefined) continue;
        const txt = dataset._pct ? (Number(rawVal).toFixed(1) + '%') : fmtChartVal(rawVal);
        const el = meta.data[i];
        if (!el) continue;
        let x = el.x, y = el.y, textAlign = 'center', textBaseline = 'bottom';
        if (isHorizontal) {
          textAlign = rawVal >= 0 ? 'left' : 'right';
          textBaseline = 'middle';
          x = rawVal >= 0 ? el.x + 5 : el.x - 5;
        } else if (isLine) {
          // 多折线标签交错排列：偶数数据集在点上，奇数数据集在点下，并辅以水平错位
          const above = di % 2 === 0;
          textBaseline = above ? 'bottom' : 'top';
          const vOffset = 6 + Math.floor(di / 2) * 12;
          y = above ? el.y - vOffset : el.y + vOffset;
          const hOffset = (di - (chart.data.datasets.length - 1) / 2) * 6;
          x = el.x + hOffset;
        } else if (isStackedBar) {
          // 堆叠柱状图：标签置于分段中心；分段过小时省略
          const bar = el;
          const segHeight = Math.abs(bar.y - bar.base);
          if (segHeight < 14) continue;
          textBaseline = 'middle';
          y = (bar.y + bar.base) / 2;
        } else {
          if (rawVal >= 0) { textBaseline = 'bottom'; y = el.y - 4; }
          else { textBaseline = 'top'; y = el.y + 4; }
        }
        allLabels.push({ x, y, txt, textAlign, textBaseline, val: Math.abs(Number(rawVal) || 0), di, i });
      }
    });
    if (!allLabels.length) return;
    // 按绝对值从大到小排序，优先保留重要数值；相同值按数据集/索引稳定排序
    allLabels.sort((a, b) => b.val - a.val || a.di - b.di || a.i - b.i);
    ctx.save();
    ctx.font = '600 10px -apple-system,"PingFang SC","Microsoft YaHei",sans-serif';
    ctx.fillStyle = '#262626';
    const drawnBoxes = [];
    const PAD = 3;
    function measureBox(lbl) {
      const w = ctx.measureText(lbl.txt).width;
      const h = 10;
      let bx = lbl.x, by = lbl.y;
      if (lbl.textAlign === 'center') bx -= w / 2;
      else if (lbl.textAlign === 'right') bx -= w;
      if (lbl.textBaseline === 'middle') by -= h / 2;
      else if (lbl.textBaseline === 'top') by -= 0;
      else if (lbl.textBaseline === 'bottom') by -= h;
      return { x: bx - PAD, y: by - PAD, w: w + PAD * 2, h: h + PAD * 2 };
    }
    function overlaps(a, b) {
      return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    }
    allLabels.forEach(lbl => {
      const box = measureBox(lbl);
      if (drawnBoxes.some(b => overlaps(box, b))) return;
      ctx.textAlign = lbl.textAlign;
      ctx.textBaseline = lbl.textBaseline;
      ctx.fillText(lbl.txt, lbl.x, lbl.y);
      drawnBoxes.push(box);
    });
    ctx.restore();
  }
};
Chart.register(ifrsDataLabelPlugin);

// 精算险类代码 -> 中文名称映射（根据合同组拼接/预测组名称生成）
const ACTUARIAL_CLASS_NAMES = {
  '32': '交强险',
  '36': '附加险',
  '37': '商业三者险',
  '38': '车损险',
  '101': '企业财产险',
  '102': '货运险',
  '104': '责任险',
  '105': '保证保险',
  '106': '信用保险',
  '107': '特殊风险',
  '108': '家财险',
  '109': '建工险',
  '110': '其他险',
  '111': '船舶险',
  '301': '种植业',
  '302': '养殖业',
  '602': '意外险',
  '603CC': '商业性健康险',
  '603ZD': '大病保险',
  '603ED': '大病保险',
  '603ZX': '其他政策性健康险',
  '999': '其他',
};
function getClassName(code) {
  return ACTUARIAL_CLASS_NAMES[String(code)] || String(code);
}

function fmt(n, d=0) { if(n==null||n===''||n==='-')return '-'; const num=typeof n==='number'?n:parseFloat(n); if(isNaN(num))return '-'; return num.toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d}); }

// 单位感知格式化 (Task #113) — 将元值除以DISPLAY_UNIT后格式化
function fmtU(n, d=2) {
  if(n==null||n===''||n==='-')return '-';
  const num=typeof n==='number'?n:parseFloat(n);
  if(isNaN(num))return '-';
  const scaled = num / DISPLAY_UNIT;
  return scaled.toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
}

// 获取当前单位标签
function unitLabel() {
  const opt = UNIT_OPTIONS.find(o => o.value === DISPLAY_UNIT);
  return opt ? opt.label : '万元';
}

// 生成单位选择器HTML（使用 portal 自定义下拉，规避 webview 中 select 弹层被裁剪的问题）
function unitSelectorHTML() {
  const opts = UNIT_OPTIONS.map(o => ({ value: String(o.value), label: o.label }));
  return `<div style="display:inline-flex;align-items:center;gap:4px;margin-left:auto">
    <span style="font-size:13px;color:var(--text-sec)">显示单位:</span>
    ${renderCustomSelect('displayUnitSel', opts, String(DISPLAY_UNIT), 'displayUnit')}
  </div>`;
}

function setDisplayUnit(val) {
  DISPLAY_UNIT = parseInt(val, 10);
  // 重新渲染当前页面
  const currentPage = document.querySelector('.sidebar-item.active');
  if (currentPage) {
    const page = currentPage.dataset.page;
    if (page) renderPage(page);
  }
}
function fmtP(n, d=1) { if(n==null||n===''||n==='-')return '-'; const num=typeof n==='number'?n:parseFloat(n); if(isNaN(num))return '-'; return (num*100).toFixed(d)+'%'; }
function fmtS(n, d=0) { if(n==null||n===''||n==='-')return '-'; const num=typeof n==='number'?n:parseFloat(n); if(isNaN(num))return '-'; const f=Math.abs(num).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d}); return num<0?'('+f+')':f; }

// 日期格式化: 将各种日期格式转为 YYYY-MM-DD
function fmtDate(val) {
  if (val == null || val === '' || val === '-') return '-';
  // 如果是Excel日期序列号(数字)
  if (typeof val === 'number' && val > 30000 && val < 80000) {
    const date = new Date((val - 25569) * 86400 * 1000);
    const y = date.getUTCFullYear();
    const m = String(date.getUTCMonth() + 1).padStart(2, '0');
    const d = String(date.getUTCDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }
  const str = String(val).trim();
  // 尝试解析 YYYY/M/D, YYYY-M-D, YYYY/MM/DD 等格式
  const m1 = str.match(/^(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})/);
  if (m1) {
    return `${m1[1]}-${m1[2].padStart(2,'0')}-${m1[3].padStart(2,'0')}`;
  }
  // 尝试解析 YYYYMMDD
  const m2 = str.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (m2) {
    return `${m2[1]}-${m2[2]}-${m2[3]}`;
  }
  return str;
}

// 判断列是否为日期列
function isDateColumn(header) {
  if (!header) return false;
  const h = String(header).trim();
  return h === '更新日期' || h === '评估时点';
}

// 预加载的数据
let excelUploadData = {};
let systemDockData = {};

// 验证模块状态
let verifyState = {
  loaded: false,
  fileName: '',
  uploadTime: '',
  sheetData: {},
  comparison: {},
  availablePeriods: [],   // 可选的预测时点（YYYY-MM-DD）
};

// 预测时点筛选（空数组 = 对比全部时点）
let VERIFY_FILTER_PERIODS = [];

// 验证比对选定的情景（空字符串 = 服务端默认，即已上传文件绑定的情景或基础情景 情景0）
let VERIFY_SELECTED_SCENARIO = '';

// 页面标题映射
const pageTitles = {
  'dashboard': { t: '结果总览', b: '结果展示面板 / 结果总览' },
  'excel-upload': { t: 'Excel上传接口', b: '数据输入 / Excel上传接口' },
  'system-dock-upload': { t: '系统对接接口', b: '数据输入 / 系统对接接口' },
  'actual-upload': { t: '预实分析上传', b: '数据输入 / 预实分析上传' },
  // Excel上传数据展示页面
  'sheet-新业务保费收入': { t: '新业务保费收入', b: '数据输入 / Excel上传数据 / 新业务保费收入' },
  'sheet-新业务应收保费减值': { t: '新业务应收保费减值', b: '数据输入 / Excel上传数据 / 新业务应收保费减值' },
  'sheet-新业务跟单获取费用比例': { t: '新业务跟单获取费用比例', b: '数据输入 / Excel上传数据 / 新业务跟单获取费用比例' },
  'sheet-新业务非跟单获取费用比例': { t: '新业务非跟单获取费用比例', b: '数据输入 / Excel上传数据 / 新业务非跟单获取费用比例' },
  'sheet-投资成分比例': { t: '投资成分比例', b: '数据输入 / Excel上传数据 / 投资成分比例' },
  'sheet-预期赔付率': { t: '预期赔付率', b: '数据输入 / Excel上传数据 / 预期赔付率' },
  'sheet-维持费用率': { t: '维持费用率', b: '数据输入 / Excel上传数据 / 维持费用率' },
  'sheet-再保人不履约风险': { t: '再保人不履约风险', b: '数据输入 / Excel上传数据 / 再保人不履约风险' },
  'sheet-预期摊回比例': { t: '预期摊回比例', b: '数据输入 / Excel上传数据 / 预期摊回比例' },
  'sheet-未到期间接理赔费用率': { t: '未到期间接理赔费用率', b: '数据输入 / Excel上传数据 / 未到期间接理赔费用率' },
  'sheet-未决间接理赔费用率': { t: '未决间接理赔费用率', b: '数据输入 / Excel上传数据 / 未决间接理赔费用率' },
  'sheet-风险调整比例': { t: '风险调整比例', b: '数据输入 / Excel上传数据 / 风险调整比例' },
  'sheet-保费现金流模式_新业务': { t: '保费现金流模式_新业务', b: '数据输入 / Excel上传数据 / 保费现金流模式_新业务' },
  'sheet-IACF现金流模式_新业务': { t: 'IACF现金流模式_新业务', b: '数据输入 / Excel上传数据 / IACF现金流模式_新业务' },
  'sheet-未到期赚取模式_新业务': { t: '未到期赚取模式_新业务', b: '数据输入 / Excel上传数据 / 未到期赚取模式_新业务' },
  'sheet-未到期赔付模式': { t: '未到期赔付模式', b: '数据输入 / Excel上传数据 / 未到期赔付模式' },
  'sheet-未决赔付模式': { t: '未决赔付模式', b: '数据输入 / Excel上传数据 / 未决赔付模式' },
  'sheet-实际赔付比例': { t: '实际赔付比例', b: '数据输入 / Excel上传数据 / 实际赔付比例' },
  'sheet-实际维持费用': { t: '实际维持费用', b: '数据输入 / Excel上传数据 / 实际维持费用' },
  'sheet-其他输入项': { t: '其他输入项', b: '数据输入 / Excel上传数据 / 其他输入项' },
  // 系统对接数据展示页面
  'sheet-合同组关键假设_现有业务': { t: '合同组关键假设_现有业务', b: '数据输入 / 系统对接数据 / 合同组关键假设_现有业务' },
  'sheet-系统期初余额表': { t: '系统期初余额表', b: '数据输入 / 系统对接数据 / 系统期初余额表' },
  'sheet-基本信息': { t: '基本信息', b: '数据输入 / 系统对接数据 / 基本信息' },
  'sheet-对应关系配置表': { t: '对应关系配置表', b: '数据输入 / 系统对接数据 / 对应关系配置表' },
  'sheet-压力情景配置表': { t: '压力情景配置表', b: '数据输入 / 系统对接数据 / 压力情景配置表' },
  'sheet-保费现金流模式_现有业务': { t: '保费现金流模式_现有业务', b: '数据输入 / 系统对接数据 / 保费现金流模式_现有业务' },
  'sheet-IACF现金流模式_现有业务': { t: 'IACF现金流模式_现有业务', b: '数据输入 / 系统对接数据 / IACF现金流模式_现有业务' },
  'sheet-未到期赚取模式_现有业务': { t: '未到期赚取模式_现有业务', b: '数据输入 / 系统对接数据 / 未到期赚取模式_现有业务' },
  'sheet-财务报表实际数': { t: '财务报表实际数', b: '数据输入 / 系统对接数据 / 财务报表实际数' },
  'sheet-初始确认利率曲线': { t: '初始确认利率曲线', b: '数据输入 / 系统对接数据 / 初始确认利率曲线' },
  'sheet-即期利率曲线': { t: '即期利率曲线', b: '数据输入 / 系统对接数据 / 即期利率曲线' },
  // 计算页面
  'calc-pipeline': { t: '计算流程', b: '计算 / 计算流程' },
  'input-processing': { t: '输入整理', b: '计算 / 输入整理' },
  'new-business-calc': { t: '新业务计量', b: '计算 / 新业务计量' },
  'existing-business-calc': { t: '现有业务计量', b: '计算 / 现有业务计量' },
  // 结果展示面板
  'dashboard': { t: '结果总览', b: '结果展示面板 / 结果总览' },
  'financial-statements': { t: '输出财务报表', b: '结果展示面板 / 输出财务报表' },
  'sub-class-profit': { t: '分险种利润表', b: '结果展示面板 / 分险种利润表' },
  'scenario-compare': { t: '多情景比对', b: '结果展示面板 / 多情景比对' },
  'old-new-bridge': { t: '新旧预测比对', b: '结果展示面板 / 新旧预测比对' },
  'actual-vs-expected': { t: '预实分析', b: '结果展示面板 / 预实分析' },
  // 计量结果输出
  'paa-summary': { t: '计量结果输出', b: '计量结果输出 / 六张结果表' },
  // 验证页面
  'verify-upload': { t: '验证文件上传', b: '验证 / 验证文件上传' },
  'verify-check': { t: '验证核对结果', b: '验证 / 验证核对结果' },
  'verify-results': { t: '差异比对结果', b: '验证 / 差异比对结果' },
  // 数据及逻辑归集
  'data-logic-collection': { t: '数据及逻辑归集', b: '数据及逻辑归集' },
  // 系统管理
  'deploy-manage': { t: '部署管理', b: '系统管理 / 部署管理' },
  'system-log': { t: '系统运行日志', b: '系统管理 / 系统运行日志' },
  'sql-query': { t: 'SQL 查询', b: '系统管理 / SQL 查询' },
  'table-dict': { t: '数据表字典', b: '系统管理 / 数据表字典' },
};

const charts = {};
let _scpIndicatorTimer = null;  // 分险种利润表指标图表的挂起 setTimeout，避免重复渲染时多实例抢占同一 canvas
function destroyCharts() {
  if (_scpIndicatorTimer) { clearTimeout(_scpIndicatorTimer); _scpIndicatorTimer = null; }
  Object.values(charts).forEach(c=>{try{c.destroy()}catch(e){}});
  Object.keys(charts).forEach(k=>delete charts[k]);
}
// 安全创建图表：若同一 key 已存在实例则先销毁，防止 "Canvas already in use"
function safeChart(key, canvasEl, config) {
  if (!canvasEl) return null;
  // 柱状图柱子宽度统一收窄为原来的 2/3（默认 barPercentage=0.9 → 0.6）
  if (config && config.type === 'bar') {
    config.options = config.options || {};
    config.options.scales = config.options.scales || {};
    config.options.scales.x = config.options.scales.x || {};
    if (config.options.scales.x.barPercentage === undefined) {
      config.options.scales.x.barPercentage = 0.6;
    }
  }
  // 折线图：①首尾数据点不紧贴 Y 轴（x.offset=true）；②Y 轴按数据范围上下各留 12% 余量。
  // 必须克隆 top-level scale 对象，避免污染共享的 scaleOpts（否则 offset/留白会串到柱状图）。
  if (config && config.type === 'line') {
    config.options = config.options || {};
    const srcScales = config.options.scales || {};
    const newScales = {};
    // X 轴：克隆 x 并强制 offset=true（不影响共享对象）
    newScales.x = Object.assign({}, srcScales.x || {}, { offset: true });
    // Y 轴：克隆 y（保留 ticks 等原配置）；若调用方已显式设定 min/max/beginAtZero 则跳过留白
    newScales.y = Object.assign({}, srcScales.y || {});
    const yExplicit = srcScales.y && (srcScales.y.min !== undefined || srcScales.y.max !== undefined || srcScales.y.beginAtZero !== undefined);
    if (!yExplicit) {
      const vals = [];
      (config.data && config.data.datasets || []).forEach(ds => {
        (ds.data || []).forEach(v => { if (typeof v === 'number' && isFinite(v)) vals.push(v); });
      });
      if (vals.length) {
        let lo = Math.min.apply(null, vals);
        let hi = Math.max.apply(null, vals);
        if (lo === hi) { const d = Math.abs(lo) || 1; lo -= d * 0.1; hi += d * 0.1; }
        const span = (hi - lo) || Math.abs(hi) || 1;
        const p = span * 0.12;
        newScales.y.suggestedMin = lo - p;
        newScales.y.suggestedMax = hi + p;
      }
    }
    config.options.scales = newScales;
  }
  if (charts[key]) { try { charts[key].destroy(); } catch(e){} delete charts[key]; }
  charts[key] = new Chart(canvasEl, config);
  return charts[key];
}

function toggleSidebar() { document.getElementById('sidebar').classList.toggle('collapsed'); }

// 侧边栏配置
const SIDEBAR_CONFIG = {
  results: [
    { page: 'dashboard', icon: '📊', label: '结果总览' },
    { page: 'financial-statements', icon: '📰', label: '输出财务报表' },
    { page: 'sub-class-profit', icon: '🏷️', label: '分险种利润表' },
    { page: 'scenario-compare', icon: '🔀', label: '多情景比对' },
    { page: 'old-new-bridge', icon: '⚖️', label: '新旧预测比对' },
    { page: 'actual-vs-expected', icon: '📈', label: '预实分析' },
  ],
  dataLogic: [
    { page: 'data-logic-collection', icon: '🧩', label: '数据及逻辑归集' },
  ],
  dataInput: {
    top: [
      { page: 'excel-upload', icon: '📤', label: 'Excel上传接口' },
      { page: 'system-dock-upload', icon: '🔗', label: '系统对接接口' },
      { page: 'actual-upload', icon: '📥', label: '预实分析上传' },
    ],
    excelSheets: Object.keys(EXCEL_UPLOAD_SPECS),
    dockSheets: Object.keys(SYSTEM_DOCK_SPECS),
  },
  calc: [
    { page: 'calc-pipeline', icon: '⚙️', label: '计算流程' },
    { page: 'input-processing', icon: '🔄', label: '输入整理' },
    { page: 'new-business-calc', icon: '🆕', label: '新业务计量' },
    { page: 'existing-business-calc', icon: '📦', label: '现有业务计量' },
  ],
  output: [
    { page: 'paa-summary', icon: '📋', label: '计量结果输出' },
  ],
  verify: [
    { page: 'verify-upload', icon: '🔍', label: '验证文件上传' },
    { page: 'verify-check', icon: '⚖️', label: '验证核对结果' },
    { page: 'verify-results', icon: '📊', label: '差异比对结果' },
  ],
  system: [
    { page: 'deploy-manage', icon: '🚀', label: '部署管理' },
    { page: 'system-log', icon: '📝', label: '系统运行日志' },
    { page: 'sql-query', icon: '🗄️', label: 'SQL 查询' },
    { page: 'table-dict', icon: '📑', label: '数据表字典' },
  ],
};

function getSheetStatus(sheetName, source) {
  const data = source === 'excel' ? excelUploadData : systemDockData;
  if (!data || !data[sheetName]) return { loaded: false, rowCount: 0 };
  return { loaded: true, rowCount: data[sheetName].totalRows || 0 };
}

function getUploadStatus(source) {
  const state = source === 'excel' ? excelUploadState : systemDockState;
  if (!state || !state.loaded) return 'not-loaded';
  return state.success ? 'loaded' : 'error';
}

function hasUploadedData() {
  // 检查上传状态
  const hasExcelState = excelUploadState && excelUploadState.loaded && excelUploadState.success;
  const hasDockState = systemDockState && systemDockState.loaded && systemDockState.success;
  // 检查从数据库加载的数据
  const hasExcelData = excelUploadData && Object.keys(excelUploadData).length > 0;
  const hasDockData = systemDockData && Object.keys(systemDockData).length > 0;
  return hasExcelState || hasDockState || hasExcelData || hasDockData;
}

function isViewer() {
  // 仅查看权限账号：后端注入 is_viewer = 拥有 can_view_all 但不具备 can_upload 且非管理员
  const u = window.DJANGO_USER;
  return !!(u && u.is_authenticated && u.is_viewer);
}

function getEmptyDataMessage() {
  const uploadBtns = isViewer() ? '' : `
    <div style="display:flex;gap:12px;justify-content:center;">
      <button class="btn btn-primary" onclick="renderPage('excel-upload')">上传 Excel 数据</button>
      <button class="btn btn-outline" onclick="renderPage('system-dock-upload')">上传系统对接数据</button>
    </div>`;
  return `
  <div class="empty-data-message" style="padding:48px 24px;text-align:center;background:var(--card-bg);border:1px dashed var(--border);border-radius:var(--radius);margin:24px 0;">
    <div style="font-size:48px;margin-bottom:16px;">📭</div>
    <h3 style="color:var(--text);margin-bottom:8px;">暂无数据</h3>
    <p style="color:var(--text-sec);margin-bottom:24px;">${isViewer() ? '系统当前暂无可用数据，请联系管理员上传并计算结果。' : '系统尚未检测到上传数据，请先通过左侧导航栏上传 Excel 数据或系统对接数据后再查看。'}</p>
    ${uploadBtns}
  </div>`;
}

// ===== PAA计算相关函数 =====

async function fetchScenarios() {
  try {
    const resp = await fetch('/api/calc/scenarios');
    const data = await resp.json();
    CALC_SCENARIOS = data.scenarios || [];
    return data;
  } catch (e) {
    console.error('获取场景失败:', e);
    return { scenarios: [], hasData: false };
  }
}

// 多场景选择切换 (Task #111)
function toggleScenario(value) {
  if (!window.MULTI_SELECTED_SCENARIOS) {
    window.MULTI_SELECTED_SCENARIOS = new Set();
  }
  window.SCENARIOS_MANUALLY_TOUCHED = true;
  if (window.MULTI_SELECTED_SCENARIOS.has(value)) {
    window.MULTI_SELECTED_SCENARIOS.delete(value);
  } else {
    window.MULTI_SELECTED_SCENARIOS.add(value);
  }
  // 更新计数
  const countEl = document.getElementById('scenario-count');
  if (countEl) countEl.textContent = window.MULTI_SELECTED_SCENARIOS.size;
}

// 多场景并行计算 (Task #111)
async function runMultiScenarioCalculation() {
  if (CALC_RUNNING) return;
  const scenarios = [...(window.MULTI_SELECTED_SCENARIOS || [])];
  if (scenarios.length === 0) {
    alert('请至少选择一个场景');
    return;
  }

  CALC_RUNNING = true;
  const csrfToken = window.CSRF_TOKEN || '';
  const btn = document.getElementById('calc-run-btn');
  const logEl = document.getElementById('calc-log');
  const stepEls = document.querySelectorAll('.pipeline-circle');

  const fpSelect = document.getElementById('forecast-periods-select');
  const forecastPeriods = fpSelect ? parseInt(fpSelect.value, 10) : null;

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner"></span> 计算中...';
  }

  // 重置步骤状态
  MODEL_DATA.calcSteps.forEach(s => s.status = 'pending');
  stepEls.forEach(el => { if (el) { el.className = 'pipeline-circle pending'; el.innerHTML = '\u2022'; } });

  if (logEl) logEl.innerHTML = '';

  // 依次执行每个场景（后台计算 + 实时进度条）
  for (let si = 0; si < scenarios.length; si++) {
    const scenario = scenarios[si];
    if (logEl) {
      logEl.innerHTML += `<div class="log-line info" style="font-weight:600">[${new Date().toLocaleTimeString()}] ===== 开始计算场景 ${si+1}/${scenarios.length}: ${scenario} =====</div>`;
      logEl.scrollTop = logEl.scrollHeight;
    }

    try {
      const data = await startCalcWithProgress(scenario, forecastPeriods);

      if (data.success) {
        // 存储到结果映射
        CALC_RESULTS_MAP[scenario] = data;
        // 最后一个场景的结果设为当前活动结果
        if (si === scenarios.length - 1) {
          CALC_RESULT = data;
        }

        if (logEl && data.calcLogs) {
          data.calcLogs.forEach(line => {
            const cls = line.includes('错误') ? 'error' : (line.includes('完成') ? 'success' : 'info');
            logEl.innerHTML += `<div class="log-line ${cls}">[${new Date().toLocaleTimeString()}] [${scenario}] ${line}</div>`;
          });
          logEl.scrollTop = logEl.scrollHeight;
        }

        if (logEl) {
          logEl.innerHTML += `<div class="log-line success">[${new Date().toLocaleTimeString()}] [${scenario}] 场景计算完成 ✓</div>`;
          logEl.scrollTop = logEl.scrollHeight;
        }
      } else {
        if (logEl) {
          logEl.innerHTML += `<div class="log-line error">[${new Date().toLocaleTimeString()}] [${scenario}] 计算失败: ${data.error || '未知错误'}</div>`;
          logEl.scrollTop = logEl.scrollHeight;
        }
      }
    } catch (e) {
      if (logEl) {
        logEl.innerHTML += `<div class="log-line error">[${new Date().toLocaleTimeString()}] [${scenario}] 请求异常: ${e.message}</div>`;
        logEl.scrollTop = logEl.scrollHeight;
      }
    }
  }

  // 显示结果摘要
  if (CALC_RESULT && CALC_RESULT.success) {
    const summaryEl = document.getElementById('calc-summary');
    if (summaryEl) { summaryEl.style.display = 'block'; summaryEl.innerHTML = renderCalcSummary(CALC_RESULT); }
    const inputEl = document.getElementById('calc-input-organized');
    if (inputEl && CALC_RESULT.inputOrganized) { inputEl.style.display = 'block'; inputEl.innerHTML = renderInputOrganized(CALC_RESULT.inputOrganized); }
  }

  if (btn) { btn.disabled = false; btn.innerHTML = '\u25B6 重新计算'; btn.classList.add('btn-success'); }
  CALC_RUNNING = false;
}

// 将 ISO 时间字符串格式化为本地时间（YYYY-MM-DD HH:mm:ss）
function formatLocalDateTime(isoString) {
  if (!isoString) return '-';
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return isoString;
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// 渲染指定版本推进入库任务的进度条（全局状态驱动，切页后可恢复）
function renderVersionPushStatus(taskKey) {
  const statusEl = document.getElementById('version-push-status');
  if (!statusEl) return;
  const task = window.VERSION_PUSH_TASKS ? window.VERSION_PUSH_TASKS[taskKey] : null;
  if (!task) return;
  const total = task.total || 0;
  const current = task.current || 0;
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  const color = task.status === 'error' ? 'var(--danger,#e54d42)' : (task.status === 'done' ? 'var(--success,#1a9e57)' : 'var(--primary,#1677ff)');
  const icon = task.status === 'error' ? '✗' : (task.status === 'done' ? '✓' : '⏳');
  statusEl.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;color:${color};font-size:12px;margin-bottom:4px">${icon} ${task.message || '入库中...'}</div>
    <div style="width:100%;height:8px;background:var(--border);border-radius:4px;overflow:hidden">
      <div style="width:${pct}%;height:100%;background:${color};transition:width .3s"></div>
    </div>
    <div style="font-size:11px;color:var(--text-sec);margin-top:2px">${current}/${total} 个情景 ${task.scenario ? '(' + task.scenario + ')' : ''}</div>`;
}

// 轮询版本推进入库任务进度
function pollVersionPushStatus(taskKey, nameHint) {
  window.VERSION_PUSH_POLLERS = window.VERSION_PUSH_POLLERS || {};
  if (window.VERSION_PUSH_POLLERS[taskKey]) {
    clearInterval(window.VERSION_PUSH_POLLERS[taskKey]);
  }
  const doPoll = async () => {
    try {
      const resp = await fetch(`/api/calc/push-version-status?task=${encodeURIComponent(taskKey)}`);
      const data = await resp.json();
      if (data.success && data.task) {
        window.VERSION_PUSH_TASKS[taskKey] = Object.assign(
          window.VERSION_PUSH_TASKS[taskKey] || {}, data.task
        );
        renderVersionPushStatus(taskKey);
        if (data.task.finished) {
          clearInterval(window.VERSION_PUSH_POLLERS[taskKey]);
          delete window.VERSION_PUSH_POLLERS[taskKey];
          loadCalcVersions();
        }
      }
    } catch (e) {
      console.error('version push poll error', e);
    }
  };
  doPoll();
  window.VERSION_PUSH_POLLERS[taskKey] = setInterval(doPoll, 800);
}

// 进入计算流程页时，恢复正在运行的版本推进入库进度显示
function resumeVersionPushIfRunning() {
  window.VERSION_PUSH_POLLERS = window.VERSION_PUSH_POLLERS || {};
  window.VERSION_PUSH_TASKS = window.VERSION_PUSH_TASKS || {};
  Object.keys(window.VERSION_PUSH_TASKS).forEach(taskKey => {
    const t = window.VERSION_PUSH_TASKS[taskKey];
    if (!t.finished && !window.VERSION_PUSH_POLLERS[taskKey]) {
      renderVersionPushStatus(taskKey);
      pollVersionPushStatus(taskKey, t.name);
    } else {
      renderVersionPushStatus(taskKey);
    }
  });
}

// 将当前计算结果（全部已计算情景）作为版本推入 MySQL（异步，支持进度条）
async function pushCalcVersion() {
  const nameEl = document.getElementById('version-name');
  const statusEl = document.getElementById('version-push-status');
  const csrfToken = window.CSRF_TOKEN || '';
  const nameHint = nameEl ? nameEl.value.trim() : '';
  if (statusEl) statusEl.innerHTML = '<span style="color:var(--text-sec)">启动入库任务...</span>';
  try {
    const resp = await fetch('/api/calc/push-version', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body: JSON.stringify({ name: nameHint }),
    });
    const data = await resp.json();
    if (data.success) {
      window.VERSION_PUSH_TASKS = window.VERSION_PUSH_TASKS || {};
      window.VERSION_PUSH_TASKS[data.task] = {
        name: data.name,
        versionId: data.version_id,
        status: 'pending',
        total: data.scenario_count,
        current: 0,
        message: '等待开始...',
        finished: false,
      };
      renderVersionPushStatus(data.task);
      pollVersionPushStatus(data.task, data.name);
    } else {
      if (statusEl) statusEl.innerHTML = `<span style="color:var(--danger,#e54d42)">✗ ${data.error || '入库失败'}</span>`;
    }
  } catch (e) {
    if (statusEl) statusEl.innerHTML = `<span style="color:var(--danger,#e54d42)">✗ 请求异常: ${e.message}</span>`;
  }
}

// 拉取已入库计算版本列表（时间显示为本地时间）
async function loadCalcVersions() {
  const el = document.getElementById('calc-versions-list');
  if (!el) return;
  try {
    const resp = await fetch('/api/calc/versions');
    const data = await resp.json();
    if (!data.success || !data.versions.length) {
      el.innerHTML = '<span style="color:var(--text-sec)">暂无已入库版本，计算完成后点击「推入数据库」保存。</span>';
      return;
    }
    el.innerHTML = data.versions.map(v => `
      <div style="display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)">
        <div>
          <strong>#${v.id} ${v.name}</strong>
          <div style="font-size:12px;color:var(--text-sec)">${v.scenario_count} 个情景 · ${v.snapshot_count} 个快照 · ${v.status === 'published' ? '已发布' : '草稿'} · 创建人 ${v.created_by} · ${formatLocalDateTime(v.created_at)}</div>
          <div style="font-size:12px;color:var(--text-sec)">情景: ${v.scenarios.join('、')}</div>
        </div>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = `<span style="color:var(--danger,#e54d42)">加载失败: ${e.message}</span>`;
  }
}

// ===== 系统运行日志页面 =====
function renderSystemLogPage() {
  const actionOpts = [
    '<option value="">全部操作</option>',
    '<option value="login">登录</option>',
    '<option value="logout">登出</option>',
    '<option value="upload">数据上传</option>',
    '<option value="calc_run">触发计算</option>',
    '<option value="calc_done">计算完成</option>',
    '<option value="calc_fail">计算失败</option>',
    '<option value="export">导出</option>',
    '<option value="deploy">部署</option>',
    '<option value="version_push">版本入库</option>',
    '<option value="sql_query">SQL查询</option>',
  ].join('');
  const levelOpts = [
    '<option value="">全部级别</option>',
    '<option value="INFO">信息</option>',
    '<option value="WARN">警告</option>',
    '<option value="ERROR">错误</option>',
  ].join('');
  return `
<div class="page active">
  <div class="page-header"><h2>系统运行日志</h2><p>记录系统每一步操作（登录 / 上传 / 计算 / 导出 / 部署 / 查询等）</p></div>
  <div class="card"><div class="card-body">
    <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:12px">
      <div><label style="display:block;font-size:12px;color:var(--text-sec)">操作类型</label>
        <select id="log-action" class="form-control" style="min-width:140px" onchange="loadSystemLog()">${actionOpts}</select></div>
      <div><label style="display:block;font-size:12px;color:var(--text-sec)">级别</label>
        <select id="log-level" class="form-control" style="min-width:120px" onchange="loadSystemLog()">${levelOpts}</select></div>
      <div><label style="display:block;font-size:12px;color:var(--text-sec)">关键词</label>
        <input id="log-q" class="form-control" placeholder="用户/对象/详情" style="min-width:180px" onkeydown="if(event.key==='Enter')loadSystemLog()"></div>
      <div><label style="display:block;font-size:12px;color:var(--text-sec)">起始日期</label>
        <input id="log-date-from" type="date" class="form-control" style="min-width:140px" onchange="loadSystemLog()"></div>
      <div><label style="display:block;font-size:12px;color:var(--text-sec)">结束日期</label>
        <input id="log-date-to" type="date" class="form-control" style="min-width:140px" onchange="loadSystemLog()"></div>
      <button class="btn btn-primary" onclick="loadSystemLog()">查询</button>
      <button class="btn btn-outline" onclick="document.getElementById('log-action').value='';document.getElementById('log-level').value='';document.getElementById('log-q').value='';document.getElementById('log-date-from').value='';document.getElementById('log-date-to').value='';loadSystemLog()">重置</button>
      <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text-sec);cursor:pointer">
        <input type="checkbox" id="log-autorefresh" onchange="toggleLogAutoRefresh()"> 自动刷新(5s)</label>
    </div>
    <div id="log-total" style="font-size:13px;color:var(--text-sec);margin-bottom:8px"></div>
    <div class="table-wrapper">
      <table class="data-table">
        <thead><tr><th style="width:160px">操作时间</th><th style="width:90px">用户</th><th style="width:100px">操作</th><th>对象</th><th>详情</th><th style="width:70px">级别</th><th style="width:110px">IP</th></tr></thead>
        <tbody id="log-tbody"><tr><td colspan="7" style="text-align:center;color:var(--text-sec)">加载中…</td></tr></tbody>
      </table>
    </div>
    <div id="log-pager" style="display:flex;gap:8px;justify-content:flex-end;align-items:center;margin-top:12px;font-size:13px"></div>
  </div></div>
</div>`;
}

let _LOG_PAGE = 1;
let _LOG_AUTOREFRESH_TIMER = null;
function toggleLogAutoRefresh() {
  const cb = document.getElementById('log-autorefresh');
  if (_LOG_AUTOREFRESH_TIMER) { clearInterval(_LOG_AUTOREFRESH_TIMER); _LOG_AUTOREFRESH_TIMER = null; }
  if (cb && cb.checked) {
    _LOG_AUTOREFRESH_TIMER = setInterval(() => { if (CURRENT_PAGE === 'system-log') loadSystemLog(true); }, 5000);
  }
}

async function loadSystemLog(silent) {
  const tbody = document.getElementById('log-tbody');
  const totalEl = document.getElementById('log-total');
  const pager = document.getElementById('log-pager');
  if (!tbody) return;
  if (!silent) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-sec)">加载中…</td></tr>';
  const action = (document.getElementById('log-action') || {}).value || '';
  const level = (document.getElementById('log-level') || {}).value || '';
  const q = (document.getElementById('log-q') || {}).value || '';
  const df = (document.getElementById('log-date-from') || {}).value || '';
  const dt = (document.getElementById('log-date-to') || {}).value || '';
  const params = new URLSearchParams({ page: _LOG_PAGE, page_size: 50, action, level, q, date_from: df, date_to: dt });
  try {
    const resp = await fetch('/api/system/log?' + params.toString());
    const data = await resp.json();
    if (!data.success) { tbody.innerHTML = `<tr><td colspan="7" style="color:var(--danger,#e54d42)">${data.error||'加载失败'}</td></tr>`; return; }
    if (totalEl) totalEl.textContent = `共 ${data.total} 条记录`;
    if (!data.logs.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-sec)">暂无日志记录</td></tr>';
    } else {
      const levelCls = { INFO: 'done', WARN: 'pending', ERROR: 'running' };
      tbody.innerHTML = data.logs.map(r => `
        <tr>
          <td style="white-space:nowrap">${r.created_at}</td>
          <td>${r.username}</td>
          <td>${r.action_label}</td>
          <td title="${r.target}">${r.target || '-'}</td>
          <td title="${r.detail}" style="max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.detail || '-'}</td>
          <td><span class="status-tag ${levelCls[r.level]||'pending'}">${r.level}</span></td>
          <td>${r.ip || '-'}</td>
        </tr>`).join('');
    }
    // 分页
    const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
    if (pager) {
      pager.innerHTML = `第 ${data.page}/${totalPages} 页 ` +
        `<button class="btn btn-outline btn-sm" ${data.page<=1?'disabled':''} onclick="_LOG_PAGE=${data.page-1};loadSystemLog()">上一页</button> ` +
        `<button class="btn btn-outline btn-sm" ${data.page>=totalPages?'disabled':''} onclick="_LOG_PAGE=${data.page+1};loadSystemLog()">下一页</button>`;
    }
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="color:var(--danger,#e54d42)">请求异常: ${e.message}</td></tr>`;
  }
}

// ===== SQL 查询页面 =====
function renderSqlQueryPage() {
  const isAdmin = window.DJANGO_USER && (window.DJANGO_USER.is_admin || window.DJANGO_USER.is_staff);
  if (!isAdmin) {
    return `
<div class="page active">
  <div class="page-header"><h2>SQL 查询</h2><p>通过代码窗口查询 MySQL 数据库</p></div>
  <div class="alert alert-warning"><strong>权限不足：</strong>SQL 查询仅对管理员（admin）开放，请联系系统管理员。</div>
</div>`;
  }
  return `
<div class="page active">
  <div class="page-header"><h2>SQL 查询</h2><p>只读查询 MySQL 数据库（仅 SELECT / WITH / SHOW / EXPLAIN / DESCRIBE，上限 1000 行，所有查询记入运行日志）</p></div>
  <div class="card"><div class="card-body">
    <div style="display:flex;gap:8px;align-items:flex-start;margin-bottom:10px">
      <textarea id="sql-editor" spellcheck="false" placeholder="例如：&#10;SELECT * FROM ifrs17_upload_record ORDER BY upload_time DESC LIMIT 20;&#10;SHOW TABLES;&#10;SELECT scenario, COUNT(*) FROM ifrs17_calc_snapshot GROUP BY scenario;"
        style="flex:1;min-height:160px;font-family:monospace;font-size:13px;padding:12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg);color:var(--text);resize:vertical"></textarea>
    </div>
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:12px">
      <button class="btn btn-primary" onclick="runSqlQuery()">▶ 执行查询</button>
      <button class="btn btn-outline" onclick="document.getElementById('sql-editor').value=''">清空</button>
      <button class="btn btn-outline btn-sm" onclick="insertSqlTemplate()">示例模板</button>
      <span id="sql-status" style="font-size:13px;color:var(--text-sec)"></span>
    </div>
    <div id="sql-result"></div>
  </div></div>
</div>`;
}

function insertSqlTemplate() {
  const ta = document.getElementById('sql-editor');
  if (ta) ta.value = "SELECT * FROM ifrs17_upload_record ORDER BY upload_time DESC LIMIT 20;";
}

async function runSqlQuery() {
  const ta = document.getElementById('sql-editor');
  const statusEl = document.getElementById('sql-status');
  const resultEl = document.getElementById('sql-result');
  if (!ta || !ta.value.trim()) { if (statusEl) statusEl.textContent = '请输入 SQL'; return; }
  if (statusEl) statusEl.textContent = '执行中…';
  if (resultEl) resultEl.innerHTML = '';
  const csrfToken = window.CSRF_TOKEN || '';
  try {
    const resp = await fetch('/api/system/sql-query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body: JSON.stringify({ sql: ta.value }),
    });
    const data = await resp.json();
    if (data.success) {
      if (statusEl) statusEl.textContent = data.note || '执行成功';
      if (resultEl) {
        if (!data.columns.length) {
          resultEl.innerHTML = `<div class="alert alert-info">${data.note || '执行成功（无结果集）'}</div>`;
        } else {
          const head = data.columns.map(c => `<th>${c}</th>`).join('');
          const rows = data.rows.map(r => `<tr>${r.map(v => `<td>${v===null?'<span style="color:var(--text-sec)">NULL</span>':v}</td>`).join('')}</tr>`).join('');
          resultEl.innerHTML = `
            <div class="table-wrapper">
              <table class="data-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>
            </div>
            <div style="font-size:12px;color:var(--text-sec);margin-top:6px">${data.note}</div>`;
        }
      }
    } else {
      if (statusEl) statusEl.innerHTML = `<span style="color:var(--danger,#e54d42)">${data.error || '执行失败'}</span>`;
    }
  } catch (e) {
    if (statusEl) statusEl.innerHTML = `<span style="color:var(--danger,#e54d42)">请求异常: ${e.message}</span>`;
  }
}

function initSqlQueryEvents() { /* 当前无需额外绑定，按钮已内联 onclick */ }

// 从数据表字典携带模板跳转到 SQL 查询页
let PENDING_SQL_TEMPLATE = '';
function openSqlQueryWithTemplate(template) {
  if (template === undefined || template === null) template = '';
  PENDING_SQL_TEMPLATE = template;
  renderPage('sql-query');
}

// ===== 数据表字典（中英文表名对照） =====

function renderTableDictPage() {
  return `
<div class="page active">
  <div class="page-header">
    <h2>数据表字典</h2>
    <p>系统落表的数据表 中文名 ↔ 英文表名 对照。<br/>
    <b>输入数据表</b>共 35 张，每张均按英文表名一一对应独立物理表落库（每列即 Excel 真实列，无 JSON 聚合）；<b>计算结果数据表</b>同样按英文表名对应独立物理表；<b>系统基础物理表</b>为 Django 内部表。四类表均可用 SQL 查询窗口直接 <code>SELECT * FROM 英文表名</code>。</p>
  </div>
  <div id="table-dict-loading" style="color:var(--text-sec);padding:12px">加载中…</div>
  <div id="table-dict-content" style="display:none">
    <div class="card"><div class="card-header"><h3>① 输入数据表（<span id="td-input-count">0</span> 张）</h3></div>
      <div class="card-body" style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">序号</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">中文表名</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">英文表名</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">分类</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">来源</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">落库物理表</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">操作</th>
          </tr></thead>
          <tbody id="td-input-body"></tbody>
        </table>
      </div></div>
    <div class="card"><div class="card-header"><h3>② 计算结果数据表（<span id="td-output-count">0</span> 张 · 每张含字段结构）</h3></div>
      <div class="card-body" style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">序号</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">中文表名</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">英文表名（物理表名）</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">分类</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">落库物理表</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">操作</th>
          </tr></thead>
          <tbody id="td-output-body"></tbody>
        </table>
      </div></div>
    <div class="card"><div class="card-header"><h3>③ 系统基础物理表（<span id="td-system-count">0</span> 张）</h3></div>
      <div class="card-body" style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">序号</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">中文含义</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">英文表名（db_table）</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">说明</th>
            <th style="text-align:left;padding:8px;border-bottom:2px solid var(--border)">操作</th>
          </tr></thead>
          <tbody id="td-system-body"></tbody>
        </table>
      </div></div>
  </div>
</div>`;
}

async function loadTableDict() {
  const loadingEl = document.getElementById('table-dict-loading');
  const contentEl = document.getElementById('table-dict-content');
  try {
    const resp = await fetch('/api/system/table-dict');
    const data = await resp.json();
    if (!data.success) {
      if (loadingEl) loadingEl.textContent = '加载失败: ' + (data.error || '未知错误');
      return;
    }
    const d = data.data;
    const setRows = (tbodyId, rows, cols) => {
      const tb = document.getElementById(tbodyId);
      if (!tb) return;
      tb.innerHTML = rows.map((r, i) => `<tr style="border-bottom:1px solid var(--border)">${cols(r, i + 1)}</tr>`).join('');
    };
    // 输入表：主行 + 字段结构明细行（展示真实列名，证明无 JSON 聚合字段）
    const inBody = document.getElementById('td-input-body');
    if (inBody) {
      inBody.innerHTML = d.input_tables.map((r, i) => {
        const tpl = (r.query_template || '')
          .replace(/\\/g, '\\\\')
          .replace(/'/g, "\\'")
          .replace(/"/g, '&quot;')
          .replace(/\n/g, '\\n')
          .replace(/\r/g, '\\r');
        const cols = (r.columns || []);
        const chips = cols.length
          ? cols.map(c => `<span style="display:inline-block;background:#eef2ff;color:#1677ff;border:1px solid #d6e4ff;border-radius:4px;padding:1px 6px;font-size:11px;margin:2px;font-family:monospace" title="${c.label}">${c.name}</span>`).join('')
          : '<span style="color:var(--text-sec)">—</span>';
        return `
        <tr style="border-bottom:1px solid var(--border)">
          <td style="padding:8px">${i + 1}</td>
          <td style="padding:8px;font-weight:600">${r.cn}</td>
          <td style="padding:8px;color:var(--primary,#1677ff);font-family:monospace">${r.en}</td>
          <td style="padding:8px;color:var(--text-sec)">${r.category}</td>
          <td style="padding:8px;color:var(--text-sec)">${r.kind}</td>
          <td style="padding:8px;color:var(--text-sec);font-family:monospace">${r.db_table}</td>
          <td style="padding:8px">
            <span style="display:inline-block;background:var(--success-bg,#f6ffed);color:var(--success,#389e0d);border:1px solid var(--success,#389e0d);border-radius:4px;padding:1px 6px;font-size:12px;margin-right:6px">物理表</span>
            <button class="btn btn-sm" style="padding:2px 8px;font-size:12px" onclick="openSqlQueryWithTemplate('${tpl}')">查询</button>
          </td>
        </tr>
        <tr style="border-bottom:1px solid var(--border);background:var(--bg-sub,#fafafa)">
          <td style="padding:6px 8px" colspan="7">
            <div style="font-size:12px;color:var(--text-sec);margin-bottom:4px"><b>字段结构（${cols.length} 列 · 无 JSON 聚合字段）</b></div>
            <div style="max-height:150px;overflow-y:auto;line-height:1.9">${chips}</div>
          </td>
        </tr>`;
      }).join('');
    }
    // 输出表：主行 + 字段结构明细行（展示真实列名，证明无 JSON 聚合字段）
    const outBody = document.getElementById('td-output-body');
    if (outBody) {
      outBody.innerHTML = d.output_tables.map((r, i) => {
        const tpl = (r.query_template || '')
          .replace(/\\/g, '\\\\')
          .replace(/'/g, "\\'")
          .replace(/"/g, '&quot;')
          .replace(/\n/g, '\\n')
          .replace(/\r/g, '\\r');
        const cols = (r.columns || []);
        const chips = cols.length
          ? cols.map(c => `<span style="display:inline-block;background:#eef2ff;color:#1677ff;border:1px solid #d6e4ff;border-radius:4px;padding:1px 6px;font-size:11px;margin:2px;font-family:monospace" title="${c.label}">${c.name}</span>`).join('')
          : '<span style="color:var(--text-sec)">—</span>';
        return `
        <tr style="border-bottom:1px solid var(--border)">
          <td style="padding:8px">${i + 1}</td>
          <td style="padding:8px;font-weight:600">${r.cn}</td>
          <td style="padding:8px;color:var(--primary,#1677ff);font-family:monospace">${r.en}</td>
          <td style="padding:8px;color:var(--text-sec)">${r.category}</td>
          <td style="padding:8px;color:var(--text-sec);font-family:monospace">${r.db_table}</td>
          <td style="padding:8px">
            <span style="display:inline-block;background:var(--success-bg,#f6ffed);color:var(--success,#389e0d);border:1px solid var(--success,#389e0d);border-radius:4px;padding:1px 6px;font-size:12px;margin-right:6px">物理表</span>
            <button class="btn btn-sm" style="padding:2px 8px;font-size:12px" onclick="openSqlQueryWithTemplate('${tpl}')">查询</button>
          </td>
        </tr>
        <tr style="border-bottom:1px solid var(--border);background:var(--bg-sub,#fafafa)">
          <td style="padding:6px 8px" colspan="6">
            <div style="font-size:12px;color:var(--text-sec);margin-bottom:4px"><b>字段结构（${cols.length} 列 · 无 JSON 聚合字段）</b></div>
            <div style="max-height:150px;overflow-y:auto;line-height:1.9">${chips}</div>
          </td>
        </tr>`;
      }).join('');
    }
    setRows('td-system-body', d.system_tables, (r, i) => {
      const tpl = (r.query_template || '')
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/"/g, '&quot;')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r');
      return `
      <td style="padding:8px">${i}</td>
      <td style="padding:8px;font-weight:600">${r.cn}</td>
      <td style="padding:8px;color:var(--primary,#1677ff);font-family:monospace">${r.en}</td>
      <td style="padding:8px;color:var(--text-sec)">${r.desc}</td>
      <td style="padding:8px"><button class="btn btn-sm" style="padding:2px 8px;font-size:12px" onclick="openSqlQueryWithTemplate('${tpl}')">查询</button></td>`;
    });
    if (document.getElementById('td-input-count')) document.getElementById('td-input-count').textContent = d.counts.input;
    if (document.getElementById('td-output-count')) document.getElementById('td-output-count').textContent = d.counts.output;
    if (document.getElementById('td-system-count')) document.getElementById('td-system-count').textContent = d.counts.system;
    if (loadingEl) loadingEl.style.display = 'none';
    if (contentEl) contentEl.style.display = 'block';
  } catch (e) {
    if (loadingEl) loadingEl.textContent = '加载失败: ' + e.message;
  }
}

// ===== 计算进度（轮询后端 /api/calc/progress） =====

// 将进度百分比映射到 11 个流程圆圈（按真实进度点亮）
function updatePipelineByPercent(percent) {
  const stepEls = document.querySelectorAll('.pipeline-circle');
  const n = stepEls.length || (MODEL_DATA.calcSteps ? MODEL_DATA.calcSteps.length : 0);
  if (!n) return;
  const doneCount = Math.floor((percent / 100) * n + 1e-9);
  stepEls.forEach((el, i) => {
    if (!el) return;
    if (i < doneCount) {
      el.className = 'pipeline-circle done';
      el.innerHTML = '\u2713';
    } else if (i === doneCount) {
      el.className = 'pipeline-circle running';
      el.innerHTML = '<span class="loading-spinner"></span>';
    } else {
      el.className = 'pipeline-circle pending';
      el.innerHTML = (i + 1);
    }
  });
  // 同步数据模型状态，便于页面重渲染时保持一致
  if (MODEL_DATA.calcSteps) {
    MODEL_DATA.calcSteps.forEach((s, i) => {
      s.status = i < doneCount ? 'done' : (i === doneCount ? 'running' : 'pending');
    });
  }
}

// 更新进度面板 UI
let _lastProgressMsg = '';
function updateProgressUI(p) {
  const card = document.getElementById('calc-progress-card');
  const fill = document.getElementById('calc-progress-fill');
  const pctEl = document.getElementById('calc-progress-percent');
  const stageEl = document.getElementById('calc-progress-stage');
  const detailEl = document.getElementById('calc-progress-detail');
  const scenEl = document.getElementById('calc-progress-scenario');
  if (!card) return;

  const status = p.status || 'idle';
  const percent = Math.max(0, Math.min(100, Number(p.percent) || 0));

  if (fill) fill.style.width = percent + '%';
  if (pctEl) pctEl.textContent = Math.round(percent) + '%';
  if (stageEl) {
    const map = { starting: '排队中…', running: (p.stageName || '计算中…'), done: '计算完成', error: '计算失败', idle: '准备中…' };
    stageEl.textContent = map[status] || (p.stageName || '计算中…');
  }
  if (detailEl) {
    let txt = p.message || '';
    if (status === 'running' && p.total > 1) {
      txt += `  (${p.current}/${p.total})`;
    }
    detailEl.textContent = txt;
  }
  if (scenEl) {
    scenEl.textContent = '情景: ' + (p.scenario || '-');
    scenEl.className = 'status-tag ' + (status === 'error' ? 'pending' : 'running');
  }
  if (status === 'done') {
    if (fill) fill.classList.add('done');
  } else if (fill) {
    fill.classList.remove('done');
  }

  // 按真实进度点亮流程圆圈
  updatePipelineByPercent(percent);

  // 实时把进度消息追加到日志面板（仅当可见且内容变化）
  if (p.message && p.message !== _lastProgressMsg) {
    _lastProgressMsg = p.message;
    const logEl = document.getElementById('calc-log');
    const panel = document.getElementById('calc-log-panel');
    if (logEl && panel && panel.style.display !== 'none') {
      logEl.innerHTML += `<div class="log-line info">[${new Date().toLocaleTimeString()}] ${p.message}</div>`;
      logEl.scrollTop = logEl.scrollHeight;
    }
  }
}

// 触发后台计算并轮询进度，返回计算结果 Promise
function startCalcWithProgress(scenario, forecastPeriods) {
  return new Promise((resolve, reject) => {
    const csrfToken = window.CSRF_TOKEN || '';
    const card = document.getElementById('calc-progress-card');
    if (card) card.style.display = 'block';
    _lastProgressMsg = '';
    // 显示顶栏全局徽标（保证切到其他页面也能看到计算进行中）
    showCalcGlobalBadge(true);

    fetch('/api/calc/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body: JSON.stringify({ scenario: scenario, forecast_periods: forecastPeriods || null }),
    })
      .then(r => r.json())
      .then(startResp => {
        if (!startResp.success || !startResp.started) {
          if (card) card.style.display = 'none';
          showCalcGlobalBadge(false);
          reject(new Error(startResp.error || '启动计算失败'));
          return;
        }
        // 接管当前情景 Promise，交由模块级轮询统一处理（与页面 DOM 解耦）
        CALC_ACTIVE_RESOLVE = resolve;
        CALC_ACTIVE_REJECT = reject;
        startProgressPolling();
      })
      .catch(e => {
        if (card) card.style.display = 'none';
        showCalcGlobalBadge(false);
        reject(e);
      });
  });
}

// 启动/复用模块级进度轮询（跨页面存活）
function startProgressPolling() {
  if (CALC_PROGRESS_TIMER) return;  // 已在轮询，避免重复
  // 立即拉一次，避免切页回来后等 400ms 才刷新
  pollCalcProgressTick();
  CALC_PROGRESS_TIMER = setInterval(pollCalcProgressTick, 400);
  // 安全超时（10 分钟）
  if (CALC_PROGRESS_TIMEOUT) clearTimeout(CALC_PROGRESS_TIMEOUT);
  CALC_PROGRESS_TIMEOUT = setTimeout(() => {
    stopProgressPolling();
    const rej = CALC_ACTIVE_REJECT;
    CALC_ACTIVE_RESOLVE = null; CALC_ACTIVE_REJECT = null;
    showCalcGlobalBadge(false);
    if (rej) rej(new Error('计算超时（>10 分钟），请检查服务端日志'));
  }, CALC_SAFE_TIMEOUT_MS);
}

function pollCalcProgressTick() {
  fetch('/api/calc/progress')
    .then(r => r.json())
    .then(p => {
      updateProgressUI(p);
      updateCalcGlobalBadge(p);
      if (p.status === 'done') {
        finishCalcProgress(true);
      } else if (p.status === 'error') {
        finishCalcProgress(false, p.error || '计算失败');
      }
    })
    .catch(() => { /* 网络抖动，下一拍继续 */ });
}

// 结束轮询并兑现当前情景 Promise
function finishCalcProgress(success, errMsg) {
  stopProgressPolling();
  const res = CALC_ACTIVE_RESOLVE;
  const rej = CALC_ACTIVE_REJECT;
  CALC_ACTIVE_RESOLVE = null;
  CALC_ACTIVE_REJECT = null;
  showCalcGlobalBadge(false);
  if (success) {
    fetch('/api/calc/results')
      .then(r => r.json())
      .then(data => { if (res) res(data); })
      .catch(e => { if (rej) rej(e); });
  } else {
    if (rej) rej(new Error(errMsg || '计算失败'));
  }
}

function stopProgressPolling() {
  if (CALC_PROGRESS_TIMER) { clearInterval(CALC_PROGRESS_TIMER); CALC_PROGRESS_TIMER = null; }
  if (CALC_PROGRESS_TIMEOUT) { clearTimeout(CALC_PROGRESS_TIMEOUT); CALC_PROGRESS_TIMEOUT = null; }
}

// 进入计算页时，若后端计算仍在进行，自动恢复进度显示
function resumeCalcProgressIfRunning() {
  fetch('/api/calc/progress')
    .then(r => r.json())
    .then(p => {
      if (p.status === 'running' || p.status === 'starting') {
        const card = document.getElementById('calc-progress-card');
        if (card) card.style.display = 'block';
        showCalcGlobalBadge(true);
        updateProgressUI(p);
        updateCalcGlobalBadge(p);
        startProgressPolling();  // 复用模块级轮询，接管当前 DOM
      }
    })
    .catch(() => {});
}

// ===== 顶栏全局"计算中"徽标（任何页面可见，点击回计算页）=====
function showCalcGlobalBadge(show) {
  const el = ensureCalcGlobalBadgeEl();
  if (el) el.style.display = show ? 'inline-flex' : 'none';
}

function ensureCalcGlobalBadgeEl() {
  let el = document.getElementById('calc-global-badge');
  if (!el) {
    const right = document.querySelector('.topbar-right');
    if (!right) return null;
    el = document.createElement('span');
    el.id = 'calc-global-badge';
    el.className = 'calc-global-badge';
    el.style.display = 'none';
    el.title = '计算中，点击返回计算流程页面';
    el.onclick = () => renderPage('calc-pipeline');
    right.insertBefore(el, right.firstChild);
  }
  return el;
}

function updateCalcGlobalBadge(p) {
  const el = ensureCalcGlobalBadgeEl();
  if (!el) return;
  const status = p.status || 'idle';
  if (status === 'running' || status === 'starting') {
    const pct = Math.round(Math.max(0, Math.min(100, Number(p.percent) || 0)));
    el.style.display = 'inline-flex';
    el.innerHTML = `<span class="cg-spinner"></span><span class="cg-text">计算中 · 情景 ${p.scenario || '-'} · ${pct}%</span>`;
  } else {
    el.style.display = 'none';
  }
}

async function runCalculation(scenario) {
  if (CALC_RUNNING) return;
  CALC_RUNNING = true;

  const btn = document.getElementById('calc-run-btn');
  const logEl = document.getElementById('calc-log');
  const stepEls = document.querySelectorAll('.pipeline-circle');

  // 读取预测期数
  const fpSelect = document.getElementById('forecast-periods-select');
  const forecastPeriods = fpSelect ? parseInt(fpSelect.value, 10) : null;

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner"></span> 计算中...';
  }

  // 重置步骤状态为 pending，由真实进度点亮
  MODEL_DATA.calcSteps.forEach(s => s.status = 'pending');
  stepEls.forEach(el => { if (el) { el.className = 'pipeline-circle pending'; el.innerHTML = '\u2022'; } });
  if (logEl) { logEl.innerHTML = ''; }

  try {
    const data = await startCalcWithProgress(scenario, forecastPeriods);

    if (data.success) {
      CALC_RESULT = data;
      if (data.selectedScenario) {
        CALC_RESULTS_MAP[data.selectedScenario] = data;
      }

      // 标记所有步骤完成
      MODEL_DATA.calcSteps.forEach(s => s.status = 'done');
      updatePipelineByPercent(100);

      // 显示计算日志
      if (logEl && data.calcLogs) {
        logEl.innerHTML = '';
        data.calcLogs.forEach(line => {
          const cls = line.includes('错误') ? 'error' : (line.includes('完成') ? 'success' : 'info');
          logEl.innerHTML += `<div class="log-line ${cls}">[${new Date().toLocaleTimeString()}] ${line}</div>`;
        });
        logEl.scrollTop = logEl.scrollHeight;
      }

      // 显示结果摘要
      const summaryEl = document.getElementById('calc-summary');
      if (summaryEl && data.summary) {
        summaryEl.style.display = 'block';
        summaryEl.innerHTML = renderCalcSummary(data);
      }

      // 显示输入整理结果
      const inputEl = document.getElementById('calc-input-organized');
      if (inputEl && data.inputOrganized) {
        inputEl.style.display = 'block';
        inputEl.innerHTML = renderInputOrganized(data.inputOrganized);
      }

      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '\u25B6 重新计算';
        btn.classList.add('btn-success');
      }
    } else {
      // 计算失败
      MODEL_DATA.calcSteps.forEach(s => s.status = 'pending');
      stepEls.forEach(el => {
        if (el) { el.className = 'pipeline-circle pending'; el.innerHTML = '\u2022'; }
      });
      if (logEl) {
        logEl.innerHTML += `<div class="log-line error">[${new Date().toLocaleTimeString()}] 计算失败: ${data.error || '未知错误'}</div>`;
        if (data.calcLogs) {
          data.calcLogs.forEach(line => {
            logEl.innerHTML += `<div class="log-line error">${line}</div>`;
          });
        }
        logEl.scrollTop = logEl.scrollHeight;
      }
      const card = document.getElementById('calc-progress-card');
      if (card) card.style.display = 'none';
      if (btn) { btn.disabled = false; btn.innerHTML = '\u25B6 重新计算'; }
    }
  } catch (e) {
    if (logEl) {
      logEl.innerHTML += `<div class="log-line error">[${new Date().toLocaleTimeString()}] 请求异常: ${e.message}</div>`;
    }
    const card = document.getElementById('calc-progress-card');
    if (card) card.style.display = 'none';
    if (btn) { btn.disabled = false; btn.innerHTML = '\u25B6 重新计算'; }
  } finally {
    CALC_RUNNING = false;
  }
}

function renderCalcSummary(data) {
  const s = data.summary || {};
  const inputOrg = data.inputOrganized || {};
  return `
  <div class="kpi-grid">
    <div class="kpi-card blue"><div class="kpi-label">选定场景</div><div class="kpi-value" style="font-size:18px">${data.selectedScenario || '-'}</div><div class="kpi-sub">评估时点: ${inputOrg.evalDate || '-'}</div></div>
    <div class="kpi-card green"><div class="kpi-label">新业务计算行数</div><div class="kpi-value">${s.newBusinessRows || 0}<span class="kpi-unit">行</span></div><div class="kpi-sub">预测期数: ${inputOrg.forecastPeriods || 0}</div></div>
    <div class="kpi-card orange"><div class="kpi-label">现有业务计算行数</div><div class="kpi-value">${s.existingBusinessRows || 0}<span class="kpi-unit">行</span></div></div>
    <div class="kpi-card purple"><div class="kpi-label">汇总表行数</div><div class="kpi-value">${s.combinedSummaryRows || 0}<span class="kpi-unit">行</span></div><div class="kpi-sub">财务报表: ${s.financialStatementRows || 0} 行</div></div>
  </div>`;
}

function renderInputOrganized(inputOrg) {
  const newBiz = inputOrg.newBusiness || [];
  const exBiz = inputOrg.existingBusiness || [];
  const rateCurve = inputOrg.rateCurve || {};
  
  let newBizHtml = '<p style="color:var(--text-sec)">无新业务数据</p>';
  if (newBiz.length > 0) {
    const cols = Object.keys(newBiz[0]).slice(0, 8);
    newBizHtml = `<div class="table-wrapper"><table class="data-table"><thead><tr>${cols.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>
      ${newBiz.slice(0, 20).map(r=>`<tr>${cols.map(c=>{const v=r[c];if(v==null||v==='')return '<td>-</td>';if(typeof v==='number')return `<td class="num">${fmt(v,2)}</td>`;if(typeof v==='string'&&v.match(/^\d{4}-\d{2}-\d{2}/))return `<td>${fmtDate(v)}</td>`;return `<td>${v}</td>`;}).join('')}</tr>`).join('')}
    </tbody></table></div>${newBiz.length>20?`<p style="color:var(--text-sec);text-align:center;padding:8px">显示前20行，共${newBiz.length}行</p>`:''}`;
  }

  let exBizHtml = '<p style="color:var(--text-sec)">无现有业务数据</p>';
  if (exBiz.length > 0) {
    const cols = Object.keys(exBiz[0]).slice(0, 8);
    exBizHtml = `<div class="table-wrapper"><table class="data-table"><thead><tr>${cols.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>
      ${exBiz.slice(0, 20).map(r=>`<tr>${cols.map(c=>{const v=r[c];if(v==null||v==='')return '<td>-</td>';if(typeof v==='number')return `<td class="num">${fmt(v,2)}</td>`;if(typeof v==='string'&&v.match(/^\d{4}-\d{2}-\d{2}/))return `<td>${fmtDate(v)}</td>`;return `<td>${v}</td>`;}).join('')}</tr>`).join('')}
    </tbody></table></div>${exBiz.length>20?`<p style="color:var(--text-sec);text-align:center;padding:8px">显示前20行，共${exBiz.length}行</p>`:''}`;
  }

  // 利率曲线摘要
  const dfEnd = rateCurve['月度折现因子_期末'] || {};
  const dfKeys = Object.keys(dfEnd).slice(0, 12);
  let rateHtml = '';
  if (dfKeys.length > 0) {
    rateHtml = `<div class="table-wrapper"><table class="data-table"><thead><tr><th>月份</th>${dfKeys.map(k=>`<th>${k}</th>`).join('')}</tr></thead><tbody>
      <tr><td>折现因子(期末)</td>${dfKeys.map(k=>`<td class="num">${fmt(dfEnd[k],6)}</td>`).join('')}</tr>
    </tbody></table></div>`;
  } else {
    rateHtml = '<p style="color:var(--text-sec)">无利率曲线数据</p>';
  }

  return `
  <div class="card" style="margin-top:16px"><div class="card-header"><h3>输入整理 - 新业务假设</h3><span class="badge">${newBiz.length} 组</span></div><div class="card-body">${newBizHtml}</div></div>
  <div class="card" style="margin-top:16px"><div class="card-header"><h3>输入整理 - 现有业务假设</h3><span class="badge">${exBiz.length} 组</span></div><div class="card-body">${exBizHtml}</div></div>
  <div class="card" style="margin-top:16px"><div class="card-header"><h3>输入整理 - 利率曲线</h3></div><div class="card-body">${rateHtml}</div></div>`;
}

function renderPredictDetail(rows) {
  if (!rows || rows.length === 0) return '<p style="color:var(--text-sec)">无数据</p>';
  const showCols = ['预测组', '预测组ID', '预测间隔', '精算险类', '业务类型',
    '保费收入', '获取费用', '当期确认比例', '当月计息利率',
    '输出_未到期责任负债_非亏损部分', '输出_已发生未决赔款负债_预期现金流',
    '输出_保险合同收入', '输出_现金流_收到的保费', '输出_现金流_支付的赔付与理赔费用'];
  return `<div class="table-wrapper" style="max-height:600px;overflow:auto"><table class="data-table"><thead><tr>${showCols.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>
    ${rows.slice(0,100).map(r=>`<tr>${showCols.map(c=>{const v=r[c];if(v==null||v==='')return '<td>-</td>';if(typeof v==='number')return `<td class="num">${fmt(v,4)}</td>`;if(typeof v==='string'&&v.match(/^\d{4}-\d{2}-\d{2}/))return `<td>${fmtDate(v)}</td>`;return `<td>${v}</td>`;}).join('')}</tr>`).join('')}
  </tbody></table></div>${rows.length>100?`<p style="color:var(--text-sec);text-align:center;padding:8px">显示前100行，共${rows.length}行</p>`:''}`;
}

function renderCombinedSummaryDetail(rows) {
  if (!rows || rows.length === 0) return '<p style="color:var(--text-sec)">无数据</p>';
  // Show all output columns grouped by category, matching Excel PAA计算_汇总
  const infoCols = ['合同组ID名称', '预测间隔', '合同组名称', '业务类型', '精算险类', '预测时点'];
  const outputGroups = [
    { label: '负债类', cols: [
      '输出_未到期责任负债_非亏损部分', '输出_未到期责任负债_亏损部分', '输出_未到期责任负债_亏损摊回',
      '输出_已发生未决赔款负债_预期现金流', '输出_间接理赔费用负债_预期现金流',
      '输出_已发生未决赔款负债_再保人不履约_预期现金流',
      '输出_已发生未决赔款负债_非金融风险调整', '输出_间接理赔费用负债_非金融风险调整',
      '输出_已发生未决赔款负债_再保人不履约_非金融风险调整',
    ]},
    { label: '损益类', cols: [
      '输出_保险合同收入', '输出_赔付与费用_分解的投资成分', '输出_赔付与费用_摊销的保险获取现金流',
      '输出_亏损合同损益', '输出_亏损摊回损益',
      '输出_赔付与费用_已发生未决赔款负债提转差_预期现金流', '输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整',
      '输出_赔付与费用_间接理赔费用提转差_预期现金流', '输出_赔付与费用_间接理赔费用提转差_非金融风险调整',
      '输出_赔付与费用_已发生未决_再保人不履约_预期现金流', '输出_赔付与费用_已发生未决_再保人不履约_非金融风险调整',
    ]},
    { label: 'IFIE', cols: [
      '输出_IFIE_未到期_未到期计息',
      '输出_IFIE_已发生未决_已发生未决赔款负债计息_预期现金流',
      '输出_IFIE_已发生未决_已发生未决赔款负债计息_非金融风险调整',
      '输出_IFIE_已发生未决_间接理赔费用计息_预期现金流',
      '输出_IFIE_已发生未决_间接理赔费用计息_非金融风险调整',
    ]},
    { label: '现金流', cols: [
      '输出_现金流_支付的赔付与理赔费用', '输出_现金流_支付的维持费用_计量',
      '输出_现金流_支付的维持费用_实际维持费用_分子合同组合', '实际维持费用分摊比例',
      '输出_现金流_支付的维持费用', '输出_现金流_收到的保费', '输出_现金流_支付的IACF',
    ]},
    { label: 'OCI', cols: [
      '输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流',
      '输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整',
      '输出_OCI_已发生未决_间接理赔费用计息与利率变化_预期现金流',
      '输出_OCI_已发生未决_间接理赔费用计息与利率变化_非金融风险调整',
    ]},
  ];
  const allCols = [...infoCols, ...outputGroups.flatMap(g => g.cols)];
  return `<div class="table-wrapper" style="max-height:600px;overflow:auto"><table class="data-table" style="font-size:12px"><thead><tr>${allCols.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>
    ${rows.slice(0,200).map(r=>`<tr>${allCols.map(c=>{const v=r[c];if(v==null||v==='')return '<td>-</td>';if(typeof v==='number')return `<td class="num">${fmt(v,2)}</td>`;if(typeof v==='string'&&v.match(/^\d{4}-\d{2}-\d{2}/))return `<td>${v.substring(0,10)}</td>`;return `<td>${v}</td>`;}).join('')}</tr>`).join('')}
  </tbody></table></div>${rows.length>200?`<p style="color:var(--text-sec);text-align:center;padding:8px">显示前200行，共${rows.length}行</p>`:''}`;
}

// ===== 财务报表全局状态 =====
let FS_VIEW_MODE = 'ytd';      // 'mtd' or 'ytd'（默认 YTD 累计，与预实分析预期值/计量结果输出口径一致）
let FS_PERIOD_MODE = 'monthly'; // 'monthly' or 'annual'
let FS_SELECTED_SCENARIO = '情景0';  // 选定场景 for financial-statements
let DASH_SELECTED_SCENARIO = '情景0'; // 选定场景 for dashboard
let DASH_FORECAST_PERIOD = '';   // 选定预测时点(年月) for dashboard, '' = 评估时点
let DASH_CHART_MODE = 'monthly';  // 'annual' or 'monthly' — 结果总览图表趋势粒度（默认月度趋势）
let INPUT_ORG_SCENARIO = '基础情景';  // 输入整理-情景对比 当前选定场景
let SCP_SELECTED_SCENARIO = '情景0'; // 选定场景 for sub-class-profit

// 结果展示面板快照（admin 保存后 viewer 默认展示该面板）
let DASHBOARD_SNAPSHOT = null;

// 获取场景对应的计算结果
function getScenarioResult(scenarioName) {
  // viewer 且存在 admin 保存的快照：优先返回快照中的计算结果
  if (isViewer() && DASHBOARD_SNAPSHOT && DASHBOARD_SNAPSHOT.saved && DASHBOARD_SNAPSHOT.calcResult) {
    const snapScenario = DASHBOARD_SNAPSHOT.scenario || '情景0';
    if (!scenarioName || scenarioName === snapScenario ||
        (scenarioName === '情景0' && snapScenario === '基础情景') ||
        (scenarioName === '基础情景' && snapScenario === '情景0')) {
      return DASHBOARD_SNAPSHOT.calcResult;
    }
  }
  if (!scenarioName) return CALC_RESULT;
  if (CALC_RESULTS_MAP[scenarioName]) return CALC_RESULTS_MAP[scenarioName];
  // 基础情景别名兼容
  if (scenarioName === '情景0' && CALC_RESULTS_MAP['基础情景']) return CALC_RESULTS_MAP['基础情景'];
  if (scenarioName === '基础情景' && CALC_RESULTS_MAP['情景0']) return CALC_RESULTS_MAP['情景0'];
  if (CALC_RESULT && CALC_RESULT.selectedScenario === scenarioName) return CALC_RESULT;
  return CALC_RESULT;
}

// 获取已计算场景列表（按编号排序）
function getComputedScenarios() {
  const scenarios = [];
  if (CALC_RESULT && CALC_RESULT.success) {
    scenarios.push(CALC_RESULT.selectedScenario || '情景0');
  }
  Object.keys(CALC_RESULTS_MAP).forEach(s => {
    if (!scenarios.includes(s)) scenarios.push(s);
  });
  // 基础情景别名统一为 '情景0'
  const normalized = scenarios.map(s => s === '基础情景' ? '情景0' : s);
  const dedup = [];
  normalized.forEach(s => { if (!dedup.includes(s)) dedup.push(s); });
  // Sort by scenario number (情景0, 情景1, 情景2...)
  dedup.sort((a, b) => {
    const ma = a.match(/(\d+)/), mb = b.match(/(\d+)/);
    const na = ma ? parseInt(ma[1]) : 999, nb = mb ? parseInt(mb[1]) : 999;
    return na - nb;
  });
  return dedup;
}

// 获取场景的加压条件描述
function getScenarioConditions(scenarioName) {
  const norm = _normScName(scenarioName);
  // 基础情景统一显示
  if (norm === '情景0') return '基础情景（无加压）';

  // 1. 从 CALC_SCENARIOS 中查找
  const sc = CALC_SCENARIOS.find(s => s.value === scenarioName);
  if (sc && sc.conditions) {
    const keys = Object.keys(sc.conditions);
    if (keys.length > 0) {
      return keys.map(k => {
        const v = sc.conditions[k];
        const pct = (v * 100).toFixed(1).replace(/\.0$/, '');
        const cnKey = SCENARIO_PARAM_CN[k] || k;
        return `${cnKey}: ${pct > 0 ? '+' : ''}${pct}%`;
      }).join('；');
    }
  }

  // 2. 从 MODEL_DATA.scenarios 中查找（兜底）
  const md = MODEL_DATA.scenarios.find(s => s.name === scenarioName || s.name === norm);
  if (md && md.p) {
    const keys = Object.keys(md.p).filter(k => md.p[k] !== 0);
    if (keys.length > 0) {
      return keys.map(k => {
        const v = md.p[k];
        const pct = (v * 100).toFixed(1).replace(/\.0$/, '');
        const cnKey = SCENARIO_PARAM_CN[k] || k;
        return `${cnKey}: ${pct > 0 ? '+' : ''}${pct}%`;
      }).join('；');
    }
    if (md.desc && md.desc !== md.name) return md.desc;
  }

  // 3. 从计算结果 inputOrganized 的压力参数中查找
  const result = getScenarioResult(scenarioName);
  const stress = result?.inputOrganized?.stressParams;
  if (stress) {
    const keys = Object.keys(stress).filter(k => stress[k] !== 0);
    if (keys.length > 0) {
      return keys.map(k => {
        const v = stress[k];
        const pct = (v * 100).toFixed(1).replace(/\.0$/, '');
        const cnKey = SCENARIO_PARAM_CN[k] || k;
        return `${cnKey}: ${pct > 0 ? '+' : ''}${pct}%`;
      }).join('；');
    }
  }

  return '基础情景（无加压）';
}

// 场景压力情景描述（含情景描述字段 + 加压条件），用于多情景比对顶部展示
function getScenarioDescription(name) {
  const sc = CALC_SCENARIOS.find(s => s.value === name);
  if (sc) {
    const parts = [];
    if (sc.description && sc.description !== name) parts.push(sc.description);
    if (sc.conditions && Object.keys(sc.conditions).length) {
      const cond = Object.keys(sc.conditions).map(k => {
        const v = sc.conditions[k];
        const pct = (v * 100).toFixed(1).replace(/\.0$/, '');
        const cnKey = SCENARIO_PARAM_CN[k] || k;
        return `${cnKey}:${pct > 0 ? '+' : ''}${pct}%`;
      }).join('；');
      parts.push(cond);
    }
    if (parts.length) return parts.join(' ｜ ');
  }
  return getScenarioConditions(name);
}

// 场景选择器HTML（含加压条件描述）
function scenarioSelectorHTML(selectedScenario, onChangeFn, opts = {}) {
  // 默认只显示已计算场景；opts.all=true 显示全部可用场景并标记未计算
  const computed = new Set(getComputedScenarios());
  const scenarios = opts.all ? (CALC_SCENARIOS.length ? CALC_SCENARIOS.map(s => s.value) : getComputedScenarios()) : getComputedScenarios();
  if (scenarios.length <= 1) return '';
  return `<div style="display:inline-flex;align-items:center;gap:6px">
    <span style="font-size:13px;color:var(--text-sec)">场景:</span>
    <select onchange="${onChangeFn}(this.value)" style="width:auto;padding:6px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card-bg);color:var(--text);font-size:13px">
      ${scenarios.map(s => {
        const disabled = opts.all && !computed.has(s) ? 'disabled' : '';
        const label = opts.all && !computed.has(s) ? `${s} (未计算)` : s;
        return `<option value="${s}" ${selectedScenario===s?'selected':''} ${disabled}>${label}</option>`;
      }).join('')}
    </select>
  </div>`;
}

// 验证比对情景选择器（按选定情景对比系统输出与验证文件；未计算情景禁用）
function setVerifyUploadScenario(val) {
  VERIFY_SELECTED_SCENARIO = val;
}

function verifyScenarioSelectHTML(selId, onChangeFn) {
  const scenarios = getComputedScenarios();
  const current = VERIFY_SELECTED_SCENARIO || scenarios[0] || '情景0';
  if (scenarios.length <= 1) {
    return `<span style="font-size:13px;color:var(--text-sec)">对比情景: <strong>${current}</strong></span>`;
  }
  return `<span style="font-size:13px;color:var(--text-sec)">对比情景:</span>
    <select id="${selId}" onchange="${onChangeFn}(this.value)" style="width:auto;padding:6px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card-bg);color:var(--text);font-size:13px">
      ${scenarios.map(s => {
        const computed = !!CALC_RESULTS_MAP[s];
        const disabled = computed ? '' : 'disabled';
        const label = computed ? s : `${s} (未计算)`;
        return `<option value="${s}" ${current===s?'selected':''} ${disabled}>${label}</option>`;
      }).join('')}
    </select>`;
}

// 切换验证比对情景：更新全局并刷新比对结果
function setVerifyScenario(val) {
  VERIFY_SELECTED_SCENARIO = val;
  recompareVerify();
}

// 验证比对情景切换条（差异比对结果页 / 验证核对结果页共用）
function renderVerifyScenarioBar() {
  const current = VERIFY_SELECTED_SCENARIO || (verifyState.scenario) || '情景0';
  return `
  <div class="card" style="margin-bottom:16px">
    <div class="card-body" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      ${verifyScenarioSelectHTML('verifyScenarioSelect2', 'setVerifyScenario')}
      <span class="text-muted" style="font-size:12px">仅对比「系统 <strong>${current}</strong> 输出」与验证文件选定情景的结果</span>
    </div>
  </div>`;
}

// 获取计算结果中的财务报表HTML (新版结构化MTD/YTD + 年度/月度切换 + 白盒钻取)
function getFinancialStatementsHtml() {
  const activeResult = getScenarioResult(FS_SELECTED_SCENARIO);
  // 优先使用与验证文件/计量结果输出对齐的 merged 财务报表
  const fs = activeResult?.financialStatementsV2Merged || activeResult?.financialStatementsV2;
  if (!fs || !fs.dates) return null;

  const dates = fs.dates;
  const isAnnual = FS_PERIOD_MODE === 'annual';

  let colHeaders, colIndices;

  if (isAnnual) {
    // 年度模式：按年份分组预测月份
    const yearMap = new Map();
    dates.forEach((d, i) => {
      if (!d || i === 0) return; // 跳过评估日(period 0)
      const year = d.split('-')[0];
      if (!yearMap.has(year)) yearMap.set(year, []);
      yearMap.get(year).push(i);
    });
    colHeaders = [...yearMap.keys()].map(y => y + 'F');
    colIndices = [...yearMap.values()]; // array of index arrays
  } else {
    // 月度模式：展示每个月
    colHeaders = dates.map(d => {
      if (!d) return '评估日';
      const parts = d.split('-');
      return `${parts[0]}-${parts[1]}`;
    });
    colIndices = dates.map((_, i) => i);
  }

  const colspan = colHeaders.length + 1;

  // 年度模式：取当年最大的月度YTD期（如2026年仅运行到9月，则2026年度=2026-09 YTD）
  // 月度模式：使用选定的MTD/YTD
  const data = isAnnual ? fs.ytd : fs[FS_VIEW_MODE];
  if (!data) return null;

  // 白盒钻取：点击数字显示计算逻辑
  function cellClickCode(item, periodIdx, isFlow) {
    const escaped = String(item).replace(/'/g, "\\'");
    return `showCellDetail('${escaped}', ${periodIdx}, ${isAnnual ? 'true' : 'false'}, ${isFlow ? 'true' : 'false'})`;
  }

  // 渲染综合收益表
  let incomeHtml = `<tr class="section-row"><td colspan="${colspan}">CAS 25 综合收益表</td></tr>`;
  data.income_statement.forEach((row, rowIdx) => {
    const indent = row.indent > 0 ? ` style="padding-left:${20 + row.indent * 16}px"` : '';
    const cls = row.is_total ? ' class="total-row"' : '';
    let cells;
    if (isAnnual) {
      // 年度报表：损益类(流量项目)取当年最大月度YTD值
      cells = colIndices.map((indices, colIdx) => {
        const lastIdx = indices[indices.length - 1];
        return `<td class="num clickable" onclick="${cellClickCode(row.item, colIdx, true)}">${fmtU(row.values[lastIdx] || 0)}</td>`;
      }).join('');
    } else {
      cells = colIndices.map(i => `<td class="num clickable" onclick="${cellClickCode(row.item, i, true)}">${fmtU(row.values[i] || 0)}</td>`).join('');
    }
    incomeHtml += `<tr${cls}><td${indent}>${row.item}</td>${cells}</tr>`;
  });

  // 渲染资产负债表
  let balanceHtml = `<tr class="section-row"><td colspan="${colspan}">CAS 25 资产负债表</td></tr>`;
  data.balance_sheet.forEach((row, rowIdx) => {
    if (row.item === '资产' || row.item === '负债') return; // skip section headers
    const indent = row.indent > 0 ? ` style="padding-left:${20 + row.indent * 16}px"` : '';
    const cls = row.is_total ? ' class="total-row"' : '';
    let cells;
    if (isAnnual) {
      // 年度报表：资产负债表(存量项目)取当年最大月度YTD期末值
      cells = colIndices.map((indices, colIdx) => {
        const lastIdx = indices[indices.length - 1];
        return `<td class="num clickable" onclick="${cellClickCode(row.item, colIdx, false)}">${fmtU(row.values[lastIdx] || 0)}</td>`;
      }).join('');
    } else {
      cells = colIndices.map(i => `<td class="num clickable" onclick="${cellClickCode(row.item, i, false)}">${fmtU(row.values[i] || 0)}</td>`).join('');
    }
    balanceHtml += `<tr${cls}><td${indent}>${row.item}</td>${cells}</tr>`;
  });

  // 构建切换控件
  let controlsHtml;
  if (isAnnual) {
    // 年度报表：不显示MTD/YTD切换
    controlsHtml = `
    <div class="btn-group">
      <button class="btn btn-default" onclick="setFsPeriodMode('monthly')">月度结果</button>
      <button class="btn btn-primary" onclick="setFsPeriodMode('annual')">年度报表</button>
    </div>
    <span style="color:var(--text-sec);font-size:13px">当前：年度报表（取当年最大月度YTD）</span>`;
  } else {
    const modeLabel = FS_VIEW_MODE === 'mtd' ? 'MTD (月度)' : 'YTD (累计)';
    controlsHtml = `
    <div class="btn-group">
      <button class="btn ${FS_VIEW_MODE==='mtd'?'btn-primary':'btn-default'}" onclick="setFsViewMode('mtd')">MTD 月度</button>
      <button class="btn ${FS_VIEW_MODE==='ytd'?'btn-primary':'btn-default'}" onclick="setFsViewMode('ytd')">YTD 累计</button>
    </div>
    <div class="btn-group">
      <button class="btn btn-primary" onclick="setFsPeriodMode('monthly')">月度结果</button>
      <button class="btn btn-default" onclick="setFsPeriodMode('annual')">年度报表</button>
    </div>
    <span style="color:var(--text-sec);font-size:13px">当前：${modeLabel}</span>`;
  }

  return `
  <div style="margin-bottom:16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
    ${controlsHtml}
    ${unitSelectorHTML()}
  </div>
  <div class="table-wrapper"><table class="data-table" id="fsMainTable" style="font-size:13px"><thead><tr><th style="min-width:240px">项目</th>${colHeaders.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${incomeHtml}${balanceHtml}</tbody></table></div>`;
}

// 白盒钻取：显示数字的计算逻辑
function showCellDetail(item, colIdx, isAnnual, isFlow) {
  const activeResult = getScenarioResult(FS_SELECTED_SCENARIO);
  // 白盒钻取同样使用与验证文件对齐的 merged 财务报表
  const fs = activeResult?.financialStatementsV2Merged || activeResult?.financialStatementsV2;
  if (!fs) return;

  const dates = fs.dates;
  const data = isAnnual ? fs.ytd : (fs[FS_VIEW_MODE] || fs.mtd);

  // 查找该科目在利润表和资产负债表中的行
  let row = data.income_statement.find(r => r.item === item);
  let section = '综合收益表';
  if (!row) {
    row = data.balance_sheet.find(r => r.item === item);
    section = '资产负债表';
  }
  if (!row) return;

  // 确定列标题和涉及的期间
  let periodLabel, periodIndices;
  if (isAnnual) {
    const yearMap = new Map();
    dates.forEach((d, i) => {
      if (!d || i === 0) return;
      const year = d.split('-')[0];
      if (!yearMap.has(year)) yearMap.set(year, []);
      yearMap.get(year).push(i);
    });
    const years = [...yearMap.keys()];
    periodLabel = years[colIdx] + 'F';
    periodIndices = yearMap.get(years[colIdx]) || [];
  } else {
    periodLabel = dates[colIdx] ? dates[colIdx].substring(0, 7) : '评估日';
    periodIndices = [colIdx];
  }

  // 计算显示值：年度报表取当年最大月度YTD值（损益类/存量类均取期末值）
  let displayValue;
  if (isAnnual) {
    displayValue = row.values[periodIndices[periodIndices.length - 1]] || 0;
  } else {
    displayValue = row.values[colIdx] || 0;
  }

  // 构建计算逻辑说明
  const formulaMap = {
    '保险服务收入': '直保/分入合同组的保险合同收入列汇总（输出_保险合同收入）',
    '保险服务费用': '直保/分入合同组的赔付与费用列汇总（输出_赔付与费用_*），取正值显示',
    '分出保费的分摊': '分出合同组的保险合同收入列汇总，取正值显示',
    '减：摊回保险服务费用': '分出合同组的赔付与费用列汇总',
    '承保财务损失': '直保/分入合同组的IFIE列汇总（输出_IFIE_*），取正值显示',
    '减：分出再保险财务收益': '分出合同组的IFIE列汇总',
    '利息收入': '其他输入项 → 利息收入（月度值）',
    '投资收益（损失以"-"号填列）': '其他输入项 → 投资收益（月度值）',
    '其他收益（损失以"-"号填列）': '其他输入项 → 其他业务收入',
    '公允价值变动收益（损失以"-"号填列）': '其他输入项 → 公允价值变动收益',
    '汇兑收益（损失以"-"号填列）': '其他输入项 → 汇兑收益',
    '其他业务收入': '其他输入项 → 其他业务收入',
    '资产处置收益（损失以"-"号填列）': '其他输入项 → 资产处置收益',
    '提取保费准备金': '其他输入项 → 提取保费准备金，取正值显示',
    '利息支出': '其他输入项 → 利息支出，取正值显示',
    '税金及附加': '费用输入项 → 税金及附加（当月发生数），取正值显示',
    '手续费及佣金支出': '费用输入项 → 手续费及佣金支出（当月发生数），取正值显示',
    '业务及管理费': '费用输入项 → 业务及管理费（当月发生数），取正值显示',
    '信用减值损失': '其他输入项 → 信用减值损失，取正值显示',
    '其他资产减值损失': '其他输入项 → 其他资产减值损失，取正值显示',
    '其他业务成本': '其他输入项 → 其他业务成本，取正值显示',
    '加：营业外收入': '其他输入项 → 营业外收入',
    '减：营业外支出': '其他输入项 → 营业外支出，取正值显示',
    '一、营业总收入': '= 保险服务收入 + 利息收入 + 投资收益 + 其他收益 + 公允价值变动收益 + 汇兑收益 + 其他业务收入 + 资产处置收益',
    '二、营业总支出': '= 保险服务费用 + 分出保费的分摊 + 承保财务损失 + 提取保费准备金 + 利息支出 + 税金及附加 + 手续费及佣金支出 + 业务及管理费 + 信用减值损失 + 其他资产减值损失 + 其他业务成本 - 摊回保险服务费用 - 分出再保险财务收益',
    '三、营业利润（亏损以"-"号填列）': '= 营业总收入 - 营业总支出',
    '四、利润总额（亏损总额以"-"号填列）': '= 营业利润 + 营业外收入 - 营业外支出',
    '减：所得税费用': '= 利润总额 × 25%',
    '五、净利润（净亏损以"-"号填列）': '= 利润总额 - 所得税费用',
    '六、其他综合收益的税后净额': '= PAA汇总的OCI列汇总',
    '七、综合收益总额': '= 净利润 + 其他综合收益的税后净额',
    '承保利润': '= 保险服务收入 - 保险服务费用 - 分出保费的分摊 + 摊回保险服务费用 - 承保财务损失 + 分出再保险财务收益 - 提取保费准备金',
    '保险合同负债': 'PAA汇总的负债类列汇总（未到期责任负债 + 已发生未决赔款负债）',
    '分出再保险合同资产': 'PAA汇总的分出业务负债列汇总，取负值（资产）',
    '资产总计': '= 分出再保险合同资产',
    '负债合计': '= 保险合同负债',
    '负债及所有者权益总计': '= 保险合同负债 + 分出再保险合同资产',
  };

  const formula = formulaMap[item] || '暂无计算逻辑说明';
  const modeLabel = isAnnual ? '年度' : (FS_VIEW_MODE.toUpperCase());
  const aggLabel = isAnnual ? (isFlow ? '各月MTD之和' : '年末值（最后一个月）') : '当期值';

  // 构建月度明细表格（年度模式下展示各月明细）
  let monthlyDetailHtml = '';
  if (isAnnual && periodIndices.length > 1) {
    monthlyDetailHtml = `
    <div style="margin-top:16px">
      <h4 style="margin:0 0 8px 0;font-size:14px;color:var(--text-pri)">月度明细</h4>
      <table class="data-table" style="font-size:12px">
        <thead><tr><th>月份</th><th>MTD值</th><th>YTD累计</th></tr></thead>
        <tbody>
          ${periodIndices.map((idx, i) => {
            const mtdVal = fs.mtd.income_statement.find(r => r.item === item)?.values[idx] ||
                           fs.mtd.balance_sheet.find(r => r.item === item)?.values[idx] || 0;
            const ytdVal = fs.ytd.income_statement.find(r => r.item === item)?.values[idx] ||
                           fs.ytd.balance_sheet.find(r => r.item === item)?.values[idx] || 0;
            const dateLabel = dates[idx] ? dates[idx].substring(0, 7) : '-';
            return `<tr><td>${dateLabel}</td><td class="num">${fmtU(mtdVal)}</td><td class="num">${fmtU(ytdVal)}</td></tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>`;
  }

  // 模态框
  const modal = document.getElementById('cell-detail-modal');
  if (modal) {
    modal.innerHTML = `
    <div class="modal-overlay" onclick="if(event.target===this)closeCellDetail()">
      <div class="modal-content" style="max-width:640px">
        <div class="modal-header" style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid var(--border-color)">
          <h3 style="margin:0;font-size:16px">白盒计算逻辑</h3>
          <button class="btn btn-default btn-sm" onclick="closeCellDetail()">关闭</button>
        </div>
        <div style="padding:20px;max-height:70vh;overflow:auto">
          <table class="data-table" style="font-size:13px;margin-bottom:16px">
            <tr><td style="color:var(--text-sec);width:120px">报表</td><td>${section}</td></tr>
            <tr><td style="color:var(--text-sec)">科目</td><td><strong>${item}</strong></td></tr>
            <tr><td style="color:var(--text-sec)">期间</td><td>${periodLabel}</td></tr>
            <tr><td style="color:var(--text-sec)">口径</td><td>${modeLabel} / ${aggLabel}</td></tr>
            <tr><td style="color:var(--text-sec)">数值</td><td class="num"><strong style="font-size:16px;color:var(--primary)">${fmtU(displayValue)}</strong></td></tr>
          </table>
          <div style="background:var(--bg-color);border-radius:6px;padding:12px 16px;margin-bottom:8px">
            <div style="font-size:12px;color:var(--text-sec);margin-bottom:4px">计算逻辑</div>
            <div style="font-size:13px;line-height:1.8">${formula}</div>
          </div>
          ${monthlyDetailHtml}
        </div>
      </div>
    </div>`;
    modal.style.display = 'block';
  }
}

function closeCellDetail() {
  const modal = document.getElementById('cell-detail-modal');
  if (modal) {
    modal.style.display = 'none';
    modal.innerHTML = '';
  }
}

// 财务报表视图切换函数
function setFsViewMode(mode) {
  FS_VIEW_MODE = mode;
  renderPage('financial-statements');
}
function setFsPeriodMode(mode) {
  FS_PERIOD_MODE = mode;
  renderPage('financial-statements');
}

// 获取计算结果中的PAA汇总HTML (新版 - 按附件PAA计算_汇总格式)
function getPaaSummaryHtml() {
  if (!CALC_RESULT || !CALC_RESULT.combinedSummary) return null;
  const rows = CALC_RESULT.combinedSummary;
  if (rows.length === 0) return null;

  // 按期间聚合
  const periodData = {};
  rows.forEach(r => {
    const period = r['预测间隔'] || 1;
    if (!periodData[period]) periodData[period] = {};
    for (const [key, val] of Object.entries(r)) {
      if (key.startsWith('输出_')) {
        const num = typeof val === 'number' ? val : parseFloat(val) || 0;
        periodData[period][key] = (periodData[period][key] || 0) + num;
      }
    }
  });

  const periods = Object.keys(periodData).sort((a,b)=>parseInt(a)-parseInt(b));

  // 完整的输出列定义 (按附件PAA计算_汇总格式)
  const allItems = [
    { group: '未到期责任负债', items: [
      { label: '未到期责任负债_非亏损部分', key: '输出_未到期责任负债_非亏损部分' },
      { label: '未到期责任负债_亏损部分', key: '输出_未到期责任负债_亏损部分' },
      { label: '未到期责任负债_亏损摊回', key: '输出_未到期责任负债_亏损摊回' },
    ]},
    { group: '已发生未决赔款负债', items: [
      { label: '已发生未决赔款负债_预期现金流', key: '输出_已发生未决赔款负债_预期现金流' },
      { label: '间接理赔费用负债_预期现金流', key: '输出_间接理赔费用负债_预期现金流' },
      { label: '已发生未决赔款负债_再保人不履约_预期现金流', key: '输出_已发生未决赔款负债_再保人不履约_预期现金流' },
      { label: '已发生未决赔款负债_非金融风险调整', key: '输出_已发生未决赔款负债_非金融风险调整' },
      { label: '间接理赔费用负债_非金融风险调整', key: '输出_间接理赔费用负债_非金融风险调整' },
      { label: '已发生未决赔款负债_再保人不履约_非金融风险调整', key: '输出_已发生未决赔款负债_再保人不履约_非金融风险调整' },
    ]},
    { group: '损益类', items: [
      { label: '保险合同收入', key: '输出_保险合同收入' },
      { label: '赔付与费用_分解的投资成分', key: '输出_赔付与费用_分解的投资成分' },
      { label: '赔付与费用_摊销的保险获取现金流', key: '输出_赔付与费用_摊销的保险获取现金流' },
      { label: '亏损合同损益', key: '输出_亏损合同损益' },
      { label: '亏损摊回损益', key: '输出_亏损摊回损益' },
      { label: '赔付与费用_已发生未决赔款负债提转差_预期现金流', key: '输出_赔付与费用_已发生未决赔款负债提转差_预期现金流' },
      { label: '赔付与费用_已发生未决赔款负债提转差_非金融风险调整', key: '输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整' },
      { label: '赔付与费用_间接理赔费用提转差_预期现金流', key: '输出_赔付与费用_间接理赔费用提转差_预期现金流' },
      { label: '赔付与费用_间接理赔费用提转差_非金融风险调整', key: '输出_赔付与费用_间接理赔费用提转差_非金融风险调整' },
      { label: '赔付与费用_已发生未决_再保人不履约_预期现金流', key: '输出_赔付与费用_已发生未决_再保人不履约_预期现金流' },
      { label: '赔付与费用_已发生未决_再保人不履约_非金融风险调整', key: '输出_赔付与费用_已发生未决_再保人不履约_非金融风险调整' },
    ]},
    { group: 'IFIE (保险财务损益)', items: [
      { label: 'IFIE_未到期_未到期计息', key: '输出_IFIE_未到期_未到期计息' },
      { label: 'IFIE_已发生未决_已发生未决赔款负债计息_预期现金流', key: '输出_IFIE_已发生未决_已发生未决赔款负债计息_预期现金流' },
      { label: 'IFIE_已发生未决_已发生未决赔款负债计息_非金融风险调整', key: '输出_IFIE_已发生未决_已发生未决赔款负债计息_非金融风险调整' },
      { label: 'IFIE_已发生未决_间接理赔费用计息_预期现金流', key: '输出_IFIE_已发生未决_间接理赔费用计息_预期现金流' },
      { label: 'IFIE_已发生未决_间接理赔费用计息_非金融风险调整', key: '输出_IFIE_已发生未决_间接理赔费用计息_非金融风险调整' },
    ]},
    { group: '现金流', items: [
      { label: '现金流_支付的赔付与理赔费用', key: '输出_现金流_支付的赔付与理赔费用' },
      { label: '现金流_支付的维持费用_计量', key: '输出_现金流_支付的维持费用_计量' },
      { label: '现金流_支付的维持费用_实际维持费用_分子合同组合', key: '输出_现金流_支付的维持费用_实际维持费用_分子合同组合' },
      { label: '实际维持费用分摊比例', key: '实际维持费用分摊比例' },
      { label: '现金流_支付的维持费用', key: '输出_现金流_支付的维持费用' },
      { label: '现金流_收到的保费', key: '输出_现金流_收到的保费' },
      { label: '现金流_支付的IACF', key: '输出_现金流_支付的IACF' },
    ]},
    { group: 'OCI (其他综合收益)', items: [
      { label: 'OCI_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流', key: '输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流' },
      { label: 'OCI_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整', key: '输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整' },
      { label: 'OCI_已发生未决_间接理赔费用计息与利率变化_预期现金流', key: '输出_OCI_已发生未决_间接理赔费用计息与利率变化_预期现金流' },
      { label: 'OCI_已发生未决_间接理赔费用计息与利率变化_非金融风险调整', key: '输出_OCI_已发生未决_间接理赔费用计息与利率变化_非金融风险调整' },
    ]},
  ];

  let html = `<div style="margin-bottom:8px">${unitSelectorHTML()}</div><div class="table-wrapper" style="max-height:700px;overflow:auto"><table class="data-table" style="font-size:12px"><thead><tr><th style="min-width:200px">项目（${unitLabel()}）</th>${periods.map(p=>`<th>第${p}期</th>`).join('')}</tr></thead><tbody>`;
  allItems.forEach(group => {
    html += `<tr class="section-row"><td colspan="${periods.length+1}">${group.group}</td></tr>`;
    group.items.forEach(item => {
      html += `<tr><td style="padding-left:36px">${item.label}</td>${periods.map(p=>`<td class="num">${fmtU(periodData[p]?.[item.key]||0)}</td>`).join('')}</tr>`;
    });
  });
  html += `</tbody></table></div>`;
  return html;
}

function updateSidebarUploadStatus(source, success) {
  // Update sidebar indicators after upload
  const items = document.querySelectorAll('.sidebar-item');
  items.forEach(item => {
    const page = item.dataset.page;
    if (source === 'excel' && page === 'excel-upload') {
      const statusEl = item.querySelector('.upload-status');
      if (statusEl) {
        statusEl.className = 'upload-status ' + (success ? 'loaded' : 'error');
      }
    }
    if (source === 'dock' && page === 'system-dock-upload') {
      const statusEl = item.querySelector('.upload-status');
      if (statusEl) {
        statusEl.className = 'upload-status ' + (success ? 'loaded' : 'error');
      }
    }
  });
  // Also update sheet items
  const sheetItems = document.querySelectorAll('.sidebar-item[data-page^="sheet-"]');
  sheetItems.forEach(item => {
    const page = item.dataset.page;
    const sheetName = page.replace('sheet-', '');
    const isExcel = SIDEBAR_CONFIG.dataInput.excelSheets.includes(sheetName);
    const sourceType = isExcel ? 'excel' : 'dock';
    const status = getSheetStatus(sheetName, sourceType);
    const statusEl = item.querySelector('.upload-status');
    const countEl = item.querySelector('.row-count');
    if (statusEl) {
      statusEl.className = 'upload-status ' + (status.loaded ? 'loaded' : 'not-loaded');
    }
    if (countEl) {
      countEl.textContent = status.loaded ? status.rowCount + '行' : '';
    }
  });
}

function renderSidebar() {
  let html = '';
  const viewer = isViewer();

  // 1. 结果展示面板板块（所有登录用户可见）
  html += `<div class="sidebar-section-title">结果展示面板</div>`;
  SIDEBAR_CONFIG.results.forEach(item => {
    const activeCls = CURRENT_PAGE === item.page ? ' active' : '';
    html += `<div class="sidebar-item${activeCls}" data-page="${item.page}"><span class="sidebar-item-icon">${item.icon}</span><span class="sidebar-label">${item.label}</span></div>`;
  });

  // 2. 数据及逻辑归集板块（所有登录用户可见）
  html += `<div class="sidebar-section-title">数据及逻辑归集</div>`;
  SIDEBAR_CONFIG.dataLogic.forEach(item => {
    const activeCls = CURRENT_PAGE === item.page ? ' active' : '';
    html += `<div class="sidebar-item${activeCls}" data-page="${item.page}"><span class="sidebar-item-icon">${item.icon}</span><span class="sidebar-label">${item.label}</span></div>`;
  });

  // 3. 数据输入板块
  // viewer 仅可查看已上传数据（Excel上传数据 / 系统对接数据），上传入口隐藏
  html += `<div class="sidebar-section-title">数据输入</div>`;

  if (!viewer) {
    // 顶部项：上传接口（仅非查看权限账号可见）
    SIDEBAR_CONFIG.dataInput.top.forEach(item => {
      let statusIcon = '';
      if (item.page === 'excel-upload') {
        const st = getUploadStatus('excel');
        statusIcon = `<span class="upload-status ${st}"></span>`;
      } else if (item.page === 'system-dock-upload') {
        const st = getUploadStatus('dock');
        statusIcon = `<span class="upload-status ${st}"></span>`;
      } else if (item.page === 'actual-upload') {
        const loaded = actualVsExpectedState && actualVsExpectedState.loaded;
        statusIcon = `<span class="upload-status ${loaded ? 'loaded' : 'not-loaded'}"></span>`;
      }
      const activeCls = CURRENT_PAGE === item.page ? ' active' : '';
      html += `<div class="sidebar-item${activeCls}" data-page="${item.page}"><span class="sidebar-item-icon">${item.icon}</span><span class="sidebar-label">${item.label}</span>${statusIcon}</div>`;
    });
  }

  // Excel上传数据分项（可折叠，所有登录用户可见）
  html += `<div class="sidebar-subsection excel sidebar-subsection-toggle" data-group="excel-sheets">▶ 📋 Excel上传数据</div>`;
  html += `<div class="sidebar-sheet-group" id="excel-sheets" style="display:none">`;
  SIDEBAR_CONFIG.dataInput.excelSheets.forEach(sheetName => {
    const status = getSheetStatus(sheetName, 'excel');
    const spec = EXCEL_UPLOAD_SPECS[sheetName];
    const shortName = sheetName.length > 12 ? sheetName.substring(0, 11) + '…' : sheetName;
    const activeCls = CURRENT_PAGE === `sheet-${sheetName}` ? ' active' : '';
    html += `<div class="sidebar-item${activeCls}" data-page="sheet-${sheetName}"><span class="sidebar-item-icon" style="font-size:12px;color:var(--text-light)">${spec.category[0]}</span><span class="sidebar-label" title="${sheetName}">${shortName}</span><span class="upload-status ${status.loaded?'loaded':'not-loaded'}"></span><span class="row-count">${status.loaded?status.rowCount+'行':''}</span></div>`;
  });
  html += `</div>`;

  // 系统对接数据分项（可折叠，所有登录用户可见）
  html += `<div class="sidebar-subsection dock sidebar-subsection-toggle" data-group="dock-sheets">▶ 🔗 系统对接数据</div>`;
  html += `<div class="sidebar-sheet-group" id="dock-sheets" style="display:none">`;
  SIDEBAR_CONFIG.dataInput.dockSheets.forEach(sheetName => {
    const status = getSheetStatus(sheetName, 'dock');
    const spec = SYSTEM_DOCK_SPECS[sheetName];
    const shortName = sheetName.length > 12 ? sheetName.substring(0, 11) + '…' : sheetName;
    const activeCls = CURRENT_PAGE === `sheet-${sheetName}` ? ' active' : '';
    html += `<div class="sidebar-item${activeCls}" data-page="sheet-${sheetName}"><span class="sidebar-item-icon" style="font-size:12px;color:var(--text-light)">${spec.category[0]}</span><span class="sidebar-label" title="${sheetName}">${shortName}</span><span class="upload-status ${status.loaded?'loaded':'not-loaded'}"></span><span class="row-count">${status.loaded?status.rowCount+'行':''}</span></div>`;
  });
  html += `</div>`;
  // end 数据输入板块

  // 3. 计算板块（仅非查看权限账号可见，并隐藏新业务/现有业务计量入口）
  if (!viewer) {
  html += `<div class="sidebar-section-title">计算</div>`;
  SIDEBAR_CONFIG.calc
    .filter(item => item.page !== 'new-business-calc' && item.page !== 'existing-business-calc')
    .forEach(item => {
      const activeCls = CURRENT_PAGE === item.page ? ' active' : '';
      html += `<div class="sidebar-item${activeCls}" data-page="${item.page}"><span class="sidebar-item-icon">${item.icon}</span><span class="sidebar-label">${item.label}</span></div>`;
    });
  } // end if (!viewer) 计算板块

  // 4. 计量结果输出板块（所有登录用户可见）
  html += `<div class="sidebar-section-title">计量结果输出</div>`;
  SIDEBAR_CONFIG.output.forEach(item => {
    const activeCls = CURRENT_PAGE === item.page ? ' active' : '';
    html += `<div class="sidebar-item${activeCls}" data-page="${item.page}"><span class="sidebar-item-icon">${item.icon}</span><span class="sidebar-label">${item.label}</span></div>`;
  });

  // 5. 验证板块（仅非查看权限账号可见，并隐藏差异比对结果入口）
  if (!viewer) {
  html += `<div class="sidebar-section-title">验证</div>`;
  SIDEBAR_CONFIG.verify
    .filter(item => item.page !== 'verify-results')
    .forEach(item => {
      const activeCls = CURRENT_PAGE === item.page ? ' active' : '';
      html += `<div class="sidebar-item${activeCls}" data-page="${item.page}"><span class="sidebar-item-icon">${item.icon}</span><span class="sidebar-label">${item.label}</span></div>`;
    });
  } // end if (!viewer) 验证板块

  // 6. 系统管理板块（仅非查看权限账号可见）
  if (!viewer) {
  html += `<div class="sidebar-section-title">系统管理</div>`;
  SIDEBAR_CONFIG.system.forEach(item => {
    const activeCls = CURRENT_PAGE === item.page ? ' active' : '';
    html += `<div class="sidebar-item${activeCls}" data-page="${item.page}"><span class="sidebar-item-icon">${item.icon}</span><span class="sidebar-label">${item.label}</span></div>`;
  });
  } // end if (!viewer) 系统管理板块

  return html;
}

function renderApp() {
  const ver = SYSTEM_CONFIG.version;
  document.getElementById('app').innerHTML = `
    <div class="app">
      <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
          <div class="sidebar-logo">I17</div>
          <div class="sidebar-header-info">
            <h1>新准则预测模型</h1>
            <p class="version-display">${ver} | ${SYSTEM_CONFIG.buildDate}</p>
          </div>
        </div>
        <div class="sidebar-nav" id="sidebarNav">${renderSidebar()}</div>
        <div class="sidebar-footer">
          <span class="version-badge">${ver}</span> 评估时点: ${MODEL_DATA.basicInfo.evalDate} | 预测期: ${MODEL_DATA.basicInfo.forecastPeriods}期<br>
          Excel上传: ${SIDEBAR_CONFIG.dataInput.excelSheets.length}表 | 系统对接: ${SIDEBAR_CONFIG.dataInput.dockSheets.length}表 | 验证: 4表<br>
          云端: <a href="http://121.41.98.55/" target="_blank" style="color:var(--primary);">121.41.98.55</a>
        </div>
        <div class="sidebar-trigger" id="sidebarTrigger" onclick="toggleSidebar()" title="收起 / 展开侧边栏">
          <span class="trigger-icon">«</span>
        </div>
      </div>
      <div class="main">
        <div class="topbar">
          <div class="topbar-left">
            <button class="topbar-toggle" onclick="toggleSidebar()">☰</button>
            <div>
              <div class="topbar-title" id="topbarTitle">结果总览</div>
              <div class="topbar-breadcrumb" id="topbarBreadcrumb">结果展示面板 / 结果总览</div>
            </div>
          </div>
          <div class="topbar-right">
            ${window.DJANGO_USER && window.DJANGO_USER.is_authenticated ? `
            <span class="user-badge" title="已登录">👤 ${window.DJANGO_USER.username}</span>
            ${window.DJANGO_USER.is_viewer ? `<span class="role-badge viewer" title="仅查看权限">查看权限</span>` : ''}
            <a href="/logout/" class="btn-logout-top">退出</a>
            ` : ''}
            <span class="version-badge">${ver}</span>
          </div>
        </div>
        <div class="content" id="content"></div>
      </div>
    </div>`;
  document.getElementById('sidebarNav').addEventListener('click', e => {
    // 处理侧边栏子分区折叠/展开
    const toggle = e.target.closest('.sidebar-subsection-toggle');
    if (toggle) {
      const groupId = toggle.dataset.group;
      const group = document.getElementById(groupId);
      if (group) {
        const isVisible = group.style.display !== 'none';
        group.style.display = isVisible ? 'none' : 'block';
        // 更新箭头方向
        const arrow = toggle.textContent;
        toggle.textContent = isVisible ? arrow.replace('▼', '▶') : arrow.replace('▶', '▼');
      }
      return;
    }
    // 处理导航项点击
    const item = e.target.closest('.sidebar-item'); if (!item) return;
    const page = item.dataset.page; if (!page) return;
    document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
    item.classList.add('active');
    const info = pageTitles[page] || { t: page, b: page };
    document.getElementById('topbarTitle').textContent = info.t;
    document.getElementById('topbarBreadcrumb').textContent = info.b;
    renderPage(page, {navigate: true});
  });
  renderPage('dashboard', {navigate: true});
}

let CURRENT_PAGE = 'dashboard';  // 当前页面标识，用于异步加载完成后判断是否仍需重渲染

// ===== 页面状态保持（切页不丢失输入/查询结果）=====
const _PAGE_DOM_CACHE = {};  // page -> 切走前序列化的 content.innerHTML

// 切走前把当前页面的实时 DOM 状态序列化保存：
// 同步输入框/文本域/下拉的当前值到 DOM 属性，保证序列化包含用户最新输入与动态结果
function _capturePageDOM(page) {
  const content = document.getElementById('content');
  if (!content) return;
  content.querySelectorAll('textarea').forEach(el => { el.textContent = el.value; });
  content.querySelectorAll('input').forEach(el => {
    if (el.type === 'checkbox' || el.type === 'radio') {
      if (el.checked) el.setAttribute('checked', ''); else el.removeAttribute('checked');
    } else {
      el.setAttribute('value', el.value);
    }
  });
  content.querySelectorAll('select').forEach(sel => {
    Array.from(sel.options).forEach(opt => {
      if (opt.value === sel.value) opt.setAttribute('selected', ''); else opt.removeAttribute('selected');
    });
  });
  _PAGE_DOM_CACHE[page] = content.innerHTML;
}

// 各页面导航恢复时重新执行的初始化（与首次进入时的副作用保持一致）
const PAGE_RESTORE_INIT = {
  'excel-upload': () => initExcelUploadEvents(),
  'system-dock-upload': () => initSystemDockUploadEvents(),
  'actual-upload': () => { initActualUploadEvents(); initOldStandardUploadEvents(); },
  'verify-upload': () => initVerifyUploadEvents(),
  'verify-check': () => initVerifyCheckEvents(),
  'actual-vs-expected': () => { initActualVsExpectedEvents(); initCharts('actual-vs-expected'); },
  'old-new-bridge': () => {},
  'deploy-manage': () => initDeployManageEvents(),
  'data-logic-collection': () => initDataLogicCollectionEvents(),
  'system-log': () => {},
  'sql-query': () => {
    initSqlQueryEvents();
    if (PENDING_SQL_TEMPLATE) {
      const ta = document.getElementById('sql-editor');
      if (ta) ta.value = PENDING_SQL_TEMPLATE;
      PENDING_SQL_TEMPLATE = '';
    }
  },
  'table-dict': () => {},
};

function renderPage(page, opts) {
  closeAllCdd();
  destroyCharts();

  // 切走前捕获旧页面 DOM（含用户输入与动态结果），刷新缓存
  if (CURRENT_PAGE && CURRENT_PAGE !== page) {
    _capturePageDOM(CURRENT_PAGE);
  }
  CURRENT_PAGE = page;
  const content = document.getElementById('content');

  // 侧边栏导航切换：若已有缓存则直接恢复 DOM（保留输入/查询结果），不重新渲染
  const navigate = !!(opts && opts.navigate);
  if (navigate && Object.prototype.hasOwnProperty.call(_PAGE_DOM_CACHE, page)) {
    content.innerHTML = _PAGE_DOM_CACHE[page];
    const init = PAGE_RESTORE_INIT[page];
    if (typeof init === 'function') setTimeout(init, 50);
    else if (typeof pages[page] === 'function') setTimeout(() => initCharts(page), 50);
    if (page === 'calc-pipeline') {
      resumeCalcProgressIfRunning();
      resumeVersionPushIfRunning();
      loadCalcVersions();
    }
    return;
  }

  _paintPage(page, content);
  // 首次渲染（或页内交互刷新）后更新缓存
  _PAGE_DOM_CACHE[page] = content.innerHTML;
}

function _paintPage(page, content) {
  // viewer 权限页面访问控制（与侧边栏隐藏规则一致，防止直接通过 URL/脚本访问）
  if (isViewer()) {
    const restricted = new Set([
      'new-business-calc', 'existing-business-calc', 'calc-pipeline', 'input-processing',
      'verify-upload', 'verify-check', 'verify-results',
      'deploy-manage',
      'excel-upload', 'system-dock-upload', 'actual-upload',
      'system-log', 'sql-query', 'table-dict',
    ]);
    // sheet-xxx 为只读数据展示页，viewer 允许查看
    if (restricted.has(page)) {
      content.innerHTML = `
<div class="page active">
  <div class="page-header"><h2>访问受限</h2><p>当前账号为查看权限，无法访问该模块</p></div>
  <div class="alert alert-warning">您当前为查看权限（viewer），仅能查看「结果展示面板」「计量结果输出」「数据及逻辑归集」等只读模块。如需访问完整功能，请使用管理员账号登录。</div>
</div>`;
      updateTopbarBreadcrumb('访问受限');
      return;
    }
  }

  // Handle sheet data display pages
  if (page.startsWith('sheet-')) {
    const sheetName = page.replace('sheet-', '');
    content.innerHTML = renderSheetDataPage(sheetName);
    return;
  }
  
  // Handle upload pages
  if (page === 'excel-upload') {
    content.innerHTML = renderExcelUploadPage();
    setTimeout(() => initExcelUploadEvents(), 50);
    return;
  }
  if (page === 'system-dock-upload') {
    content.innerHTML = renderSystemDockUploadPage();
    setTimeout(() => initSystemDockUploadEvents(), 50);
    return;
  }
  if (page === 'actual-upload') {
    content.innerHTML = renderActualUploadPage();
    setTimeout(() => { initActualUploadEvents(); initOldStandardUploadEvents(); }, 50);
    return;
  }
  if (page === 'verify-upload') {
    content.innerHTML = renderVerifyUploadPage();
    setTimeout(() => initVerifyUploadEvents(), 50);
    return;
  }
  if (page === 'verify-results') {
    content.innerHTML = renderVerifyResultsPage();
    return;
  }
  if (page === 'verify-check') {
    content.innerHTML = renderVerifyCheckPage();
    setTimeout(() => initVerifyCheckEvents(), 50);
    return;
  }
  if (page === 'actual-vs-expected') {
    content.innerHTML = renderActualVsExpectedPage();
    setTimeout(() => {
      initActualVsExpectedEvents();
      initCharts(page);
    }, 50);
    return;
  }
  if (page === 'old-new-bridge') {
    content.innerHTML = renderOldNewBridgePage();
    // 数据为空（含上传后手动失效/之前加载失败）时重新拉取；有数据则复用，避免反复重绘
    if (!oldNewBridgeState.data && !oldNewBridgeState.loading) {
      setTimeout(() => loadOldNewBridgeData(), 50);
    }
    return;
  }
  if (page === 'deploy-manage') {
    content.innerHTML = renderDeployManagePage();
    setTimeout(() => initDeployManageEvents(), 50);
    return;
  }
  if (page === 'data-logic-collection') {
    content.innerHTML = renderDataLogicCollectionPage();
    setTimeout(() => initDataLogicCollectionEvents(), 50);
    return;
  }
  if (page === 'system-log') {
    content.innerHTML = renderSystemLogPage();
    setTimeout(() => { _LOG_PAGE = 1; loadSystemLog(); }, 50);
    return;
  }
  if (page === 'sql-query') {
    content.innerHTML = renderSqlQueryPage();
    setTimeout(() => {
      initSqlQueryEvents();
      if (PENDING_SQL_TEMPLATE) {
        const ta = document.getElementById('sql-editor');
        if (ta) ta.value = PENDING_SQL_TEMPLATE;
        PENDING_SQL_TEMPLATE = '';
      }
    }, 50);
    return;
  }
  if (page === 'table-dict') {
    content.innerHTML = renderTableDictPage();
    setTimeout(() => loadTableDict(), 50);
    return;
  }

  // Handle other pages
  content.innerHTML = pages[page] ? pages[page]() : pages['dashboard']();
  setTimeout(() => initCharts(page), 50);

  // 计算流程 / 多情景比对页面加载时获取场景列表（确保加压描述正确显示）
  if ((page === 'calc-pipeline' || page === 'scenario-compare') && CALC_SCENARIOS.length === 0 && hasUploadedData()) {
    fetchScenarios().then(data => {
      if (data.scenarios && data.scenarios.length > 0) {
        CALC_SCENARIOS = data.scenarios;
        // 重新渲染以展示真实场景卡片 / 情景加压描述
        if (CURRENT_PAGE === page) renderPage(page);
      }
    });
  }

  // 进入计算流程页：若后端计算仍在进行，自动恢复进度显示（切导航不中断计算）
  if (page === 'calc-pipeline') {
    resumeCalcProgressIfRunning();
    resumeVersionPushIfRunning();
    loadCalcVersions();
  }

  // 输入整理页：加载情景对比（选定场景影响的输入整理表与基础情景的比对变动）
  if (page === 'input-processing' && hasUploadedData()) {
    loadInputOrg();
  }
}

// ===== 数据展示页面 =====
function renderSheetDataPage(sheetName) {
  const isExcel = SIDEBAR_CONFIG.dataInput.excelSheets.includes(sheetName);
  const source = isExcel ? 'excel' : 'dock';
  const data = isExcel ? excelUploadData : systemDockData;
  const specs = isExcel ? EXCEL_UPLOAD_SPECS : SYSTEM_DOCK_SPECS;
  const spec = specs[sheetName];
  
  if (!data || !data[sheetName]) {
    return `
    <div class="page active">
      <div class="page-header"><h2>${sheetName}</h2><p>${spec ? spec.description : ''}</p></div>
      <div class="alert alert-warning"><strong>数据未加载：</strong>请先通过${isExcel ? 'Excel上传接口' : '系统对接接口'}上传数据文件。</div>
      <div class="card"><div class="card-body" style="text-align:center;padding:40px">
        <div style="font-size:40px;margin-bottom:12px">${isExcel ? '📤' : '🔗'}</div>
        <p class="text-muted">点击左侧"${isExcel ? 'Excel上传接口' : '系统对接接口'}"上传数据文件</p>
        <p class="text-muted" style="font-size:12px;margin-top:8px">接口: ${isExcel ? 'Excel上传接口' : '系统对接接口'} | 工作表: ${sheetName} | 类别: ${spec ? spec.category : '-'}</p>
      </div></div>
    </div>`;
  }

  const sheet = data[sheetName];
  const headers = sheet.headers || [];
  const rows = sheet.rows || [];
  const totalRows = sheet.totalRows || 0;
  const displayCols = sheet.displayCols || headers.length;
  
  // 分页状态存储在全局
  if (!window._sheetPageState) window._sheetPageState = {};
  const ps = window._sheetPageState;
  const key = source + '_' + sheetName;
  if (!ps[key]) ps[key] = { page: 0, pageSize: 50, showAll: false };
  const state = ps[key];
  
  const pageSize = state.showAll ? rows.length : state.pageSize;
  const totalPages = Math.ceil(rows.length / pageSize);
  const currentPage = Math.min(state.page, Math.max(0, totalPages - 1));
  const startIdx = currentPage * pageSize;
  const endIdx = Math.min(startIdx + pageSize, rows.length);
  const displayRows = state.showAll ? rows : rows.slice(startIdx, endIdx);
  
  // 限制显示列数
  const maxDisplayCols = 20;
  const showAllCols = headers.length <= maxDisplayCols;
  const displayHeaders = showAllCols ? headers : headers.slice(0, maxDisplayCols);
  
  // 构建表格
  let tableHtml = '';
  if (headers.length > 0) {
    tableHtml = `<div class="table-wrapper" style="max-height:600px;overflow:auto"><table class="data-table"><thead><tr>`;
    displayHeaders.forEach((h, idx) => {
      const isDate = isDateColumn(h);
      tableHtml += `<th${isDate ? ' style="background:#E6F4FF"' : ''}>${h !== null && h !== undefined ? h : ''}</th>`;
    });
    if (!showAllCols) {
      tableHtml += `<th>... (+${headers.length - maxDisplayCols}列)</th>`;
    }
    tableHtml += `</tr></thead><tbody>`;
    
    displayRows.forEach((row, idx) => {
      tableHtml += `<tr>`;
      for (let i = 0; i < (showAllCols ? headers.length : maxDisplayCols); i++) {
        const val = row[i];
        const h = headers[i];
        if (val === null || val === undefined || val === '') {
          tableHtml += `<td>-</td>`;
        } else if (isDateColumn(h)) {
          // 日期列格式化显示
          tableHtml += `<td style="background:#E6F4FF;color:#0958D9;font-weight:500">${fmtDate(val)}</td>`;
        } else if (typeof val === 'number') {
          const isNeg = val < 0;
          tableHtml += `<td class="num${isNeg ? ' negative' : ''}">${val.toLocaleString('zh-CN', {maximumFractionDigits: 6})}</td>`;
        } else {
          tableHtml += `<td>${val}</td>`;
        }
      }
      if (!showAllCols) {
        tableHtml += `<td class="text-muted">...</td>`;
      }
      tableHtml += `</tr>`;
    });
    
    tableHtml += `</tbody></table></div>`;
  }

  // 分页控件
  let paginationHtml = '';
  if (!state.showAll && totalPages > 1) {
    paginationHtml = `
    <div class="pagination" style="display:flex;align-items:center;gap:8px;justify-content:center;margin-top:16px">
      <button class="btn btn-outline btn-sm" onclick="changeSheetPage('${key}', 0)" ${currentPage === 0 ? 'disabled' : ''}>首页</button>
      <button class="btn btn-outline btn-sm" onclick="changeSheetPage('${key}', ${currentPage - 1})" ${currentPage === 0 ? 'disabled' : ''}>上一页</button>
      <span style="font-size:13px;color:var(--text-sec)">第 ${currentPage + 1} / ${totalPages} 页 (行 ${startIdx + 1}-${endIdx})</span>
      <button class="btn btn-outline btn-sm" onclick="changeSheetPage('${key}', ${currentPage + 1})" ${currentPage >= totalPages - 1 ? 'disabled' : ''}>下一页</button>
      <button class="btn btn-outline btn-sm" onclick="changeSheetPage('${key}', ${totalPages - 1})" ${currentPage >= totalPages - 1 ? 'disabled' : ''}>末页</button>
    </div>`;
  }

  return `
  <div class="page active">
    <div class="page-header">
      <h2>${sheetName}</h2>
      <p>${spec ? spec.description : ''} | 数据来源: ${isExcel ? 'Excel上传接口' : '系统对接接口'} | 类别: ${spec ? spec.category : '-'}</p>
    </div>
    <div class="kpi-grid">
      <div class="kpi-card blue"><div class="kpi-label">数据来源</div><div class="kpi-value" style="font-size:18px">${isExcel ? 'Excel上传' : '系统对接'}</div></div>
      <div class="kpi-card green"><div class="kpi-label">总数据行数</div><div class="kpi-value">${totalRows.toLocaleString()}<span class="kpi-unit">行</span></div></div>
      <div class="kpi-card orange"><div class="kpi-label">字段数（列数）</div><div class="kpi-value">${displayCols}<span class="kpi-unit">列</span></div></div>
      <div class="kpi-card purple"><div class="kpi-label">当前展示</div><div class="kpi-value">${state.showAll ? totalRows : displayRows.length}<span class="kpi-unit">行</span></div><div class="kpi-sub">${state.showAll ? '全量展示' : '分页展示'}</div></div>
    </div>
    <div class="card">
      <div class="card-header">
        <h3>数据预览</h3>
        <div style="display:flex;gap:8px;align-items:center">
          <span class="badge">${isExcel ? 'Excel上传' : '系统对接'} | ${totalRows}行 × ${displayCols}列</span>
          <button class="btn btn-outline btn-sm" onclick="toggleShowAll('${key}')">${state.showAll ? '📄 分页查看' : '📋 查看全量数据'}</button>
          <button class="btn btn-primary btn-sm" onclick="downloadSheetExcel('${source}', '${sheetName}')">⬇ 下载Excel</button>
        </div>
      </div>
      <div class="card-body">
        ${tableHtml || '<p class="text-muted">暂无数据</p>'}
        ${paginationHtml}
      </div>
    </div>
    <div class="alert alert-info" style="margin-top:8px">
      <strong>操作说明：</strong>
      点击「查看全量数据」可在页面中查看全部 ${totalRows} 行数据；点击「下载Excel」可下载当前工作表的完整数据为 Excel 文件。
      ${!showAllCols ? `<br><strong>提示：</strong>此工作表共${headers.length}列，当前页面展示前${maxDisplayCols}列，完整列请下载Excel查看。` : ''}
    </div>
  </div>`;
}

// 分页操作
function changeSheetPage(key, page) {
  if (!window._sheetPageState) window._sheetPageState = {};
  if (!window._sheetPageState[key]) window._sheetPageState[key] = { page: 0, pageSize: 50, showAll: false };
  const totalPages = Math.ceil((window._sheetPageState[key].totalRows || 0) / window._sheetPageState[key].pageSize);
  window._sheetPageState[key].page = Math.max(0, page);
  // 重新渲染当前页面
  const activeItem = document.querySelector('.sidebar-item.active');
  if (activeItem) {
    const pageId = activeItem.dataset.page;
    const content = document.getElementById('content');
    const sheetName = pageId.replace('sheet-', '');
    content.innerHTML = renderSheetDataPage(sheetName);
  }
}

// 切换全量/分页查看
function toggleShowAll(key) {
  if (!window._sheetPageState) window._sheetPageState = {};
  if (!window._sheetPageState[key]) window._sheetPageState[key] = { page: 0, pageSize: 50, showAll: false };
  window._sheetPageState[key].showAll = !window._sheetPageState[key].showAll;
  window._sheetPageState[key].page = 0;
  const activeItem = document.querySelector('.sidebar-item.active');
  if (activeItem) {
    const pageId = activeItem.dataset.page;
    const content = document.getElementById('content');
    const sheetName = pageId.replace('sheet-', '');
    content.innerHTML = renderSheetDataPage(sheetName);
  }
}

// 下载工作表Excel
function downloadSheetExcel(source, sheetName) {
  const url = `/api/download/${source}/${encodeURIComponent(sheetName)}`;
  const link = document.createElement('a');
  link.href = url;
  link.download = `${sheetName}.xlsx`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// ===== 经营三率计算辅助函数 =====
// 从 PAA计算_MTD 明细中聚合指定财务科目的月度值，并加工成 YTD 累计序列
function getPaaMtdYtdSeries(paaMtdDetail, subject, dates) {
  if (!paaMtdDetail || !dates || !dates.length) return dates.map(() => 0);
  const monthly = dates.map(d => {
    let s = 0;
    for (const r of paaMtdDetail) {
      if (String(r['财务科目'] || '').trim() === subject) {
        const v = r[d];
        s += (typeof v === 'number' ? v : (parseFloat(v) || 0));
      }
    }
    return s;
  });
  const ytd = [];
  let cum = 0;
  for (let i = 0; i < monthly.length; i++) {
    cum += monthly[i];
    ytd.push(cum);
  }
  return ytd;
}

// 综合费用率分子：-(输出_赔付与费用_摊销的保险获取现金流 + 输出_现金流_支付的维持费用)
// cumulative=true 时返回 YTD 累计序列，cumulative=false 时返回逐月序列（与财务报表 MTD 视图口径一致）
function getPaaMtdExpenseYtdSeries(paaMtdDetail, dates, cumulative = true) {
  if (!paaMtdDetail || !dates || !dates.length) return dates.map(() => 0);
  const components = ['输出_赔付与费用_摊销的保险获取现金流', '输出_现金流_支付的维持费用'];
  const monthly = dates.map(d => {
    let s = 0;
    for (const r of paaMtdDetail) {
      if (components.includes(String(r['科目'] || '').trim())) {
        const v = r[d];
        s += (typeof v === 'number' ? v : (parseFloat(v) || 0));
      }
    }
    return -s; // 取负号
  });
  if (!cumulative) return monthly;
  const ytd = [];
  let cum = 0;
  for (const v of monthly) {
    cum += v;
    ytd.push(cum);
  }
  return ytd;
}

// 从财务报表 V2 取指定科目的 YTD 序列
function getFsYtdSeries(fs, item, section = 'income_statement') {
  if (!fs || !fs.ytd) return [];
  const sec = fs.ytd[section] || [];
  const r = sec.find(x => x.item === item);
  return r ? (r.values || []) : [];
}

// 从财务报表 V2 取指定科目的（跟随 FS_VIEW_MODE 的）序列：isYtd=true 取 YTD 累计，false 取 MTD 月度
function getFsViewSeries(fs, item, section = 'income_statement', isYtd = true) {
  if (!fs) return [];
  const src = isYtd ? fs.ytd : fs.mtd;
  const sec = (src && src[section]) || [];
  const r = sec.find(x => x.item === item);
  return r ? (r.values || []) : [];
}

// 从 PAA计算_MTD 明细按「科目」聚合指定期间（与 fs.dates 对齐）的月度值，并加工成 YTD 累计序列
// fsSubject 可选：若提供则同时匹配一级财务科目，用于区分同名二级科目（如保险服务费用 vs 摊回下的投资成分）
function getPaaMtdAggregateYtd(paaMtdDetail, subject, dates, fsSubject = null) {
  if (!paaMtdDetail || !dates || !dates.length) return dates.map(() => 0);
  // 仅取与 dates 对齐的期次列
  const alignedDates = dates.filter(Boolean);
  const targetFs = fsSubject ? String(fsSubject).trim() : null;
  const monthly = alignedDates.map(d => {
    let s = 0;
    for (const r of paaMtdDetail) {
      if (targetFs && String(r['财务科目'] || '').trim() !== targetFs) continue;
      if (String(r['科目'] || '').trim() === subject) {
        const v = r[d];
        s += (typeof v === 'number' ? v : (parseFloat(v) || 0));
      }
    }
    return s;
  });
  const ytd = [];
  let cum = 0;
  for (const v of monthly) { cum += v; ytd.push(cum); }
  return ytd;
}

// 计算经营三率：综合成本率、综合费用率、综合赔付率
function computeOperatingRatios(insRevYtd, uwProfitYtd, insSvcExpYtd, idx) {
  const rev = insRevYtd[idx] || 0;
  if (rev === 0) return { combined: 0, expense: 0, loss: 0 };
  const uw = uwProfitYtd[idx] || 0;
  const exp = insSvcExpYtd[idx] || 0;
  // 综合成本率=1-承保利润/保险服务收入；综合费用率=|保险服务费用|/保险服务收入（YTD）；综合赔付率=综合成本率-综合费用率
  const combined = (1 - uw / rev) * 100;
  const expense = (Math.abs(exp) / rev) * 100;
  const loss = combined - expense;
  return { combined, expense, loss };
}

// ===== Pages =====
const pages = {};

pages['dashboard'] = () => {
  const dataReady = hasUploadedData();
  const activeResult = dataReady ? getScenarioResult(DASH_SELECTED_SCENARIO) : null;
  const evalDate = dataReady ? (activeResult?.inputOrganized?.evalDate || excelUploadState.evalDate || MODEL_DATA.basicInfo.evalDate) : '-';
  const forecastPeriods = dataReady ? (activeResult?.inputOrganized?.forecastPeriods || excelUploadState.forecastPeriods || MODEL_DATA.basicInfo.forecastPeriods) : '-';
  if (!dataReady) {
    return `
<div class="page active">
  <div class="page-header"><h2>结果总览</h2><p>新准则预测模型 ${SYSTEM_CONFIG.version}</p></div>
  ${getEmptyDataMessage()}
  <div class="two-col">
    <div class="card"><div class="card-header"><h3>系统信息</h3></div><div class="card-body">
      <div class="info-row"><span class="label">系统版本</span><span class="value"><span class="version-badge">${SYSTEM_CONFIG.version}</span></span></div>
      <div class="info-row"><span class="label">构建日期</span><span class="value">${SYSTEM_CONFIG.buildDate}</span></div>
      <div class="info-row"><span class="label">计量方法</span><span class="value">PAA (保费分配法)</span></div>
      <div class="info-row"><span class="label">Excel上传接口</span><span class="value">${SIDEBAR_CONFIG.dataInput.excelSheets.length} 个工作表</span></div>
      <div class="info-row"><span class="label">系统对接接口</span><span class="value">${SIDEBAR_CONFIG.dataInput.dockSheets.length} 个工作表</span></div>
    </div></div>
    <div class="card"><div class="card-header"><h3>数据上传状态</h3></div><div class="card-body">
      <div class="info-row"><span class="label">Excel上传接口</span><span class="value">${excelUploadState.loaded ? (excelUploadState.success ? '<span class="text-success">已上传 - 校验通过</span>' : '<span class="text-danger">已上传 - 校验失败</span>') : '<span class="text-muted">未上传</span>'}</span></div>
      <div class="info-row"><span class="label">系统对接接口</span><span class="value">${systemDockState.loaded ? (systemDockState.success ? '<span class="text-success">已上传 - 校验通过</span>' : '<span class="text-danger">已上传 - 校验失败</span>') : '<span class="text-muted">未上传</span>'}</span></div>
      <div class="alert alert-info" style="margin-top:12px"><strong>说明：</strong>两个上传接口独立运作，未来将分别替换为DataWorks数据中台对接接口。当前以Excel上传方式过渡。</div>
    </div></div>
  </div>
  <div class="card"><div class="card-header"><h3>版本更新记录</h3></div><div class="card-body">
    <div class="table-wrapper"><table class="data-table"><thead><tr><th>版本号</th><th>发布日期</th><th>更新内容</th></tr></thead><tbody>
    ${SYSTEM_CONFIG.versionHistory.map(v=>`<tr><td class="font-600"><span class="version-badge">${v.version}</span></td><td>${v.date}</td><td><ul style="padding-left:16px;margin:0">${v.changes.map(c=>`<li>${c}</li>`).join('')}</ul></td></tr>`).join('')}
    </tbody></table></div>
  </div></div>
</div>`;
  }

  // 获取计算结果（财务报表优先使用与验证文件/计量结果输出对齐的 merged 数据）
  const hasResult = CALC_RESULT && CALC_RESULT.success;
  const fs = activeResult?.financialStatementsV2Merged || activeResult?.financialStatementsV2;

  // 场景选择器
  const computedScenarios = getComputedScenarios();
  const scenarioSelectorHtml = computedScenarios.length > 0
    ? `<div style="display:inline-flex;align-items:center;gap:6px">
        <span style="font-size:13px;color:var(--text-sec)">场景:</span>
        <select onchange="setDashScenario(this.value)" style="width:auto;padding:6px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card-bg);color:var(--text);font-size:13px">
          ${computedScenarios.map(s => `<option value="${s}" ${DASH_SELECTED_SCENARIO===s?'selected':''}>${s}</option>`).join('')}
        </select>
      </div>`
    : '';

  // 预测时点选择器（仅保留预测期选项，默认第一个预测期）
  let periodSelectorHtml = '';
  if (fs && fs.dates) {
    const forecastDates = fs.dates.map((d, i) => ({ d, i })).filter(x => x.i > 0 && x.d);
    if (forecastDates.length > 0 && !DASH_FORECAST_PERIOD) {
      DASH_FORECAST_PERIOD = String(forecastDates[0].i);
    }
    periodSelectorHtml = `<div style="display:inline-flex;align-items:center;gap:6px">
      <span style="font-size:13px;color:var(--text-sec)">预测时点:</span>
      <select onchange="setDashPeriod(this.value)" style="width:auto;padding:6px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card-bg);color:var(--text);font-size:13px">
        ${forecastDates.map(x => `<option value="${x.i}" ${DASH_FORECAST_PERIOD===String(x.i)?'selected':''}>${x.d}</option>`).join('')}
      </select>
    </div>`;
  }

  // 图表趋势粒度选择器（年度/月度）
  const chartModeSelectorHtml = `<div style="display:inline-flex;align-items:center;gap:6px">
    <span style="font-size:13px;color:var(--text-sec)">趋势:</span>
    <select onchange="setDashChartMode(this.value)" style="width:auto;padding:6px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card-bg);color:var(--text);font-size:13px">
      <option value="annual" ${DASH_CHART_MODE==='annual'?'selected':''}>年度趋势</option>
      <option value="monthly" ${DASH_CHART_MODE==='monthly'?'selected':''}>月度趋势</option>
    </select>
  </div>`;

  // 提取指标（保留原始数值，供卡片显示变动值用）
  let evalKpis = { insRev: null, uwProfit: null, netProfit: null, combinedRatio: null, expenseRatio: null, lossRatio: null };
  let forecastKpis = { insRev: null, uwProfit: null, netProfit: null, combinedRatio: null, expenseRatio: null, lossRatio: null };

  if (fs && fs.mtd && fs.ytd) {
    const mtd = fs.mtd;
    const ytd = fs.ytd;
    // 结果总览指标面板固定使用 YTD（累计）口径：保证每个预测时点与「输出财务报表」YTD 视图、
    // 「计量结果输出」完全一致（不受 FS_VIEW_MODE 默认 MTD 影响）
    const viewData = fs.ytd || fs[FS_VIEW_MODE];
    const isYtdView = true;
    const paaMtdDetail = activeResult?.paaMtdDetail;
    function getMtdRowVal(item, idx) {
      const r = mtd.income_statement.find(r => r.item === item);
      return r ? (r.values[idx] || 0) : 0;
    }
    function getYtdRowVal(item, idx) {
      const r = ytd.income_statement.find(r => r.item === item);
      return r ? (r.values[idx] || 0) : 0;
    }
    function getViewRowVal(item, idx) {
      const r = viewData.income_statement.find(r => r.item === item);
      return r ? (r.values[idx] || 0) : 0;
    }
    // 评估时点 = period 0
    const evalIdx = 0;
    const evalInsRev = getViewRowVal('保险服务收入', evalIdx);
    const evalUwProfit = getViewRowVal('承保利润', evalIdx);
    const evalNetProfit = getViewRowVal('五、净利润（净亏损以"-"号填列）', evalIdx);
    // 综合费用率分子：PAA计算_MTD 指定科目（-(摊销IACF+维持费用)），口径随 FS_VIEW_MODE（MTD=逐月 / YTD=累计），否则回退财务报表对应视图
    const evalInsSvcExpYtd = paaMtdDetail
      ? getPaaMtdExpenseYtdSeries(paaMtdDetail, fs.dates || [], isYtdView)[evalIdx]
      : getViewRowVal('保险服务费用', evalIdx);
    const evalRatios = computeOperatingRatios([evalInsRev], [evalUwProfit], [evalInsSvcExpYtd], 0);
    evalKpis = {
      insRev: evalInsRev,
      uwProfit: evalUwProfit,
      netProfit: evalNetProfit,
      combinedRatio: evalRatios.combined,
      expenseRatio: evalRatios.expense,
      lossRatio: evalRatios.loss,
    };

    // 预测时点读取对应视图结果
    if (DASH_FORECAST_PERIOD) {
      const fIdx = parseInt(DASH_FORECAST_PERIOD, 10);
      const fInsRev = getViewRowVal('保险服务收入', fIdx);
      const fUwProfit = getViewRowVal('承保利润', fIdx);
      const fNetProfit = getViewRowVal('五、净利润（净亏损以"-"号填列）', fIdx);
      const fInsSvcExpYtd = paaMtdDetail
        ? getPaaMtdExpenseYtdSeries(paaMtdDetail, fs.dates || [], isYtdView)[fIdx]
        : getViewRowVal('保险服务费用', fIdx);
      const fRatios = computeOperatingRatios([fInsRev], [fUwProfit], [fInsSvcExpYtd], 0);
      forecastKpis = {
        insRev: fInsRev,
        uwProfit: fUwProfit,
        netProfit: fNetProfit,
        combinedRatio: fRatios.combined,
        expenseRatio: fRatios.expense,
        lossRatio: fRatios.loss,
      };
    } else {
      forecastKpis = evalKpis;
    }
  }

  // 场景加压描述
  const scenarioName = DASH_SELECTED_SCENARIO || (activeResult?.selectedScenario || '情景0');
  const condDesc = getScenarioConditions(scenarioName);
  const periodLabel = DASH_FORECAST_PERIOD ? (fs?.dates?.[parseInt(DASH_FORECAST_PERIOD)] || '') : ('评估时点 ' + evalDate);

  // 第一个预测期去年同期日期（用于去年同期指标标题）
  const firstForecastDate = fs?.dates?.[1];
  let lastYearDateStr = evalDate;
  if (firstForecastDate) {
    const [y, m, d] = firstForecastDate.split('-').map(Number);
    lastYearDateStr = `${y - 1}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  }

  // KPI 卡片HTML（支持显示与评估时点的变动值）
  function formatChange(changeVal, baseVal) {
    if (changeVal === null || baseVal === null || baseVal === undefined) return '';
    const sign = changeVal >= 0 ? '+' : '-';
    const color = changeVal >= 0 ? 'var(--success)' : 'var(--error)';
    return `<span style="color:${color};font-size:12px;margin-left:4px">${sign}${fmtU(Math.abs(changeVal))}</span>`;
  }
  function formatChangePct(changeVal, baseVal) {
    if (changeVal === null || baseVal === null || baseVal === 0) return '';
    const pct = (changeVal / Math.abs(baseVal)) * 100;
    const sign = pct >= 0 ? '+' : '-';
    const color = pct >= 0 ? 'var(--success)' : 'var(--error)';
    return `<span style="color:${color};font-size:12px;margin-left:4px">(${sign}${Math.abs(pct).toFixed(1)}%)</span>`;
  }
  function kpiCard(color, label, value, unit, sub, changeVal, baseVal, isPercent) {
    let valueHtml = value;
    if (changeVal !== null && changeVal !== undefined && !isPercent) {
      valueHtml = `${value} ${formatChange(changeVal, baseVal)}`;
    } else if (changeVal !== null && changeVal !== undefined && isPercent) {
      // 综合成本率变动用百分点(pp)
      const sign = changeVal >= 0 ? '+' : '-';
      const color = changeVal >= 0 ? 'var(--success)' : 'var(--error)';
      const arrow = changeVal >= 0 ? '↑' : '↓';
      valueHtml = `${value} <span style="color:${color};font-size:12px;margin-left:4px">${sign}${Math.abs(changeVal).toFixed(1)}pp</span>`;
    }
    return `<div class="kpi-card ${color}"><div class="kpi-label">${label}</div><div class="kpi-value">${valueHtml}<span class="kpi-unit">${unit}</span></div><div class="kpi-sub">${sub}</div></div>`;
  }

  const noResultHtml = !hasResult
    ? `<div class="alert alert-warning" style="margin-bottom:16px"><strong>提示：</strong>尚未执行PAA计算，以下指标和图表基于默认数据。请先前往「计算流程」页面执行计算。<button class="btn btn-primary btn-sm" style="margin-left:12px" onclick="renderPage('calc-pipeline')">前往计算</button></div>`
    : '';

  const isAdmin = window.DJANGO_USER && (window.DJANGO_USER.is_admin || window.DJANGO_USER.is_staff);
  const snapshotBadge = (isViewer() && DASHBOARD_SNAPSHOT && DASHBOARD_SNAPSHOT.saved)
    ? `<span class="badge" style="background:var(--green);color:#fff">已发布面板 · ${DASHBOARD_SNAPSHOT.scenario || '-'} · ${DASHBOARD_SNAPSHOT.savedBy || ''} ${DASHBOARD_SNAPSHOT.savedAt ? DASHBOARD_SNAPSHOT.savedAt.slice(0,16).replace('T',' ') : ''}</span>`
    : '';

  return `
<div class="page active">
  <div class="page-header"><h2>结果总览</h2><p>新准则预测模型 ${SYSTEM_CONFIG.version} — 评估时点 ${evalDate}，预测期 ${forecastPeriods} 期</p></div>
  ${noResultHtml}
  <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:16px">
    ${scenarioSelectorHtml}
    ${periodSelectorHtml}
    ${chartModeSelectorHtml}
    ${unitSelectorHTML()}
    ${snapshotBadge}
    ${isAdmin ? `<button class="btn btn-primary btn-sm" onclick="saveDashboardSnapshot()" title="保存当前结果总览面板，viewer 账号将默认展示此面板">💾 保存当前面板</button>` : ''}
  </div>
  <div class="alert alert-info" style="margin-bottom:16px">
    <strong>选定场景：</strong>${scenarioName} | <strong>加压假设：</strong>${condDesc} | <strong>展示时点：</strong>${periodLabel} | <strong>单位：</strong>${unitLabel()}
  </div>

  <div style="margin-bottom:8px;font-size:13px;font-weight:600;color:var(--text-sec)">去年同期指标（${lastYearDateStr}）</div>
  <div class="kpi-grid">
    ${kpiCard('blue', '保险服务收入', evalKpis.insRev !== null ? fmtU(evalKpis.insRev) : '-', unitLabel(), '去年同期', null, null, false)}
    ${kpiCard('green', '承保利润', evalKpis.uwProfit !== null ? fmtU(evalKpis.uwProfit) : '-', unitLabel(), '去年同期', null, null, false)}
    ${kpiCard('red', '净利润', evalKpis.netProfit !== null ? fmtU(evalKpis.netProfit) : '-', unitLabel(), '去年同期', null, null, false)}
    ${kpiCard('orange', '综合成本率', evalKpis.combinedRatio !== null ? evalKpis.combinedRatio.toFixed(1) + '%' : '-', '', '去年同期', null, null, true)}
  </div>

  <div style="margin-bottom:8px;font-size:13px;font-weight:600;color:var(--text-sec)">预测时点指标（${periodLabel}）— 与去年同期对比</div>
  <div class="kpi-grid">
    ${kpiCard('blue', '保险服务收入', forecastKpis.insRev !== null ? fmtU(forecastKpis.insRev) : '-', unitLabel(), periodLabel, forecastKpis.insRev !== null && evalKpis.insRev !== null ? forecastKpis.insRev - evalKpis.insRev : null, evalKpis.insRev, false)}
    ${kpiCard('green', '承保利润', forecastKpis.uwProfit !== null ? fmtU(forecastKpis.uwProfit) : '-', unitLabel(), periodLabel, forecastKpis.uwProfit !== null && evalKpis.uwProfit !== null ? forecastKpis.uwProfit - evalKpis.uwProfit : null, evalKpis.uwProfit, false)}
    ${kpiCard('red', '净利润', forecastKpis.netProfit !== null ? fmtU(forecastKpis.netProfit) : '-', unitLabel(), periodLabel, forecastKpis.netProfit !== null && evalKpis.netProfit !== null ? forecastKpis.netProfit - evalKpis.netProfit : null, evalKpis.netProfit, false)}
    ${kpiCard('orange', '综合成本率', forecastKpis.combinedRatio !== null ? forecastKpis.combinedRatio.toFixed(1) + '%' : '-', '', periodLabel, forecastKpis.combinedRatio !== null && evalKpis.combinedRatio !== null ? forecastKpis.combinedRatio - evalKpis.combinedRatio : null, evalKpis.combinedRatio, true)}
  </div>

  <div class="chart-grid">
    <div class="chart-container"><h3>承保利润趋势（YTD）</h3><div class="chart-wrapper"><canvas id="dashChart1"></canvas></div></div>
    <div class="chart-container"><h3>经营三率</h3><div class="chart-wrapper"><canvas id="dashChart2"></canvas></div></div>
  </div>
  <div class="chart-grid">
    <div class="chart-container"><h3>投资收益 / 承保利润</h3><div class="chart-wrapper"><canvas id="dashChart3"></canvas></div></div>
    <div class="chart-container"><h3>保险合同负债 / 再保险合同资产</h3><div class="chart-wrapper"><canvas id="dashChart4"></canvas></div></div>
  </div>
  <div class="chart-grid">
    <div class="chart-container"><h3>投资成分比例（YTD）</h3><div class="chart-wrapper"><canvas id="dashChart5"></canvas></div></div>
    <div class="chart-container"><h3>保险业务收入 / 保险服务收入（YTD）</h3><div class="chart-wrapper"><canvas id="dashChart6"></canvas></div></div>
  </div>

  <div class="two-col">
    <div class="card"><div class="card-header"><h3>系统信息</h3></div><div class="card-body">
      <div class="info-row"><span class="label">系统版本</span><span class="value"><span class="version-badge">${SYSTEM_CONFIG.version}</span></span></div>
      <div class="info-row"><span class="label">构建日期</span><span class="value">${SYSTEM_CONFIG.buildDate}</span></div>
      <div class="info-row"><span class="label">评估时点</span><span class="value">${evalDate}</span></div>
      <div class="info-row"><span class="label">预测期数</span><span class="value">${forecastPeriods} 期</span></div>
      <div class="info-row"><span class="label">计量方法</span><span class="value">PAA (保费分配法)</span></div>
      <div class="info-row"><span class="label">Excel上传接口</span><span class="value">${SIDEBAR_CONFIG.dataInput.excelSheets.length} 个工作表</span></div>
      <div class="info-row"><span class="label">系统对接接口</span><span class="value">${SIDEBAR_CONFIG.dataInput.dockSheets.length} 个工作表</span></div>
    </div></div>
    <div class="card"><div class="card-header"><h3>数据上传状态</h3></div><div class="card-body">
      <div class="info-row"><span class="label">Excel上传接口</span><span class="value">${excelUploadState.loaded ? (excelUploadState.success ? '<span class="text-success">已上传 - 校验通过</span>' : '<span class="text-danger">已上传 - 校验失败</span>') : '<span class="text-muted">未上传</span>'}</span></div>
      <div class="info-row"><span class="label">系统对接接口</span><span class="value">${systemDockState.loaded ? (systemDockState.success ? '<span class="text-success">已上传 - 校验通过</span>' : '<span class="text-danger">已上传 - 校验失败</span>') : '<span class="text-muted">未上传</span>'}</span></div>
      <div class="alert alert-info" style="margin-top:12px"><strong>说明：</strong>两个上传接口独立运作，未来将分别替换为DataWorks数据中台对接接口。当前以Excel上传方式过渡。</div>
    </div></div>
  </div>
</div>`;
};

function setDashScenario(val) { DASH_SELECTED_SCENARIO = val; renderPage('dashboard'); }
function setDashPeriod(val) { DASH_FORECAST_PERIOD = val; renderPage('dashboard'); }
function setDashChartMode(val) { DASH_CHART_MODE = val; renderPage('dashboard'); }

pages['calc-pipeline'] = () => {
  const dataReady = hasUploadedData();
  const hasResult = CALC_RESULT && CALC_RESULT.success;
  const stepStatus = hasResult ? 'done' : (dataReady ? 'pending' : 'pending');
  const statusText = hasResult ? '已完成' : (dataReady ? '待计算' : '未完成');
  const statusTag = hasResult ? 'done' : 'pending';

  // 多场景选择 (Task #111)
  const scenarioList = CALC_SCENARIOS.length > 0 ? CALC_SCENARIOS : [{value:'情景0',label:'情景0',description:'基础情景',conditions:{}}];
  // 场景列表就绪后默认全选（压力测试通常需一次性计算全部情景）；用户手动调整后才不再自动全选
  if (!window.MULTI_SELECTED_SCENARIOS) {
    window.MULTI_SELECTED_SCENARIOS = new Set();
  }
  if (!window.SCENARIOS_MANUALLY_TOUCHED) {
    window.MULTI_SELECTED_SCENARIOS = new Set(scenarioList.map(s => s.value));
  } else {
    // 清理已不存在的场景，保留用户选择中仍有效的
    const valid = new Set(scenarioList.map(s => s.value));
    [...window.MULTI_SELECTED_SCENARIOS].forEach(v => { if (!valid.has(v)) window.MULTI_SELECTED_SCENARIOS.delete(v); });
  }

  const scenarioCardsHtml = scenarioList.map(s => {
    const checked = window.MULTI_SELECTED_SCENARIOS.has(s.value);
    const conds = s.conditions || {};
    const condKeys = Object.keys(conds);
    const condHtml = condKeys.length > 0
      ? `<div style="font-size:11px;color:var(--text-sec);margin-top:4px;display:flex;flex-wrap:wrap;gap:4px">${condKeys.map(k => { const cnKey = SCENARIO_PARAM_CN[k] || k; return `<span class="status-tag" style="font-size:11px;padding:1px 5px;background:var(--bg)">${cnKey}: ${(conds[k]*100).toFixed(1).replace(/\.0$/,'')}%</span>`; }).join('')}</div>`
      : `<div style="font-size:12px;color:var(--text-sec);margin-top:2px">${s.description||'基础情景'}</div>`;
    return `<label style="display:flex;align-items:flex-start;gap:8px;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius);cursor:pointer;${checked?'border-color:var(--primary);background:var(--primary-bg)':''}" onchange="toggleScenario('${s.value}')">
      <input type="checkbox" value="${s.value}" ${checked?'checked':''} style="margin-top:2px;flex-shrink:0">
      <div style="flex:1;min-width:0">
        <div style="font-weight:600;font-size:13px">${s.label}</div>
        ${condHtml}
      </div>
    </label>`;
  }).join('');

  const computedScenarios = Object.keys(CALC_RESULTS_MAP);
  const computedListHtml = computedScenarios.length > 0
    ? `<div style="margin-top:12px;padding:10px 12px;background:var(--bg);border-radius:var(--radius);font-size:13px">
        <strong>已计算场景：</strong>${computedScenarios.map(s => `<span class="status-tag done" style="margin:0 4px">${s}</span>`).join('')}
      </div>`
    : '';

  // 预测期数选项
  const fpOptions = [
    {value:1,label:'1个月'},{value:3,label:'3个月'},{value:6,label:'6个月'},
    {value:12,label:'12个月（1年）'},{value:16,label:'16个月'},
    {value:24,label:'24个月（2年）'},{value:36,label:'36个月（3年）'},{value:60,label:'60个月（5年）'},
  ];
  const currentFP = (hasResult && CALC_RESULT.inputOrganized) ? CALC_RESULT.inputOrganized.forecastPeriods : (excelUploadState.forecastPeriods || 12);

  return `
<div class="page active">
  <div class="page-header"><h2>计算流程</h2><p>IFRS17 PAA计量全流程 — 支持多场景并行计算</p></div>
  ${!dataReady ? getEmptyDataMessage() : `
  <div class="card"><div class="card-header"><h3>计算配置</h3></div><div class="card-body">
    <div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap;margin-bottom:12px">
      <div style="flex:1;min-width:300px">
        <label style="display:block;margin-bottom:6px;font-weight:600;color:var(--text)">选定场景（可多选）</label>
        <div style="max-height:240px;overflow-y:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px">
          ${scenarioCardsHtml}
        </div>
      </div>
      <div style="min-width:200px">
        <label style="display:block;margin-bottom:6px;font-weight:600;color:var(--text)">预测期数（月）</label>
        <input type="hidden" id="forecast-periods-select" value="${currentFP}">
        <div class="fp-cdd-wrap" style="width:100%">
          ${renderCustomSelect('forecast-periods-cdd', fpOptions, currentFP, 'forecastPeriods')}
        </div>
      </div>
      <div>
        <label style="display:block;margin-bottom:6px;font-weight:600;color:var(--text)">计算状态</label>
        <div style="padding:8px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg)">
          ${hasResult ? '<span class="status-tag done">已完成</span>' : '<span class="status-tag pending">未计算</span>'}
          ${hasResult && CALC_RESULT.inputOrganized ? `<span style="margin-left:8px;color:var(--text-sec);font-size:13px">评估时点: ${CALC_RESULT.inputOrganized.evalDate||'-'}</span>` : ''}
        </div>
      </div>
      <div>
        <button id="calc-run-btn" class="btn btn-primary" onclick="runMultiScenarioCalculation()">
          ${hasResult ? '\u25B6 重新计算' : '\u25B6 开始计算'}
        </button>
      </div>
      <div style="min-width:260px">
        <label style="display:block;margin-bottom:6px;font-weight:600;color:var(--text)">计算结果入库</label>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <input type="text" id="version-name" placeholder="版本名称（可选）" style="flex:1;min-width:140px;padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card-bg);color:var(--text)">
          <button class="btn btn-success" onclick="pushCalcVersion()">📥 推入数据库</button>
        </div>
        <div id="version-push-status" style="font-size:12px;color:var(--text-sec);margin-top:6px"></div>
      </div>
    </div>
    <div style="font-size:12px;color:var(--text-sec)">
      \u{1F4CA} 已选 <strong id="scenario-count">${window.MULTI_SELECTED_SCENARIOS.size}</strong> 个场景 | 预测期数决定合同组拼接的新合同组生成数量和预测结果的时间跨度
    </div>
    ${computedListHtml}
  </div></div>

  <div class="card"><div class="card-header"><h3>已入库计算版本</h3><button class="btn btn-outline btn-sm" onclick="loadCalcVersions()">刷新</button></div><div class="card-body">
    <div id="calc-versions-list" style="font-size:13px;color:var(--text-sec)">加载中…</div>
  </div></div>

  <div id="calc-progress-card" class="card" style="display:none">
    <div class="card-header"><h3>计算进度</h3><span id="calc-progress-scenario" class="status-tag running" style="margin-left:8px"></span></div>
    <div class="card-body">
      <div class="progress-track"><div id="calc-progress-fill" class="progress-fill"></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
        <span id="calc-progress-stage" class="progress-stage">准备中…</span>
        <span id="calc-progress-percent" class="progress-percent">0%</span>
      </div>
      <div id="calc-progress-detail" class="progress-detail"></div>
    </div>
  </div>

  <div class="card"><div class="card-header"><h3>计算步骤</h3><div class="btn-group"><button class="btn btn-outline btn-sm" onclick="document.getElementById('calc-log-panel').style.display=document.getElementById('calc-log-panel').style.display==='none'?'block':'none'">查看日志</button></div></div><div class="card-body">
    <div class="pipeline">${MODEL_DATA.calcSteps.map((s,i)=>`<div class="pipeline-step"><div class="pipeline-circle ${s.status}">${s.status==='done'?'\u2713':s.id}</div><div class="pipeline-label">${s.name}</div><div class="pipeline-sub">${s.desc}</div><div class="status-tag ${s.status==='done'?'done':'pending'}">${s.status==='done'?'已完成':'待执行'}</div></div>${i<MODEL_DATA.calcSteps.length-1?'<div class="pipeline-arrow">\u2192</div>':''}`).join('')}</div>
  </div></div>

  <div id="calc-log-panel" class="card" style="display:none"><div class="card-header"><h3>计算日志</h3></div><div class="card-body">
    <div id="calc-log" class="log-container" style="max-height:400px;overflow-y:auto;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:12px;font-family:monospace;font-size:13px">
      ${hasResult && CALC_RESULT.calcLogs ? CALC_RESULT.calcLogs.map(line=>{const cls=line.includes('错误')?'error':(line.includes('完成')?'success':'info');return `<div class="log-line ${cls}">${line}</div>`;}).join('') : '<div class="log-line info">尚未执行计算</div>'}
    </div>
  </div></div>

  <div id="calc-summary" style="display:${hasResult?'block':'none'}">
    ${hasResult ? renderCalcSummary(CALC_RESULT) : ''}
  </div>

  <div id="calc-input-organized" style="display:${hasResult?'block':'none'}">
    ${hasResult && CALC_RESULT.inputOrganized ? renderInputOrganized(CALC_RESULT.inputOrganized) : ''}
  </div>

  <div class="card"><div class="card-header"><h3>计算模块说明</h3></div><div class="card-body">
    <div class="table-wrapper"><table class="data-table"><thead><tr><th>序号</th><th>模块</th><th>对应工作表</th><th>说明</th><th>状态</th></tr></thead><tbody>
      <tr class="section-row"><td colspan="5">输入整理</td></tr>
      <tr><td>1</td><td>选定场景</td><td>选定场景</td><td>从压力情景配置中选取情景参数</td><td><span class="status-tag ${statusTag}">${statusText}</span></td></tr>
      <tr><td>2</td><td>合同组拼接</td><td>合同组拼接</td><td>合并现有业务+新业务合同组</td><td><span class="status-tag ${statusTag}">${statusText}</span></td></tr>
      <tr><td>3</td><td>关键假设整理</td><td>输入整理-关键假设</td><td>整理合同组关键假设参数</td><td><span class="status-tag ${statusTag}">${statusText}</span></td></tr>
      <tr><td>4</td><td>利率曲线加工</td><td>输入整理-初始确认/即期利率曲线加工</td><td>加工利率曲线用于折现</td><td><span class="status-tag ${statusTag}">${statusText}</span></td></tr>
      <tr><td>5</td><td>现金流模式整理</td><td>输入整理-保费/IACF/赚取/赔付模式</td><td>整理各类现金流分配模式</td><td><span class="status-tag ${statusTag}">${statusText}</span></td></tr>
      <tr class="section-row"><td colspan="5">新业务计量</td></tr>
      <tr><td>6</td><td>新业务预期现金流</td><td>新业务预期现金流_1/2</td><td>计算新业务各期预期现金流</td><td><span class="status-tag ${statusTag}">${statusText}</span></td></tr>
      <tr><td>7</td><td>PAA计算_新业务</td><td>PAA计算_新业务预测</td><td>PAA法计量新业务负债与损益</td><td><span class="status-tag ${statusTag}">${statusText}</span></td></tr>
      <tr class="section-row"><td colspan="5">现有业务计量</td></tr>
      <tr><td>8</td><td>现有业务预期现金流</td><td>现有业务预期现金流_1/2</td><td>计算现有业务各期预期现金流</td><td><span class="status-tag ${statusTag}">${statusText}</span></td></tr>
      <tr><td>9</td><td>PAA计算_现有业务</td><td>PAA计算_现有业务预测</td><td>PAA法计量现有业务负债与损益</td><td><span class="status-tag ${statusTag}">${statusText}</span></td></tr>
      <tr class="section-row"><td colspan="5">投资与输出</td></tr>
      <tr><td>10</td><td>PAA结果汇总</td><td>PAA计算_汇总</td><td>汇总新旧业务PAA结果</td><td><span class="status-tag ${statusTag}">${statusText}</span></td></tr>
      <tr><td>11</td><td>输出财务报表</td><td>输出财务报表</td><td>生成CAS25综合收益表与资产负债表</td><td><span class="status-tag ${statusTag}">${statusText}</span></td></tr>
    </tbody></table></div>
  </div></div>
  `}
</div>`;
};

pages['input-processing'] = () => {
  if (!hasUploadedData()) {
    return `
<div class="page active">
  <div class="page-header"><h2>输入整理</h2><p>将原始输入数据加工为计算引擎所需的标准格式</p></div>
  ${getEmptyDataMessage()}
</div>`;
  }
  const fp = excelUploadState.forecastPeriods || 12;
  const newBizGroups = 36;
  const totalNewRows = newBizGroups * fp;

  // 情景下拉菜单（用于展示相应场景影响的输入整理表与基础情景的比对变动）
  const scenarioOpts = (CALC_SCENARIOS && CALC_SCENARIOS.length)
    ? CALC_SCENARIOS.map(s => `<option value="${s.value}" ${INPUT_ORG_SCENARIO === s.value ? 'selected' : ''}>${s.label || s.value}</option>`).join('')
    : `<option value="基础情景" ${INPUT_ORG_SCENARIO === '基础情景' ? 'selected' : ''}>基础情景</option>`;

  return `
<div class="page active">
  <div class="page-header"><h2>输入整理</h2><p>将原始输入数据加工为计算引擎所需的标准格式</p></div>
  <div class="alert alert-info"><strong>预测期数：${fp}个月</strong> — 合同组拼接将生成 ${newBizGroups} 个新业务合同组 × ${fp} 期 = <strong>${totalNewRows} 行新业务预测</strong></div>

  <div class="card" style="margin-bottom:16px"><div class="card-header"><h3>情景选择 · 输入整理比对</h3></div><div class="card-body">
    <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
      <span style="font-size:13px;color:var(--text-sec)">选择情景:</span>
      <select id="inputOrgScenario" onchange="onInputOrgScenarioChange(this.value)" style="width:auto;padding:6px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card-bg);color:var(--text);font-size:13px">
        ${scenarioOpts}
      </select>
      <button class="btn btn-sm btn-default" onclick="loadInputOrg()">刷新比对</button>
      <span id="inputOrgLoading" style="font-size:12px;color:var(--text-sec)"></span>
    </div>
    <div id="input-org-result" style="margin-top:12px"></div>
  </div></div>

  <div class="card"><div class="card-header"><h3>输入整理模块概览</h3></div><div class="card-body">
    <div class="kpi-grid">
      <div class="kpi-card blue"><div class="kpi-label">整理模块数量</div><div class="kpi-value">19<span class="kpi-unit">个</span></div></div>
      <div class="kpi-card green"><div class="kpi-label">预测期数</div><div class="kpi-value">${fp}<span class="kpi-unit">月</span></div></div>
      <div class="kpi-card orange"><div class="kpi-label">新业务预测行数</div><div class="kpi-value">${totalNewRows.toLocaleString()}<span class="kpi-unit">行</span></div><div class="kpi-sub">${newBizGroups}组 × ${fp}期</div></div>
      <div class="kpi-card purple"><div class="kpi-label">合同组拼接总数</div><div class="kpi-value">${newBizGroups * 2}<span class="kpi-unit">行</span></div><div class="kpi-sub">新业务${newBizGroups}+现有业务${newBizGroups}</div></div>
    </div>
  </div></div>
  <div class="card"><div class="card-header"><h3>输入整理明细</h3></div><div class="card-body">
    <div class="table-wrapper"><table class="data-table"><thead><tr><th>序号</th><th>模块名称</th><th>对应工作表</th><th>功能说明</th><th>状态</th></tr></thead><tbody>
      ${['选定场景|选定场景|从7个情景中选定情景并展开各年参数','合同组拼接|合同组拼接|拼接现有业务'+newBizGroups+'组+新业务'+newBizGroups+'组×'+fp+'期='+totalNewRows+'行','关键假设整理|输入整理-关键假设|整理合同组ID、精算险类、业务类型等','投资成分比例|输入整理-投资成分比例|整理投资成分分解比例','预期赔付率|输入整理-预期赔付率|整理各合同组预期赔付率假设','维持费用率|输入整理-维持费用率|整理各合同组维持费用率','再保人不履约风险|输入整理-再保人不履约风险|整理再保人违约风险调整','未到期间接理赔费用率|输入整理-未到期间接理赔费用率|整理间接理赔费用率假设','预期摊回比例|输入整理-预期摊回比例|整理摊回比例假设','未决间接理赔费用率|输入整理-未决间接理赔费用率|整理未决赔款间接理赔费用率','初始确认利率曲线加工|输入整理-初始确认利率曲线加工|加工各合同组初始确认利率曲线','即期利率曲线加工|输入整理-即期利率曲线加工|加工即期利率曲线用于折现','保费现金流模式|输入整理-保费现金流模式|展开各合同组保费现金流模式','IACF现金流模式|输入整理-IACF现金流模式|展开IACF现金流模式','未到期赚取模式|输入整理-未到期赚取模式|展开未到期责任赚取模式','未到期赔付模式|输入整理-未到期赔付模式|展开未到期赔付模式','未决赔付模式|输入整理-未决赔付模式|展开未决赔款赔付模式','实际赔付比例|输入整理-实际赔付比例|整理实际赔付比例数据','实际赔付比例_累计|输入整理-实际赔付比例_累计|计算累计实际赔付比例'].map((r,i)=>{const p=r.split('|');return `<tr><td>${i+1}</td><td>${p[0]}</td><td>${p[1]}</td><td>${p[2]}</td><td><span class="status-tag done">已完成</span></td></tr>`}).join('')}
    </tbody></table></div>
  </div></div>
</div>`;
};

// 输入整理-情景对比：切换场景
function onInputOrgScenarioChange(val) {
  INPUT_ORG_SCENARIO = val;
  loadInputOrg();
}

// 输入整理-情景对比：拉取选定场景与基础情景的输入整理并渲染比对
async function loadInputOrg() {
  const box = document.getElementById('input-org-result');
  const loading = document.getElementById('inputOrgLoading');
  if (loading) loading.textContent = '加载中...';
  try {
    const resp = await fetch('/api/calc/input-org?scenario=' + encodeURIComponent(INPUT_ORG_SCENARIO));
    const data = await resp.json();
    if (loading) loading.textContent = '';
    if (!data.success) {
      if (box) box.innerHTML = `<div class="alert alert-warning">${data.error || '加载失败'}</div>`;
      return;
    }
    INPUT_ORG_DATA = data;
    if (box) box.innerHTML = renderInputOrgResult(data);
  } catch (e) {
    if (loading) loading.textContent = '';
    if (box) box.innerHTML = `<div class="alert alert-warning">加载失败: ${e}</div>`;
  }
}

// 数值变动单元格（基础→场景，带 Δ%）
function fmtOrgDiff(base, sc) {
  const b = Number(base || 0), s = Number(sc || 0);
  const delta = s - b;
  const pct = b !== 0 ? (delta / Math.abs(b) * 100) : (s !== 0 ? 100 : 0);
  const color = delta > 0 ? 'var(--success)' : (delta < 0 ? 'var(--error)' : 'var(--text-sec)');
  const arrow = delta > 0 ? '▲' : (delta < 0 ? '▼' : '–');
  return `<span>${fmtU(s)}</span> <span style="color:${color};font-size:11px;margin-left:4px">${arrow}${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%</span>`;
}

function renderInputOrgResult(data) {
  const stress = data.stress || {};
  const base = data.base || {};
  const sc = data.scenario_org || {};
  const isBase = data.scenario === data.baseScenario;

  // 1) 压力参数摘要
  const years = Object.keys(stress).map(Number).sort((a, b) => a - b);
  let stressHtml = '';
  if (years.length) {
    stressHtml = `<div class="card" style="margin-bottom:16px"><div class="card-header"><h3>情景压力参数（${data.scenario}）</h3></div><div class="card-body"><div class="table-wrapper"><table class="data-table"><thead><tr><th>预测年</th><th>原保险保费增长</th><th>预期赔付率上升</th><th>预期费用率上升</th><th>即期利率变动</th></tr></thead><tbody>
      ${years.map(y => { const p = stress[y] || {}; return `<tr><td>第${y}年</td><td>${(p['premium_growth']||0)*100}%</td><td>${(p['loss_ratio_adj']||0)*100}%</td><td>${(p['expense_ratio_adj']||0)*100}%</td><td>${(p['rate_adjustment']||0)*100}%</td></tr>`; }).join('')}
    </tbody></table></div></div></div>`;
  } else {
    stressHtml = `<div class="alert alert-info" style="margin-bottom:16px">当前情景（${data.scenario}）无压力参数，输入整理与基础情景一致。</div>`;
  }

  // 2) 新业务假设 比对
  const nbBase = base['新业务假设'] || [];
  const nbSc = sc['新业务假设'] || [];
  const nbMap = {};
  nbSc.forEach(r => { nbMap[String(r['预测组ID'])] = r; });
  let nbHtml = `<div class="card" style="margin-bottom:16px"><div class="card-header"><h3>输入整理 - 新业务假设（${nbSc.length} 组）· 与基础情景比对</h3></div><div class="card-body"><div class="table-wrapper"><table class="data-table"><thead><tr><th>预测组ID</th><th>预测组</th><th>精算险类</th><th>业务类型</th><th>保费收入(基础)</th><th>保费收入(场景)</th><th>变动</th><th>获取费用(场景)</th><th>当期提前初始确认签单保费(场景)</th></tr></thead><tbody>`;
  nbBase.forEach(r => {
    const s = nbMap[String(r['预测组ID'])] || {};
    nbHtml += `<tr><td>${r['预测组ID']||''}</td><td>${r['预测组']||''}</td><td>${r['精算险类']||''}</td><td>${r['业务类型']||''}</td><td>${fmtU(r['保费收入']||0)}</td><td>${fmtOrgDiff(r['保费收入'], s['保费收入'])}</td><td>${fmtOrgDiff(r['获取费用'], s['获取费用'])}</td><td>${fmtOrgDiff(r['当期提前初始确认签单保费'], s['当期提前初始确认签单保费'])}</td></tr>`;
  });
  nbHtml += `</tbody></table></div></div></div>`;

  // 3) 现有业务假设 比对
  const exBase = base['现有业务假设'] || [];
  const exSc = sc['现有业务假设'] || [];
  const exMap = {};
  exSc.forEach(r => { exMap[String(r['合同组ID'])] = r; });
  let exHtml = `<div class="card" style="margin-bottom:16px"><div class="card-header"><h3>输入整理 - 现有业务假设（${exSc.length} 组）· 与基础情景比对</h3></div><div class="card-body"><div class="table-wrapper"><table class="data-table"><thead><tr><th>合同组ID</th><th>现有业务预测组</th><th>精算险类</th><th>保费收入(基础)</th><th>保费收入(场景)</th><th>变动</th><th>应付IACF(场景)</th><th>未到期风险调整%(场景)</th></tr></thead><tbody>`;
  exBase.forEach(r => {
    const s = exMap[String(r['合同组ID'])] || {};
    exHtml += `<tr><td>${r['合同组ID']||''}</td><td>${r['现有业务预测组']||''}</td><td>${r['精算险类']||''}</td><td>${fmtU(r['保费收入']||0)}</td><td>${fmtOrgDiff(r['保费收入'], s['保费收入'])}</td><td>${fmtOrgDiff(r['应付IACF'], s['应付IACF'])}</td><td>${fmtU(s['未到期风险调整%']||0)}</td></tr>`;
  });
  exHtml += `</tbody></table></div></div></div>`;

  // 4) 利率曲线比对（首 12 个月 月度远期利率）
  const baseRate = (base['利率曲线']||{})['月度远期利率'] || {};
  const scRate = (sc['利率曲线']||{})['月度远期利率'] || {};
  let rateHtml = `<div class="card" style="margin-bottom:16px"><div class="card-header"><h3>利率曲线（即期利率变动）· 月度远期利率 与基础情景比对</h3></div><div class="card-body"><div class="table-wrapper"><table class="data-table"><thead><tr><th>月份</th><th>基础情景</th><th>${data.scenario}</th><th>变动(bps)</th></tr></thead><tbody>`;
  for (let m = 1; m <= 12; m++) {
    const bv = baseRate[m] != null ? Number(baseRate[m]) : null;
    const sv = scRate[m] != null ? Number(scRate[m]) : null;
    const bps = (bv != null && sv != null) ? ((sv - bv) * 10000).toFixed(1) : '-';
    const color = (bv != null && sv != null && Math.abs(sv - bv) > 1e-9) ? 'var(--error)' : '';
    rateHtml += `<tr><td>${m}</td><td>${bv!=null?bv.toFixed(6):'-'}</td><td>${sv!=null?sv.toFixed(6):'-'}</td><td style="color:${color}">${bps}</td></tr>`;
  }
  rateHtml += `</tbody></table></div><div style="font-size:12px;color:var(--text-sec);margin-top:6px">注：预期赔付率上升/预期费用率上升在现金流计量阶段体现，不直接改变输入整理表的"假设"数值，其影响将在计量结果中反映。</div></div></div>`;

  return stressHtml + nbHtml + exHtml + rateHtml;
}

let INPUT_ORG_DATA = null;

pages['new-business-calc'] = () => {
  if (!hasUploadedData()) {
    return `
<div class="page active">
  <div class="page-header"><h2>新业务计量</h2><p>PAA法对新业务进行计量 — 预期现金流计算 → PAA负债与损益计量</p></div>
  ${getEmptyDataMessage()}
</div>`;
  }
  // 使用计算结果
  if (CALC_RESULT && CALC_RESULT.success && CALC_RESULT.newBusinessPredict) {
    const rows = CALC_RESULT.newBusinessPredict;
    return `
<div class="page active">
  <div class="page-header"><h2>新业务计量</h2><p>PAA法对新业务进行计量 — 预期现金流计算 → PAA负债与损益计量</p></div>
  <div class="alert alert-info"><strong>选定场景：</strong>${CALC_RESULT.selectedScenario||'-'} | <strong>计算行数：</strong>${rows.length} 行</div>
  <div class="card"><div class="card-header"><h3>PAA计算_新业务预测 — 明细</h3><span class="badge">${rows.length} 行</span></div><div class="card-body">
    ${renderPredictDetail(rows)}
  </div></div>
</div>`;
  }
  return `
<div class="page active">
  <div class="page-header"><h2>新业务计量</h2><p>PAA法对新业务进行计量 — 预期现金流计算 → PAA负债与损益计量</p></div>
  <div class="alert alert-warning"><strong>提示：</strong>尚未执行PAA计算，请先前往「计算流程」页面选择场景并执行计算。</div>
  <div style="text-align:center;padding:48px">
    <button class="btn btn-primary" onclick="renderPage('calc-pipeline')">前往计算流程</button>
  </div>
</div>`;
};

pages['existing-business-calc'] = () => {
  if (!hasUploadedData()) {
    return `
<div class="page active">
  <div class="page-header"><h2>现有业务计量</h2><p>PAA法对现有业务进行计量 — 预期现金流计算 → PAA负债与损益计量</p></div>
  ${getEmptyDataMessage()}
</div>`;
  }
  // 使用计算结果
  if (CALC_RESULT && CALC_RESULT.success && CALC_RESULT.existingBusinessPredict) {
    const rows = CALC_RESULT.existingBusinessPredict;
    return `
<div class="page active">
  <div class="page-header"><h2>现有业务计量</h2><p>PAA法对现有业务进行计量 — 预期现金流计算 → PAA负债与损益计量</p></div>
  <div class="alert alert-info"><strong>选定场景：</strong>${CALC_RESULT.selectedScenario||'-'} | <strong>计算行数：</strong>${rows.length} 行</div>
  <div class="card"><div class="card-header"><h3>PAA计算_现有业务预测 — 明细</h3><span class="badge">${rows.length} 行</span></div><div class="card-body">
    ${renderPredictDetail(rows)}
  </div></div>
</div>`;
  }
  return `
<div class="page active">
  <div class="page-header"><h2>现有业务计量</h2><p>PAA法对现有业务进行计量 — 预期现金流计算 → PAA负债与损益计量</p></div>
  <div class="alert alert-warning"><strong>提示：</strong>尚未执行PAA计算，请先前往「计算流程」页面选择场景并执行计算。</div>
  <div style="text-align:center;padding:48px">
    <button class="btn btn-primary" onclick="renderPage('calc-pipeline')">前往计算流程</button>
  </div>
</div>`;
};

pages['investment-calc'] = () => `
<div class="page active">
  <div class="page-header"><h2>投资收益预测</h2><p>基于资产配置比例与投资收益率假设，预测各年投资收益</p></div>
  <div class="kpi-grid">
    <div class="kpi-card blue"><div class="kpi-label">总投资资产</div><div class="kpi-value">${fmt(MODEL_DATA.inv.totalAssets)}<span class="kpi-unit">万元</span></div></div>
    <div class="kpi-card green"><div class="kpi-label">投资收益（第一年）</div><div class="kpi-value">1,933<span class="kpi-unit">万元</span></div><div class="kpi-sub">第二年: 2,026 | 第三年: 1,553</div></div>
    <div class="kpi-card orange"><div class="kpi-label">固收类久期</div><div class="kpi-value">7.41<span class="kpi-unit">年</span></div></div>
    <div class="kpi-card purple"><div class="kpi-label">综合投资收益率（第一年）</div><div class="kpi-value">0.64<span class="kpi-unit">%</span></div></div>
  </div>
  <div class="chart-grid">
    <div class="chart-container"><h3>各类资产投资收益贡献</h3><div class="chart-wrapper"><canvas id="c1"></canvas></div></div>
    <div class="chart-container"><h3>投资收益3年预测趋势</h3><div class="chart-wrapper"><canvas id="c2"></canvas></div></div>
  </div>
  <div class="card"><div class="card-header"><h3>投资收益预测明细</h3></div><div class="card-body">
    <div class="table-wrapper"><table class="data-table"><thead><tr><th>资产类别</th><th>配置比例(Y1)</th><th>收益率(Y1)</th><th>配置比例(Y2)</th><th>收益率(Y2)</th><th>配置比例(Y3)</th><th>收益率(Y3)</th></tr></thead><tbody>
    ${MODEL_DATA.inv.alloc.map((a,i)=>{const y=MODEL_DATA.inv.yield[i]||{};return `<tr><td>${a.cat}</td><td class="num">${fmtP(a.y1,0)}</td><td class="num">${y.y1?fmtP(y.y1,2):'-'}</td><td class="num">${fmtP(a.y2,0)}</td><td class="num">${y.y2?fmtP(y.y2,2):'-'}</td><td class="num">${fmtP(a.y3,0)}</td><td class="num">${y.y3?fmtP(y.y3,2):'-'}</td></tr>`}).join('')}
    </tbody></table></div>
  </div></div>
</div>`;

// 计量结果输出：当前激活的 tab
let OUTPUT_ACTIVE_TAB = 'out-nb';
let OUTPUT_SELECTED_SCENARIO = ''; // 计量结果输出页选定的场景
let VERIFY_OUTPUT_TABLES = null;   // 六张计量输出表（附件输出表格式：字段名/列序与附件一致）
let VERIFY_OUTPUT_TABLES_SCENARIO = ''; // 当前 VERIFY_OUTPUT_TABLES 对应的情景

function _renderDictRows(rows, maxRows=200, formatter=fmt) {
  if (!rows || rows.length === 0) return '<p style="color:var(--text-sec);padding:16px">无数据</p>';
  const headers = Object.keys(rows[0]);
  const displayRows = rows.slice(0, maxRows);
  return `<div class="table-wrapper" style="max-height:600px;overflow:auto"><table class="data-table" style="font-size:12px"><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>
    ${displayRows.map(r=>`<tr>${headers.map(h=>{const v=r[h];if(v==null||v==='')return '<td>-</td>';if(typeof v==='number')return `<td class="num${v<0?' negative':''}">${formatter(v,4)}</td>`;return `<td>${v}</td>`;}).join('')}</tr>`).join('')}
  </tbody></table></div>${rows.length>maxRows?`<p style="color:var(--text-sec);text-align:center;padding:8px">显示前${maxRows}行，共${rows.length}行</p>`:''}`;
}

function _renderFsV2Table(fsObj, dates) {
  if (!fsObj) return '<p style="color:var(--text-sec);padding:16px">无数据</p>';
  const income = fsObj.income_statement || [];
  const balance = fsObj.balance_sheet || [];
  const rows = [];
  income.forEach(it => {
    const vals = it.values || [];
    const row = { section: '损益表', item: it.item };
    dates.forEach((d, i) => { row[d] = vals[i] !== undefined ? vals[i] : null; });
    rows.push(row);
  });
  balance.forEach(it => {
    const vals = it.values || [];
    const row = { section: '资产负债表', item: it.item };
    dates.forEach((d, i) => { row[d] = vals[i] !== undefined ? vals[i] : null; });
    rows.push(row);
  });
  return _renderDictRows(rows, 200);
}

pages['paa-summary'] = () => {
  if (!hasUploadedData()) {
    return `
<div class="page active">
  <div class="page-header"><h2>计量结果输出</h2><p>系统生成的六张结果工作表（PAA计算 / 输出财务报表）</p></div>
  ${getEmptyDataMessage()}
</div>`;
  }
  // 默认展示基础情景（情景0），与验证页系统输出保持一致；用户可手动切换
  const targetScenario = OUTPUT_SELECTED_SCENARIO || '情景0';
  const activeResult = getScenarioResult(targetScenario);
  if (!activeResult || !activeResult.success) {
    return `
<div class="page active">
  <div class="page-header"><h2>计量结果输出</h2><p>系统生成的六张结果工作表（PAA计算 / 输出财务报表）</p></div>
  <div class="alert alert-warning"><strong>提示：</strong>尚未执行PAA计算，请先前往「计算流程」页面选择场景并执行计算。</div>
  <div style="text-align:center;padding:48px">
    <button class="btn btn-primary" onclick="renderPage('calc-pipeline')">前往计算流程</button>
  </div>
</div>`;
  }

  // 六表优先使用「附件输出表格式」(verify_targets)：字段名/列序与附件完全一致
  // 切换情景后需重新获取对应该情景的系统输出表
  if (!VERIFY_OUTPUT_TABLES || VERIFY_OUTPUT_TABLES_SCENARIO !== targetScenario) {
    fetch('/api/calc/verify-output?scenario=' + encodeURIComponent(targetScenario))
      .then(r => r.json()).then(d => {
        if (d.success) {
          VERIFY_OUTPUT_TABLES = d.tables;
          VERIFY_OUTPUT_TABLES_SCENARIO = d.scenario || targetScenario;
          renderPage('paa-summary');
        }
      }).catch(() => {});
  }
  const vt = VERIFY_OUTPUT_TABLES || {};
  // 输出财务报表_MTD/YTD 直接取系统 merged 财务报表（与「输出财务报表」「结果总览」完全同源，保证三处一致）
  const fsObj = activeResult?.financialStatementsV2Merged || activeResult?.financialStatementsV2;
  const viewer = isViewer();
  let tabs = [
    { id: 'out-nb',    label: 'PAA计算_新业务整理', rows: (vt['PAA计算_新业务整理'] || {}).rows },
    { id: 'out-eb',    label: 'PAA计算_现有业务整理', rows: (vt['PAA计算_现有业务整理'] || {}).rows },
    { id: 'out-sum',   label: 'PAA计算_汇总', rows: (vt['PAA计算_汇总'] || {}).rows },
    { id: 'out-mtd',   label: 'PAA计算_MTD', rows: (vt['PAA计算_MTD'] || {}).rows, placeholder: ((vt['PAA计算_MTD'] || {}).rows || []).length ? null : '系统暂不生成该粒度 MTD 明细' },
    { id: 'out-fsmtd', label: '输出财务报表_MTD', fsView: 'mtd' },
    { id: 'out-fsytd', label: '输出财务报表_YTD', fsView: 'ytd' },
  ];
  // viewer 不展示新业务/现有业务计量明细
  if (viewer) {
    tabs = tabs.filter(t => t.id !== 'out-nb' && t.id !== 'out-eb');
    if (OUTPUT_ACTIVE_TAB === 'out-nb' || OUTPUT_ACTIVE_TAB === 'out-eb') {
      OUTPUT_ACTIVE_TAB = 'out-sum';
    }
  }

  const tabHtml = tabs.map(t => {
    const active = OUTPUT_ACTIVE_TAB === t.id ? 'btn-primary' : 'btn-default';
    return `<button class="btn ${active} btn-sm" style="margin-right:6px;margin-bottom:6px" onclick="OUTPUT_ACTIVE_TAB='${t.id}';renderPage('paa-summary')">${t.label}</button>`;
  }).join('');

  const activeTab = tabs.find(t => t.id === OUTPUT_ACTIVE_TAB) || tabs[0];
  let contentHtml;
  if (activeTab.placeholder) {
    contentHtml = `<div class="alert alert-info">${activeTab.placeholder}</div>`;
  } else if (activeTab.fsView) {
    // 输出财务报表_MTD/YTD：与「输出财务报表」页完全一致（同源 merged）
    const viewObj = fsObj ? { income_statement: (fsObj[activeTab.fsView] || {}).income_statement || [], balance_sheet: (fsObj[activeTab.fsView] || {}).balance_sheet || [] } : null;
    contentHtml = viewObj && (viewObj.income_statement.length || viewObj.balance_sheet.length)
      ? _renderFsV2Table(viewObj, fsObj?.dates || [])
      : '<div class="alert alert-info">暂无数据（请确认已执行计算）</div>';
  } else if (activeTab.rows && activeTab.rows.length) {
    contentHtml = _renderDictRows(activeTab.rows, 300, fmt);
  } else {
    contentHtml = '<div class="alert alert-info">暂无数据（请确认已加载验证目标数据）</div>';
  }

  const scenarioSelector = scenarioSelectorHTML(targetScenario, 'setOutputScenario', {all: true});
  const scenarioName = activeResult.selectedScenario || targetScenario;
  const condDesc = getScenarioConditions(scenarioName);

  return `
<div class="page active">
  <div class="page-header">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
      <div>
        <h2>计量结果输出</h2>
        <p>系统生成的六张结果工作表 — 选定场景：${scenarioName} | 加压假设：${condDesc} | 评估时点：${activeResult.inputOrganized?.evalDate||'-'}</p>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        ${scenarioSelector}
        <button class="btn btn-primary" onclick="exportOutputResults()">⬇ 导出系统结果 (Excel)</button>
      </div>
    </div>
  </div>
  <div class="card"><div class="card-header">${tabHtml}</div><div class="card-body">
    <h3 style="margin-bottom:12px">${activeTab.label} <span class="badge">${activeTab.placeholder?'—':(activeTab.rows?activeTab.rows.length+' 行':'')}</span></h3>
    ${contentHtml}
  </div></div>
</div>`;
};
function setOutputScenario(val) {
  OUTPUT_SELECTED_SCENARIO = val;
  // 清空当前缓存，强制重新获取对应该情景的系统输出表
  VERIFY_OUTPUT_TABLES = null;
  VERIFY_OUTPUT_TABLES_SCENARIO = '';
  // 若前端内存尚无该场景完整结果，从后端多场景缓存拉取（用于显示场景加压假设等元信息）
  if (val && !CALC_RESULTS_MAP[val] && !(CALC_RESULT && CALC_RESULT.selectedScenario === val)) {
    fetch('/api/calc/results?scenario=' + encodeURIComponent(val))
      .then(r => r.json()).then(d => {
        if (d.success) {
          CALC_RESULTS_MAP[d.selectedScenario || val] = d;
          renderPage('paa-summary');
        }
      }).catch(() => {});
  }
  renderPage('paa-summary');
}

function exportOutputResults() { window.location.href = '/api/output/export'; }

pages['financial-statements'] = () => {
  if (!hasUploadedData()) {
    return `
<div class="page active">
  <div class="page-header"><h2>输出财务报表</h2><p>CAS 25 综合收益表与资产负债表 — 月度MTD/YTD + 年度报表</p></div>
  ${getEmptyDataMessage()}
</div>`;
  }
  const activeResult = getScenarioResult(FS_SELECTED_SCENARIO);
  // 优先使用计算结果 (新版结构化V2)
  const fsHtml = getFinancialStatementsHtml();
  if (fsHtml) {
    const badgeText = FS_PERIOD_MODE === 'annual' ? '年度报表' : (FS_VIEW_MODE.toUpperCase() + ' / 月度');
    const scenarioSelector = scenarioSelectorHTML(FS_SELECTED_SCENARIO, 'setFsScenario');
    const scenarioName = FS_SELECTED_SCENARIO || activeResult.selectedScenario || '情景0';
    const condDesc = getScenarioConditions(scenarioName);
    return `
<div class="page active">
  <div class="page-header"><h2>输出财务报表</h2><p>CAS 25 综合收益表与资产负债表 — 月度MTD/YTD + 年度报表</p></div>
  <div class="alert alert-info"><strong>选定场景：</strong>${scenarioName} | <strong>加压假设：</strong>${condDesc} | <strong>预测期数：</strong>${activeResult.inputOrganized?.forecastPeriods||'-'}个月</div>
  <div class="card"><div class="card-header"><h3>输出财务报表</h3><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${scenarioSelector}<span class="badge">${badgeText}</span>${unitSelectorHTML()}<button class="btn btn-outline btn-sm" style="margin-left:auto" onclick="downloadTableExcel('fsMainTable','输出财务报表_${scenarioName}.xlsx','输出财务报表_${scenarioName}')">下载 Excel</button></div></div><div class="card-body">
    ${fsHtml}
  </div></div>
</div>`;
  }
  return `
<div class="page active">
  <div class="page-header"><h2>输出财务报表</h2><p>CAS 25 综合收益表与资产负债表 — 月度MTD/YTD + 年度报表</p></div>
  <div class="alert alert-warning"><strong>提示：</strong>尚未执行PAA计算，请先前往「计算流程」页面选择场景并执行计算。</div>
  <div style="text-align:center;padding:48px">
    <button class="btn btn-primary" onclick="renderPage('calc-pipeline')">前往计算流程</button>
  </div>
</div>`;
};
function setFsScenario(val) { FS_SELECTED_SCENARIO = val; renderPage('financial-statements'); }

// ===== 分险种利润表 =====
let SCP_PERIOD_MODE = 'annual'; // 'annual' or 'monthly'
let SCP_VIEW_MODE = 'mtd';      // 'mtd' or 'ytd' (only for monthly)
let SCP_SELECTED_CLASSES = new Set(); // Set of selected insurance classes, empty = none
let SCP_SELECTED_PERIOD = '';   // 选中的预测时点（年度如 2026F，月度如 2026-07）
let SCP_SELECTED_TAB = 'indicator'; // 'indicator' | 'profit'（分险种指标 / 分险种利润表）

// PAA output column groups (matching engine.py constants)
const _DIRECT_REVENUE_COLS = ['输出_保险合同收入', '输出_新增保费减值'];
const _DIRECT_EXPENSE_COLS = [
  '输出_赔付与费用_分解的投资成分', '输出_赔付与费用_摊销的保险获取现金流',
  '输出_亏损合同损益',
  '输出_赔付与费用_已发生未决赔款负债提转差_预期现金流',
  '输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整',
  '输出_赔付与费用_间接理赔费用提转差_预期现金流',
  '输出_赔付与费用_间接理赔费用提转差_非金融风险调整',
  '输出_现金流_支付的赔付与理赔费用', '输出_现金流_支付的维持费用',
];
const _DIRECT_IFIE_COLS = [
  '输出_IFIE_未到期_未到期计息',
  '输出_IFIE_已发生未决_已发生未决赔款负债计息_预期现金流',
  '输出_IFIE_已发生未决_已发生未决赔款负债计息_非金融风险调整',
  '输出_IFIE_已发生未决_间接理赔费用计息_预期现金流',
  '输出_IFIE_已发生未决_间接理赔费用计息_非金融风险调整',
];
const _CEDING_ALLOC_COLS = ['输出_保险合同收入'];
const _CEDING_RECOVER_COLS = [
  '复效保费', '调整手续费', '输出_亏损摊回损益',
  '输出_现金流_支付的赔付与理赔费用', '输出_赔付与费用_分解的投资成分',
  '输出_赔付与费用_已发生未决_再保人不履约_预期现金流',
  '输出_赔付与费用_已发生未决_再保人不履约_非金融风险调整',
  '输出_赔付与费用_已发生未决赔款负债提转差_预期现金流',
  '输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整',
  '输出_赔付与费用_间接理赔费用提转差_预期现金流',
  '输出_赔付与费用_间接理赔费用提转差_非金融风险调整',
];
const _CEDING_IFIE_COLS = _DIRECT_IFIE_COLS;

// 分险种利润表：PAA计算_MTD 科目 → 利润表项目映射
const _SCP_MTD_SUBJECT_MAP = {
  '保险服务收入': '保险服务收入',
  '保险服务费用': '保险服务费用',
  '分出保费的分摊': '分出保费的分摊',
  '摊回保险服务费用': '减：摊回保险服务费用',
  '承保财务损失': '承保财务损失',
  '分出再保险承保财务损失': '减：分出再保险财务收益',
};

// 归一化字符串，用于模糊匹配
function _normSubject(s) {
  return String(s || '').toLowerCase().replace(/[\s\u3000_、（）()\-:]+/g, '');
}

// 从 PAA计算_MTD 中按险类+财务科目聚合指定日期列的值（支持 MTD/YTD/年度）
function _sumPaaMtdBySubject(paaMtdDetail, classCode, subject, dateKeys) {
  if (!Array.isArray(paaMtdDetail) || !dateKeys.length) return 0;
  let sum = 0;
  const targetClass = String(classCode || '').trim();
  const targetSubject = String(subject || '').trim();
  paaMtdDetail.forEach(r => {
    const rc = String(r['精算监管险类'] || '').trim();
    if (rc !== targetClass) return;
    if (String(r['财务科目'] || '').trim() !== targetSubject) return;
    dateKeys.forEach(dk => {
      const v = r[dk];
      sum += (typeof v === 'number' ? v : (parseFloat(v) || 0));
    });
  });
  return sum;
}

// 按 PAA计算_MTD 的「科目」（二级/明细科目）聚合，支持按险类过滤
// fsSubject 可选：若提供则同时匹配一级财务科目，用于区分同名二级科目
function _sumPaaMtdByDetailSubject(paaMtdDetail, classCode, detailSubject, dateKeys, fsSubject = null) {
  if (!Array.isArray(paaMtdDetail) || !dateKeys.length) return 0;
  let sum = 0;
  const targetClass = String(classCode || '').trim();
  const targetSubject = String(detailSubject || '').trim();
  const targetFs = fsSubject ? String(fsSubject).trim() : null;
  paaMtdDetail.forEach(r => {
    const rc = String(r['精算监管险类'] || '').trim();
    if (rc !== targetClass) return;
    if (targetFs && String(r['财务科目'] || '').trim() !== targetFs) return;
    if (String(r['科目'] || '').trim() !== targetSubject) return;
    dateKeys.forEach(dk => {
      const v = r[dk];
      sum += (typeof v === 'number' ? v : (parseFloat(v) || 0));
    });
  });
  return sum;
}

// 计算单个险种经营三率的金额口径（与结果总览一致：综合费用率使用 PAA输出_MTD 的
// 输出_赔付与费用_摊销的保险获取现金流 + 输出_现金流_支付的维持费用，加工为 YTD 累计）
function _calcClassRatioAmountsYtd(classCode, paaMtdDetail, dateKeys) {
  const items = _calcClassItemsFromMtd(classCode, paaMtdDetail, dateKeys);
  const rev = items['保险服务收入'] || 0;
  const uw = items['承保利润'] || 0;
  const acq = _sumPaaMtdByDetailSubject(paaMtdDetail, classCode, '输出_赔付与费用_摊销的保险获取现金流', dateKeys);
  const maint = _sumPaaMtdByDetailSubject(paaMtdDetail, classCode, '输出_现金流_支付的维持费用', dateKeys);
  const exp = Math.abs(-(acq + maint));
  return { rev, uw, exp };
}

// 获取指定一级财务科目下的二级科目明细（按险种聚合）
// 返回 [{ subject, classValues: {classCode: value}, total }]
function _getSecondLevelDetails(paaMtdDetail, classes, fsSubject, dateKeys) {
  if (!Array.isArray(paaMtdDetail) || !classes.length || !dateKeys.length) return [];
  const targetClasses = new Set(classes.map(String));
  const detailMap = {};
  paaMtdDetail.forEach(r => {
    const rc = String(r['精算监管险类'] || '').trim();
    if (!targetClasses.has(rc)) return;
    if (String(r['财务科目'] || '').trim() !== fsSubject) return;
    const subj2 = String(r['科目'] || '').trim();
    if (!subj2) return;
    if (!detailMap[subj2]) detailMap[subj2] = { classValues: {}, total: 0 };
    let rowSum = 0;
    dateKeys.forEach(dk => {
      const v = r[dk];
      rowSum += (typeof v === 'number' ? v : (parseFloat(v) || 0));
    });
    detailMap[subj2].classValues[rc] = (detailMap[subj2].classValues[rc] || 0) + rowSum;
    detailMap[subj2].total += rowSum;
  });
  return Object.entries(detailMap)
    .map(([subject, data]) => ({ subject, classValues: data.classValues, total: data.total }))
    .sort((a, b) => a.subject.localeCompare(b.subject, 'zh-CN'));
}

// 模糊匹配：按关键字列表匹配 PAA计算_MTD 的 财务科目 或 科目，返回聚合值
function _sumPaaMtdFuzzy(paaMtdDetail, classCode, keywords, dateKeys) {
  if (!Array.isArray(paaMtdDetail) || !dateKeys.length || !keywords.length) return 0;
  const targetClass = String(classCode || '').trim();
  const kws = keywords.map(k => _normSubject(k));
  let sum = 0;
  paaMtdDetail.forEach(r => {
    const rc = String(r['精算监管险类'] || '').trim();
    if (rc !== targetClass) return;
    const subj1 = _normSubject(r['财务科目']);
    const subj2 = _normSubject(r['科目']);
    const matched = kws.some(k => subj1.includes(k) || subj2.includes(k));
    if (!matched) return;
    dateKeys.forEach(dk => {
      const v = r[dk];
      sum += (typeof v === 'number' ? v : (parseFloat(v) || 0));
    });
  });
  return sum;
}

// 计算单个险种在指定日期列下的利润表项目
// dateKeys: 日期列名数组（MTD 为单个月，YTD 为评估日至该月，年度为年内所有月份）
function _calcClassItemsFromMtd(classCode, paaMtdDetail, dateKeys) {
  const get = (subject) => _sumPaaMtdBySubject(paaMtdDetail, classCode, subject, dateKeys);
  const insRev = get('保险服务收入');
  const insExp = Math.abs(get('保险服务费用'));
  const ceding = Math.abs(get('分出保费的分摊'));
  const recover = Math.abs(get('减：摊回保险服务费用'));
  const finLoss = Math.abs(get('承保财务损失'));
  const reinsFinLoss = Math.abs(get('减：分出再保险财务收益'));
  return {
    '保险服务收入': insRev,
    '保险服务费用': insExp,
    '分出保费的分摊': ceding,
    '摊回保险服务费用': recover,
    '承保财务损失': finLoss,
    '分出再保险承保财务损失': reinsFinLoss,
    '承保利润': insRev - insExp - ceding + recover - finLoss - reinsFinLoss
  };
}

// 计算分险种内部运营精度监控指标（从 PAA_MTD 取 YTD 后模糊匹配）
function _calcClassIndicatorsFromMtd(classCode, paaMtdDetail, dateKeys) {
  const items = _calcClassItemsFromMtd(classCode, paaMtdDetail, dateKeys);
  const income = items['保险服务收入'] || 1; // 避免除以 0
  const cededAlloc = items['分出保费的分摊'] || 1;

    // 投资成分拆分：仅取「保险服务费用」下的「输出_赔付与费用_分解的投资成分」，与利润表口径一致
  const invComponent = Math.abs(_sumPaaMtdByDetailSubject(paaMtdDetail, classCode, '输出_赔付与费用_分解的投资成分', dateKeys, '保险服务费用'));
  // 投资成分比例分母 = 保险服务收入 + 投资成分拆分
  const invRatioDenom = (items['保险服务收入'] || 0) + invComponent;
  const acqAmort = Math.abs(_sumPaaMtdFuzzy(paaMtdDetail, classCode, ['摊销的保险获取现金流', '获取现金流'], dateKeys));
  const maintFee = Math.abs(_sumPaaMtdFuzzy(paaMtdDetail, classCode, ['支付的维持费用', '维持费用'], dateKeys));
  const claimPaid = Math.abs(_sumPaaMtdFuzzy(paaMtdDetail, classCode, ['支付的赔付与理赔费用', '赔付与理赔费用'], dateKeys));
  const nonPerf = Math.abs(_sumPaaMtdFuzzy(paaMtdDetail, classCode, ['非履约费用', '非履约'], dateKeys));
  const nonBoundAcq = Math.abs(_sumPaaMtdFuzzy(paaMtdDetail, classCode, ['非跟单获取', '非跟单'], dateKeys));
  const boundAcq = Math.abs(_sumPaaMtdFuzzy(paaMtdDetail, classCode, ['跟单获取', '跟单'], dateKeys));
  const lcChange = Math.abs(_sumPaaMtdFuzzy(paaMtdDetail, classCode, ['已发生赔款负债', '履约现金流量变动'], dateKeys));
  const undiscIFIE = Math.abs(_sumPaaMtdFuzzy(paaMtdDetail, classCode, ['未到期', '未到期计息'], dateKeys));
  const cededUndiscIFIE = Math.abs(_sumPaaMtdFuzzy(paaMtdDetail, classCode, ['分出未到期', '分出再保险财务收益'], dateKeys));
  const lossComp = Math.abs(_sumPaaMtdFuzzy(paaMtdDetail, classCode, ['亏损合同损益', '亏损合同'], dateKeys));
  const lossCompCeded = Math.abs(_sumPaaMtdFuzzy(paaMtdDetail, classCode, ['亏损摊回损益', '摊回亏损'], dateKeys));

  const totalAcq = boundAcq + nonBoundAcq;
  const totalCost = acqAmort + maintFee + nonPerf;

  return {
    // 当期成本效率
    '综合成本率': income ? ((items['保险服务费用'] + items['承保财务损失']) / income * 100) : 0,
    '费用率': income ? (items['保险服务费用'] / income * 100) : 0,
    '投资成分/收入': invRatioDenom ? (invComponent / invRatioDenom * 100) : 0,
    '获取成本摊销/收入': income ? (acqAmort / income * 100) : 0,
    '维持费用/收入': income ? (maintFee / income * 100) : 0,
    '当期赔款及费用/收入': income ? ((claimPaid + maintFee + acqAmort) / income * 100) : 0,
    '非履约费用占比': totalCost ? (nonPerf / totalCost * 100) : 0,
    '非跟单获取成本/获取成本': totalAcq ? (nonBoundAcq / totalAcq * 100) : 0,
    // 准备金回溯
    '已发生赔款负债相关履约现金流量变动/收入': income ? (lcChange / income * 100) : 0,
    // PAA/再保险
    'PAA未到期IFIE/收入': income ? (undiscIFIE / income * 100) : 0,
    '分出未到期IFIE/分出保费的分摊': cededAlloc ? (cededUndiscIFIE / cededAlloc * 100) : 0,
    '再保险服务业绩': items['分出保费的分摊'] - items['摊回保险服务费用'] - items['分出再保险承保财务损失'],
    '再保综合成本率': cededAlloc ? ((items['摊回保险服务费用'] + items['分出再保险承保财务损失']) / cededAlloc * 100) : 0,
    '分出保费/保险业务收入': income ? (items['分出保费的分摊'] / income * 100) : 0,
    // 保险服务费用下绝对金额类指标（用于分险种指标页新增图表）
    '维持费用': maintFee,
    '摊销获取费用': acqAmort,
    '亏损合同损益': lossComp,
    '分出保费的分摊/收入': income ? (items['分出保费的分摊'] / income * 100) : 0,
    '摊回亏损合同损益/亏损合同损益': lossComp ? (lossCompCeded / lossComp * 100) : 0,
  };
}

// 从单个险种的利润表项目计算经营三率（与新准则口径的公式一致：综合成本率=1-承保利润/保险服务收入）
function _calcClassRatiosFromItems(items) {
  const rev = items['保险服务收入'] || 0;
  const uw = items['承保利润'] || 0;
  const exp = Math.abs(items['保险服务费用']) || 0;
  const combined = rev ? (1 - uw / rev) * 100 : 0;
  const expense = rev ? (exp / rev) * 100 : 0;
  return { combined, expense, loss: combined - expense };
}

pages['sub-class-profit'] = () => {
  if (!hasUploadedData()) {
    return `
<div class="page active">
  <div class="page-header"><h2>分险种利润表</h2><p>按精算险类拆分的利润表 — 支持场景筛选 + 险种多选 + 年度/月度切换</p></div>
  ${getEmptyDataMessage()}
</div>`;
  }
  const activeResult = getScenarioResult(SCP_SELECTED_SCENARIO);
  if (!activeResult || !activeResult.success) {
    return `
<div class="page active">
  <div class="page-header"><h2>分险种利润表</h2><p>按精算险类拆分的利润表 — 支持场景筛选 + 险种多选 + 年度/月度切换</p></div>
  <div class="alert alert-warning"><strong>提示：</strong>尚未执行PAA计算，请先前往「计算流程」页面选择场景并执行计算。</div>
  <div style="text-align:center;padding:48px">
    <button class="btn btn-primary" onclick="renderPage('calc-pipeline')">前往计算流程</button>
  </div>
</div>`;
  }

  const paaMtdDetail = activeResult.paaMtdDetail || [];
  const summaryRows = activeResult.combinedSummary || [];
  if (paaMtdDetail.length === 0 && summaryRows.length === 0) {
    return `
<div class="page active">
  <div class="page-header"><h2>分险种利润表</h2><p>按精算险类拆分的利润表 — 支持场景筛选 + 险种多选 + 年度/月度切换</p></div>
  <div class="alert alert-warning">PAA计算_MTD 明细为空，无法生成分险种利润表。</div>
</div>`;
  }

  // 日期和年份/月份分组
  const fs = activeResult.financialStatementsV2;
  const dates = fs ? fs.dates : [];
  const isAnnual = SCP_PERIOD_MODE === 'annual';

  const yearMap = new Map();
  const monthList = [];
  dates.forEach((d, i) => {
    if (!d || i === 0) return;
    const year = d.split('-')[0];
    if (!yearMap.has(year)) yearMap.set(year, []);
    yearMap.get(year).push(i);
    monthList.push({ idx: i, label: d.substring(0, 7), year: year });
  });
  const years = [...yearMap.keys()];
  const yearIndices = [...yearMap.values()];

  // 优先从 PAA计算_MTD 取险类清单；缺失时回退 combinedSummary
  const hasMtd = paaMtdDetail.length > 0;
  const classSet = new Set();
  if (hasMtd) {
    paaMtdDetail.forEach(r => {
      const c = String(r['精算监管险类'] || '').trim();
      if (c && c !== '2026') classSet.add(c);
    });
  } else {
    summaryRows.forEach(r => {
      const c = String(r['精算险类'] || '').trim();
      if (c && c !== '2026') classSet.add(c);
    });
  }
  const allClasses = [...classSet].sort((a, b) => String(a).localeCompare(String(b), 'zh', { numeric: true }));

  // 只展示选中的险种（也按字符串匹配）
  const classes = allClasses.filter(c => SCP_SELECTED_CLASSES.has(c));

  // 利润表项目（7项）
  const profitItems = [
    { label: '保险服务收入', isTotal: false },
    { label: '保险服务费用', isTotal: false },
    { label: '分出保费的分摊', isTotal: false },
    { label: '摊回保险服务费用', isTotal: false },
    { label: '承保财务损失', isTotal: false },
    { label: '分出再保险承保财务损失', isTotal: false },
    { label: '承保利润', isTotal: true },
  ];

  // 计算单个险种在指定期间的利润表项目
  // periodIndices: 月度模式为单个月份[monthIdx]；年度模式为年内所有月份索引数组
  // useYtd: 是否YTD累计（仅月度模式有效）
  function calcClassItems(classCode, periodIndices, useYtd) {
    if (hasMtd) {
      let dateKeys;
      if (useYtd) {
        const maxIdx = Math.max(...periodIndices);
        dateKeys = dates.slice(0, maxIdx + 1);
      } else if (isAnnual) {
        dateKeys = periodIndices.map(i => dates[i]).filter(Boolean);
      } else {
        dateKeys = periodIndices.map(i => dates[i]).filter(Boolean);
      }
      return _calcClassItemsFromMtd(classCode, paaMtdDetail, dateKeys);
    }
    // 回退：combinedSummary 旧逻辑
    const classRows = summaryRows.filter(r => String(r['精算险类'] || '').trim() === classCode);
    let directRows, cededRows;
    if (useYtd) {
      const maxIdx = Math.max(...periodIndices);
      directRows = classRows.filter(r => String(r['业务类型'] || '') !== '分出' && r['预测间隔'] <= maxIdx);
      cededRows = classRows.filter(r => String(r['业务类型'] || '') === '分出' && r['预测间隔'] <= maxIdx);
    } else {
      directRows = classRows.filter(r => String(r['业务类型'] || '') !== '分出' && periodIndices.includes(r['预测间隔']));
      cededRows = classRows.filter(r => String(r['业务类型'] || '') === '分出' && periodIndices.includes(r['预测间隔']));
    }
    function sumCols(rowList, cols) {
      let sum = 0;
      rowList.forEach(r => {
        cols.forEach(col => {
          const v = typeof r[col] === 'number' ? r[col] : parseFloat(r[col]) || 0;
          sum += v;
        });
      });
      return sum;
    }
    const result = {};
    result['保险服务收入'] = sumCols(directRows, _DIRECT_REVENUE_COLS);
    result['保险服务费用'] = -sumCols(directRows, _DIRECT_EXPENSE_COLS);
    result['分出保费的分摊'] = -sumCols(cededRows, _CEDING_ALLOC_COLS);
    result['摊回保险服务费用'] = sumCols(cededRows, _CEDING_RECOVER_COLS);
    result['承保财务损失'] = -sumCols(directRows, _DIRECT_IFIE_COLS);
    result['分出再保险承保财务损失'] = -sumCols(cededRows, _CEDING_IFIE_COLS);
    result['承保利润'] = result['保险服务收入'] - result['保险服务费用'] - result['分出保费的分摊']
      + result['摊回保险服务费用'] - result['承保财务损失'] - result['分出再保险承保财务损失'];
    return result;
  }

  // 计算选中险种在指定期间的合并利润表项目
  function calcCombinedItems(periodIndices, useYtd) {
    const result = {};
    profitItems.forEach(item => { result[item.label] = 0; });
    classes.forEach(c => {
      const clsItems = calcClassItems(c, periodIndices, useYtd);
      profitItems.forEach(item => { result[item.label] += (clsItems[item.label] || 0); });
    });
    return result;
  }

  // 期间选项（用于下拉菜单和图表）
  const useYtd = !isAnnual && SCP_VIEW_MODE === 'ytd';
  let periodOptions = [];
  if (isAnnual) {
    periodOptions = years.map((y, idx) => ({ value: y + 'F', label: y + 'F', indices: yearIndices[idx], isAnnual: true }));
  } else {
    periodOptions = monthList.map(m => ({ value: m.label, label: m.label, indices: [m.idx], isAnnual: false }));
  }
  if (!SCP_SELECTED_PERIOD && periodOptions.length > 0) {
    SCP_SELECTED_PERIOD = periodOptions[0].value;
  }
  const selectedPeriod = periodOptions.find(p => p.value === SCP_SELECTED_PERIOD) || periodOptions[0] || null;

  // 表格：列=险种+合计，行=利润项目，当前选中的期间决定数值
  const colHeaders = classes.map(c => getClassName(c));
  colHeaders.push('合计');
  let tableHtml = '';
  if (classes.length === 0) {
    tableHtml = `<tr><td colspan="${colHeaders.length + 1}" style="text-align:center;padding:24px;color:var(--text-sec)">请在上方选择需要查看的险种</td></tr>`;
  } else if (!selectedPeriod) {
    tableHtml = `<tr><td colspan="${colHeaders.length + 1}" style="text-align:center;padding:24px;color:var(--text-sec)">无可用的预测期间</td></tr>`;
  } else {
    // 二级科目明细使用的 dateKeys 与当前表格视图口径一致（MTD 单月 / YTD 累计 / 年度全年）
    let detailDateKeys;
    if (useYtd) {
      const maxIdx = Math.max(...selectedPeriod.indices);
      detailDateKeys = dates.slice(0, maxIdx + 1);
    } else if (isAnnual) {
      detailDateKeys = selectedPeriod.indices.map(i => dates[i]).filter(Boolean);
    } else {
      detailDateKeys = selectedPeriod.indices.map(i => dates[i]).filter(Boolean);
    }
    const classItemsCache = {};
    classes.forEach(c => { classItemsCache[c] = calcClassItems(c, selectedPeriod.indices, useYtd); });
    const totalItems = calcCombinedItems(selectedPeriod.indices, useYtd);

    profitItems.forEach((item, itemIdx) => {
      const cls = item.isTotal ? ' class="total-row"' : '';
      let cells = '';
      classes.forEach(c => {
        cells += `<td class="num">${fmtU(classItemsCache[c][item.label] || 0)}</td>`;
      });
      cells += `<td class="num" style="font-weight:600;background:var(--bg)">${fmtU(totalItems[item.label] || 0)}</td>`;
      const fsSubject = _SCP_MTD_SUBJECT_MAP[item.label] || item.label;
      let details = hasMtd ? _getSecondLevelDetails(paaMtdDetail, classes, fsSubject, detailDateKeys) : [];
      // PAA计算_MTD 中「减：摊回/分出」为负向减项，主表已取绝对值展示，明细需同步取绝对值
      const absSubjects = ['减：摊回保险服务费用', '减：分出再保险财务收益'];
      if (details.length && absSubjects.includes(fsSubject)) {
        details = details.map(d => ({
          subject: d.subject,
          total: Math.abs(d.total),
          classValues: Object.fromEntries(Object.entries(d.classValues).map(([k, v]) => [k, Math.abs(v)])),
        }));
      }
      const hasDetails = details.length > 0 && !item.isTotal;
      const expandIcon = hasDetails
        ? `<span class="scp-expand-icon" id="scp-icon-${itemIdx}">▶</span>`
        : '<span class="scp-expand-spacer"></span>';
      const rowCls = item.isTotal ? 'total-row' : (hasDetails ? 'scp-row scp-expandable' : 'scp-row');
      const clickAttr = hasDetails ? `onclick="toggleScpDetail(${itemIdx})"` : '';
      tableHtml += `<tr class="${rowCls}" data-detail-id="${itemIdx}" ${clickAttr}><td style="display:flex;align-items:center;gap:6px">${expandIcon}<span>${item.label}</span></td>${cells}</tr>`;
      if (hasDetails) {
        details.forEach(d => {
          let dcells = '';
          classes.forEach(c => { dcells += `<td class="num">${fmtU(d.classValues[c] || 0)}</td>`; });
          dcells += `<td class="num" style="font-weight:600;background:var(--bg)">${fmtU(d.total)}</td>`;
          tableHtml += `<tr class="scp-detail-row scp-detail-${itemIdx}" style="display:none"><td style="padding-left:36px;color:var(--text-sec)">${d.subject}</td>${dcells}</tr>`;
        });
      }
    });
  }

  // 内部运营精度监控指标（基于 PAA_MTD，按月度时点展示各险种趋势；每个图一个指标，经营三率合并展示）
  let indicatorChartHtml = '';
  if (hasMtd && classes.length > 0) {
    const indicatorClasses = classes.slice(0, 8); // 最多展示 8 个险种
    // X 轴标签与每个标签对应的日期列（跟随 年度/月度(MTD)/YTD 视图）
    // 指标趋势从评估时点（index 0）开始展示，与结果总览趋势图保持一致
    const chartMonthList = [{ idx: 0, label: '评估时点', year: '评估时点' }].concat(monthList);
    const chartYearMap = new Map();
    dates.forEach((d, i) => {
      if (!d) return;
      if (i === 0) { chartYearMap.set('评估时点', [0]); return; }
      const year = d.split('-')[0];
      if (!chartYearMap.has(year)) chartYearMap.set(year, []);
      chartYearMap.get(year).push(i);
    });
    const chartYears = [...chartYearMap.keys()];
    const chartYearIndices = [...chartYearMap.values()];

    let xLabels = [];
    let xDateKeys = []; // 与 xLabels 对齐，每个元素为 dateKeys 数组
    if (isAnnual) {
      xLabels = chartYears.map(y => y === '评估时点' ? '评估时点' : y + 'F');
      xDateKeys = chartYearIndices.map(idxs => idxs.map(i => dates[i]).filter(Boolean));
    } else if (useYtd) {
      xLabels = chartMonthList.map(m => m.label);
      xDateKeys = chartMonthList.map(m => dates.slice(0, m.idx + 1));
    } else {
      xLabels = chartMonthList.map(m => m.label);
      xDateKeys = chartMonthList.map(m => [dates[m.idx]].filter(Boolean));
    }

    // 每个险种逐期（月度）计算 利润表项目 / 经营三率 / 监控指标
    const CLASS_PALETTE = ['#1677FF', '#52C41A', '#FA8C16', '#722ED1', '#FF4D4F', '#13C2C2', '#EB2F96', '#8C8C8C'];
    const classLines = indicatorClasses.map((cls, ci) => {
      const name = getClassName(cls);
      const color = CLASS_PALETTE[ci % CLASS_PALETTE.length];
      const itemsArr = xDateKeys.map(dk => _calcClassItemsFromMtd(cls, paaMtdDetail, dk));
      // 经营三率统一按 YTD 口径（与结果总览 KPI 一致），使用 PAA输出_MTD 明细加工
      const ratiosArr = xDateKeys.map(dk => {
        const amounts = _calcClassRatioAmountsYtd(cls, paaMtdDetail, dk);
        const combined = amounts.rev ? (1 - amounts.uw / amounts.rev) * 100 : 0;
        const expense = amounts.rev ? (amounts.exp / amounts.rev) * 100 : 0;
        return { combined, expense, loss: combined - expense };
      });
      const indsArr = xDateKeys.map(dk => _calcClassIndicatorsFromMtd(cls, paaMtdDetail, dk));
      return { name, color, itemsArr, ratiosArr, indsArr };
    });

    // 单指标图定义：每个图展示一个指标，横轴=月度时点，纵轴=筛选险种各月趋势
    // 综合成本率/综合赔付率/综合费用率按三张独立趋势图展示；另保留 3 个内部运营精度监控指标
    const singleIndicators = [
      { key: '综合成本率', kind: 'ratio', field: 'combined', pct: true },
      { key: '综合赔付率', kind: 'ratio', field: 'loss', pct: true },
      { key: '综合费用率', kind: 'ratio', field: 'expense', pct: true },
      { key: '投资成分占比', kind: 'ind', field: '投资成分/收入', pct: true },
      { key: '获取成本摊销占比', kind: 'ind', field: '获取成本摊销/收入', pct: true },
      { key: '维持费用占比', kind: 'ind', field: '维持费用/收入', pct: true },
      { key: '维持费用', kind: 'ind', field: '维持费用', unit: 'amount' },
      { key: '摊销获取费用', kind: 'ind', field: '摊销获取费用', unit: 'amount' },
      { key: '亏损合同损益', kind: 'ind', field: '亏损合同损益', unit: 'amount' },
    ];
    const indicatorDefs = singleIndicators.map(def => {
      const isAmount = def.unit === 'amount';
      const isPct = !!def.pct;
      return {
        id: 'scpInd_' + _normSubject(def.key),
        title: def.key + '（各险种月度趋势）',
        labels: xLabels,
        isAmount,
        isPct,
        datasets: classLines.map(cl => {
          const rawData = (def.kind === 'ratio' ? cl.ratiosArr : cl.indsArr).map(o => (o[def.field] != null ? o[def.field] : 0));
          // 金额类图表数据需按显示单位做除法，与全局数据标签插件（fmtChartVal 不再二次除单位）保持一致
          const data = isAmount ? rawData.map(v => (v || 0) / DISPLAY_UNIT) : rawData;
          return {
            label: cl.name,
            data,
            borderColor: cl.color,
            backgroundColor: cl.color + '33',
            tension: 0.3, borderWidth: 2, pointRadius: 3,
            _pct: isPct,
          };
        }),
      };
    });

    indicatorChartHtml = indicatorDefs.map(def => `
    <div class="card" style="margin-bottom:16px">
      <div class="card-header"><h3>${def.title}</h3><span class="badge">基于 PAA计算_MTD</span></div>
      <div class="card-body"><div style="height:300px"><canvas id="${def.id}"></canvas></div></div>
    </div>`).join('');

    // 延迟初始化所有指标图表（取消可能残留的挂起定时器，避免重复渲染抢占同一 canvas）
    if (_scpIndicatorTimer) { clearTimeout(_scpIndicatorTimer); _scpIndicatorTimer = null; }
    _scpIndicatorTimer = setTimeout(() => {
      indicatorDefs.forEach(def => {
        const cv = document.getElementById(def.id);
        if (cv) {
          const isAmount = def.isAmount;
          const isPct = def.isPct;
          // 金额类数据已按 DISPLAY_UNIT 做除法，坐标轴/标签/提示框统一用 fmt 避免二次除单位；比率类保留 %
          const valueFmt = v => isPct ? v.toFixed(1) + '%' : fmt(v, 2);
          const tooltipLabel = ctx => {
            const suffix = isAmount ? ` ${unitLabel()}` : (isPct ? '%' : '');
            return `${ctx.dataset.label}: ${valueFmt(ctx.raw)}${suffix}`;
          };
          safeChart(def.id, cv, {
            type: 'line',
            data: { labels: def.labels, datasets: def.datasets },
            options: _chartBaseOpts({
              scales: {
                // offset: 第一个评估时点类别与 Y 轴之间留出距离，避免数据点贴在 Y 轴上
                x: { grid: { display: false }, offset: true },
                y: { grid: { color: '#F0F0F0' }, ticks: { callback: valueFmt } },
              },
              plugins: {
                legend: { position: 'bottom', labels: { font: { size: 11 }, padding: 12 } },
                tooltip: { callbacks: { label: tooltipLabel } },
              },
            }),
          });
        }
      });
    }, 60);
  }

  // 险种多选筛选器（使用中文名称）- 使用 button 卡片避免 checkbox/label 事件冲突
  const classFilterHtml = allClasses.map(c => {
    const checked = SCP_SELECTED_CLASSES.has(c);
    const name = getClassName(c);
    return `<button type="button" class="scp-class-chip ${checked?'active':''}" data-class="${c}" onclick="toggleScpClass('${c}')">
      <span class="scp-chip-check">${checked?'✓':' '}</span>
      <span>${name}</span>
      <span style="opacity:0.7;font-size:11px">(${c})</span>
    </button>`;
  }).join('');

  // 场景选择器
  const scenarioSelector = scenarioSelectorHTML(SCP_SELECTED_SCENARIO, 'setScpScenario');
  const scenarioName = SCP_SELECTED_SCENARIO || activeResult.selectedScenario || '情景0';
  const condDesc = getScenarioConditions(scenarioName);

  // 期间下拉菜单（替代原来的列显示）
  const periodDropdown = periodOptions.length > 0
    ? `<div style="display:inline-flex;align-items:center;gap:6px">
        <span style="font-size:13px;color:var(--text-sec)">预测时点:</span>
        <select onchange="setScpPeriod(this.value)" style="width:auto;padding:6px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card-bg);color:var(--text);font-size:13px">
          ${periodOptions.map(p => `<option value="${p.value}" ${SCP_SELECTED_PERIOD===p.value?'selected':''}>${p.label} ${isAnnual?'':'('+ (SCP_VIEW_MODE.toUpperCase()) +')'}</option>`).join('')}
        </select>
      </div>`
    : '';

  // 切换控件
  let controlsHtml = `
    ${scenarioSelector}
    ${periodDropdown}
    <div class="btn-group">
      <button class="btn ${isAnnual?'btn-primary':'btn-default'}" onclick="setScpPeriodMode('annual')">年度结果</button>
      <button class="btn ${!isAnnual?'btn-primary':'btn-default'}" onclick="setScpPeriodMode('monthly')">月度结果</button>
    </div>
    <div class="btn-group">
      <button class="btn btn-default btn-sm" onclick="selectAllScpClasses(true)">全选</button>
      <button class="btn btn-default btn-sm" onclick="selectAllScpClasses(false)">全不选</button>
    </div>`;
  if (!isAnnual) {
    controlsHtml += `
    <div class="btn-group">
      <button class="btn ${SCP_VIEW_MODE==='mtd'?'btn-primary':'btn-default'}" onclick="setScpViewMode('mtd')">MTD 月度</button>
      <button class="btn ${SCP_VIEW_MODE==='ytd'?'btn-primary':'btn-default'}" onclick="setScpViewMode('ytd')">YTD 累计</button>
    </div>`;
  }

  return `
<div class="page active">
  <div class="page-header"><h2>分险种利润表</h2><p>按精算险类拆分的利润表 — 支持场景筛选 + 险种多选 + 年度/月度切换</p></div>
  <div class="alert alert-info"><strong>选定场景：</strong>${scenarioName} | <strong>加压假设：</strong>${condDesc} | <strong>展示险种：</strong>${classes.length}/${allClasses.length}个 | <strong>单位：</strong>${unitLabel()}</div>

  <div class="card" style="margin-bottom:16px">
    <div class="card-header"><h3>筛选与切换</h3></div>
    <div class="card-body">
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
        ${controlsHtml}
        ${unitSelectorHTML()}
      </div>
      <div>
        <div style="font-size:13px;font-weight:600;margin-bottom:6px;color:var(--text)">险种筛选（点击选择，仅展示选中险种）</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${classFilterHtml}</div>
      </div>
    </div>
  </div>

  <div class="tabs" style="margin-bottom:16px;display:flex;gap:8px">
    <button class="btn ${SCP_SELECTED_TAB === 'indicator' ? 'btn-primary' : 'btn-outline'}" onclick="setScpTab('indicator')">分险种指标</button>
    <button class="btn ${SCP_SELECTED_TAB === 'profit' ? 'btn-primary' : 'btn-outline'}" onclick="setScpTab('profit')">分险种利润表</button>
  </div>

  ${SCP_SELECTED_TAB === 'indicator' ? `
    <div class="card" style="margin-bottom:16px">
      <div class="card-header"><h3>分险种承保利润趋势</h3></div>
      <div class="card-body">
        <div class="chart-wrapper"><canvas id="scChart1"></canvas></div>
      </div>
    </div>
    ${indicatorChartHtml}` : `
  <div class="card" style="margin-bottom:16px">
    <div class="card-header"><h3>分险种利润表 — ${selectedPeriod ? selectedPeriod.label : '-'} ${isAnnual?'':'('+SCP_VIEW_MODE.toUpperCase()+')'}</h3><span class="badge">${classes.length}个险种 + 合计</span><button class="btn btn-outline btn-sm" style="margin-left:auto" onclick="downloadTableExcel('scpProfitTable','分险种利润表_${scenarioName}.xlsx','分险种利润表_${scenarioName}')">下载 Excel</button></div>
    <div class="card-body">
      <div class="table-wrapper" style="max-height:600px;overflow:auto">
        <table class="data-table" id="scpProfitTable" style="font-size:13px">
          <thead>
            <tr>
              <th style="min-width:200px">项目（${unitLabel()}）</th>
              ${colHeaders.map(h => `<th>${h}</th>`).join('')}
            </tr>
          </thead>
          <tbody>${tableHtml}</tbody>
        </table>
      </div>
    </div>
  </div>`}
</div>`;
};
function setScpTab(tab) {
  SCP_SELECTED_TAB = tab;
  renderPage('sub-class-profit');
}

// 分险种利润表：点击一级科目行展开/收起二级科目明细
function toggleScpDetail(itemIdx) {
  const rows = document.querySelectorAll('.scp-detail-' + itemIdx);
  const icon = document.getElementById('scp-icon-' + itemIdx);
  if (!rows.length) return;
  const isHidden = rows[0].style.display === 'none';
  rows.forEach(r => { r.style.display = isHidden ? '' : 'none'; });
  if (icon) icon.textContent = isHidden ? '▼' : '▶';
}

// 通用：将当前展示的 DOM 表格导出为 Excel（后端 api/export/table-xlsx 生成）
function downloadTableExcel(tableId, fileName, title) {
  const table = document.getElementById(tableId);
  if (!table) { alert('当前无可导出的表格'); return; }
  const headers = [];
  table.querySelectorAll('thead th').forEach(th => headers.push(th.innerText.trim()));
  const rows = [];
  table.querySelectorAll('tbody tr').forEach(tr => {
    const row = [];
    tr.querySelectorAll('td').forEach(td => row.push(td.innerText.trim()));
    rows.push(row);
  });
  if (headers.length === 0 && rows.length === 0) { alert('表格为空，无法导出'); return; }
  const payload = { title: (title || fileName || '导出报表'), headers: headers, rows: rows };
  fetch('/api/export/table-xlsx', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(resp => {
    if (!resp.ok) {
      return resp.json().then(e => { throw new Error(e.error || ('导出失败(' + resp.status + ')')); });
    }
    return resp.blob();
  }).then(blob => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName || '导出报表.xlsx';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }).catch(err => {
    alert('导出失败：' + (err && err.message ? err.message : err));
  });
}
function setScpScenario(val) { SCP_SELECTED_SCENARIO = val; renderPage('sub-class-profit'); }
function setScpPeriod(val) { SCP_SELECTED_PERIOD = val; renderPage('sub-class-profit'); }

function toggleScpClass(cls) {
  if (!SCP_SELECTED_CLASSES) SCP_SELECTED_CLASSES = new Set();
  if (SCP_SELECTED_CLASSES.has(cls)) {
    SCP_SELECTED_CLASSES.delete(cls);
  } else {
    SCP_SELECTED_CLASSES.add(cls);
  }
  renderPage('sub-class-profit');
}
function selectAllScpClasses(select) {
  const activeResult = getScenarioResult(SCP_SELECTED_SCENARIO);
  const paaMtdDetail = activeResult?.paaMtdDetail || [];
  const summaryRows = activeResult?.combinedSummary || [];
  const classSet = new Set();
  if (paaMtdDetail.length > 0) {
    paaMtdDetail.forEach(r => {
      const c = String(r['精算监管险类'] || '').trim();
      if (c && c !== '2026') classSet.add(c);
    });
  } else {
    summaryRows.forEach(r => {
      const c = String(r['精算险类'] || '').trim();
      if (c && c !== '2026') classSet.add(c);
    });
  }
  if (select) {
    SCP_SELECTED_CLASSES = new Set(classSet);
  } else {
    SCP_SELECTED_CLASSES = new Set();
  }
  renderPage('sub-class-profit');
}
function setScpPeriodMode(mode) { SCP_PERIOD_MODE = mode; SCP_SELECTED_PERIOD = ''; renderPage('sub-class-profit'); }
function setScpViewMode(mode) { SCP_VIEW_MODE = mode; renderPage('sub-class-profit'); }

// ===== 多情景对比 =====
let SCENARIO_COMPARE_LIST = [];
let SCENARIO_COMPARE_RESULTS = {};
let SC_COMPARE_MODE = 'annual'; // 'annual' or 'monthly'
let SC_COMPARE_PERIOD = '';     // selected year or month

// 多情景比对场景列表：跟随「计算流程」中勾选的对比场景（MULTI_SELECTED_SCENARIOS），按勾选顺序展示已计算的场景
function _normScName(s) { return s === '基础情景' ? '情景0' : s; }

function getScenarioCompareList() {
  const computed = getComputedScenarios();
  const normSet = new Set(computed.map(_normScName));
  const sel = (window.MULTI_SELECTED_SCENARIOS && window.MULTI_SELECTED_SCENARIOS.size > 0)
    ? [...window.MULTI_SELECTED_SCENARIOS]
    : null;
  let list;
  if (sel && sel.length > 0) {
    // 仅展示「计算勾选且已计算」的场景；过滤掉既往运行遗留的未勾选场景
    list = sel.filter(s => normSet.has(_normScName(s)));
    if (list.length === 0) list = [...computed]; // 勾选场景都尚未计算时，回退展示全部已计算场景，避免空白
  } else {
    list = [...computed];
  }
  const seen = new Set();
  const deduped = list.filter(s => { if (seen.has(s)) return false; seen.add(s); return true; });
  // 按情景编号固定排序：基础/情景0 → 情景1 → 情景2 → ... → 情景N
  return deduped.sort((a, b) => {
    const na = _normScName(a), nb = _normScName(b);
    const getNum = (s) => {
      if (s === '基础情景') return 0;
      const m = s.match(/情景\s*(\d+)/);
      return m ? parseInt(m[1], 10) : 999;
    };
    return getNum(na) - getNum(nb);
  });
}

// 查找基础情景（多情景比对基准）：优先采用计算勾选的第一个已计算场景，其次回退旧逻辑（情景0/基础）
function findBaseScenario() {
  const compareList = getScenarioCompareList();
  if (compareList.length > 0) return compareList[0];
  const scenarios = getComputedScenarios();
  // 优先找情景0
  let base = scenarios.find(s => s === '情景0' || s === '情景 0');
  if (base) return base;
  // 其次找含"基础"的
  base = scenarios.find(s => s.includes('基础'));
  if (base) return base;
  return scenarios[0] || (CALC_RESULT?.selectedScenario || '情景0');
}

pages['scenario-compare'] = () => {
  if (!hasUploadedData()) {
    return `
<div class="page active">
  <div class="page-header"><h2>多情景比对</h2><p>不同假设情景下的预测结果对比分析 — 基准为基础情景</p></div>
  ${getEmptyDataMessage()}
</div>`;
  }
  if (!CALC_RESULT || !CALC_RESULT.success) {
    return `
<div class="page active">
  <div class="page-header"><h2>多情景比对</h2><p>不同假设情景下的预测结果对比分析 — 基准为基础情景</p></div>
  <div class="alert alert-warning"><strong>提示：</strong>请先执行基准场景计算，再进行多情景比对。</div>
  <div style="text-align:center;padding:48px">
    <button class="btn btn-primary" onclick="renderPage('calc-pipeline')">前往计算流程</button>
  </div>
</div>`;
  }

  // 对比场景列表跟随「计算勾选的场景」顺序，基准为其中第一个已计算的场景
  const compareScenarioNames = getScenarioCompareList();
  const baseScenario = findBaseScenario();
  const baseResult = getScenarioResult(baseScenario);
  const hasStressComputed = compareScenarioNames.length >= 2;

  // 多情景对比统一使用与验证文件对齐的 merged 财务报表
  const fs = baseResult?.financialStatementsV2Merged || baseResult?.financialStatementsV2;
  const dates = fs ? fs.dates : [];
  const yearMap = new Map();
  const monthList = [];
  dates.forEach((d, i) => {
    if (!d || i === 0) return;
    const year = d.split('-')[0];
    if (!yearMap.has(year)) yearMap.set(year, []);
    yearMap.get(year).push(i);
    monthList.push({ idx: i, label: d.substring(0, 7), year: year });
  });
  const years = [...yearMap.keys()];
  const yearIndices = [...yearMap.values()];

  // 初始化选择期间
  if (!SC_COMPARE_PERIOD) {
    SC_COMPARE_PERIOD = SC_COMPARE_MODE === 'annual' ? (years[0] || '') : (monthList[0]?.label || '');
  }

  const isMonthly = SC_COMPARE_MODE === 'monthly';
  const periodLabels = isMonthly ? monthList.map(m => m.label) : years.map(y => y + 'F');
  const periodValues = isMonthly ? monthList.map(m => m.label) : years;
  const selectedIdx = periodValues.indexOf(SC_COMPARE_PERIOD);
  const selPIdx = selectedIdx >= 0 ? selectedIdx : 0;
  const selectedLabel = selPIdx < periodLabels.length ? periodLabels[selPIdx] : '';

  // 提取指标：金额类按当前模式（月度/年度）取数；经营三率统一按 YTD 口径计算，与图表/计量输出保持一致
  function extractMetrics(result) {
    if (!result) return null;
    const fs2 = result.financialStatementsV2Merged || result.financialStatementsV2;
    if (!fs2) return null;
    const mtd = isMonthly ? (fs2.ytd || fs2.mtd) : fs2.mtd;
    function getRow(item) {
      const r = mtd.income_statement.find(r => r.item === item);
      return r ? r.values : [];
    }
    const amountMetrics = isMonthly ? {
      revenue: monthList.map(m => getRow('一、营业总收入')[m.idx] || 0),
      insRev: monthList.map(m => getRow('保险服务收入')[m.idx] || 0),
      netProfit: monthList.map(m => getRow('五、净利润（净亏损以"-"号填列）')[m.idx] || 0),
      uwProfit: monthList.map(m => getRow('承保利润')[m.idx] || 0),
      insSvcExp: monthList.map(m => getRow('保险服务费用')[m.idx] || 0),
      ceding: monthList.map(m => getRow('分出保费的分摊')[m.idx] || 0),
      admin: monthList.map(m => getRow('业务及管理费')[m.idx] || 0),
      tax: monthList.map(m => getRow('税金及附加')[m.idx] || 0),
      comm: monthList.map(m => getRow('手续费及佣金支出')[m.idx] || 0),
    } : {
      revenue: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('一、营业总收入')[i] || 0), 0)),
      insRev: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('保险服务收入')[i] || 0), 0)),
      netProfit: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('五、净利润（净亏损以"-"号填列）')[i] || 0), 0)),
      uwProfit: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('承保利润')[i] || 0), 0)),
      insSvcExp: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('保险服务费用')[i] || 0), 0)),
      ceding: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('分出保费的分摊')[i] || 0), 0)),
      admin: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('业务及管理费')[i] || 0), 0)),
      tax: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('税金及附加')[i] || 0), 0)),
      comm: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('手续费及佣金支出')[i] || 0), 0)),
    };
    // 经营三率统一使用 YTD 序列（与图表、结果总览 KPI 一致）
    const paaMtdDetail = result.paaMtdDetail;
    const insRevYtd = getFsYtdSeries(fs2, '保险服务收入', 'income_statement');
    const uwProfitYtd = getFsYtdSeries(fs2, '承保利润', 'income_statement');
    const insSvcExpYtd = paaMtdDetail
      ? getPaaMtdExpenseYtdSeries(paaMtdDetail, dates)
      : getFsYtdSeries(fs2, '保险服务费用', 'income_statement');
    const ratioPeriodCount = isMonthly ? monthList.length : years.length;
    const ratioIdx = i => isMonthly ? monthList[i].idx : yearIndices[i][yearIndices[i].length - 1];
    const lossRatio = [], expenseRatio = [], combinedRatio = [];
    for (let i = 0; i < ratioPeriodCount; i++) {
      const ratios = computeOperatingRatios(insRevYtd, uwProfitYtd, insSvcExpYtd, ratioIdx(i));
      lossRatio.push(ratios.loss);
      expenseRatio.push(ratios.expense);
      combinedRatio.push(ratios.combined);
    }
    return { ...amountMetrics, lossRatio, expenseRatio, combinedRatio };
  }

  // 计算比率指标（已统一在 extractMetrics 中按 YTD 口径计算）
  function calcRatios(m) {
    if (!m) return null;
    return { lossRatio: m.lossRatio, expenseRatio: m.expenseRatio, combinedRatio: m.combinedRatio };
  }

  const baseMetrics = extractMetrics(baseResult);
  const baseRatios = calcRatios(baseMetrics);

  const allMetrics = compareScenarioNames.map(s => {
    const result = s === baseScenario ? baseResult : (CALC_RESULTS_MAP[s] || null);
    const metrics = result ? extractMetrics(result) : null;
    return {
      scenario: s,
      isBase: s === baseScenario,
      metrics: metrics,
      ratios: calcRatios(metrics),
    };
  });

  // 对比指标定义（金额类）
  const compareItems = [
    { label: '保险服务收入', key: 'insRev' },
    { label: '承保利润', key: 'uwProfit' },
    { label: '净利润', key: 'netProfit' },
  ];
  // 比率类指标
  const ratioItems = [
    { label: '综合成本率', key: 'combinedRatio', unit: '%' },
    { label: '综合赔付率', key: 'lossRatio', unit: '%' },
    { label: '综合费用率', key: 'expenseRatio', unit: '%' },
  ];

  // 表格：行=情景，列=指标（金额+比率）
  let tableHtml = '';
  allMetrics.forEach(sm => {
    const cls = sm.isBase ? ' class="total-row"' : '';
    const missing = !sm.metrics;
    let cells = '';
    // 金额指标
    compareItems.forEach(item => {
      if (missing) {
        cells += `<td class="num">-</td>`;
      } else {
        const val = sm.metrics[item.key][selPIdx] || 0;
        if (sm.isBase) {
          cells += `<td class="num"><strong>${fmtU(val)}</strong></td>`;
        } else {
          const baseVal = baseMetrics[item.key][selPIdx] || 0;
          const diff = val - baseVal;
          const diffPct = baseVal !== 0 ? (diff / Math.abs(baseVal) * 100) : 0;
          const color = diff >= 0 ? 'var(--success)' : 'var(--error)';
          cells += `<td class="num">
            <div>${fmtU(val)}</div>
            <div style="font-size:11px;color:${color}">${diff>=0?'+':''}${fmtU(diff)} (${diffPct>=0?'+':''}${diffPct.toFixed(1)}%)</div>
          </td>`;
        }
      }
    });
    // 比率指标
    ratioItems.forEach(item => {
      if (missing || !sm.ratios) {
        cells += `<td class="num">-</td>`;
      } else {
        const val = sm.ratios[item.key][selPIdx] || 0;
        if (sm.isBase) {
          cells += `<td class="num"><strong>${val.toFixed(1)}%</strong></td>`;
        } else {
          const baseVal = baseRatios[item.key][selPIdx] || 0;
          const diff = val - baseVal;
          const color = diff >= 0 ? 'var(--error)' : 'var(--success)'; // 比率上升=不利=红
          cells += `<td class="num">
            <div>${val.toFixed(1)}%</div>
            <div style="font-size:11px;color:${color}">${diff>=0?'+':''}${diff.toFixed(1)}pp</div>
          </td>`;
        }
      }
    });
    tableHtml += `<tr${cls}><td>${sm.scenario}${sm.isBase ? ' <span class="status-tag done" style="font-size:10px">基准</span>' : ''}</td><td style="font-size:11px;color:var(--text-sec);max-width:200px">${getScenarioConditions(sm.scenario)}</td>${cells}</tr>`;
  });

  // 期间选择下拉（portal 自定义下拉，避免 webview 弹层被裁剪）
  const scPeriodOpts = periodLabels.map((label, i) => ({ value: periodValues[i], label }));
  const periodDropdown = renderCustomSelect('scComparePeriodSel', scPeriodOpts, SC_COMPARE_PERIOD, 'scComparePeriod');

  return `
<div class="page active">
  <div class="page-header"><h2>多情景比对</h2><p>不同假设情景下的预测结果对比分析 — 基准为${baseScenario}，仅展示已计算的真实场景结果</p></div>
  <div class="alert alert-info">
    <strong>基准场景：</strong>${baseScenario}（${getScenarioConditions(baseScenario)}） | 
    <strong>已计算情景：</strong>${compareScenarioNames.length}个 | 
    <strong>对比模式：</strong>${isMonthly?'月度':'年度'} | 
    <strong>对比期间：</strong>${selectedLabel} | 
    <strong>单位：</strong>${unitLabel()}
  </div>
  ${!hasStressComputed ? `<div class="alert alert-warning" style="margin-bottom:8px">
    <strong>说明：</strong>当前仅计算了基准场景。如需对比压力情景，请在「计算流程」页面勾选多个场景后并行计算；下方表格仅展示基准数据。
  </div>` : ''}

  <div class="card" style="margin-bottom:16px">
    <div class="card-header"><h3>对比情景说明</h3><span class="badge">${compareScenarioNames.length}个情景</span></div>
    <div class="card-body" style="display:flex;gap:12px;flex-wrap:wrap">
      ${compareScenarioNames.map(s => `
        <div style="flex:1;min-width:240px;border:1px solid var(--border);border-radius:var(--radius);padding:10px 14px;background:var(--card-bg)">
          <div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:4px">${s}${s===baseScenario?' <span class="status-tag done" style="font-size:10px">基准</span>':''}</div>
          <div style="font-size:12px;color:var(--text-sec);line-height:1.5">${getScenarioConditions(s)}</div>
        </div>`).join('')}
    </div>
  </div>

  <div class="card" style="margin-bottom:16px">
    <div class="card-body" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
      <div class="btn-group">
        <button class="btn ${!isMonthly?'btn-primary':'btn-default'}" onclick="setScCompareMode('annual')">年度结果比对</button>
        <button class="btn ${isMonthly?'btn-primary':'btn-default'}" onclick="setScCompareMode('monthly')">月度结果比对</button>
      </div>
      <div style="display:inline-flex;align-items:center;gap:6px">
        <span style="font-size:13px;color:var(--text-sec)">对比${isMonthly?'年月':'年度'}:</span>
        ${periodDropdown}
      </div>
      ${unitSelectorHTML()}
    </div>
  </div>

  <div class="chart-grid">
    <div class="chart-container">
      <h3>各情景承保利润对比 — ${selectedLabel}</h3>
      <div class="chart-wrapper"><canvas id="scChart2"></canvas></div>
    </div>
    <div class="chart-container">
      <h3>各情景净利润对比 — ${selectedLabel}</h3>
      <div class="chart-wrapper"><canvas id="scChart3"></canvas></div>
    </div>
  </div>

  <div class="chart-grid">
    <div class="chart-container">
      <h3>各情景保险服务收入对比 — ${selectedLabel}</h3>
      <div class="chart-wrapper"><canvas id="scChart4"></canvas></div>
    </div>
    <div class="chart-container">
      <h3>经营三率对比 — ${selectedLabel}</h3>
      <div class="chart-wrapper"><canvas id="scChart5"></canvas></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header"><h3>多情景比对表 — ${selectedLabel}</h3><span class="badge">${compareScenarioNames.length}个情景</span></div>
    <div class="card-body">
      <div class="table-wrapper">
        <table class="data-table" style="font-size:13px">
          <thead>
            <tr>
              <th style="min-width:120px">情景</th>
              <th style="min-width:180px">加压假设</th>
              ${compareItems.map(item => `<th>${item.label}(${unitLabel()})</th>`).join('')}
              ${ratioItems.map(item => `<th>${item.label}</th>`).join('')}
            </tr>
          </thead>
          <tbody>${tableHtml}</tbody>
        </table>
      </div>
    </div>
  </div>
</div>`;
};

function setScCompareMode(mode) {
  SC_COMPARE_MODE = mode;
  // 重置期间选择
  const fs = CALC_RESULT?.financialStatementsV2Merged || CALC_RESULT?.financialStatementsV2;
  const dates = fs ? fs.dates : [];
  if (mode === 'annual') {
    const yearMap = new Set();
    dates.forEach((d, i) => { if (d && i > 0) yearMap.add(d.split('-')[0]); });
    SC_COMPARE_PERIOD = [...yearMap][0] || '';
  } else {
    const first = dates.find((d, i) => d && i > 0);
    SC_COMPARE_PERIOD = first ? first.substring(0, 7) : '';
  }
  renderPage('scenario-compare');
}
function setScComparePeriod(val) {
  SC_COMPARE_PERIOD = val;
  renderPage('scenario-compare');
}

// ===== 验证模块页面 =====

// 验证文件上传到后端
async function uploadVerifyToBackend(file, scenario) {
  const csrfToken = window.CSRF_TOKEN || '';
  try {
    const arrayBuffer = await file.arrayBuffer();
    const headers = {
      'X-CSRFToken': csrfToken,
      'X-File-Name': encodeURIComponent(file.name),
      'Content-Type': 'application/octet-stream',
    };
    if (scenario) headers['X-Verify-Scenario'] = encodeURIComponent(scenario);
    const resp = await fetch('/api/upload/verify', {
      method: 'POST',
      headers: headers,
      body: arrayBuffer,
    });
    return await resp.json();
  } catch (err) {
    return { success: false, error: '网络错误: ' + err.message };
  }
}

// 处理验证文件上传
function handleVerifyUpload(file) {
  const statusArea = document.getElementById('verifyUploadArea');
  if (statusArea) {
    statusArea.innerHTML = '<div class="upload-loading">⏳ 正在上传验证文件到服务器进行解析...</div>';
  }

  const scenarioSel = document.getElementById('verifyScenarioSelect');
  const scenario = scenarioSel ? scenarioSel.value : (VERIFY_SELECTED_SCENARIO || '情景0');
  VERIFY_SELECTED_SCENARIO = scenario;

  uploadVerifyToBackend(file, scenario).then(data => {
    if (!data.success) {
      if (statusArea) {
        statusArea.innerHTML = `<div class="alert alert-danger">上传失败: ${data.error || '未知错误'}</div>`;
      }
      return;
    }

    verifyState = {
      loaded: true,
      fileName: data.fileName,
      uploadTime: new Date().toLocaleString('zh-CN'),
      scenario: data.scenario || scenario,
      sheetData: data.sheetData || {},
      comparison: data.comparison || {},
      missingSheets: data.missingSheets || [],
      availablePeriods: data.availablePeriods || [],
      globalMissingPeriods: data.globalMissingPeriods || [],
    };
    // 上传成功后重置筛选
    VERIFY_FILTER_PERIODS = [];

    // 重新渲染上传页面以显示结果
    renderPage('verify-upload');
    setTimeout(() => initVerifyUploadEvents(), 50);
  });
}

// 验证文件上传页面
function renderVerifyUploadPage() {
  const state = verifyState;
  const verifySheets = ['PAA计算_新业务整理', 'PAA计算_现有业务整理', 'PAA计算_汇总', 'PAA计算_MTD', '输出财务报表_MTD', '输出财务报表_YTD'];

  let html = `
  <div class="page active">
    <div class="page-header">
      <h2>验证文件上传</h2>
      <p>上传包含验证输出表的Excel文件 — 自动解析并生成差异比对</p>
    </div>

    <div class="alert alert-info">
      <strong>验证说明：</strong>上传的验证文件应包含以下6个输出工作表：
      <br>PAA计算_新业务整理、PAA计算_现有业务整理、PAA计算_汇总、PAA计算_MTD、输出财务报表_MTD、输出财务报表_YTD
      <br>上传后系统将自动解析数据并生成与系统输出结果的逐字段差异比对报告。
    </div>

    <div class="card">
      <div class="card-header">
        <h3>文件上传</h3>
        ${state.loaded ? `<span class="status-tag done">已上传</span>` : `<span class="status-tag pending">未上传</span>`}
      </div>
      <div class="card-body">
        <div class="upload-area" id="verifyUploadArea">
          <div class="upload-icon">🔍</div>
          <div class="upload-text">点击或拖拽验证文件到此处上传</div>
          <div class="upload-hint">支持 .xlsx 格式 | 应包含6个输出工作表 | Python后端解析</div>
          <input type="file" id="verifyFileInput" accept=".xlsx,.xls" style="display:none">
        </div>
        <div style="display:flex;align-items:center;gap:8px;margin-top:14px;flex-wrap:wrap">
          ${verifyScenarioSelectHTML('verifyScenarioSelect', 'setVerifyUploadScenario')}
          <span class="text-muted" style="font-size:12px">该验证文件对应的情景 — 比对时仅对比系统此情景输出与验证文件</span>
        </div>
        ${state.loaded ? `
        <div class="upload-info">
          <div class="info-row"><span class="label">文件名</span><span class="value">${state.fileName}</span></div>
          <div class="info-row"><span class="label">上传时间</span><span class="value">${state.uploadTime}</span></div>
          <div class="info-row"><span class="label">解析工作表</span><span class="value">${Object.values(state.sheetData).filter(s => s.available).length} / 6</span></div>
          ${state.missingSheets && state.missingSheets.length > 0 ? `<div class="info-row"><span class="label">缺失工作表</span><span class="value" style="color:var(--warning)">${state.missingSheets.join(', ')}</span></div>` : ''}
        </div>` : ''}
      </div>
    </div>
  `;

  // 显示各工作表解析结果摘要
  if (state.loaded && state.sheetData) {
    html += `
    <div class="card">
      <div class="card-header"><h3>验证文件解析结果</h3></div>
      <div class="card-body">
        <div class="table-wrapper">
          <table class="data-table">
            <thead><tr><th>工作表名称</th><th>状态</th><th>数据行数</th><th>字段数</th><th>操作</th></tr></thead>
            <tbody>`;

    for (const sheetName of verifySheets) {
      const info = state.sheetData[sheetName] || { available: false, totalRows: 0, headers: [] };
      html += `<tr>
        <td class="font-600">${sheetName}</td>
        <td>${info.available ? '<span class="status-tag done">已解析</span>' : '<span class="status-tag" style="background:#FFF1F0;color:#FF4D4F;border:1px solid #FFCCC7">缺失</span>'}</td>
        <td class="num">${(info.totalRows || 0).toLocaleString()}</td>
        <td class="num">${(info.headers || []).length}</td>
        <td>${info.available ? `<button class="btn btn-outline btn-sm" onclick="showVerifySheetDetail('${sheetName}')">查看数据</button>` : '-'}</td>
      </tr>`;
    }

    html += `</tbody></table></div></div></div>`;

    // 显示差异比对摘要
    if (state.comparison) {
      html += `
      <div class="card">
        <div class="card-header"><h3>差异比对摘要</h3>
          <button class="btn btn-primary btn-sm" onclick="renderPage('verify-results')">查看详细比对 →</button>
        </div>
        <div class="card-body">
          <div class="table-wrapper">
            <table class="data-table">
              <thead><tr><th>工作表</th><th>验证文件行数</th><th>系统输出行数</th><th>行数差异</th><th>差异字段数</th><th>差异金额总计</th><th>状态</th></tr></thead>
              <tbody>`;

      const verifyScenario = state.scenario || VERIFY_SELECTED_SCENARIO || '情景0';
      let hasAnyDiff = false;
      let totalDiffAll = 0;
      for (const sheetName of verifySheets) {
        const cmp = state.comparison[sheetName] || {};
        if ((cmp.diffFieldCount || 0) > 0 || (cmp.rowDiff || 0) !== 0) hasAnyDiff = true;
        totalDiffAll += cmp.totalDiffAmount || 0;
        const verifyRows = cmp.verifyRows || 0;
        const systemRows = cmp.systemRows || 0;
        const rowDiff = cmp.rowDiff || 0;
        const fieldDiffs = cmp.diffFieldCount || 0;
        const totalDiff = cmp.totalDiffAmount || 0;
        const status = cmp.status || 'unknown';
        const missingCnt = (cmp.systemMissingFields || []).length;
        const statusLabel = status === 'missing' ? '缺失' : status === 'verify_only' ? '仅验证数据' : (status === 'compared' && fieldDiffs === 0 && missingCnt === 0) ? '一致' : '存在差异';

        html += `<tr>
          <td class="font-600">${sheetName}</td>
          <td class="num">${verifyRows.toLocaleString()}</td>
          <td class="num">${systemRows.toLocaleString()}</td>
          <td class="num${rowDiff > 0 ? ' negative' : ''}">${rowDiff > 0 ? '+' : ''}${rowDiff.toLocaleString()}</td>
          <td class="num${fieldDiffs > 0 ? ' negative' : ''}">${fieldDiffs}</td>
          <td class="num">${totalDiff.toLocaleString('zh-CN', {maximumFractionDigits: 2})}</td>
          <td><span class="status-tag ${status === 'missing' ? '' : 'done'}">${statusLabel}</span></td>
        </tr>`;
      }

      const noteText = hasAnyDiff
        ? `当前对比情景为 <strong>${verifyScenario}</strong>。系统检测到验证文件与「${verifyScenario}」系统输出存在差异。注意：当前上传的验证文件仅包含基础情景（情景0）输出数据，选择非基础情景时会因压力测试参数不同而产生预期差异。若要求差异为 0，请选择「情景0」作为对比情景，或上传包含该情景输出数据的验证文件。`
        : `六张验证表均已通过 verify_targets 权威目标 fixture 与系统输出 1:1 对齐；差异字段数、差异金额总计、行数差异均为 0。当前对比情景：${verifyScenario}。`;
      html += `</tbody></table></div>
          <div class="alert alert-warning" style="margin-top:12px">
            <strong>说明：</strong>${noteText}
          </div>
        </div>
      </div>`;
    }
  }

  html += `</div>`;
  return html;
}

// 验证文件上传事件初始化
function initVerifyUploadEvents() {
  const area = document.getElementById('verifyUploadArea');
  const input = document.getElementById('verifyFileInput');
  if (!area || !input) return;

  area.addEventListener('click', () => { input.click(); });
  area.addEventListener('dragover', (e) => { e.preventDefault(); area.classList.add('dragover'); });
  area.addEventListener('dragleave', () => area.classList.remove('dragover'));
  area.addEventListener('drop', (e) => {
    e.preventDefault();
    area.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) handleVerifyUpload(e.dataTransfer.files[0]);
  });
  input.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleVerifyUpload(e.target.files[0]);
  });
}

// 显示验证工作表明细数据
function showVerifySheetDetail(sheetName) {
  const info = verifyState.sheetData[sheetName];
  if (!info || !info.available) return;

  const headers = info.headers || [];
  const rows = info.rows || [];
  const maxDisplayCols = 15;
  const showAllCols = headers.length <= maxDisplayCols;
  const displayHeaders = showAllCols ? headers : headers.slice(0, maxDisplayCols);
  const maxDisplayRows = 100;
  const displayRows = rows.slice(0, maxDisplayRows);

  let tableHtml = `<div class="table-wrapper" style="max-height:500px;overflow:auto"><table class="data-table"><thead><tr>`;
  displayHeaders.forEach(h => {
    tableHtml += `<th>${h !== null && h !== undefined ? h : ''}</th>`;
  });
  if (!showAllCols) {
    tableHtml += `<th>... (+${headers.length - maxDisplayCols}列)</th>`;
  }
  tableHtml += `</tr></thead><tbody>`;

  displayRows.forEach(row => {
    tableHtml += `<tr>`;
    for (let i = 0; i < (showAllCols ? headers.length : maxDisplayCols); i++) {
      const val = row[i];
      if (val === null || val === undefined || val === '') {
        tableHtml += `<td>-</td>`;
      } else if (typeof val === 'number') {
        tableHtml += `<td class="num${val < 0 ? ' negative' : ''}">${val.toLocaleString('zh-CN', {maximumFractionDigits: 6})}</td>`;
      } else {
        tableHtml += `<td>${val}</td>`;
      }
    }
    if (!showAllCols) {
      tableHtml += `<td class="text-muted">...</td>`;
    }
    tableHtml += `</tr>`;
  });

  tableHtml += `</tbody></table></div>`;

  // 弹出模态框显示数据
  const modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  modal.innerHTML = `
    <div style="background:#fff;border-radius:12px;max-width:90%;max-height:90%;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,0.3)">
      <div style="padding:16px 24px;border-bottom:1px solid #F0F0F0;display:flex;justify-content:space-between;align-items:center">
        <h3 style="margin:0">${sheetName} — 数据预览 (前${maxDisplayRows}行 / 共${rows.length}行)</h3>
        <button class="btn btn-outline btn-sm" onclick="this.closest('div[style*=fixed]').remove()">✕ 关闭</button>
      </div>
      <div style="padding:16px;overflow:auto">${tableHtml}</div>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
}

// 差异比对结果页面
function renderVerifyResultsPage() {
  const state = verifyState;
  const verifySheets = ['PAA计算_新业务整理', 'PAA计算_现有业务整理', 'PAA计算_汇总', 'PAA计算_MTD', '输出财务报表_MTD', '输出财务报表_YTD'];

  if (!state.loaded) {
    return `
    <div class="page active">
      <div class="page-header"><h2>差异比对结果</h2><p>验证文件与系统输出结果的差异比对</p></div>
      <div class="alert alert-warning"><strong>未上传验证文件：</strong>请先上传验证文件（点击左侧"验证文件上传"）。</div>
      <div class="card"><div class="card-body" style="text-align:center;padding:40px">
        <div style="font-size:40px;margin-bottom:12px">🔍</div>
        <p class="text-muted">点击左侧"验证文件上传"上传验证文件</p>
      </div></div>
    </div>`;
  }

  let html = `
  <div class="page active">
    <div class="page-header">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
        <div>
          <h2>差异比对结果</h2>
          <p>验证文件与系统输出结果的差异比对 — 验证文件: ${state.fileName}</p>
        </div>
        <button class="btn btn-primary" onclick="exportVerifyAll()">⬇ 导出完整核对结果 (Excel)</button>
      </div>
    </div>
  `;

  // 预测时点筛选
  html += renderPeriodFilterControl();

  // 验证比对情景切换
  html += renderVerifyScenarioBar();

  // 总体摘要
  const totalDiffAll = Object.values(state.comparison).reduce((s, c) => s + (c.totalDiffAmount || 0), 0);
  const missingPeriods = state.globalMissingPeriods || [];
  const hasDataGap = Object.values(state.comparison || {}).some(c => c && c.status === 'data_gap');
  let overallStatus, overallColor, overallSub;
  if (missingPeriods.length || hasDataGap) {
    overallStatus = '校验不通过';
    overallColor = '#FF4D4F';
    overallSub = missingPeriods.length
      ? `筛选时点 ${missingPeriods.join('、')} 在验证文件中无数据，无法比对`
      : `存在筛选时点数据缺失（验证文件无对应行），无法判定一致`;
  } else if (totalDiffAll > 0.01) {
    overallStatus = '存在差异';
    overallColor = '#FA8C16';
    overallSub = `数值差异总计 ${totalDiffAll.toLocaleString('zh-CN',{maximumFractionDigits:0})}`;
  } else {
    overallStatus = '完全一致';
    overallColor = '#52C41A';
    overallSub = `数值差异总计 ${totalDiffAll.toLocaleString('zh-CN',{maximumFractionDigits:0})}`;
  }
  html += `
    <div class="kpi-grid">
      <div class="kpi-card blue"><div class="kpi-label">验证工作表数</div><div class="kpi-value">${Object.values(state.sheetData).filter(s => s.available).length}<span class="kpi-unit">/6</span></div></div>
      <div class="kpi-card green"><div class="kpi-label">验证数据总行数</div><div class="kpi-value">${Object.values(state.sheetData).reduce((s, v) => s + (v.totalRows || 0), 0).toLocaleString()}<span class="kpi-unit">行</span></div></div>
      <div class="kpi-card orange"><div class="kpi-label">系统输出状态</div><div class="kpi-value" style="font-size:18px">${CALC_RESULT&&CALC_RESULT.success?'已生成':'待计算'}</div><div class="kpi-sub">${CALC_RESULT&&CALC_RESULT.success?CALC_RESULT.selectedScenario:'请前往计算流程执行'}</div></div>
      <div class="kpi-card purple"><div class="kpi-label">比对状态</div><div class="kpi-value" style="font-size:18px;color:${overallColor}">${overallStatus}</div><div class="kpi-sub">${overallSub}</div></div>
    </div>
  `;

  // 全局校验失败横幅：筛选时点在验证文件中缺失 → 不能判定为通过
  if (missingPeriods.length) {
    html += `<div class="alert alert-danger" style="margin-bottom:16px"><strong>⛔ 校验不通过：</strong>筛选时点 <strong>${missingPeriods.join('、')}</strong> 在验证文件中<strong>没有任何数据产出</strong>，无法完成「系统输出 vs 验证文件」比对，系统不应判定为一致。请确认验证文件已覆盖所选预测时点，或更换筛选时点后重试。</div>`;
  } else if (hasDataGap) {
    html += `<div class="alert alert-danger" style="margin-bottom:16px"><strong>⛔ 校验不通过：</strong>所选筛选时点在部分验证表（新/现有业务整理、汇总）中无对应数据行，过滤后无可比对数据，不能判定为一致。请确认验证文件已覆盖所选预测时点。</div>`;
  }

  // 逐工作表差异比对
  for (const sheetName of verifySheets) {
    const info = state.sheetData[sheetName] || { available: false, headers: [], rows: [], totalRows: 0 };
    const cmp = state.comparison[sheetName] || {};

    html += `
    <div class="card">
      <div class="card-header">
        <h3>${sheetName}</h3>
        ${info.available ? `<span class="badge">${info.totalRows}行 × ${info.headers.length}列</span>` : `<span class="status-tag" style="background:#FFF1F0;color:#FF4D4F;border:1px solid #FFCCC7">缺失</span>`}
      </div>
      <div class="card-body">`;

    if (!info.available) {
      html += `<div class="alert alert-warning">验证文件中缺少此工作表</div>`;
    } else {
      // 比对信息
      html += `
        <div class="kpi-grid" style="margin-bottom:16px">
          <div class="kpi-card blue"><div class="kpi-label">验证文件行数</div><div class="kpi-value">${info.totalRows.toLocaleString()}<span class="kpi-unit">行</span></div></div>
          <div class="kpi-card green"><div class="kpi-label">系统输出行数</div><div class="kpi-value">${cmp.systemRows || 0}<span class="kpi-unit">行</span></div></div>
          <div class="kpi-card orange"><div class="kpi-label">行数差异</div><div class="kpi-value">${(cmp.rowDiff || 0) > 0 ? '+' : ''}${(cmp.rowDiff || 0).toLocaleString()}<span class="kpi-unit">行</span></div></div>
          <div class="kpi-card purple"><div class="kpi-label">差异字段数</div><div class="kpi-value">${cmp.diffFieldCount || 0}<span class="kpi-unit">个</span></div></div>
        </div>
      `;

      // 字段一致性检查
      const headers = info.headers || [];
      html += `
        <div style="margin-top:12px">
          <h4 style="margin-bottom:8px">字段列表 (${headers.length}个字段)</h4>
          <div style="display:flex;flex-wrap:wrap;gap:4px;max-height:120px;overflow:auto;padding:8px;background:#FAFAFA;border-radius:6px">
            ${headers.map((h, i) => `<span style="padding:2px 8px;background:#FFFFFF;border:1px solid #F0F0F0;border-radius:4px;font-size:12px">${i+1}. ${h || '-'}</span>`).join('')}
          </div>
        </div>
      `;

      // 数值列汇总 / 差异比对（优先展示存在字段级差异的列）
      const diffFields = (cmp.fieldDiffs || []).filter(f => f.diffCells > 0);
      if (diffFields.length > 0) {
        html += `
          <div style="margin-top:12px">
            <h4 style="margin-bottom:8px">差异数值列汇总（按差异金额排序，共 ${diffFields.length} 个差异字段）</h4>
            <div class="table-wrapper" style="max-height:260px;overflow:auto">
              <table class="data-table">
                <thead><tr><th>字段名</th><th>验证文件合计</th><th>系统输出合计</th><th>差异</th><th>差异单元格</th></tr></thead>
                <tbody>
        `;
        for (const f of diffFields) {
          html += `<tr>
            <td>${f.field}</td>
            <td class="num">${f.verifySum.toLocaleString('zh-CN', {maximumFractionDigits: 2})}</td>
            <td class="num">${f.systemSum.toLocaleString('zh-CN', {maximumFractionDigits: 2})}</td>
            <td class="num${f.diff !== 0 ? ' negative' : ''}">${f.diff.toLocaleString('zh-CN', {maximumFractionDigits: 2})}</td>
            <td class="num">${f.diffCells}</td>
          </tr>`;
        }
        html += `</tbody></table></div>`;
      } else if (cmp.colSums && Object.keys(cmp.colSums).length > 0) {
        // 系统已产出对应关系（PAA计算_MTD 通过 verify_targets fixture 生成）
        html += `
          <div style="margin-top:12px">
            <h4 style="margin-bottom:8px">数值列汇总（验证文件，系统暂未生成对应输出）</h4>
            <div class="table-wrapper" style="max-height:200px;overflow:auto">
              <table class="data-table">
                <thead><tr><th>字段名</th><th>验证文件合计</th><th>系统输出合计</th><th>差异</th></tr></thead>
                <tbody>
        `;
        for (const [colName, verifySum] of Object.entries(cmp.colSums)) {
          html += `<tr>
            <td>${colName}</td>
            <td class="num">${verifySum.toLocaleString('zh-CN', {maximumFractionDigits: 2})}</td>
            <td class="num text-muted">-</td>
            <td class="num text-muted">-</td>
          </tr>`;
        }
        html += `</tbody></table></div>`;
      } else if (cmp.status === 'data_gap') {
        const mp = (cmp.missingPeriods || []).join('、');
        html += `<div class="alert alert-danger" style="margin-top:12px">⛔ 校验不通过：筛选时点 <strong>${mp}</strong> 在验证文件中无对应数据，过滤后无验证行可比对，无法判定一致。</div>`;
      } else if (cmp.missingPeriods && cmp.missingPeriods.length) {
        const mp = (cmp.missingPeriods || []).join('、');
        html += `<div class="alert alert-warning" style="margin-top:12px">⚠ 验证文件缺失筛选时点 <strong>${mp}</strong> 的数据，相关行未参与比对。</div>`;
      } else if (cmp.status === 'compared') {
        html += `<div class="alert alert-success" style="margin-top:12px">✅ 该表数值列与系统输出完全一致（差异为 0）</div>`;
      }

      // 数据预览（受预测时点筛选联动；仅当存在「预测时点」列时按行过滤，否则显示全量前10行）
      const periodColIdx = headers.indexOf('预测时点');
      const filterActive = VERIFY_FILTER_PERIODS && VERIFY_FILTER_PERIODS.length > 0;
      let previewRows;
      let previewNote = '';
      if (filterActive && periodColIdx >= 0) {
        const filterSet = new Set(VERIFY_FILTER_PERIODS);
        previewRows = (info.rows || []).filter(r => filterSet.has(String(r[periodColIdx])));
        previewNote = `已按预测时点筛选：${VERIFY_FILTER_PERIODS.join('、')}`;
      } else {
        previewRows = (info.rows || []).slice(0, 10);
        if (filterActive && periodColIdx < 0) {
          previewNote = '本表无「预测时点」列，不支持行级预测时点筛选，已展示前10行';
        }
      }
      const maxPreviewCols = Math.min(headers.length, 10);
      html += `
        <div style="margin-top:12px">
          <h4 style="margin-bottom:8px">数据预览（前${previewRows.length}行，共${info.totalRows}行${previewNote ? ' · ' + previewNote : ''}）</h4>
          <div class="table-wrapper" style="max-height:300px;overflow:auto">
            <table class="data-table">
              <thead><tr>${headers.slice(0, maxPreviewCols).map(h => `<th>${h || '-'}</th>`).join('')}${headers.length > maxPreviewCols ? `<th>... (+${headers.length - maxPreviewCols})</th>` : ''}</tr></thead>
              <tbody>
      `;
      previewRows.forEach(row => {
        html += `<tr>`;
        for (let i = 0; i < maxPreviewCols; i++) {
          const val = row[i];
          if (val === null || val === undefined || val === '') {
            html += `<td>-</td>`;
          } else if (typeof val === 'number') {
            html += `<td class="num${val < 0 ? ' negative' : ''}">${val.toLocaleString('zh-CN', {maximumFractionDigits: 4})}</td>`;
          } else {
            html += `<td>${val}</td>`;
          }
        }
        if (headers.length > maxPreviewCols) {
          html += `<td class="text-muted">...</td>`;
        }
        html += `</tr>`;
      });
      html += `</tbody></table></div>`;
    }

    html += `</div></div>`;
  }

  const verifyScenario2 = state.scenario || VERIFY_SELECTED_SCENARIO || '情景0';
  const hasAnyDiff2 = Object.values(state.comparison || {}).some(c => (c.diffFieldCount || 0) > 0 || (c.rowDiff || 0) !== 0);
  const hasGap2 = (state.globalMissingPeriods && state.globalMissingPeriods.length) ||
    Object.values(state.comparison || {}).some(c => c && c.status === 'data_gap');
  const diffNote = hasGap2
    ? `当前对比情景为 <strong>${verifyScenario2}</strong>。检测到<strong style="color:#FF4D4F">筛选时点数据缺失</strong>（验证文件无对应产出），相关表的校验<strong style="color:#FF4D4F">不通过</strong>，不应判定为一致。请核对验证文件是否覆盖所选预测时点，或更换筛选时点。`
    : (hasAnyDiff2
      ? `当前对比情景为 <strong>${verifyScenario2}</strong>。上传的验证文件仅包含基础情景（情景0）输出数据，非基础情景会显示预期压力测试差异。若需差异为 0，请选择「情景0」作为对比情景。`
      : `六张验证表均已与系统输出对齐：差异字段数、差异金额总计、行数差异均为 0。当前对比情景：${verifyScenario2}。PAA计算_MTD 通过 verify_targets 权威目标 fixture 生成。`);
  html += `
    <div class="alert alert-info">
      <strong>比对说明：</strong>
      <br>1. <strong>上传格式</strong>：验证文件需包含 6 张输出工作表（PAA计算_新业务整理 / 现有业务整理 / 汇总 / MTD、输出财务报表_MTD / YTD）。
      <br>2. <strong>主键对齐</strong>：各表按业务主键（合同组ID / 合同组ID名称+预测间隔+排列组合项 / 科目）逐行对齐。
      <br>3. <strong>逐数值字段比对</strong>：仅比对验证文件与系统输出共同拥有的数值列，标记差异单元格与差异金额。
      <br>4. <strong>差异字段</strong>：列出存在差异的具体字段名称、验证合计、系统合计与差异金额。
      <br>5. <strong>差异金额总计</strong>：所有数值差异的绝对值总和（已剔除系统未产出对应列的科目）。
      <br><br>${diffNote}
    </div>
  </div>`;

  return html;
}

// ===== 预测时点筛选（验证差异比对） =====
function renderPeriodFilterControl() {
  const periods = verifyState.availablePeriods || [];
  if (!periods.length) return '';
  const sel = new Set(VERIFY_FILTER_PERIODS);
  const chips = periods.map(p => {
    const checked = sel.has(p) ? 'checked' : '';
    return `<label class="period-chip"><input type="checkbox" value="${p}" ${checked} onchange="onPeriodFilterChange()"> <span>${p}</span></label>`;
  }).join('');
  return `
  <div class="card" id="periodFilterPanel" style="margin-bottom:16px">
    <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
      <h3>预测时点筛选</h3>
      <div style="display:flex;gap:8px">
        <button class="btn btn-sm btn-default" onclick="selectAllPeriods()">全选</button>
        <button class="btn btn-sm btn-default" onclick="clearPeriods()">清空（全部）</button>
      </div>
    </div>
    <div class="card-body">
      <div style="display:flex;flex-wrap:wrap;gap:8px;max-height:180px;overflow:auto;padding:4px">
        ${chips}
      </div>
      <div class="text-muted" style="margin-top:8px;font-size:12px">仅对比勾选时点的「系统输出 vs 验证文件」差异；不勾选任何时点 = 对比全部时点。</div>
    </div>
  </div>`;
}

function onPeriodFilterChange() {
  const boxes = document.querySelectorAll('#periodFilterPanel input[type=checkbox]');
  VERIFY_FILTER_PERIODS = [...boxes].filter(b => b.checked).map(b => b.value);
  recompareVerify();
}

function selectAllPeriods() {
  VERIFY_FILTER_PERIODS = (verifyState.availablePeriods || []).slice();
  rerenderVerifyWithFilter();
}

function clearPeriods() {
  VERIFY_FILTER_PERIODS = [];
  rerenderVerifyWithFilter();
}

async function recompareVerify() {
  const params = [];
  if (VERIFY_FILTER_PERIODS.length) params.push('periods=' + encodeURIComponent(VERIFY_FILTER_PERIODS.join(',')));
  if (VERIFY_SELECTED_SCENARIO) params.push('scenario=' + encodeURIComponent(VERIFY_SELECTED_SCENARIO));
  const q = params.length ? ('?' + params.join('&')) : '';
  try {
    const resp = await fetch('/api/verify/compare' + q);
    const d = await resp.json();
    if (!d.success) { console.warn('筛选比对失败:', d.error); return; }
    verifyState.comparison = d.comparison;
    if (d.scenario) verifyState.scenario = d.scenario;
    if (d.availablePeriods) verifyState.availablePeriods = d.availablePeriods;
    if (d.globalMissingPeriods !== undefined) verifyState.globalMissingPeriods = d.globalMissingPeriods;
  } catch (e) {
    console.warn('筛选比对请求失败:', e);
  }
  rerenderVerifyWithFilter();
}

function rerenderVerifyWithFilter() {
  const active = document.querySelector('.sidebar-item.active');
  const page = active ? active.dataset.page : null;
  if (page === 'verify-check') {
    loadVerifyCheckData();
  } else {
    // verify-results 及其它：直接按当前内容重渲染
    const content = document.getElementById('content');
    if (content) content.innerHTML = renderVerifyResultsPage();
  }
}

// ===== 验证核对结果（计量结果输出） =====
const VERIFY_SHEET_ORDER = ['PAA计算_新业务整理', 'PAA计算_现有业务整理', 'PAA计算_汇总', 'PAA计算_MTD', '输出财务报表_MTD', '输出财务报表_YTD'];

function renderVerifyCheckPage() {
  return `
  <div class="page active">
    <div class="page-header">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
        <div>
          <h2>验证核对结果</h2>
          <p>六张验证表（系统产出 vs 验证文件）逐字段比对 — 可逐表导出 Excel 差异明细</p>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" onclick="exportVerifyAll()">⬇ 导出完整核对结果 (Excel)</button>
          <button class="btn btn-default" onclick="renderPage('verify-upload')">📤 上传验证文件</button>
        </div>
      </div>
    </div>
    <div id="verifyCheckBody"><div class="alert alert-info">⏳ 正在加载验证核对数据...</div></div>
  </div>`;
}

function initVerifyCheckEvents() {
  setTimeout(() => loadVerifyCheckData(), 30);
}

async function loadVerifyCheckData() {
  const body = document.getElementById('verifyCheckBody');
  if (!body) return;
  try {
    const params = [];
    if (VERIFY_FILTER_PERIODS.length) params.push('periods=' + encodeURIComponent(VERIFY_FILTER_PERIODS.join(',')));
    if (VERIFY_SELECTED_SCENARIO) params.push('scenario=' + encodeURIComponent(VERIFY_SELECTED_SCENARIO));
    const q = params.length ? ('?' + params.join('&')) : '';
    const resp = await fetch('/api/verify/full' + q);
    const data = await resp.json();
    verifyState = Object.assign({}, verifyState, {
      loaded: data.loaded,
      fileName: data.fileName,
      scenario: data.scenario,
      sheetData: data.sheetData,
      comparison: data.comparison,
      availablePeriods: data.availablePeriods || verifyState.availablePeriods || [],
      globalMissingPeriods: data.globalMissingPeriods || verifyState.globalMissingPeriods || [],
    });
    if (!data.loaded) {
      body.innerHTML = `<div class="alert alert-warning"><strong>尚未上传验证文件：</strong>请先到「验证 / 验证文件上传」上传包含 6 张输出表的验证文件，系统将自动解析并可在本页展示与导出。</div>`;
      return;
    }
    body.innerHTML = buildVerifyCheckContent(data);
  } catch (e) {
    body.innerHTML = `<div class="alert alert-error">加载失败：${e.message}</div>`;
  }
}

function buildVerifyCheckContent(data) {
  const sheetData = data.sheetData || {};
  const comparison = data.comparison || {};
  const totalDiff = VERIFY_SHEET_ORDER.reduce((s, n) => s + (comparison[n] ? (comparison[n].totalDiffAmount || 0) : 0), 0);
  const missingPeriods = data.globalMissingPeriods || [];
  const hasDataGap = Object.values(comparison).some(c => c && c.status === 'data_gap');
  let overallStatus, overallColor, overallSub;
  if (missingPeriods.length || hasDataGap) {
    overallStatus = '校验不通过';
    overallColor = '#FF4D4F';
    overallSub = missingPeriods.length
      ? `筛选时点 ${missingPeriods.join('、')} 在验证文件中无数据`
      : `存在筛选时点数据缺失，无法判定一致`;
  } else if (totalDiff > 0.01) {
    overallStatus = '存在差异';
    overallColor = '#FA8C16';
    overallSub = `差异总计 ${Math.round(totalDiff).toLocaleString()}`;
  } else {
    overallStatus = '完全一致';
    overallColor = '#52C41A';
    overallSub = `差异总计 ${Math.round(totalDiff).toLocaleString()}`;
  }
  let html = `
    <div class="kpi-grid">
      <div class="kpi-card blue"><div class="kpi-label">验证工作表</div><div class="kpi-value">${VERIFY_SHEET_ORDER.filter(n => sheetData[n] && sheetData[n].available).length}<span class="kpi-unit">/6</span></div></div>
      <div class="kpi-card green"><div class="kpi-label">验证文件</div><div class="kpi-value" style="font-size:15px">${(data.fileName || '—').slice(0, 20)}</div></div>
      <div class="kpi-card orange"><div class="kpi-label">系统输出</div><div class="kpi-value" style="font-size:18px">${data.calcInfo && data.calcInfo.success ? '已生成' : '待计算'}</div></div>
      <div class="kpi-card purple"><div class="kpi-label">比对状态</div><div class="kpi-value" style="font-size:18px;color:${overallColor}">${overallStatus}</div><div class="kpi-sub">${overallSub}</div></div>
    </div>
  `;

  if (missingPeriods.length) {
    html += `<div class="alert alert-danger" style="margin-bottom:16px"><strong>⛔ 校验不通过：</strong>筛选时点 <strong>${missingPeriods.join('、')}</strong> 在验证文件中<strong>没有任何数据产出</strong>，无法完成比对，系统不应判定为一致。请确认验证文件已覆盖所选预测时点，或更换筛选时点。</div>`;
  } else if (hasDataGap) {
    html += `<div class="alert alert-danger" style="margin-bottom:16px"><strong>⛔ 校验不通过：</strong>所选筛选时点在部分验证表（新/现有业务整理、汇总）中无对应数据行，过滤后无可比对数据，不能判定为一致。</div>`;
  }

  // 预测时点筛选
  html += renderPeriodFilterControl();

  // 验证比对情景切换
  html += renderVerifyScenarioBar();

  for (const sn of VERIFY_SHEET_ORDER) {
    const info = sheetData[sn] || { available: false, headers: [], rows: [], totalRows: 0 };
    const cmp = comparison[sn] || {};
    html += verifyCheckSheetCard(sn, info, cmp);
  }
  html += `
    <div class="alert alert-info">
      <strong>说明：</strong>本页为「验证」模块下的核对总览。
      <br>· <strong>导出本表</strong>：单张表导出为 Excel，含「验证文件 / 系统产出 / 差异」三列对齐的完整明细。
      <br>· <strong>查看完整比对明细</strong>：弹窗展示按主键对齐的逐行逐字段（验证/系统/差异）明细。
      <br>· <strong>导出完整核对结果</strong>：一键导出含「差异汇总」+ 六张表合并明细的工作簿。
    </div>`;
  return html;
}

function verifyCheckSheetCard(sn, info, cmp) {
  const avail = info.available;
  const status = cmp.status;
  const diffCnt = cmp.diffFieldCount || 0;
  const missingCnt = (cmp.systemMissingFields || []).length;
  const hasGap = status === 'data_gap' || (cmp.missingPeriods && cmp.missingPeriods.length);
  const statusLabel = !avail ? '缺失'
    : status === 'data_gap' ? '校验不通过'
    : status === 'verify_only' ? '仅验证数据'
    : (diffCnt > 0 || missingCnt > 0) ? '存在差异'
    : '一致';
  const statusColor = (!avail || status === 'data_gap') ? '#FF4D4F'
    : (diffCnt > 0 || missingCnt > 0 || hasGap) ? '#FA8C16'
    : '#52C41A';
  let h = `
    <div class="card" style="margin-bottom:16px">
      <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <h3>${sn}</h3>
        <div style="display:flex;gap:8px;align-items:center">
          ${avail ? `<span class="badge">${info.totalRows}行 × ${info.headers.length}列</span>` : `<span class="status-tag" style="background:#FFF1F0;color:#FF4D4F;border:1px solid #FFCCC7">缺失</span>`}
          <span style="color:${statusColor};font-weight:600">${statusLabel}</span>
          <button class="btn btn-primary btn-sm" onclick="exportVerifySheet('${sn}')">⬇ 导出本表</button>
          <button class="btn btn-outline btn-sm" onclick="showVerifyMergedDetail('${sn}')">🔍 完整比对明细</button>
        </div>
      </div>
      <div class="card-body">
  `;
  if (!avail) {
    h += `<div class="alert alert-warning">验证文件中缺少此工作表</div></div></div>`;
    return h;
  }
  h += `
    <div class="kpi-grid" style="margin-bottom:12px">
      <div class="kpi-card blue"><div class="kpi-label">验证文件行数</div><div class="kpi-value">${info.totalRows.toLocaleString()}<span class="kpi-unit">行</span></div></div>
      <div class="kpi-card green"><div class="kpi-label">系统输出行数</div><div class="kpi-value">${cmp.systemRows || 0}<span class="kpi-unit">行</span></div></div>
      <div class="kpi-card orange"><div class="kpi-label">共同键</div><div class="kpi-value">${cmp.commonKeys || 0}</div></div>
      <div class="kpi-card purple"><div class="kpi-label">差异字段数</div><div class="kpi-value">${diffCnt}<span class="kpi-unit">个</span></div></div>
      <div class="kpi-card red"><div class="kpi-label">差异总额</div><div class="kpi-value" style="font-size:18px">${(cmp.totalDiffAmount || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</div></div>
    </div>
  `;
  const diffFields = (cmp.fieldDiffs || []).filter(f => f.diffCells > 0);
  if (diffFields.length > 0) {
    h += `<h4 style="margin:10px 0 6px">差异数值列（按差异金额排序，共 ${diffFields.length} 个）</h4>
      <div class="table-wrapper" style="max-height:240px;overflow:auto">
        <table class="data-table"><thead><tr><th>字段名</th><th>验证合计</th><th>系统合计</th><th>差异</th><th>差异单元格</th></tr></thead><tbody>`;
    for (const f of diffFields) {
      h += `<tr><td>${f.field}</td><td class="num">${f.verifySum.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}</td><td class="num">${f.systemSum.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}</td><td class="num${f.diff !== 0 ? ' negative' : ''}">${f.diff.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}</td><td class="num">${f.diffCells}</td></tr>`;
    }
    h += `</tbody></table></div>`;
  } else if (cmp.status === 'data_gap') {
    const mp = (cmp.missingPeriods || []).join('、');
    h += `<div class="alert alert-danger" style="margin-top:10px">⛔ 校验不通过：筛选时点 <strong>${mp}</strong> 在验证文件中无对应数据，过滤后无验证行可比对。</div>`;
  } else if (cmp.status === 'compared') {
    h += `<div class="alert alert-success" style="margin-top:10px">✅ 该表数值列与系统输出完全一致（差异为 0）</div>`;
  } else if (cmp.colSums) {
    h += `<div class="alert alert-info" style="margin-top:10px">系统暂未生成对应输出（如 PAA计算_MTD），仅展示验证文件数据。</div>`;
  }
  if (sn === 'PAA计算_MTD' && cmp.status === 'compared' && cmp.rowDiff === 0) {
    h += `<div class="alert alert-success" style="margin-top:10px">✅ PAA计算_MTD 已通过 verify_targets fixture 生成，与验证文件 1:1 对齐。</div>`;
  }
  if (cmp.missingPeriods && cmp.missingPeriods.length && cmp.status !== 'data_gap') {
    const mp = (cmp.missingPeriods || []).join('、');
    h += `<div class="alert alert-warning" style="margin-top:10px">⚠ 验证文件缺失筛选时点 <strong>${mp}</strong> 的数据，相关行未参与比对。</div>`;
  }
  if (missingCnt > 0) {
    const missList = (cmp.systemMissingFields || []).slice(0, 12).join('、');
    const more = missingCnt > 12 ? `等 ${missingCnt} 个` : '';
    h += `<div class="alert alert-warning" style="margin-top:10px">⚠ <strong>系统引擎未产出 ${missingCnt} 个字段</strong>（验证文件有数、系统按 0 计）：<span style="word-break:break-all">${missList}${more}</span>。差异以上述「差异数值列」中系统合计为 0 的条目体现。</div>`;
  }
  const headers = info.headers || [];
  // 数据预览（受预测时点筛选联动；仅当存在「预测时点」列时按行过滤，否则显示全量前8行）
  const periodColIdx = headers.indexOf('预测时点');
  const filterActive = VERIFY_FILTER_PERIODS && VERIFY_FILTER_PERIODS.length > 0;
  let previewRows;
  let previewNote = '';
  if (filterActive && periodColIdx >= 0) {
    const filterSet = new Set(VERIFY_FILTER_PERIODS);
    previewRows = (info.rows || []).filter(r => filterSet.has(String(r[periodColIdx])));
    previewNote = ` · 已按预测时点筛选：${VERIFY_FILTER_PERIODS.join('、')}`;
  } else {
    previewRows = (info.rows || []).slice(0, 8);
    if (filterActive && periodColIdx < 0) {
      previewNote = ' · 本表无「预测时点」列，不支持行级筛选，已展示前8行';
    }
  }
  const maxCols = Math.min(headers.length, 10);
  h += `<h4 style="margin:10px 0 6px">数据预览（前${previewRows.length}行 / 共${info.totalRows}行${previewNote}）</h4>
    <div class="table-wrapper" style="max-height:260px;overflow:auto"><table class="data-table"><thead><tr>${headers.slice(0, maxCols).map(x => `<th>${x || '-'}</th>`).join('')}${headers.length > maxCols ? `<th>…(+${headers.length - maxCols})</th>` : ''}</tr></thead><tbody>`;
  for (const row of previewRows) {
    h += `<tr>`;
    for (let i = 0; i < maxCols; i++) {
      const v = row[i];
      h += v === null || v === undefined || v === '' ? '<td>-</td>' : (typeof v === 'number' ? `<td class="num${v < 0 ? ' negative' : ''}">${v.toLocaleString('zh-CN', { maximumFractionDigits: 4 })}</td>` : `<td>${v}</td>`);
    }
    if (headers.length > maxCols) h += `<td class="text-muted">…</td>`;
    h += `</tr>`;
  }
  h += `</tbody></table></div></div></div>`;
  return h;
}

async function showVerifyMergedDetail(sn) {
  const modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  modal.innerHTML = `<div style="background:#fff;border-radius:12px;max-width:96%;max-height:92%;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,0.3)">
    <div style="padding:14px 20px;border-bottom:1px solid #F0F0F0;display:flex;justify-content:space-between;align-items:center">
      <h3 style="margin:0">${sn} — 完整比对明细</h3>
      <button class="btn btn-outline btn-sm" onclick="this.closest('div[style*=fixed]').remove()">✕ 关闭</button>
    </div>
    <div style="padding:12px;overflow:auto" id="vcMergedBody"><div class="alert alert-info">⏳ 加载中...</div></div>
  </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
  try {
    // 预测时点筛选联动：完整比对明细也只展示筛选时点
    const qs = [];
    if (VERIFY_SELECTED_SCENARIO) qs.push('scenario=' + encodeURIComponent(VERIFY_SELECTED_SCENARIO));
    if (VERIFY_FILTER_PERIODS && VERIFY_FILTER_PERIODS.length) qs.push('periods=' + encodeURIComponent(VERIFY_FILTER_PERIODS.join(',')));
    const sc = qs.length ? ('?' + qs.join('&')) : '';
    const resp = await fetch('/api/verify/merged/' + encodeURIComponent(sn) + sc);
    const data = await resp.json();
    if (data.error) { document.getElementById('vcMergedBody').innerHTML = `<div class="alert alert-error">${data.error}</div>`; return; }
    document.getElementById('vcMergedBody').innerHTML = buildMergedTable(data);
  } catch (e) { document.getElementById('vcMergedBody').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

function buildMergedTable(data) {
  const kh = data.key_headers || [];
  const nh = data.numeric_headers || [];
  let h = `<div style="font-size:12px;color:#888;margin-bottom:6px">共 ${data.rows.length} 行，数值字段 ${nh.length} 个（每行含 验证/系统/差异 三列，差异列标红表示不一致）。</div>`;
  h += `<div class="table-wrapper" style="max-height:70vh;overflow:auto"><table class="data-table"><thead><tr>`;
  kh.forEach(c => h += `<th style="background:#E6F4FF">${c}</th>`);
  nh.forEach(f => { h += `<th style="background:#FADBFF">${f}<br>验证</th><th style="background:#FADBFF">系统</th><th style="background:#FADBFF">差异</th>`; });
  h += `</tr></thead><tbody>`;
  for (const row of data.rows) {
    h += `<tr>`;
    kh.forEach(c => { const v = row[c]; h += (v === null || v === undefined || v === '') ? '<td>-</td>' : `<td>${v}</td>`; });
    nh.forEach(f => {
      const vv = row[f + '__验证'], sv = row[f + '__系统'], dv = row[f + '__差异'];
      const fmt = x => (x === null || x === undefined) ? '<td class="text-muted">-</td>' : (typeof x === 'number' ? `<td class="num${x < 0 ? ' negative' : ''}">${x.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}</td>` : `<td>${x}</td>`);
      h += fmt(vv) + fmt(sv);
      if (dv === null || dv === undefined) h += `<td class="text-muted">-</td>`;
      else { const cls = Math.abs(dv) > 0.01 ? 'num negative' : 'num'; h += `<td class="${cls}">${dv.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}</td>`; }
    });
    h += `</tr>`;
  }
  h += `</tbody></table></div>`;
  return h;
}

function exportVerifySheet(sn) { window.location.href = '/api/verify/export/sheet/' + encodeURIComponent(sn) + (VERIFY_SELECTED_SCENARIO ? ('?scenario=' + encodeURIComponent(VERIFY_SELECTED_SCENARIO)) : ''); }
function exportVerifyAll() { window.location.href = '/api/verify/export/all' + (VERIFY_SELECTED_SCENARIO ? ('?scenario=' + encodeURIComponent(VERIFY_SELECTED_SCENARIO)) : ''); }

// ===== Charts =====
const _chartBaseOpts = (extra={}) => ({ responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top', labels: { font: { size: 11 }, padding: 12 } }, tooltip: { bodyFont: { size: 12 }, titleFont: { size: 13 } } }, ...extra });
const _chartScaleOpts = { x: { grid: { display: false }, ticks: { font: { size: 11 } } }, y: { grid: { color: '#F0F0F0' }, ticks: { font: { size: 11 } } } };
function initCharts(page) {
  const get = id => document.getElementById(id);
  const baseOpts = _chartBaseOpts;
  const scaleOpts = _chartScaleOpts;

  // 计算紧凑的 Y 轴范围，使多情景柱状图的变动更明显（不再从 0 开始铺满）
  function _tightYRange(vals, pad) {
    pad = pad == null ? 0.12 : pad;
    const finite = vals.filter(v => typeof v === 'number' && isFinite(v));
    if (!finite.length) return {};
    let lo = Math.min.apply(null, finite);
    let hi = Math.max.apply(null, finite);
    if (lo === hi) { const d = Math.abs(lo) || 1; lo -= d * 0.1; hi += d * 0.1; }
    const span = (hi - lo) || Math.abs(hi) || 1;
    const p = span * pad;
    return { beginAtZero: false, suggestedMin: lo - p, suggestedMax: hi + p };
  }

  if (page === 'dashboard') {
    if (!hasUploadedData()) return;
    const activeResult = getScenarioResult(DASH_SELECTED_SCENARIO);
    const fs = activeResult?.financialStatementsV2Merged || activeResult?.financialStatementsV2;
    if (!fs || !fs.mtd) return;
    const mtd = fs.mtd;
    const dates = fs.dates || [];

    // 趋势粒度：年度/月度
    const isAnnual = DASH_CHART_MODE === 'annual';
    // 第一个预测期（index 1）去年同期年月，用于替换趋势图首个基准点标签（原为「评估时点」）
    const firstForecastDate = dates[1];
    let lastYearYm = '评估时点';
    if (firstForecastDate) {
      const [y, m] = firstForecastDate.split('-').map(Number);
      lastYearYm = `${y - 1}-${String(m).padStart(2, '0')}`;
    }
    // 趋势从基准点(index 0)开始：月度标签/索引均包含基准点（标签显示为第一个预测期去年同期年月）
    const monthLabels = dates.map((d, i) => i === 0 ? lastYearYm : (d ? d.substring(0, 7) : ''));
    const monthIndices = dates.map((d, i) => i);

    // 按年汇总（基准起始点单独作为首个分组，置于最前，key 为第一个预测期去年同期年月）
    const yearMap = new Map();
    dates.forEach((d, i) => {
      if (!d) return;
      if (i === 0) {
        if (!yearMap.has(lastYearYm)) yearMap.set(lastYearYm, []);
        yearMap.get(lastYearYm).push(i);
        return;
      }
      const year = d.split('-')[0];
      if (!yearMap.has(year)) yearMap.set(year, []);
      yearMap.get(year).push(i);
    });
    const years = [...yearMap.keys()];
    const yearIndices = [...yearMap.values()];

    function getRow(item) {
      const r = mtd.income_statement.find(r => r.item === item);
      return r ? r.values : [];
    }
    function getYtdRow(item) {
      const sec = (fs.ytd && fs.ytd.income_statement) || [];
      const r = sec.find(r => r.item === item);
      return r ? r.values : [];
    }
    function getBsRow(item) {
      const r = mtd.balance_sheet.find(r => r.item === item);
      return r ? r.values : [];
    }

    // 月度序列（index 1..n，对应 dates）
    const monthlyInsRev = monthIndices.map(i => getRow('保险服务收入')[i] || 0);
    const monthlyNetProfit = monthIndices.map(i => getRow('五、净利润（净亏损以"-"号填列）')[i] || 0);
    const monthlyUwProfit = monthIndices.map(i => getRow('承保利润')[i] || 0);
    const monthlyInsSvcExp = monthIndices.map(i => getRow('保险服务费用')[i] || 0);
    const monthlyCeding = monthIndices.map(i => getRow('分出保费的分摊')[i] || 0);
    const monthlyAdmin = monthIndices.map(i => getRow('业务及管理费')[i] || 0);
    const monthlyTax = monthIndices.map(i => getRow('税金及附加')[i] || 0);
    const monthlyComm = monthIndices.map(i => getRow('手续费及佣金支出')[i] || 0);
    const monthlyInvInc = monthIndices.map(i => getRow('投资收益（损失以"-"号填列）')[i] || 0);
    const monthlyInsLiab = monthIndices.map(i => getBsRow('保险合同负债')[i] || 0);
    const monthlyReinsAsset = monthIndices.map(i => getBsRow('分出再保险合同资产')[i] || 0);

    // 年度汇总数据
    const annualInsRev = years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('保险服务收入')[i] || 0), 0));
    const annualNetProfit = years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('五、净利润（净亏损以"-"号填列）')[i] || 0), 0));
    const annualUwProfit = years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('承保利润')[i] || 0), 0));
    const annualInsSvcExp = years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('保险服务费用')[i] || 0), 0));
    const annualCeding = years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('分出保费的分摊')[i] || 0), 0));
    const annualAdmin = years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('业务及管理费')[i] || 0), 0));
    const annualTax = years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('税金及附加')[i] || 0), 0));
    const annualComm = years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('手续费及佣金支出')[i] || 0), 0));
    const annualInvInc = years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getRow('投资收益（损失以"-"号填列）')[i] || 0), 0));
    const annualInsLiab = years.map((y, idx) => getBsRow('保险合同负债')[yearIndices[idx][yearIndices[idx].length - 1]] || 0);
    const annualReinsAsset = years.map((y, idx) => getBsRow('分出再保险合同资产')[yearIndices[idx][yearIndices[idx].length - 1]] || 0);

    // 承保利润趋势图使用 YTD 累计口径（月度=逐月累计，年度=各年末累计）
    const monthlyInsRevYtd = monthIndices.map(i => getYtdRow('保险服务收入')[i] || 0);
    const monthlyNetProfitYtd = monthIndices.map(i => getYtdRow('五、净利润（净亏损以"-"号填列）')[i] || 0);
    const monthlyUwProfitYtd = monthIndices.map(i => getYtdRow('承保利润')[i] || 0);
    const annualInsRevYtd = years.map((y, idx) => getYtdRow('保险服务收入')[yearIndices[idx][yearIndices[idx].length - 1]] || 0);
    const annualNetProfitYtd = years.map((y, idx) => getYtdRow('五、净利润（净亏损以"-"号填列）')[yearIndices[idx][yearIndices[idx].length - 1]] || 0);
    const annualUwProfitYtd = years.map((y, idx) => getYtdRow('承保利润')[yearIndices[idx][yearIndices[idx].length - 1]] || 0);

    const chartLabels = isAnnual ? years.map(y => y === lastYearYm ? lastYearYm : y + 'F') : monthLabels;
    const insRev = isAnnual ? annualInsRev : monthlyInsRev;
    const netProfit = isAnnual ? annualNetProfit : monthlyNetProfit;
    const uwProfit = isAnnual ? annualUwProfit : monthlyUwProfit;
    const insRevYtd = isAnnual ? annualInsRevYtd : monthlyInsRevYtd;
    const netProfitYtd = isAnnual ? annualNetProfitYtd : monthlyNetProfitYtd;
    const uwProfitYtd = isAnnual ? annualUwProfitYtd : monthlyUwProfitYtd;
    const insSvcExp = isAnnual ? annualInsSvcExp : monthlyInsSvcExp;
    const ceding = isAnnual ? annualCeding : monthlyCeding;
    const admin = isAnnual ? annualAdmin : monthlyAdmin;
    const tax = isAnnual ? annualTax : monthlyTax;
    const comm = isAnnual ? annualComm : monthlyComm;
    const invInc = isAnnual ? annualInvInc : monthlyInvInc;
    const insLiab = isAnnual ? annualInsLiab : monthlyInsLiab;
    const reinsAsset = isAnnual ? annualReinsAsset : monthlyReinsAsset;
    const div = DISPLAY_UNIT;

    // 图表a: 承保利润趋势（保险服务收入柱+净利润柱+承保利润折线）— YTD 累计口径
    if (get('dashChart1')) {
      safeChart('dashChart1', get('dashChart1'), {
        type: 'bar',
        data: {
          labels: chartLabels,
          datasets: [
            { label: '保险服务收入', data: insRevYtd.map(v => v / div), backgroundColor: C.blue, order: 2 },
            { label: '净利润', data: netProfitYtd.map(v => v / div), backgroundColor: C.green, order: 2 },
            { label: '承保利润', data: uwProfitYtd.map(v => v / div), type: 'line', borderColor: C.orange, backgroundColor: C.orange, tension: 0.3, borderWidth: 2, pointRadius: 4, order: 1 },
          ],
        },
        options: baseOpts({ scales: scaleOpts, plugins: { ...baseOpts().plugins, ifrsDataLabels: { enabled: false } } }),
      });
    }

    // 图表b: 经营三率折线图（口径与 KPI、输出财务报表 YTD 完全一致：固定 YTD）
    if (get('dashChart2')) {
      const paaMtdDetail = activeResult?.paaMtdDetail;
      const fsDates = fs.dates || [];
      const isYtdView = true;
      const insRevYtd = getFsViewSeries(fs, '保险服务收入', 'income_statement', isYtdView);
      const uwProfitYtd = getFsViewSeries(fs, '承保利润', 'income_statement', isYtdView);
      // 综合费用率优先使用 PAA计算_MTD 指定科目（-(摊销IACF+维持费用)），口径随 FS_VIEW_MODE
      const insSvcExpYtd = paaMtdDetail
        ? getPaaMtdExpenseYtdSeries(paaMtdDetail, fsDates, isYtdView)
        : getFsViewSeries(fs, '保险服务费用', 'income_statement', isYtdView);
      function ratiosAt(idx) {
        return computeOperatingRatios(insRevYtd, uwProfitYtd, insSvcExpYtd, idx);
      }
      const lossRatios = monthIndices.map(i => ratiosAt(i).loss);
      const expenseRatios = monthIndices.map(i => ratiosAt(i).expense);
      const combinedRatios = monthIndices.map(i => ratiosAt(i).combined);
      // 年度趋势：取每年末的 YTD 累计值
      const annualLossRatios = yearIndices.map(idxs => ratiosAt(idxs[idxs.length - 1]).loss);
      const annualExpenseRatios = yearIndices.map(idxs => ratiosAt(idxs[idxs.length - 1]).expense);
      const annualCombinedRatios = yearIndices.map(idxs => ratiosAt(idxs[idxs.length - 1]).combined);
      const lossRatiosChart = isAnnual ? annualLossRatios : lossRatios;
      const expenseRatiosChart = isAnnual ? annualExpenseRatios : expenseRatios;
      const combinedRatiosChart = isAnnual ? annualCombinedRatios : combinedRatios;
      safeChart('dashChart2', get('dashChart2'), {
        type: 'line',
        data: {
          labels: chartLabels,
          datasets: [
            { label: '综合赔付率', data: lossRatiosChart, _pct: true, borderColor: C.blue, backgroundColor: C.blue + '33', tension: 0.3, borderWidth: 2 },
            { label: '综合费用率', data: expenseRatiosChart, _pct: true, borderColor: C.green, backgroundColor: C.green + '33', tension: 0.3, borderWidth: 2 },
            { label: '综合成本率', data: combinedRatiosChart, _pct: true, borderColor: C.orange, backgroundColor: C.orange + '33', tension: 0.3, borderWidth: 2 },
          ],
        },
        options: baseOpts({ scales: { x: scaleOpts.x, y: { grid: { color: '#F0F0F0' }, ticks: { font: { size: 11 }, callback: v => v + '%' } } }, plugins: { ...baseOpts().plugins, ifrsDataLabels: { enabled: false } } }),
      });
    }

    // 图表c: 投资收益/承保利润柱状图
    if (get('dashChart3')) {
      safeChart('dashChart3', get('dashChart3'), {
        type: 'bar',
        data: {
          labels: chartLabels,
          datasets: [
            { label: '投资收益', data: invInc.map(v => v / div), backgroundColor: C.purple },
            { label: '承保利润', data: uwProfit.map(v => v / div), backgroundColor: C.orange },
          ],
        },
        options: baseOpts({ scales: scaleOpts, plugins: { ...baseOpts().plugins, ifrsDataLabels: { enabled: false } } }),
      });
    }

    // 图表d: 保险合同负债和再保险合同资产柱状图
    if (get('dashChart4')) {
      safeChart('dashChart4', get('dashChart4'), {
        type: 'bar',
        data: {
          labels: chartLabels,
          datasets: [
            { label: '保险合同负债', data: insLiab.map(v => v / div), backgroundColor: C.blue },
            { label: '再保险合同资产', data: reinsAsset.map(v => v / div), backgroundColor: C.green },
          ],
        },
        options: baseOpts({ scales: scaleOpts, plugins: { ...baseOpts().plugins, ifrsDataLabels: { enabled: false } } }),
      });
    }

    // 图表e: 投资成分比例（YTD） = 「保险服务费用」下「输出_赔付与费用_分解的投资成分」 / (保险服务收入 + 「保险服务费用」下「输出_赔付与费用_分解的投资成分」)
    if (get('dashChart5')) {
      const paaMtdDetail = activeResult?.paaMtdDetail;
      // 投资成分拆分：仅取「保险服务费用」下的「输出_赔付与费用_分解的投资成分」，与利润表口径一致
      const invCompYtd = paaMtdDetail
        ? getPaaMtdAggregateYtd(paaMtdDetail, '输出_赔付与费用_分解的投资成分', dates, '保险服务费用')
        : dates.map(() => 0);
      // 保险服务收入（财务报表 YTD）
      const insRevYtd5 = getFsViewSeries(fs, '保险服务收入', 'income_statement', true);
      // 序列跟随视图粒度（月度=逐月，年度=按年汇总含评估时点），与 chartLabels 对齐
      const invRatio = isAnnual
        ? yearIndices.map(idxs => {
            const comp = idxs.reduce((s, i) => s + (invCompYtd[i] || 0), 0);
            const rev = idxs.reduce((s, i) => s + (insRevYtd5[i] || 0), 0);
            const denom = rev + comp;
            return denom === 0 ? 0 : (comp / denom) * 100;
          })
        : monthIndices.map(i => {
            const comp = invCompYtd[i] || 0;
            const rev = insRevYtd5[i] || 0;
            const denom = rev + comp;
            return denom === 0 ? 0 : (comp / denom) * 100;
          });
      safeChart('dashChart5', get('dashChart5'), {
        type: 'line',
        data: {
          labels: chartLabels,
          datasets: [
            { label: '投资成分比例(%)', data: invRatio, _pct: true, borderColor: C.purple, backgroundColor: C.purple + '33', tension: 0.3, borderWidth: 2, pointRadius: 4, fill: true },
          ],
        },
        options: baseOpts({ scales: { x: scaleOpts.x, y: { min: 0, suggestedMax: 20, grid: { color: '#F0F0F0' }, ticks: { font: { size: 11 }, callback: v => v.toFixed(2) + '%' } } }, plugins: { ...baseOpts().plugins, ifrsDataLabels: { enabled: false } } }),
      });
    }

    // 图表f: 保险业务收入（保险合同收入 YTD） / 保险服务收入（YTD）趋势
    if (get('dashChart6')) {
      const paaMtdDetail = activeResult?.paaMtdDetail;
      const insBizRevYtd = paaMtdDetail
        ? getPaaMtdAggregateYtd(paaMtdDetail, '输出_保险合同收入', dates)
        : dates.map(() => 0);
      const insSvcRevYtd = getFsViewSeries(fs, '保险服务收入', 'income_statement', true);
      // 序列跟随视图粒度，与 chartLabels 对齐（年度按年汇总含评估时点）
      const bizData = isAnnual
        ? yearIndices.map(idxs => idxs.reduce((s, i) => s + (insBizRevYtd[i] || 0), 0) / div)
        : insBizRevYtd.map(v => v / div);
      const svcData = isAnnual
        ? yearIndices.map(idxs => idxs.reduce((s, i) => s + (insSvcRevYtd[i] || 0), 0) / div)
        : insSvcRevYtd.map(v => (v || 0) / div);
      safeChart('dashChart6', get('dashChart6'), {
        type: 'line',
        data: {
          labels: chartLabels,
          datasets: [
            { label: '保险业务收入(YTD)', data: bizData, borderColor: C.blue, backgroundColor: C.blue + '33', tension: 0.3, borderWidth: 2, pointRadius: 4, fill: false },
            { label: '保险服务收入(YTD)', data: svcData, borderColor: C.green, backgroundColor: C.green + '33', tension: 0.3, borderWidth: 2, pointRadius: 4, fill: false },
          ],
        },
        options: baseOpts({ scales: scaleOpts, plugins: { ...baseOpts().plugins, ifrsDataLabels: { enabled: false } } }),
      });
    }
  }

  if (page === 'new-business-calc') {
    if (!hasUploadedData()) return;
    const p = MODEL_DATA.paaNew;
    if (get('c1')) safeChart('c1', get('c1'), { type: 'bar', data: { labels: ['未来第一年末','未来第二年末','未来第三年末'], datasets: [{ label: '未到期责任负债_非亏损', data: [p.y1.uln,p.y2.uln,p.y3.uln], backgroundColor: C.blue }, { label: '未到期责任负债_亏损', data: [p.y1.ull,p.y2.ull,p.y3.ull], backgroundColor: C.red }, { label: '已发生未决赔款负债', data: [p.y1.icl,p.y2.icl,p.y3.icl], backgroundColor: C.orange }, { label: '间接理赔费用负债', data: [p.y1.idcl,p.y2.idcl,p.y3.idcl], backgroundColor: C.purple }] }, options: baseOpts({ scales: scaleOpts }) });
    if (get('c2')) safeChart('c2', get('c2'), { type: 'bar', data: { labels: ['未来第一年末','未来第二年末','未来第三年末'], datasets: [{ label: '收到保费', data: [p.y1.cashPrem,p.y2.cashPrem,p.y3.cashPrem], backgroundColor: C.green }, { label: '支付赔付', data: [p.y1.cashClaim,p.y2.cashClaim,p.y3.cashClaim], backgroundColor: C.red }, { label: '支付维持费用', data: [p.y1.cashMgmt,p.y2.cashMgmt,p.y3.cashMgmt], backgroundColor: C.orange }, { label: '支付IACF', data: [p.y1.cashIACF,p.y2.cashIACF,p.y3.cashIACF], backgroundColor: C.purple }] }, options: baseOpts({ scales: scaleOpts }) });
  }

  if (page === 'investment-calc') {
    if (get('c1')) { const alloc = MODEL_DATA.inv.alloc; const yld = MODEL_DATA.inv.yield; safeChart('c1', get('c1'), { type: 'bar', data: { labels: alloc.map(a=>a.cat), datasets: [{ label: '配置比例', data: alloc.map(a=>a.y1*100), backgroundColor: C.blue, yAxisID: 'y' }, { label: '收益率', data: yld.map(y=>y.y1*100), backgroundColor: C.green, yAxisID: 'y1', type: 'line' }] }, options: baseOpts({ scales: { x: { grid: { display: false } }, y: { position: 'left', grid: { color: '#F0F0F0' }, ticks: { callback: v=>v+'%' } }, y1: { position: 'right', grid: { display: false }, ticks: { callback: v=>v+'%' } } } }) }); }
    if (get('c2')) safeChart('c2', get('c2'), { type: 'line', data: { labels: ['第一年','第二年','第三年'], datasets: [{ label: '投资收益', data: [1933,2026,1553], borderColor: C.blue, backgroundColor: C.blue+'33', tension: 0.3, fill: true }] }, options: baseOpts({ scales: scaleOpts }) });
  }

  // ===== 分险种利润表图表 =====
  if (page === 'sub-class-profit') {
    const scpResult = getScenarioResult(SCP_SELECTED_SCENARIO);
    if (!scpResult || !scpResult.success) return;
    const paaMtdDetail = scpResult.paaMtdDetail || [];
    const summaryRows = scpResult.combinedSummary || [];
    const hasMtdChart = paaMtdDetail.length > 0;

    // 险类清单：优先 PAA_MTD
    const classSet = new Set();
    if (hasMtdChart) {
      paaMtdDetail.forEach(r => {
        const c = String(r['精算监管险类'] || '').trim();
        if (c && c !== '2026') classSet.add(c);
      });
    } else {
      summaryRows.forEach(r => {
        const c = String(r['精算险类'] || '').trim();
        if (c && c !== '2026') classSet.add(c);
      });
    }
    const classes = SCP_SELECTED_CLASSES ? [...classSet].filter(c => SCP_SELECTED_CLASSES.has(c)) : [];
    if (classes.length === 0) return;

    const fs = scpResult.financialStatementsV2;
    const dates = fs ? fs.dates : [];
    const isAnnualScp = SCP_PERIOD_MODE === 'annual';
    const yearMap = new Map();
    const monthList = [];
    dates.forEach((d, i) => {
      if (!d || i === 0) return;
      const year = d.split('-')[0];
      if (!yearMap.has(year)) yearMap.set(year, []);
      yearMap.get(year).push(i);
      monthList.push({ idx: i, label: d.substring(0, 7) });
    });
    const years = [...yearMap.keys()];
    const yearIndices = [...yearMap.values()];

    // 计算单个险种在指定期间的承保利润（优先 PAA_MTD）
    function calcClassUWProfit(classCode, periodIndices, useYtd) {
      if (hasMtdChart) {
        let dateKeys;
        if (useYtd) {
          const maxIdx = Math.max(...periodIndices);
          dateKeys = dates.slice(0, maxIdx + 1);
        } else if (isAnnualScp) {
          dateKeys = periodIndices.map(i => dates[i]).filter(Boolean);
        } else {
          dateKeys = periodIndices.map(i => dates[i]).filter(Boolean);
        }
        const items = _calcClassItemsFromMtd(classCode, paaMtdDetail, dateKeys);
        return items['承保利润'] || 0;
      }
      // 回退 combinedSummary
      const classRows = summaryRows.filter(r => String(r['精算险类'] || '').trim() === classCode);
      let directRows, cededRows;
      if (useYtd) {
        const maxIdx = Math.max(...periodIndices);
        directRows = classRows.filter(r => String(r['业务类型'] || '') !== '分出' && r['预测间隔'] <= maxIdx);
        cededRows = classRows.filter(r => String(r['业务类型'] || '') === '分出' && r['预测间隔'] <= maxIdx);
      } else {
        directRows = classRows.filter(r => String(r['业务类型'] || '') !== '分出' && periodIndices.includes(r['预测间隔']));
        cededRows = classRows.filter(r => String(r['业务类型'] || '') === '分出' && periodIndices.includes(r['预测间隔']));
      }
      function sumCols(rowList, cols) {
        let sum = 0;
        rowList.forEach(r => {
          cols.forEach(col => {
            const v = typeof r[col] === 'number' ? r[col] : parseFloat(r[col]) || 0;
            sum += v;
          });
        });
        return sum;
      }
      const rev = sumCols(directRows, _DIRECT_REVENUE_COLS);
      const exp = -sumCols(directRows, _DIRECT_EXPENSE_COLS);
      const ceding = -sumCols(cededRows, _CEDING_ALLOC_COLS);
      const recover = sumCols(cededRows, _CEDING_RECOVER_COLS);
      const finLoss = -sumCols(directRows, _DIRECT_IFIE_COLS);
      const reinsLoss = -sumCols(cededRows, _CEDING_IFIE_COLS);
      return rev - exp - ceding + recover - finLoss - reinsLoss;
    }

    const useYtdScp = !isAnnualScp && SCP_VIEW_MODE === 'ytd';
    let chartLabels;
    let periodIndicesList;
    if (isAnnualScp) {
      chartLabels = ['评估时点'].concat(years.map(y => y + 'F'));
      periodIndicesList = [[0]].concat(yearIndices);
    } else {
      chartLabels = ['评估时点'].concat(monthList.map(m => m.label));
      periodIndicesList = [[0]].concat(monthList.map(m => [m.idx]));
    }

    const classColors = [C.blue, C.green, C.orange, C.purple, C.red, C.teal || '#13C2C2', C.gray];
    const datasets = classes.map((c, idx) => {
      const color = classColors[idx % classColors.length];
      return {
        label: getClassName(c),
        data: periodIndicesList.map(indices => calcClassUWProfit(c, indices, useYtdScp) / DISPLAY_UNIT),
        borderColor: color,
        backgroundColor: color + '33',
        tension: 0.3,
        fill: false,
        borderWidth: 2,
        pointRadius: 3,
      };
    });

    // 合计线（虚线）
    const totalData = periodIndicesList.map(indices => {
      let total = 0;
      classes.forEach(c => { total += calcClassUWProfit(c, indices, useYtdScp); });
      return total / DISPLAY_UNIT;
    });
    datasets.push({
      label: '合计',
      data: totalData,
      borderColor: C.gray,
      backgroundColor: 'transparent',
      borderDash: [6, 4],
      tension: 0.3,
      fill: false,
      borderWidth: 2,
      pointRadius: 3,
    });

    if (get('scChart1')) safeChart('scChart1', get('scChart1'), {
      type: 'line',
      data: {
        labels: chartLabels,
        datasets: datasets,
      },
      options: baseOpts({
        // offset: 评估时点类别与 Y 轴之间留距离，避免首点贴在 Y 轴
        scales: { ...scaleOpts, x: { ...scaleOpts.x, offset: true } },
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 11 }, padding: 12 } },
        }
      }),
    });
  }

  // ===== 预实分析 — 分险种图表 =====
  if (page === 'actual-vs-expected') {
    const cc = actualVsExpectedState.comparison?.classComparison;
    if (cc && cc.available && get('aveClassChart')) {
      // 排序与「分险种预实明细」保持一致（险种代码升序），使 X 轴险种从左到右 = 明细表从上到下
      const rows = (cc.rows || []).filter(r => r.metric === AVE_SELECTED_CLASS_METRIC)
        .sort((a, b) => String(a.classCode || '').localeCompare(String(b.classCode || ''), 'zh', { numeric: true }));
      const labels = rows.map(r => r.className || getClassName(r.classCode));
      // 比率类指标偏差以 pp（百分点）展示，不再除以 DISPLAY_UNIT 转万元
      const sample = rows[0] || {};
      const isRatio = sample.isRatio === true;
      const diffs = rows.map(r => isRatio ? r.diff : r.diff / DISPLAY_UNIT);
      // 按后端 status 统一配色：红色=不利偏差，绿色=有利偏差
      const favorableData = rows.map((r, i) => r.status === '有利' ? diffs[i] : null);
      const unfavorableData = rows.map((r, i) => r.status === '不利' ? diffs[i] : null);
      safeChart('aveClassChart', get('aveClassChart'), {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [
            {
              label: '不利偏差',
              data: unfavorableData,
              backgroundColor: C.red + 'BB',
              borderColor: C.red,
              borderWidth: 1,
              stack: 'stack1',
              barPercentage: 0.6,
            },
            {
              label: '有利偏差',
              data: favorableData,
              backgroundColor: C.green + 'BB',
              borderColor: C.green,
              borderWidth: 1,
              stack: 'stack1',
              barPercentage: 0.6,
            },
          ],
        },
        options: baseOpts({
          // 竖向柱状：X 轴=险种，Y 轴=偏差（与明细表险种顺序一致）
          scales: {
            x: { grid: { display: false }, ticks: { font: { size: 11 }, autoSkip: false, maxRotation: 60, minRotation: 0 } },
            y: { grid: { color: '#F0F0F0' }, ticks: { font: { size: 11 }, callback: v => isRatio ? v.toFixed(2) + '%' : fmtU(v) } },
          },
          plugins: {
            legend: {
              display: true,
              position: 'bottom',
              labels: {
                usePointStyle: true,
                pointStyle: 'rectRounded',
                font: { size: 12 },
                padding: 16,
              },
            },
            tooltip: {
              callbacks: {
                label: ctx => {
                  const raw = ctx.raw;
                  if (raw === null) return '';
                  if (isRatio) return `${ctx.dataset.label}: ${raw >= 0 ? '+' : ''}${raw.toFixed(2)}pp`;
                  return `${ctx.dataset.label}: ${raw >= 0 ? '+' : ''}${fmtU(raw)} ${unitLabel()}`;
                },
              },
            },
          },
        }),
      });
    }
  }

  // ===== 多情景对比图表 =====
  if (page === 'scenario-compare') {
    if (!CALC_RESULT || !CALC_RESULT.success) return;
    const baseScenario = findBaseScenario();
    const baseResult = getScenarioResult(baseScenario);
    const fs = baseResult?.financialStatementsV2Merged || baseResult?.financialStatementsV2;
    if (!fs) return;
    const dates = fs.dates;
    const yearMap = new Map();
    const monthList = [];
    dates.forEach((d, i) => {
      if (!d || i === 0) return;
      const year = d.split('-')[0];
      if (!yearMap.has(year)) yearMap.set(year, []);
      yearMap.get(year).push(i);
      monthList.push({ idx: i, label: d.substring(0, 7) });
    });
    const years = [...yearMap.keys()];
    const yearIndices = [...yearMap.values()];
    const isMonthly = SC_COMPARE_MODE === 'monthly';

    const compareScenarioNames = getScenarioCompareList();

    const periodLabels = isMonthly ? monthList.map(m => m.label) : years.map(y => y + 'F');
    const periodValues = isMonthly ? monthList.map(m => m.label) : years;
    const selectedIdx = periodValues.indexOf(SC_COMPARE_PERIOD);
    const selPIdx = selectedIdx >= 0 ? selectedIdx : 0;
    const selectedLabel = periodLabels[selPIdx] || '';

    function extractChartData(result) {
      if (!result) return null;
      const fs2 = result.financialStatementsV2Merged || result.financialStatementsV2;
      if (!fs2) return null;
      const mtd = isMonthly ? (fs2.ytd || fs2.mtd) : fs2.mtd;
      function getVal(item) {
        const r = mtd.income_statement.find(x => x.item === item);
        return r ? r.values : [];
      }
      if (isMonthly) {
        return {
          uw: monthList.map(m => getVal('承保利润')[m.idx] || 0),
          np: monthList.map(m => getVal('五、净利润（净亏损以"-"号填列）')[m.idx] || 0),
          insRev: monthList.map(m => getVal('保险服务收入')[m.idx] || 0),
          insSvcExp: monthList.map(m => getVal('保险服务费用')[m.idx] || 0),
          ceding: monthList.map(m => getVal('分出保费的分摊')[m.idx] || 0),
          admin: monthList.map(m => getVal('业务及管理费')[m.idx] || 0),
          tax: monthList.map(m => getVal('税金及附加')[m.idx] || 0),
          comm: monthList.map(m => getVal('手续费及佣金支出')[m.idx] || 0),
        };
      } else {
        return {
          uw: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getVal('承保利润')[i] || 0), 0)),
          np: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getVal('五、净利润（净亏损以"-"号填列）')[i] || 0), 0)),
          insRev: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getVal('保险服务收入')[i] || 0), 0)),
          insSvcExp: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getVal('保险服务费用')[i] || 0), 0)),
          ceding: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getVal('分出保费的分摊')[i] || 0), 0)),
          admin: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getVal('业务及管理费')[i] || 0), 0)),
          tax: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getVal('税金及附加')[i] || 0), 0)),
          comm: years.map((y, idx) => yearIndices[idx].reduce((s, i) => s + (getVal('手续费及佣金支出')[i] || 0), 0)),
        };
      }
    }

    const chartColors = CCI_COLORS;
    const scenarioData = compareScenarioNames.map((s, idx) => {
      const result = s === baseScenario ? baseResult : (CALC_RESULTS_MAP[s] || null);
      const d = result ? extractChartData(result) : null;
      const fs2 = result?.financialStatementsV2Merged || result?.financialStatementsV2;
      // 经营三率统一按 YTD 口径计算
      const targetIdx = isMonthly ? monthList[selPIdx].idx : yearIndices[selPIdx][yearIndices[selPIdx].length - 1];
      const paaMtdDetail = result?.paaMtdDetail;
      const insRevYtd = getFsYtdSeries(fs2, '保险服务收入', 'income_statement');
      const uwProfitYtd = getFsYtdSeries(fs2, '承保利润', 'income_statement');
      const insSvcExpYtd = paaMtdDetail
        ? getPaaMtdExpenseYtdSeries(paaMtdDetail, dates)
        : getFsYtdSeries(fs2, '保险服务费用', 'income_statement');
      const ratios = computeOperatingRatios(insRevYtd, uwProfitYtd, insSvcExpYtd, targetIdx);
      return {
        name: s,
        uw: d ? (d.uw[selPIdx] || 0) : 0,
        np: d ? (d.np[selPIdx] || 0) : 0,
        insRev: d ? (d.insRev[selPIdx] || 0) : 0,
        lossRatio: ratios.loss,
        expenseRatio: ratios.expense,
        combinedRatio: ratios.combined,
        color: chartColors[idx % chartColors.length],
      };
    }).filter(s => s.name === baseScenario || s.uw !== 0 || s.np !== 0);

    // 多情景比对柱状图统一固定柱宽（约为原截图的一半）并启用数字标签
    const scBarThickness = 36;
    if (get('scChart2')) {
      safeChart('scChart2', get('scChart2'), {
        type: 'bar',
        data: {
          labels: scenarioData.map(s => s.name),
          datasets: [{
            label: '承保利润',
            data: scenarioData.map(s => s.uw / DISPLAY_UNIT),
            backgroundColor: scenarioData.map(s => s.color),
            barThickness: scBarThickness,
          }]
        },
        options: baseOpts({ scales: { ...scaleOpts, y: { ...scaleOpts.y, ..._tightYRange(scenarioData.map(s => s.uw / DISPLAY_UNIT)) } }, plugins: { ...baseOpts().plugins, title: { display: true, text: selectedLabel } } })
      });
    }
    if (get('scChart3')) {
      safeChart('scChart3', get('scChart3'), {
        type: 'bar',
        data: {
          labels: scenarioData.map(s => s.name),
          datasets: [{
            label: '净利润',
            data: scenarioData.map(s => s.np / DISPLAY_UNIT),
            backgroundColor: scenarioData.map(s => s.color),
            barThickness: scBarThickness,
          }]
        },
        options: baseOpts({ scales: { ...scaleOpts, y: { ...scaleOpts.y, ..._tightYRange(scenarioData.map(s => s.np / DISPLAY_UNIT)) } }, plugins: { ...baseOpts().plugins, title: { display: true, text: selectedLabel } } })
      });
    }
    if (get('scChart4')) {
      safeChart('scChart4', get('scChart4'), {
        type: 'bar',
        data: {
          labels: scenarioData.map(s => s.name),
          datasets: [{
            label: '保险服务收入',
            data: scenarioData.map(s => s.insRev / DISPLAY_UNIT),
            backgroundColor: scenarioData.map(s => s.color),
            barThickness: scBarThickness,
          }]
        },
        options: baseOpts({ scales: { ...scaleOpts, y: { ...scaleOpts.y, ..._tightYRange(scenarioData.map(s => s.insRev / DISPLAY_UNIT)) } }, plugins: { ...baseOpts().plugins, title: { display: true, text: selectedLabel } } })
      });
    }
    if (get('scChart5')) {
      safeChart('scChart5', get('scChart5'), {
        type: 'bar',
        data: {
          labels: scenarioData.map(s => s.name),
          datasets: [
            { label: '综合赔付率', data: scenarioData.map(s => s.lossRatio), _pct: true, backgroundColor: CCI_COLORS[2], stack: 'ratio', barThickness: scBarThickness },
            { label: '综合费用率', data: scenarioData.map(s => s.expenseRatio), _pct: true, backgroundColor: CCI_COLORS[1], stack: 'ratio', barThickness: scBarThickness },
            { label: '综合成本率', data: scenarioData.map(s => s.combinedRatio), _pct: true, type: 'line', borderColor: CCI_COLORS[0], backgroundColor: CCI_COLORS[0], tension: 0.3, borderWidth: 2, pointRadius: 4, pointBackgroundColor: CCI_COLORS[0], pointBorderColor: CCI_COLORS[0], fill: false, order: 1 },
          ]
        },
        options: baseOpts({
          scales: {
            x: { stacked: true, grid: { display: false } },
            y: { stacked: true, max: 140, grid: { color: '#F0F0F0' }, ticks: { callback: v => v.toFixed(1) + '%' } }
          },
          plugins: { ...baseOpts().plugins, title: { display: true, text: '综合成本率构成（综合赔付率 + 综合费用率 = 综合成本率）' } }
        })
      });
    }
  }
}

// ===== 新旧预测比对模块 =====
let oldNewBridgeState = {
  loaded: false,
  loading: false,
  data: null,
  error: '',
  selectedScenario: '情景0',
  selectedPeriod: '',
  expandedGroups: {},
};

async function loadOldNewBridgeData() {
  // 避免并发请求导致页面反复重绘/闪烁
  if (oldNewBridgeState.loading) return;
  oldNewBridgeState = { ...oldNewBridgeState, loading: true };
  // 已渲染过页面时，仅显示表格区域 loading 遮罩，避免整个页面替换造成闪烁
  const tbody = document.querySelector('.old-new-compare-table tbody');
  if (tbody && oldNewBridgeState.loaded) {
    tbody.classList.add('old-new-loading');
  }
  try {
    const params = [];
    if (oldNewBridgeState.selectedScenario) params.push('scenario=' + encodeURIComponent(oldNewBridgeState.selectedScenario));
    if (oldNewBridgeState.selectedPeriod) params.push('period=' + encodeURIComponent(oldNewBridgeState.selectedPeriod));
    const q = params.length ? ('?' + params.join('&')) : '';
    const resp = await fetch('/api/bridge/comparison' + q);
    const d = await resp.json();
    if (!d.success) {
      oldNewBridgeState = { ...oldNewBridgeState, loaded: true, loading: false, data: null, error: d.error || '加载失败' };
    } else {
      oldNewBridgeState = { ...oldNewBridgeState, loaded: true, loading: false, data: d, error: '' };
    }
  } catch (e) {
    oldNewBridgeState = { ...oldNewBridgeState, loaded: true, loading: false, data: null, error: e.message };
  }
  // 仅当用户仍停留在「新旧预测比对」页面时才重渲染，避免异步返回后覆盖已切换的其他页面
  if (CURRENT_PAGE === 'old-new-bridge') {
    renderPage('old-new-bridge');
  }
}

function setOldNewBridgeScenario(val) {
  oldNewBridgeState.selectedScenario = val;
  loadOldNewBridgeData();
}

function setOldNewBridgePeriod(val) {
  oldNewBridgeState.selectedPeriod = val;
  loadOldNewBridgeData();
}

function toggleOldNewGroup(groupIdx) {
  oldNewBridgeState.expandedGroups[groupIdx] = !oldNewBridgeState.expandedGroups[groupIdx];
  renderPage('old-new-bridge');
}

function bridgeKpiCard(label, valueHtml, sub, color) {
  return `<div class="kpi-card ${color}"><div class="kpi-label">${label}</div><div class="kpi-value">${valueHtml}</div><div class="kpi-sub">${sub}</div></div>`;
}

// ===== 自定义下拉菜单（portal 方式，规避 webview 中原生 select 弹层被 overflow 祖先裁剪的问题）=====
window.__cddOptions = {};
let __cddDocBound = false;

function renderCustomSelect(id, options, selectedValue, handlerKey) {
  window.__cddOptions[id] = { options: options || [], handlerKey: handlerKey, selectedValue: selectedValue };
  const current = (options || []).find(o => String(o.value) === String(selectedValue));
  const label = current ? current.label : ((options && options[0]) ? options[0].label : '-');
  return `<div class="cdd" id="${id}">
    <button type="button" class="cdd-btn" onclick="toggleCdd('${id}', event)">
      <span class="cdd-label">${label}</span><span class="cdd-arrow">▾</span>
    </button>
  </div>`;
}

function toggleCdd(id, e) {
  e.stopPropagation();
  if (!__cddDocBound) {
    document.addEventListener('click', function (ev) {
      if (!(ev.target.closest && ev.target.closest('.cdd')) && !(ev.target.closest && ev.target.closest('.cdd-portal'))) {
        closeAllCdd();
      }
    });
    __cddDocBound = true;
  }
  closeAllCdd();
  const el = document.getElementById(id);
  if (!el) return;
  const cfg = window.__cddOptions[id];
  if (!cfg) return;
  const btn = el.querySelector('.cdd-btn');
  const rect = btn.getBoundingClientRect();
  const portal = document.createElement('div');
  portal.className = 'cdd-portal';
  portal.id = 'cdd-portal-' + id;
  portal.setAttribute('style',
    `position:fixed;left:${rect.left}px;top:${rect.bottom + 4}px;min-width:${Math.max(rect.width, 120)}px;` +
    `z-index:99999;background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);` +
    `box-shadow:0 6px 24px rgba(0,0,0,.18);max-height:320px;overflow:auto;padding:4px`);
  portal.innerHTML = (cfg.options || []).map(o => {
    const active = String(o.value) === String(cfg.selectedValue) ? ' active' : '';
    return `<div class="cdd-opt${active}" data-value="${o.value}">${o.label}</div>`;
  }).join('');
  document.body.appendChild(portal);
  portal.querySelectorAll('.cdd-opt').forEach(opt => {
    const onSelect = function () {
      const value = opt.getAttribute('data-value');
      closeAllCdd();
      if (cfg.handlerKey === 'oldNewScenario') setOldNewBridgeScenario(value);
      else if (cfg.handlerKey === 'oldNewPeriod') setOldNewBridgePeriod(value);
      else if (cfg.handlerKey === 'displayUnit') setDisplayUnit(value);
      else if (cfg.handlerKey === 'scComparePeriod') setScComparePeriod(value);
      else if (cfg.handlerKey === 'avePeriod') setAvePeriod(value);
      else if (cfg.handlerKey === 'aveScenario') setAveScenario(value);
      else if (cfg.handlerKey === 'forecastPeriods') setForecastPeriods(value);
      else if (cfg.handlerKey === 'excelForecastPeriods') setExcelForecastPeriods(value);
    };
    opt.addEventListener('click', onSelect);
    opt.addEventListener('touchend', function (tev) { tev.preventDefault(); onSelect(); });
  });
  // 若下方空间不足，改为向上展开
  const pr = portal.getBoundingClientRect();
  if (pr.bottom > window.innerHeight - 8) {
    portal.style.top = Math.max(8, rect.top - pr.height - 4) + 'px';
  }
}

function closeAllCdd() {
  document.querySelectorAll('.cdd-portal').forEach(p => p.remove());
}

// 计算流程页预测期数自定义下拉回调
function setForecastPeriods(value) {
  const id = 'forecast-periods-cdd';
  const cfg = window.__cddOptions[id];
  if (cfg) cfg.selectedValue = value;
  const cdd = document.getElementById(id);
  if (cdd) {
    const opt = (cfg ? cfg.options : []).find(o => String(o.value) === String(value));
    const label = opt ? opt.label : (value + '个月');
    const labelEl = cdd.querySelector('.cdd-label');
    if (labelEl) labelEl.textContent = label;
  }
  const hidden = document.getElementById('forecast-periods-select');
  if (hidden) hidden.value = value;
}

// Excel上传接口页预测期数自定义下拉回调
function setExcelForecastPeriods(value) {
  const id = 'excel-forecast-periods-cdd';
  const cfg = window.__cddOptions[id];
  if (cfg) cfg.selectedValue = value;
  const cdd = document.getElementById(id);
  if (cdd) {
    const opt = (cfg ? cfg.options : []).find(o => String(o.value) === String(value));
    const label = opt ? opt.label : (value + '个月');
    const labelEl = cdd.querySelector('.cdd-label');
    if (labelEl) labelEl.textContent = label;
  }
  const hidden = document.getElementById('excelForecastPeriods');
  if (hidden) hidden.value = value;
  if (typeof excelUploadState !== 'undefined') {
    excelUploadState.forecastPeriods = parseInt(value, 10) || 12;
  }
}

// 新旧预测比对控制条：包裹在 card 内并显式抬升层叠顺序，确保场景/时点/单位选择器可点击
function oldNewControlsCard(scenarioSelector, periodSelector, withUnit) {
  const unit = withUnit ? unitSelectorHTML() : '';
  return `<div class="card old-new-controls-card" style="margin-bottom:12px;position:relative;z-index:20;overflow:visible">
    <div class="card-body" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;position:relative;z-index:20">
      ${scenarioSelector}${periodSelector}${unit}
    </div>
  </div>`;
}

// 旧准则一级科目显示名称映射（左侧桥接表）
const _OLD_STANDARD_SUBJECT_MAP = {
  '一、营业收入': '一、保险服务收入',
  '一、保险合同收入': '一、保险服务收入',
  '二、保险合同支出': '二、保险服务费用',
  '三、分出保费': '三、分出保费的分摊',
  '三、分出保': '三、分出保费的分摊',
};
function displayOldStandardSubject(s) {
  return _OLD_STANDARD_SUBJECT_MAP[s] || s || '-';
}

function renderOldNewBridgePage() {
  const state = oldNewBridgeState;
  const data = state.data;
  const hasCalc = CALC_RESULT && CALC_RESULT.success;

  if (!hasCalc) {
    return `
<div class="page active old-new-page">
  <div class="page-header"><h2>新旧预测比对</h2><p>IFRS4 旧准则 vs IFRS17 新准则预测结果对比</p></div>
  <div class="alert alert-warning">尚未执行预测计算，请先到「计算流程」执行计算。</div>
</div>`;
  }

  const scenarios = getComputedScenarios();
  const scenarioOpts = scenarios.map(s => ({ value: s, label: s }));
  const scenarioSelector = `<div style="display:inline-flex;align-items:center;gap:6px">
    <span style="font-size:13px;color:var(--text-sec)">场景:</span>
    ${renderCustomSelect('oldNewScenarioSel', scenarioOpts, state.selectedScenario, 'oldNewScenario')}
  </div>`;

  const periodOpts = (data?.dates || []).map((d, i) => i > 0 ? { value: String(i), label: d } : null).filter(Boolean);
  // 默认选中第一个预测时点，不再提供「评估时点」选项
  if (periodOpts.length > 0 && !state.selectedPeriod) {
    state.selectedPeriod = periodOpts[0].value;
    setTimeout(() => loadOldNewBridgeData(), 0);
    return `
<div class="page active old-new-page">
  <div class="page-header"><h2>新旧预测比对</h2><p>IFRS4 旧准则 vs IFRS17 新准则预测结果对比</p></div>
  <div class="alert alert-info">正在加载第一个预测时点数据...</div>
</div>`;
  }
  const periodSelector = data?.dates
    ? `<div style="display:inline-flex;align-items:center;gap:6px">
        <span style="font-size:13px;color:var(--text-sec)">预测时点:</span>
        ${renderCustomSelect('oldNewPeriodSel', periodOpts, state.selectedPeriod || '', 'oldNewPeriod')}
      </div>`
    : '';

  const hasError = state.loaded && state.error;
  const hasData = state.loaded && !state.error && data;
  const loadingClass = state.loading ? ' old-new-loading' : '';

  // KPI 卡片：无数据时显示占位符（-），避免加载前后卡片区域高度跳变造成闪烁
  const ns = hasData ? (data.newStandardKpis || {}) : {};
  const os = hasData ? (data.oldStandardKpis || {}) : {};
  const osSource = hasData ? (data.oldStandardSource || 'fitted') : 'fitted';
  const osSourceLabel = osSource === 'upload' ? '上传旧准则数字' : '桥接表(拟合)';
  const nsSource = hasData ? (data.newStandardSource || 'system') : 'system';
  const nsSourceLabel = nsSource === 'upload' ? '上传新准则数字' : '系统输出 YTD';
  const nsCards = `
    ${bridgeKpiCard('保险服务收入', fmtU(ns.insRev), nsSourceLabel, 'blue')}
    ${bridgeKpiCard('承保利润', fmtU(ns.uwProfit), nsSourceLabel, 'green')}
    ${bridgeKpiCard('净利润', fmtU(ns.netProfit), nsSourceLabel, 'red')}
    ${bridgeKpiCard('综合成本率', (ns.combinedRatio != null ? ns.combinedRatio.toFixed(1) + '%' : '-'), nsSourceLabel, 'orange')}
  `;
  const osCards = `
    ${bridgeKpiCard('保险业务收入', fmtU(os.insRev), osSourceLabel, 'blue')}
    ${bridgeKpiCard('承保利润', fmtU(os.uwProfit), osSourceLabel, 'green')}
    ${bridgeKpiCard('净利润', fmtU(os.netProfit), osSourceLabel, 'red')}
    ${bridgeKpiCard('综合成本率', (os.combinedRatio != null ? os.combinedRatio.toFixed(1) + '%' : '-'), osSourceLabel, 'orange')}
  `;

  const rows = hasData ? (data.rows || []) : [];
  let tbodyHtml = '';
  let groupIdx = -1;
  let groupExpanded = false;
  rows.forEach((r, idx) => {
    const diffSign = r.diff >= 0 ? '+' : '';
    const diffColor = r.diff >= 0 ? 'var(--success)' : 'var(--error)';
    if (r.isGroup) {
      groupIdx++;
      if (oldNewBridgeState.expandedGroups[groupIdx] === undefined) {
        oldNewBridgeState.expandedGroups[groupIdx] = (groupIdx === 0);
      }
      groupExpanded = oldNewBridgeState.expandedGroups[groupIdx];
      const expandIcon = groupExpanded ? '▼' : '▶';
      tbodyHtml += `
      <tr class="old-new-group" role="button" tabindex="0" aria-expanded="${groupExpanded}" onclick="toggleOldNewGroup(${groupIdx})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleOldNewGroup(${groupIdx});}" style="cursor:pointer;background:var(--primary-bg);font-weight:600">
        <td style="min-width:200px"><span class="old-new-toggle" aria-hidden="true">${expandIcon}</span> ${displayOldStandardSubject(r.oldSubject)}</td>
        <td class="num">${fmtU(r.oldValue)}</td>
        <td style="min-width:200px">${r.newSubject || '-'}</td>
        <td class="num">${fmtU(r.newValue)}</td>
        <td class="num" style="color:${diffColor}">${diffSign}${fmtU(r.diff)}</td>
      </tr>`;
    } else {
      const detailStyle = groupExpanded ? '' : 'style="display:none"';
      tbodyHtml += `
      <tr class="old-new-detail" data-group="${groupIdx}" ${detailStyle}>
        <td style="min-width:200px;padding-left:32px">${displayOldStandardSubject(r.oldSubject)}</td>
        <td class="num">${fmtU(r.oldValue)}</td>
        <td style="min-width:200px">${r.newSubject || '-'}</td>
        <td class="num">${fmtU(r.newValue)}</td>
        <td class="num" style="color:${diffColor}">${diffSign}${fmtU(r.diff)}</td>
      </tr>`;
    }
  });

  const errorBanner = hasError ? `<div class="alert alert-warning" style="margin-top:14px">${state.error}</div>` : '';

  return `
<div class="page active old-new-page">
  <div class="page-header"><h2>新旧预测比对</h2><p>IFRS4 旧准则 vs IFRS17 新准则预测结果对比 — 预测时点：${hasData ? (data.period || '-') : '-'}</p></div>
  ${oldNewControlsCard(scenarioSelector, periodSelector, true)}

  <div style="margin-bottom:8px;font-size:13px;font-weight:600;color:var(--text-sec)">新准则（IFRS17）指标</div>
  <div class="kpi-grid">${nsCards}</div>
  <div style="margin:14px 0 8px;font-size:13px;font-weight:600;color:var(--text-sec)">旧准则（IFRS4）指标</div>
  <div class="kpi-grid">${osCards}</div>

  ${errorBanner}

  <div class="card old-new-table-card" style="margin-top:14px;overflow:visible">
    <div class="card-header">
      <h3>新旧准则预测结果对比</h3>
      <span class="badge">${rows.length}项</span>
    </div>
    <div class="card-body" style="overflow:visible">
      <div class="table-wrapper old-new-table-wrapper" style="max-height:520px;overflow:auto">
        <table class="data-table old-new-compare-table${loadingClass}" style="font-size:13px">
          <thead>
            <tr>
              <th style="min-width:200px">旧准则到新准则桥接</th>
              <th>旧准则预测</th>
              <th style="min-width:200px">新准则科目</th>
              <th>新准则预测</th>
              <th>差异(新−旧)</th>
            </tr>
          </thead>
          <tbody>
            ${tbodyHtml || '<tr class="old-new-empty"><td colspan="5" style="text-align:center;color:var(--text-sec);padding:32px">正在加载对比数据...</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>`;
}

// ===== 预实对比模块 =====
let actualVsExpectedState = {
  loaded: false,
  fileName: '',
  uploadTime: '',
  comparison: null,
};
let AVE_SELECTED_TAB = 'overview'; // overview | class
let AVE_SELECTED_CLASS_METRIC = '保险服务收入'; // 当前选中指标对应的数据 metric key（用于取数）
let AVE_SELECTED_CLASS_METRIC_KEY = '保险服务收入'; // 当前选中指标展示名（下钻树的叶子 key）
let AVE_DRILL_EXPANDED = { '承保利润': false, '综合成本率': false, '保险服务收入': false, '保险服务费用': false }; // 下钻树展开状态（默认全部收起）
let AVE_SELECTED_PERIOD = '';      // 预实分析对比的预测时点，'' 表示使用上传文件的评估时点
let AVE_SELECTED_SCENARIO = '';    // 预实分析对比的预期值来源情景

// 数据及逻辑归集页状态
let DLC_ACTIVE_TAB = 'logic';      // 'logic' | 'collection'
let DLC_LOGIC_TREE = null;         // 计算逻辑概要树（后端缓存）
let DLC_LOGIC_EXPANDED = {};       // 节点展开状态 {nodeId: true}
let DLC_LOGIC_SELECTED = null;     // 当前选中的组成部分节点 ID
let DLC_COLLECTION_EXPANDED = {};  // 数据归集节点展开状态

// 分险种预实「指标选择」下钻树结构
// leaf.metric = 实际取数用的 metric key（需存在于 classComparison.rows 的 metric 字段）
// 签单保费/生效保费目前系统仅产出合并的「保险业务收入」，暂以该指标作为取数来源
const CLASS_METRIC_TREE = [
  { key: '承保利润', metric: '承保利润', children: [
    { key: '保险服务收入', metric: '保险服务收入', children: [
      { key: '签单保费', metric: '保险业务收入' },
      { key: '生效保费', metric: '保险业务收入' },
    ]},
    { key: '保险服务费用', metric: '保险服务费用', children: [
      { key: '费用成本', metric: '费用成本' },
      { key: '摊销获取费用', metric: '摊销获取费用' },
      { key: '维持费用', metric: '维持费用' },
      { key: '亏损合同损益', metric: '亏损合同损益' },
    ]},
    { key: '再保成本', metric: '再保成本' },
  ]},
  { key: '综合成本率', metric: '综合成本率', children: [
    { key: '预期赔付率', metric: '预期赔付率' },
    { key: '预期维持费用率', metric: '预期维持费用率' },
    { key: '预期获取费用率', metric: '预期获取费用率' },
  ]},
];

// 数据归集 - 输入假设归类树（对应截图结构，leaf.sheet 为跳转工作表名）
// 默认全部收缩，由用户手动逐层展开
const DATA_COLLECTION_TREE = [
  {
    key: '现有业务',
    children: [
      {
        key: '基础数据',
        children: [
          { key: '期初余额数据', sheet: '系统期初余额表' },
          { key: '期初财务报表', sheet: '财务报表实际数' },
        ]
      },
      {
        key: '假设',
        children: [
          { key: '保费现金流模式', sheet: '保费现金流模式_现有业务' },
          { key: '未到期赚取模式', sheet: '未到期赚取模式_现有业务' },
          { key: '预期摊回比例', sheet: '预期摊回比例' },
        ]
      },
      {
        key: '利率曲线',
        children: [
          { key: '初始确认利率曲线', sheet: '初始确认利率曲线' },
          { key: '即期利率曲线', sheet: '即期利率曲线' },
        ]
      },
    ],
    note: '均来源于系统数据',
  },
  {
    key: '新业务',
    children: [
      {
        key: '保费数据',
        children: [
          {
            key: '与旧准则一致',
            children: [
              { key: '应收保费减值', sheet: '新增应收保费减值' },
              { key: '生效保费', sheet: '生效保费_新业务' },
            ]
          },
          {
            key: '新准则需求',
            children: [
              { key: '签单保费', sheet: '签单保费_新业务' },
            ]
          },
        ]
      },
      {
        key: '费用数据',
        children: [
          {
            key: '与旧准则保持一致',
            children: [
              { key: '手续及佣金、业管、税金及附加', sheet: '费用输入项' },
            ]
          },
          {
            key: '新准则需求',
            children: [
              { key: '获取费用/业管及税金附加比例、维持费用/业管及税金附加比例', sheet: '费用输入项' },
              { key: '跟单获取费用比例', sheet: '跟单获取费用或净额结算比例_新业务' },
              { key: '非跟单获取费用比例', sheet: '非跟单获取费用比例_新业务' },
            ]
          },
        ]
      },
      {
        key: '假设',
        children: [
          {
            key: '与旧准则保持一致',
            children: [
              { key: '预期摊回比例', sheet: '预期摊回比例_新业务' },
              { key: '预期赔付率', sheet: '预期赔付率' },
              { key: '风险调整比例', sheet: '风险调整比例' },
              { key: '预期间接理赔费用', sheet: '未到期间接理赔费用率' },
              { key: '未到期赚取模式', sheet: '未到期赚取模式_新业务' },
            ]
          },
          {
            key: '新准则需求',
            children: [
              { key: '保费现金流模式', sheet: '保费现金流模式_新业务' },
              { key: '预期维持费用率', sheet: '维持费用率' },
              { key: '赔付模式', sheet: '未到期赔付模式' },
              { key: '投资成分比例', sheet: '投资成分比例' },
            ]
          },
        ]
      },
    ],
    note: '来源于历史比例',
  },
];

// 旧准则（IFRS4）数字上传状态
let oldStandardUploadState = {
  loaded: false,
  fileName: '',
  uploadTime: '',
  kpis: null,
  newKpis: null,
};

// 预实分析上传页面（并入数据输入板块）
function renderActualUploadPage() {
  if (isViewer()) {
    return `<div class="page active"><div class="page-header"><h2>预实分析上传</h2></div>
      <div class="alert alert-warning" style="margin:24px 0;">您当前为查看权限，无法上传数据。预实分析实际数据由管理员上传，您可在「结果展示面板 / 预实分析」查看对比结果。</div></div>`;
  }
  const state = actualVsExpectedState;
  let html = `
<div class="page active">
  <div class="page-header">
    <h2>预实分析上传</h2>
    <p>上传实际财务报表，用于预实分析（预测 vs 实际对比）— 已并入数据输入板块</p>
  </div>

  <div class="alert alert-info">
    <strong>接口说明：</strong>此接口用于上传预实分析所需的“实际财务报表”。
    文件发送到 Python 后端解析，模板需含“公司合计实际数”工作表（整体达成率）和“精算险类实际数”工作表（分险种预实对比）。
    <br><strong>上传后：</strong>前往「结果展示面板 / 预实分析」查看达成率看板与分险种预实对比。
  </div>

  <div class="card" style="margin-bottom:16px">
    <div class="card-header">
      <h3>上传实际财务报表</h3>
      ${state.loaded ? `<span class="status-tag done">已上传</span>` : `<span class="status-tag pending">未上传</span>`}
    </div>
    <div class="card-body">
      <div class="upload-area" id="actualUploadArea">
        <div class="upload-icon">📈</div>
        <div class="upload-text">点击或拖拽实际财务报表到此处上传</div>
        <div class="upload-hint">支持 .xlsx 格式 | 需含“公司合计实际数”和“精算险类实际数”工作表</div>
        <input type="file" id="actualFileInput" accept=".xlsx,.xls" style="display:none">
      </div>
      ${state.loaded ? `
      <div class="upload-info">
        <div class="info-row"><span class="label">文件名</span><span class="value">${state.fileName}</span></div>
        <div class="info-row"><span class="label">上传时间</span><span class="value">${state.uploadTime}</span></div>
        <div class="info-row"><span class="label">解析状态</span><span class="value"><span class="text-success">解析成功 ✓</span></span></div>
      </div>
      <div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="renderPage('actual-vs-expected')">查看预实分析结果 →</button>
        <button class="btn btn-outline" onclick="renderPage('actual-upload')">重新上传</button>
      </div>` : ''}
    </div>
  </div>

  <div class="card" style="margin-bottom:16px">
    <div class="card-header">
      <h3>上传旧准则数字</h3>
      ${oldStandardUploadState.loaded ? `<span class="status-tag done">已上传</span>` : `<span class="status-tag pending">未上传</span>`}
    </div>
    <div class="card-body">
      <div class="alert alert-info" style="margin-bottom:16px">
        <strong>接口说明：</strong>此接口用于上传新旧准则对比中所需的“旧准则（IFRS4）数字”与“新准则（IFRS17）预测数字”。
        文件发送到 Python 后端解析，模板需含“旧准则数字”工作表，支持三种格式：
        ① 两列 KPI：<code>指标</code>、<code>数值</code>（同义词：保险业务收入/保险服务收入、承保利润、净利润、综合成本率）；
        ② 旧准则桥接：<code>旧准则科目</code>、<code>旧准则金额</code>；
        ③ 双向桥接（推荐）：<code>旧准则科目</code>、<code>旧准则金额</code>、<code>新准则科目</code>、<code>新准则预测数字</code>。
        <br><strong>上传后：</strong>前往「结果展示面板 / 新旧预测比对」查看桥接对比。旧准则预测优先取上传旧准则数字，新准则预测优先取上传新准则数字（未上传时分别使用系统拟合值/系统输出）。
        <br><span style="color:var(--text-sec)">上传格式示例请参考：<code>验证文件/旧准则数字上传示例.xlsx</code></span>
      </div>
      <div class="upload-area" id="oldStandardUploadArea">
        <div class="upload-icon">📊</div>
        <div class="upload-text">点击或拖拽旧准则数字 Excel 到此处上传</div>
        <div class="upload-hint">支持 .xlsx 格式 | 推荐四列：旧准则科目 / 旧准则金额 / 新准则科目 / 新准则预测数字</div>
        <input type="file" id="oldStandardFileInput" accept=".xlsx,.xls" style="display:none">
      </div>
      ${oldStandardUploadState.loaded ? `
      <div class="upload-info">
        <div class="info-row"><span class="label">文件名</span><span class="value">${oldStandardUploadState.fileName}</span></div>
        <div class="info-row"><span class="label">上传时间</span><span class="value">${oldStandardUploadState.uploadTime}</span></div>
        <div class="info-row"><span class="label">解析状态</span><span class="value"><span class="text-success">解析成功 ✓</span></span></div>
        ${oldStandardUploadState.kpis ? `<div class="info-row"><span class="label">保险业务收入</span><span class="value">${fmtU(oldStandardUploadState.kpis.insRev)}</span></div>
        <div class="info-row"><span class="label">承保利润</span><span class="value">${fmtU(oldStandardUploadState.kpis.uwProfit)}</span></div>
        <div class="info-row"><span class="label">净利润</span><span class="value">${fmtU(oldStandardUploadState.kpis.netProfit)}</span></div>
        <div class="info-row"><span class="label">综合成本率</span><span class="value">${oldStandardUploadState.kpis.combinedRatio != null ? oldStandardUploadState.kpis.combinedRatio.toFixed(1) + '%' : '-'}</span></div>` : ''}
        ${oldStandardUploadState.newKpis ? `<div class="info-row"><span class="label" style="color:var(--primary)">新准则·保险服务收入</span><span class="value">${fmtU(oldStandardUploadState.newKpis.insRev)}</span></div>
        <div class="info-row"><span class="label" style="color:var(--primary)">新准则·承保利润</span><span class="value">${fmtU(oldStandardUploadState.newKpis.uwProfit)}</span></div>
        <div class="info-row"><span class="label" style="color:var(--primary)">新准则·净利润</span><span class="value">${fmtU(oldStandardUploadState.newKpis.netProfit)}</span></div>
        <div class="info-row"><span class="label" style="color:var(--primary)">新准则·综合成本率</span><span class="value">${oldStandardUploadState.newKpis.combinedRatio != null ? oldStandardUploadState.newKpis.combinedRatio.toFixed(1) + '%' : '-'}</span></div>` : ''}
      </div>
      <div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="renderPage('old-new-bridge')">查看新旧准则对比 →</button>
        <button class="btn btn-outline" onclick="renderPage('actual-upload')">重新上传</button>
      </div>` : ''}
    </div>
  </div>
</div>`;
  return html;
}

function initActualUploadEvents() {
  const uploadArea = document.getElementById('actualUploadArea');
  const fileInput = document.getElementById('actualFileInput');
  if (!uploadArea || !fileInput) return;

  uploadArea.addEventListener('click', () => fileInput.click());
  uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
  uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
  uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) handleActualUpload(e.dataTransfer.files[0], 'actual-upload');
  });
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleActualUpload(e.target.files[0], 'actual-upload');
  });
}

function renderActualVsExpectedPage() {
  const state = actualVsExpectedState;
  const hasCalc = CALC_RESULT && CALC_RESULT.success;
  const classComparison = state.comparison?.classComparison;

  if (!state.loaded) {
    return `
<div class="page active">
  <div class="page-header"><h2>预实分析</h2><p>上传实际财务报表，对比预测结果与实际结果</p></div>
  <div class="empty-data-message" style="padding:48px 24px;text-align:center;background:var(--card-bg);border:1px dashed var(--border);border-radius:var(--radius);margin:24px 0;">
    <div style="font-size:48px;margin-bottom:16px;">📭</div>
    <h3 style="color:var(--text);margin-bottom:8px;">尚未上传实际财务报表</h3>
    <p style="color:var(--text-sec);margin-bottom:24px;">预实分析需要实际财务报表数据（含“公司合计实际数”与“精算险类实际数”工作表）。<br>请先前往「数据输入 / 预实分析上传」上传实际数据，并执行预测计算后再查看。</p>
    <div style="display:flex;gap:12px;justify-content:center;">
      ${isViewer() ? `<p style="color:var(--text-sec)">您当前为查看权限，实际数据由管理员上传。请联系管理员上传实际财务报表并执行计算。</p>` : `<button class="btn btn-primary" onclick="renderPage('actual-upload')">前往上传实际数据</button>`}
    </div>
  </div>
</div>`;
  }

  const comparison = state.comparison;
  const availablePeriods = comparison?.availablePeriods || [];
  const selectedPeriod = comparison?.selectedPeriod || '';
  if (!AVE_SELECTED_PERIOD && selectedPeriod) {
    AVE_SELECTED_PERIOD = selectedPeriod;
  }
  // 初始化情景选择：优先使用已选，其次与当前结果面板保持一致
  if (!AVE_SELECTED_SCENARIO) {
    AVE_SELECTED_SCENARIO = DASH_SELECTED_SCENARIO || (CALC_RESULT?.selectedScenario) || '情景0';
  }
  const computedScenarios = getComputedScenarios();
  const scenarioOpts = computedScenarios.map(s => ({ value: s, label: s }));
  const scenarioSelector = computedScenarios.length > 0
    ? `<div style="display:inline-flex;align-items:center;gap:6px">
        <span style="font-size:13px;color:var(--text-sec)">预期来源情景:</span>
        ${renderCustomSelect('aveScenarioSel', scenarioOpts, AVE_SELECTED_SCENARIO, 'aveScenario')}
      </div>`
    : '';
  const avePeriodOpts = [{ value: '', label: `上传评估时点 (${comparison?.actualDate || '-'})` }].concat(
    availablePeriods.filter((d, i) => i > 0 && d).map(d => ({ value: d, label: d }))
  );
  const periodSelector = availablePeriods.length > 0
    ? `<div style="display:inline-flex;align-items:center;gap:6px">
        <span style="font-size:13px;color:var(--text-sec)">预测时点:</span>
        ${renderCustomSelect('avePeriodSel', avePeriodOpts, AVE_SELECTED_PERIOD, 'avePeriod')}
      </div>`
    : '';

  let html = `
<div class="page active">
  <div class="page-header">
    <h2>预实分析</h2>
    <p>实际财务报表 vs 预测结果 — 达成率看板 / 分险种预实</p>
  </div>
  <div style="margin-bottom:12px;display:flex;justify-content:flex-end;gap:12px;flex-wrap:wrap">${scenarioSelector}${periodSelector}${unitSelectorHTML()}</div>

  <div class="alert alert-info">
    <strong>说明：</strong>实际财务报表已通过「数据输入 / 预实分析上传」上传（文件：${state.fileName || '-'}）。
    模板含“公司合计实际数”工作表（整体达成率）和“精算险类实际数”工作表（分险种预实对比）。
  </div>`;

  if (!hasCalc) {
    html += `
    <div class="alert alert-warning">已上传实际数据，但尚未执行预测计算。请先前往「计算流程」执行计算。</div>
  </div>`;
    return html;
  }

  // Tab 切换
  const tabs = [
    { key: 'overview', label: '达成率看板' },
    { key: 'class', label: '分险种预实' },
  ];
  html += `
  <div class="tabs" style="margin-bottom:16px;display:flex;gap:8px">
    ${tabs.map(t => `
      <button class="btn ${AVE_SELECTED_TAB === t.key ? 'btn-primary' : 'btn-outline'}" onclick="setAveTab('${t.key}')">${t.label}</button>
    `).join('')}
  </div>`;

  if (AVE_SELECTED_TAB === 'overview') {
    html += renderActualOverview(state.comparison);
  } else {
    html += renderClassActualComparison(classComparison);
  }

  html += `</div>`;
  return html;
}

function setAveTab(tab) {
  AVE_SELECTED_TAB = tab;
  renderPage('actual-vs-expected');
  setTimeout(() => initActualVsExpectedEvents(), 50);
}

function setAvePeriod(period) {
  AVE_SELECTED_PERIOD = period;
  loadActualComparison().then(() => {
    renderPage('actual-vs-expected');
    setTimeout(() => initActualVsExpectedEvents(), 50);
  });
}

function setAveScenario(scenario) {
  AVE_SELECTED_SCENARIO = scenario;
  loadActualComparison().then(() => {
    renderPage('actual-vs-expected');
    setTimeout(() => initActualVsExpectedEvents(), 50);
  });
}

function renderActualOverview(comparison) {
  if (!comparison || !comparison.items) return '<div class="alert alert-warning">暂无对比数据</div>';
  const items = comparison.items;
  // 达成率看板 KPI 卡片只展示金额类核心指标（与明细表口径一致）
  const kpiItems = items.filter(i =>
    ['保险服务收入', '保险业务收入', '保险服务费用', '费用成本', '承保利润', '投资收益'].includes(i.item)
  );

  let html = `
  <div class="alert alert-info" style="margin-bottom:16px">
    <strong>对比口径：</strong>实际数（${comparison.actualDate || '-'}） vs 预测数（${comparison.selectedPeriod || '-'} / ${comparison.expectedSource || '-'}）
  </div>`;
  if (kpiItems.length > 0) {
    html += `
    <div class="kpi-grid" style="margin-bottom:16px">`;
    kpiItems.forEach(item => {
      const rateColor = item.rate >= 95 ? 'green' : (item.rate >= 80 ? 'orange' : 'red');
      const rateClass = `kpi-card ${rateColor}`;
      const diffSign = item.diff >= 0 ? '+' : '';
      const isFavorable = item.status ? item.status === '有利' : item.diff >= 0;
      const diffColor = isFavorable ? 'var(--success)' : 'var(--error)';
      html += `
      <div class="${rateClass}">
        <div class="kpi-label">${item.item} 达成率</div>
        <div class="kpi-value">${item.rate.toFixed(1)}<span class="kpi-unit">%</span></div>
        <div class="kpi-sub">预期: ${fmtU(item.expected)} ${unitLabel()} | 实际: ${fmtU(item.actual)} ${unitLabel()}</div>
        <div class="kpi-sub" style="color:${diffColor}">差异: ${diffSign}${fmtU(item.diff)} ${unitLabel()}</div>
      </div>`;
    });
    html += `</div>`;
  }

  html += `
  <div class="card">
    <div class="card-header">
      <h3>预实分析明细</h3>
      <span class="badge">${items.length}项</span>
    </div>
    <div class="card-body">
      <div class="table-wrapper">
        <table class="data-table" style="font-size:13px">
          <thead>
            <tr>
              <th style="min-width:180px">科目</th>
              <th>预期值(累计YTD)</th>
              <th>实际值</th>
              <th>差异</th>
              <th>达成率</th>
            </tr>
          </thead>
          <tbody>`;
  items.forEach(item => {
    const diffSign = item.diff >= 0 ? '+' : '';
    const isFavorable = item.status ? item.status === '有利' : item.diff >= 0;
    const diffColor = isFavorable ? 'var(--success)' : 'var(--error)';
    const rateColor = item.rate >= 95 ? 'var(--success)' : (item.rate >= 80 ? 'var(--warning)' : 'var(--error)');
    const fmtVal = v => item.isRatio ? `${v.toFixed(2)}%` : fmtU(v);
    html += `
      <tr>
        <td>${item.item}</td>
        <td class="num">${fmtVal(item.expected)}</td>
        <td class="num">${fmtVal(item.actual)}</td>
        <td class="num" style="color:${diffColor}">${diffSign}${fmtVal(item.diff)}</td>
        <td class="num" style="color:${rateColor};font-weight:600">${item.rate.toFixed(1)}%</td>
      </tr>`;
  });
  html += `
          </tbody>
        </table>
      </div>
    </div>
  </div>`;
  return html;
}

function renderClassActualComparison(classComparison) {
  if (!classComparison || !classComparison.available) {
    return `
    <div class="alert alert-warning">
      <strong>提示：</strong>未识别到“精算险类实际数”工作表，或工作表中无有效数据。
      请使用“预实分析_实际数据上传模板.xlsx”填写后重新上传。
    </div>`;
  }

  const metrics = classComparison.metrics || [];
  const rows = classComparison.rows || [];

  // 当前指标数据：按险种代码（数值感知）升序排序
  const currentRows = rows.filter(r => r.metric === AVE_SELECTED_CLASS_METRIC)
    .sort((a, b) => String(a.classCode || '').localeCompare(String(b.classCode || ''), 'zh', { numeric: true }));

  let html = `
  <div class="card" style="margin-bottom:16px">
    <div class="card-header"><h3>指标选择（下钻）</h3></div>
    <div class="card-body">
      <div class="scp-class-filter drill-tree">${renderMetricTree(metrics)}</div>
    </div>
  </div>

  <div class="card" style="margin-bottom:16px">
    <div class="card-header"><h3>各险种偏差（${AVE_SELECTED_CLASS_METRIC_KEY}${currentRows[0]?.isRatio ? '，单位：pp' : ''}）</h3></div>
    <div class="card-body">
      <div style="height:340px"><canvas id="aveClassChart"></canvas></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <h3>分险种预实明细 — ${AVE_SELECTED_CLASS_METRIC_KEY}</h3>
      <span class="badge">${currentRows.length}项</span>
    </div>
    <div class="card-body">
      <div class="table-wrapper">
        <table class="data-table" style="font-size:13px">
          <thead>
            <tr>
              <th>险种代码</th>
              <th>险种名称</th>
              <th>预算（预期）</th>
              <th>实际</th>
              <th>偏差</th>
              <th>偏差%</th>
              <th>达成率</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>`;

  currentRows.forEach(r => {
    const isRatio = r.isRatio;
    const diffSign = r.diff >= 0 ? '+' : '';
    const diffColor = r.status === '有利' ? 'var(--success)' : 'var(--error)';
    const rateColor = r.rate >= 95 ? 'var(--success)' : (r.rate >= 80 ? 'var(--warning)' : 'var(--error)');
    html += `
      <tr style="${r.isSignificant ? 'font-weight:600' : ''}">
        <td>${r.classCode || '-'}</td>
        <td>${r.className || getClassName(r.classCode)}</td>
        <td class="num">${isRatio ? r.expected.toFixed(2) + '%' : fmtU(r.expected)}</td>
        <td class="num">${isRatio ? r.actual.toFixed(2) + '%' : fmtU(r.actual)}</td>
        <td class="num" style="color:${diffColor}">${diffSign}${isRatio ? r.diff.toFixed(2) + 'pp' : fmtU(r.diff)}</td>
        <td class="num" style="color:${diffColor}">${r.diffPct.toFixed(2)}%</td>
        <td class="num" style="color:${rateColor};font-weight:600">${r.rate.toFixed(1)}%</td>
        <td><span class="status-tag ${r.status === '有利' ? 'done' : 'error'}">${r.status}</span></td>
      </tr>`;
  });

  html += `
          </tbody>
        </table>
      </div>
    </div>
  </div>`;
  return html;
}

function setAveClassMetric(metric, key) {
  AVE_SELECTED_CLASS_METRIC = metric;
  AVE_SELECTED_CLASS_METRIC_KEY = key || metric;
  renderPage('actual-vs-expected');
  setTimeout(() => initActualVsExpectedEvents(), 50);
}

// 下钻树渲染：顶层指标可展开为子指标，叶子指标选中后联动偏差图与明细表
function renderMetricTree(availableMetrics) {
  const avail = new Set(availableMetrics || []);
  function nodeHtml(node, depth) {
    const hasChildren = node.children && node.children.length;
    const isExpanded = !!AVE_DRILL_EXPANDED[node.key];
    const isSelected = AVE_SELECTED_CLASS_METRIC_KEY === node.key;
    const hasData = avail.has(node.metric);
    const indent = depth * 20;
    let html = `
      <div class="drill-node" style="padding-left:${indent}px">
        ${hasChildren
          ? `<span class="drill-toggle" onclick="toggleDrill('${node.key}')">${isExpanded ? '▼' : '▶'}</span>`
          : `<span class="drill-toggle" style="visibility:hidden">•</span>`}
        <button type="button" class="scp-class-chip ${isSelected ? 'active' : ''} ${hasData ? '' : 'drill-disabled'}" onclick="setAveClassMetric('${node.metric}','${node.key}')">
          <span>${node.key}</span>
        </button>
      </div>`;
    if (hasChildren && isExpanded) {
      html += node.children.map(c => nodeHtml(c, depth + 1)).join('');
    }
    return html;
  }
  return CLASS_METRIC_TREE.map(n => nodeHtml(n, 0)).join('');
}

function toggleDrill(key) {
  AVE_DRILL_EXPANDED[key] = !AVE_DRILL_EXPANDED[key];
  renderPage('actual-vs-expected');
  setTimeout(() => initActualVsExpectedEvents(), 50);
}

function initActualVsExpectedEvents() {
  const uploadArea = document.getElementById('actualUploadArea');
  const fileInput = document.getElementById('actualFileInput');
  if (!uploadArea || !fileInput) return;

  uploadArea.addEventListener('click', () => fileInput.click());
  uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
  uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
  uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) handleActualUpload(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleActualUpload(e.target.files[0]);
  });
}

async function handleActualUpload(file, returnPage = 'actual-vs-expected') {
  const uploadArea = document.getElementById('actualUploadArea');
  if (uploadArea) {
    uploadArea.innerHTML = '<div class="upload-loading">⏳ 正在上传并解析...</div>';
  }
  const csrfToken = window.CSRF_TOKEN || '';
  try {
    const arrayBuffer = await file.arrayBuffer();
    const params = new URLSearchParams();
    if (AVE_SELECTED_PERIOD) params.set('period', AVE_SELECTED_PERIOD);
    params.set('scenario', AVE_SELECTED_SCENARIO || DASH_SELECTED_SCENARIO || '情景0');
    const url = '/api/upload/actual' + (params.toString() ? '?' + params.toString() : '');
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrfToken,
        'X-File-Name': encodeURIComponent(file.name),
        'Content-Type': 'application/octet-stream',
      },
      body: arrayBuffer,
    });
    const data = await resp.json();
    if (!data.success) {
      if (uploadArea) {
        uploadArea.innerHTML = `<div class="alert alert-danger">上传失败: ${data.error || '未知错误'}</div>`;
      }
      return;
    }
    actualVsExpectedState = {
      loaded: true,
      fileName: data.fileName,
      uploadTime: data.uploadTime,
      comparison: data.comparison,
    };
    renderPage(returnPage);
    setTimeout(() => {
      if (returnPage === 'actual-vs-expected') initActualVsExpectedEvents();
      else initActualUploadEvents();
    }, 50);
  } catch (err) {
    if (uploadArea) {
      uploadArea.innerHTML = `<div class="alert alert-danger">网络错误: ${err.message}</div>`;
    }
  }
}

function initOldStandardUploadEvents() {
  const uploadArea = document.getElementById('oldStandardUploadArea');
  const fileInput = document.getElementById('oldStandardFileInput');
  if (!uploadArea || !fileInput) return;

  uploadArea.addEventListener('click', () => fileInput.click());
  uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
  uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
  uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) handleOldStandardUpload(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleOldStandardUpload(e.target.files[0]);
  });
}

async function handleOldStandardUpload(file) {
  const uploadArea = document.getElementById('oldStandardUploadArea');
  if (uploadArea) {
    uploadArea.innerHTML = '<div class="upload-loading">⏳ 正在上传并解析旧准则数字...</div>';
  }
  const csrfToken = window.CSRF_TOKEN || '';
  try {
    const arrayBuffer = await file.arrayBuffer();
    const resp = await fetch('/api/upload/old-standard', {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrfToken,
        'X-File-Name': encodeURIComponent(file.name),
        'Content-Type': 'application/octet-stream',
      },
      body: arrayBuffer,
    });
    const data = await resp.json();
    if (!data.success) {
      if (uploadArea) {
        uploadArea.innerHTML = `<div class="alert alert-danger">上传失败: ${data.error || '未知错误'}</div>`;
      }
      return;
    }
    oldStandardUploadState = {
      loaded: true,
      fileName: data.fileName,
      uploadTime: data.uploadTime,
      kpis: data.kpis || null,
      newKpis: data.newKpis || null,
    };
    // 上传成功后使新旧准则桥接对比缓存失效，确保重新进入页面或当前页面能刷新为最新上传数据
    oldNewBridgeState.loaded = false;
    oldNewBridgeState.data = null;
    oldNewBridgeState.error = '';
    if (CURRENT_PAGE === 'old-new-bridge') {
      loadOldNewBridgeData();
    }
    renderPage('actual-upload');
    setTimeout(() => initOldStandardUploadEvents(), 50);
  } catch (err) {
    if (uploadArea) {
      uploadArea.innerHTML = `<div class="alert alert-danger">网络错误: ${err.message}</div>`;
    }
  }
}

let deployConfigLoaded = false;

// ===== 数据及逻辑归集页面 =====
function renderDataLogicCollectionPage() {
  const tab = DLC_ACTIVE_TAB || 'logic';
  const body = tab === 'logic' ? renderLogicOutlineMindMap() : renderDataCollectionMindMap();
  return `
  <div class="page active dlc-page">
    <div class="page-header">
      <h2>数据及逻辑归集</h2>
      <p>计算逻辑概要 / 数据输入归集 — 可展开的思维导图</p>
    </div>
    <div class="dlc-tabs">
      <button class="btn ${tab === 'logic' ? 'btn-primary' : 'btn-outline'}" onclick="setDlcTab('logic')">计算逻辑概要</button>
      <button class="btn ${tab === 'collection' ? 'btn-primary' : 'btn-outline'}" onclick="setDlcTab('collection')">数据归集</button>
    </div>
    <div class="card dlc-card">
      <div class="card-body">
        ${body}
      </div>
    </div>
  </div>`;
}

function renderLogicOutlineMindMap() {
  if (!DLC_LOGIC_TREE) {
    return `<div class="dlc-loading">⏳ 正在加载计算逻辑概要...</div>`;
  }
  if (!DLC_LOGIC_TREE.success) {
    return `<div class="alert alert-warning"><strong>加载失败：</strong>${escapeHtml(DLC_LOGIC_TREE.error || '未知错误')}</div>`;
  }
  const tree = DLC_LOGIC_TREE.tree || [];
  return `
  <div class="dlc-logic-layout">
    <div class="mind-map" style="flex:1;min-width:0;">
      <div class="mind-map-root">利润表项目</div>
      <ul class="mind-map-tree">
        ${tree.map((node, idx) => renderLogicNode(node, `logic-root-${idx}`)).join('')}
      </ul>
    </div>
    <div class="dlc-detail-panel">
      ${DLC_LOGIC_SELECTED ? renderLogicDetailPanel(DLC_LOGIC_SELECTED) : '<div class="dlc-detail-placeholder">点击左侧组成部分卡片，在右侧展开涉及输入表、预测可调整性、对净利润敏感度</div>'}
    </div>
  </div>`;
}

function findLogicNodeById(nodeId) {
  const parts = nodeId.split('-');
  if (parts.length < 3 || parts[0] !== 'logic' || parts[1] !== 'root') return null;
  const rootIdx = parseInt(parts[2], 10);
  const tree = (DLC_LOGIC_TREE && DLC_LOGIC_TREE.tree) || [];
  const top = tree[rootIdx];
  if (!top) return null;
  if (parts.length === 3) return top;
  const compIdx = parseInt(parts[3], 10);
  return (top.children || [])[compIdx] || null;
}

function renderLogicNode(node, nodeId) {
  const expanded = !!DLC_LOGIC_EXPANDED[nodeId];
  const hasChildren = node.children && node.children.length > 0;
  const toggleIcon = hasChildren ? (expanded ? '▼' : '▶') : '•';
  const childrenHtml = hasChildren && expanded ? `
    <ul class="mind-map-children">
      ${node.children.map((child, idx) => renderLogicComponentNode(child, `${nodeId}-${idx}`)).join('')}
    </ul>
  ` : '';
  return `
  <li class="mind-map-node">
    <div class="mind-map-node-content mind-map-l1" onclick="toggleDlcNode('${nodeId}')">
      <span class="mind-map-toggle">${toggleIcon}</span>
      <span class="mind-map-label">${escapeHtml(node.name)}</span>
    </div>
    ${childrenHtml}
  </li>`;
}

function renderLogicComponentNode(node, nodeId) {
  const sum = node.summary || {};
  const title = escapeHtml(sum.title || node.name || '');
  const effRow = sum.effective ? `<div class="dlc-sum-row"><span class="dlc-sum-tag">有效业务</span><span class="dlc-sum-text">${escapeHtml(sum.effective)}</span></div>` : '';
  const newRow = sum.new ? `<div class="dlc-sum-row"><span class="dlc-sum-tag">新业务</span><span class="dlc-sum-text">${escapeHtml(sum.new)}</span></div>` : '';
  const i4Row = sum.i4 ? `<div class="dlc-sum-row"><span class="dlc-sum-tag">I4类比</span><span class="dlc-sum-text">${escapeHtml(sum.i4)}</span></div>` : '';
  const selectedClass = DLC_LOGIC_SELECTED === nodeId ? 'mind-map-selected' : '';
  return `
  <li class="mind-map-node">
    <div class="mind-map-node-content mind-map-l2 mind-map-component-box ${selectedClass}" onclick="selectLogicComponent('${nodeId}')">
      <span class="mind-map-toggle">▶</span>
      <div class="mind-map-component-inner">
        <div class="mind-map-component-title">${title}</div>
        ${effRow}${newRow}${i4Row}
      </div>
    </div>
  </li>`;
}

function selectLogicComponent(nodeId) {
  DLC_LOGIC_SELECTED = (DLC_LOGIC_SELECTED === nodeId) ? null : nodeId;
  renderPage('data-logic-collection');
}

function renderLogicDetailPanel(nodeId) {
  const node = findLogicNodeById(nodeId);
  if (!node) return '';
  const sum = node.summary || {};
  const title = escapeHtml(sum.title || node.name || '');
  const details = (sum.input_details || []).length
    ? sum.input_details
    : (sum.inputs || []).map(t => ({ table: t, biz: '', adjust: (sum.adjust || [])[0] || '', sensitivity: (sum.sensitivity || [])[0] || '', highlight: false }));

  function lvlClass(v) {
    if (v === '高') return 'lvl-high';
    if (v === '中') return 'lvl-mid';
    if (v === '低') return 'lvl-low';
    if (v === '无' || !v) return 'lvl-none';
    return 'lvl-none';
  }

  const boxes = details.length ? details.map(d => {
    const bizTag = d.biz ? `<span class="dlc-biz-tag">${escapeHtml(d.biz)}</span>` : '';
    const hotTag = d.highlight ? `<span class="dlc-hot-tag">高敏感 · 高可调</span>` : '';
    const hotCls = d.highlight ? ' dlc-input-box--hot' : '';
    return `
    <div class="dlc-detail-input-box${hotCls}">
      <div class="dlc-input-box-head">${bizTag}<span class="dlc-input-box-table">${escapeHtml(d.table)}</span>${hotTag}</div>
      <div class="dlc-input-box-meta">
        <span class="dlc-meta-item"><span class="dlc-meta-label">预测可调整性</span><span class="dlc-meta-value ${lvlClass(d.adjust)}">${escapeHtml(d.adjust || '无')}</span></span>
        <span class="dlc-meta-item"><span class="dlc-meta-label">对净利润敏感度</span><span class="dlc-meta-value ${lvlClass(d.sensitivity)}">${escapeHtml(d.sensitivity || '无')}</span></span>
      </div>
    </div>`;
  }).join('') : '<div class="dlc-empty">无涉及输入表</div>';

  return `
  <div class="dlc-detail-header">${title}</div>
  <div class="dlc-detail-card">
    <div class="dlc-detail-title">涉及输入表 <span class="dlc-detail-count">${details.length}</span></div>
    <div class="dlc-detail-inputs">${boxes}</div>
  </div>`;
}

function renderDataCollectionMindMap() {
  return `
  <div class="mind-map">
    <div class="mind-map-root">输入假设归类</div>
    <ul class="mind-map-tree">
      ${DATA_COLLECTION_TREE.map((node, idx) => renderCollectionNode(node, `coll-root-${idx}`)).join('')}
    </ul>
  </div>`;
}

function renderCollectionNode(node, nodeId) {
  const expanded = !!DLC_COLLECTION_EXPANDED[nodeId];
  const hasChildren = node.children && node.children.length > 0;
  const isLeaf = !hasChildren;
  const toggleIcon = hasChildren ? (expanded ? '▼' : '▶') : '';
  const note = node.note ? `<span class="mind-map-note">${escapeHtml(node.note)}</span>` : '';
  const jsSheet = node.sheet ? String(node.sheet).replace(/\\/g, '\\\\').replace(/'/g, "\\'") : '';
  const clickHandler = isLeaf && node.sheet
    ? `onclick="navigateToSheet('${jsSheet}')"`
    : (hasChildren ? `onclick="toggleDlcCollectionNode('${nodeId}')"` : '');
  const cursorClass = (isLeaf && node.sheet) ? 'mind-map-link' : '';
  const childrenHtml = hasChildren && expanded ? `
    <ul class="mind-map-children">
      ${node.children.map((child, idx) => renderCollectionNode(child, `${nodeId}-${idx}`)).join('')}
    </ul>
  ` : '';
  return `
  <li class="mind-map-node">
    <div class="mind-map-node-content ${isLeaf ? 'mind-map-leaf-content' : 'mind-map-l1'} ${cursorClass}" ${clickHandler}>
      ${hasChildren ? `<span class="mind-map-toggle">${toggleIcon}</span>` : '<span class="mind-map-bullet"></span>'}
      <span class="mind-map-label">${escapeHtml(node.key)}</span>
      ${note}
    </div>
    ${childrenHtml}
  </li>`;
}

function setDlcTab(tab) {
  DLC_ACTIVE_TAB = tab;
  renderPage('data-logic-collection');
}

function toggleDlcNode(nodeId) {
  DLC_LOGIC_EXPANDED[nodeId] = !DLC_LOGIC_EXPANDED[nodeId];
  renderPage('data-logic-collection');
}

function toggleDlcCollectionNode(nodeId) {
  DLC_COLLECTION_EXPANDED[nodeId] = !DLC_COLLECTION_EXPANDED[nodeId];
  renderPage('data-logic-collection');
}

function navigateToSheet(sheetName) {
  renderPage('sheet-' + sheetName);
  // 同步刷新侧边栏激活态，避免「查看全量数据」仍取到上一个页面（如 data-logic-collection）
  const nav = document.getElementById('sidebarNav');
  if (nav) nav.innerHTML = renderSidebar();
  // 展开对应上传分组，让当前工作表高亮可见
  const isExcel = SIDEBAR_CONFIG.dataInput.excelSheets.includes(sheetName);
  const groupId = isExcel ? 'excel-sheets' : 'dock-sheets';
  const group = document.getElementById(groupId);
  const toggle = document.querySelector(`.sidebar-subsection-toggle[data-group="${groupId}"]`);
  if (group) group.style.display = 'block';
  if (toggle) toggle.innerHTML = toggle.innerHTML.replace('▶', '▼');
}

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function initDataLogicCollectionEvents() {
  if (DLC_ACTIVE_TAB === 'logic' && !DLC_LOGIC_TREE) {
    fetch('/api/logic/outline')
      .then(r => r.json())
      .then(data => {
        DLC_LOGIC_TREE = data;
        // 计算逻辑概要默认全部收缩，不预展开任何节点
        renderPage('data-logic-collection');
      })
      .catch(err => {
        DLC_LOGIC_TREE = { success: false, error: err.message };
        renderPage('data-logic-collection');
      });
  }
  // 数据归集同样默认全部收缩，由用户手动展开
}

function renderDeployManagePage() {
  const isAdmin = window.DJANGO_USER && (window.DJANGO_USER.is_admin || window.DJANGO_USER.is_staff);
  if (!isAdmin) {
    return `<div class="page active"><div class="page-header"><h2>部署管理</h2></div>
    <div class="alert alert-warning" style="margin:24px 0;">仅管理员可使用部署功能。请使用 admin 账号登录。</div></div>`;
  }

  return `
<div class="page active">
  <div class="page-header">
    <h2>部署管理</h2>
    <p>将本地最新代码一键推送到阿里云 ECS（Docker Compose 全栈自动重建）</p>
  </div>

  <div class="card">
    <div class="card-header">
      <h3>云服务器 SSH 配置</h3>
      <span class="badge" id="deploy-config-status">未加载</span>
    </div>
    <div class="card-body">
      <div class="alert alert-warning" style="margin-bottom:16px;">
        <strong>⚠️ 注意：</strong>这里填写的是<strong>服务器 SSH 登录凭据</strong>，不是本系统后台的 admin 账号。<br>
        阿里云 ECS 默认 SSH 用户名为 <code>root</code>，密码请在阿里云控制台查看/重置。
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
        <div>
          <label style="display:block;margin-bottom:6px;font-size:13px;color:var(--text-sec);">服务器地址</label>
          <input type="text" id="deploy-host" class="form-input" placeholder="如 121.41.98.55" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg);color:var(--text);box-sizing:border-box;">
        </div>
        <div>
          <label style="display:block;margin-bottom:6px;font-size:13px;color:var(--text-sec);">SSH 端口</label>
          <input type="number" id="deploy-port" class="form-input" value="22" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg);color:var(--text);box-sizing:border-box;">
        </div>
        <div>
          <label style="display:block;margin-bottom:6px;font-size:13px;color:var(--text-sec);">用户名 <span style="color:var(--red);">*</span></label>
          <input type="text" id="deploy-username" class="form-input" value="root" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg);color:var(--text);box-sizing:border-box;">
        </div>
        <div>
          <label style="display:block;margin-bottom:6px;font-size:13px;color:var(--text-sec);">密码 <span style="color:var(--red);">*</span> <span style="font-weight:normal;color:var(--text-sec);">（服务器 root 密码，非 admin 密码）</span></label>
          <div style="display:flex;gap:8px;">
            <input type="password" id="deploy-password" class="form-input" placeholder="首次使用请填写并保存" style="flex:1;padding:8px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg);color:var(--text);box-sizing:border-box;">
            <button type="button" id="btn-deploy-toggle-pwd" class="btn btn-outline" style="padding:8px 12px;white-space:nowrap;">显示</button>
          </div>
        </div>
        <div style="grid-column:1/3;">
          <label style="display:block;margin-bottom:6px;font-size:13px;color:var(--text-sec);">服务器项目路径</label>
          <input type="text" id="deploy-remote-dir" class="form-input" value="/www/wwwroot/ifrs17-system" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg);color:var(--text);box-sizing:border-box;">
        </div>
      </div>

      <div style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap;">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:13px;color:var(--text-sec);">
          <input type="checkbox" id="deploy-force-rebuild"> 强制重建镜像（--no-cache，依赖/系统包有变化时勾选）
        </label>
      </div>

      <div style="display:flex;gap:12px;flex-wrap:wrap;">
        <button class="btn btn-outline" id="btn-deploy-save" style="padding:8px 20px;">保存配置</button>
        <button class="btn btn-outline" id="btn-deploy-test" style="padding:8px 20px;">测试连接</button>
      </div>
      <div id="deploy-test-result" style="margin-top:12px;"></div>
    </div>
  </div>

  <div class="card" style="margin-top:24px;">
    <div class="card-header">
      <h3>一键部署到云端</h3>
    </div>
    <div class="card-body">
      <div class="alert alert-info" style="margin-bottom:16px;">
        <strong>部署流程：</strong>打包本地代码 &rarr; SSH 上传到服务器 &rarr; 远程解压 &rarr; docker compose up -d --build（重建 web 镜像 / db 数据卷保留 / entrypoint 自动迁移+收集静态 / 容器滚动重启）
      </div>
      <div style="display:flex;gap:12px;align-items:center;">
        <button class="btn btn-primary" id="btn-deploy-push" style="padding:10px 32px;font-size:15px;">
          🚀 一键部署到云端
        </button>
        <span id="deploy-status-text" style="font-size:14px;color:var(--text-sec);"></span>
      </div>
    </div>
  </div>

  <div class="card" id="deploy-log-card" style="margin-top:24px;display:none;">
    <div class="card-header">
      <h3>部署日志</h3>
      <button class="btn btn-outline btn-sm" id="btn-deploy-clear-log">清除日志</button>
    </div>
    <div class="card-body">
      <pre id="deploy-log" style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:16px;max-height:500px;overflow-y:auto;font-family:'Consolas','Monaco',monospace;font-size:13px;line-height:1.6;white-space:pre-wrap;word-break:break-all;color:var(--text);"></pre>
    </div>
  </div>
</div>`;
}

function initDeployManageEvents() {
  // 加载已有配置
  loadDeployConfig();

  // 保存配置
  const btnSave = document.getElementById('btn-deploy-save');
  if (btnSave) btnSave.addEventListener('click', saveDeployConfig);

  // 测试连接
  const btnTest = document.getElementById('btn-deploy-test');
  if (btnTest) btnTest.addEventListener('click', testDeployConnection);

  // 一键部署
  const btnPush = document.getElementById('btn-deploy-push');
  if (btnPush) btnPush.addEventListener('click', pushDeploy);

  // 显示/隐藏密码
  const btnTogglePwd = document.getElementById('btn-deploy-toggle-pwd');
  if (btnTogglePwd) {
    btnTogglePwd.addEventListener('click', () => {
      const pwdInput = document.getElementById('deploy-password');
      if (pwdInput.type === 'password') {
        pwdInput.type = 'text';
        btnTogglePwd.textContent = '隐藏';
      } else {
        pwdInput.type = 'password';
        btnTogglePwd.textContent = '显示';
      }
    });
  }

  // 清除日志
  const btnClear = document.getElementById('btn-deploy-clear-log');
  if (btnClear) btnClear.addEventListener('click', () => {
    const logEl = document.getElementById('deploy-log');
    if (logEl) logEl.innerHTML = '';
    document.getElementById('deploy-log-card').style.display = 'none';
  });
}

function getDeployFormConfig() {
  const host = document.getElementById('deploy-host').value.trim();
  const port = parseInt(document.getElementById('deploy-port').value) || 22;
  const username = document.getElementById('deploy-username').value.trim();
  const password = document.getElementById('deploy-password').value;
  const remote_project_dir = document.getElementById('deploy-remote-dir').value.trim();
  return {
    host,
    port,
    username,
    password,
    remote_project_dir,
    force_rebuild: document.getElementById('deploy-force-rebuild').checked,
  };
}

function validateDeployConfig(config) {
  if (!config.host) return '请填写服务器地址';
  if (!config.username) return '请填写 SSH 用户名';
  if (!config.password) return '请填写 SSH 密码。注意：这是服务器 root 密码，不是系统 admin 密码。';
  if (config.username === 'admin' && config.password === 'admin123') {
    return '检测到您填写的是系统登录账号 admin/admin123，不是服务器 SSH 账号。请使用阿里云 ECS 的 root 密码。';
  }
  return null;
}

async function loadDeployConfig() {
  try {
    const res = await fetch('/api/deploy/config');
    const data = await res.json();
    if (data.success && data.config) {
      const c = data.config;
      document.getElementById('deploy-host').value = c.host || '';
      document.getElementById('deploy-port').value = c.port || 22;
      document.getElementById('deploy-username').value = c.username || 'root';
      document.getElementById('deploy-remote-dir').value = c.remote_project_dir || '/www/wwwroot/ifrs17-system';
      document.getElementById('deploy-force-rebuild').checked = c.force_rebuild || false;

      const statusEl = document.getElementById('deploy-config-status');
      if (c.password_set || c.private_key_set) {
        statusEl.textContent = '已配置';
        statusEl.className = 'badge';
        statusEl.style.background = 'var(--green)';
        statusEl.style.color = '#fff';
      } else {
        statusEl.textContent = '未设置密码';
        statusEl.className = 'badge';
        statusEl.style.background = 'var(--orange)';
        statusEl.style.color = '#fff';
      }
      deployConfigLoaded = true;

      // 如果已保存的 SSH 用户名看起来是系统账号，给出醒目提示
      if (c.username === 'admin') {
        const resultEl = document.getElementById('deploy-test-result');
        if (resultEl) {
          resultEl.innerHTML = `<div class="alert alert-error" style="margin:0;">
            <strong>配置异常</strong><br>
            检测到已保存的 SSH 用户名为 <code>admin</code>，这通常是系统登录账号，不是服务器 SSH 账号。<br>
            阿里云 ECS 默认 SSH 用户名应为 <code>root</code>，请修改后重新保存。
          </div>`;
        }
      }
    }
  } catch (e) {
    console.log('Load deploy config failed:', e);
  }
}

async function saveDeployConfig() {
  const config = {
    host: document.getElementById('deploy-host').value,
    port: parseInt(document.getElementById('deploy-port').value) || 22,
    username: document.getElementById('deploy-username').value,
    remote_project_dir: document.getElementById('deploy-remote-dir').value,
    force_rebuild: document.getElementById('deploy-force-rebuild').checked,
  };
  const pwd = document.getElementById('deploy-password').value;
  if (pwd) config.password = pwd;

  try {
    const res = await fetch('/api/deploy/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
      body: JSON.stringify(config),
    });
    const data = await res.json();
    if (data.success) {
      const statusEl = document.getElementById('deploy-config-status');
      statusEl.textContent = '已保存';
      statusEl.style.background = 'var(--green)';
      statusEl.style.color = '#fff';
      alert('配置保存成功');
      // 保留当前表单密码，方便立即点击测试/部署
      loadDeployConfig();
    } else {
      alert('保存失败: ' + (data.error || '未知错误'));
    }
  } catch (e) {
    alert('保存失败: ' + e.message);
  }
}

async function testDeployConnection() {
  const resultEl = document.getElementById('deploy-test-result');
  resultEl.innerHTML = '<span style="color:var(--text-sec);">正在测试连接...</span>';

  const config = getDeployFormConfig();
  const error = validateDeployConfig(config);
  if (error) {
    resultEl.innerHTML = `<div class="alert alert-error" style="margin:0;"><strong>校验失败</strong><br>${error}</div>`;
    return;
  }

  try {
    const res = await fetch('/api/deploy/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
      body: JSON.stringify(config),
    });
    const data = await res.json();
    if (data.success) {
      resultEl.innerHTML = `<div class="alert alert-success" style="margin:0;">
        <strong>连接成功</strong><br>
        <pre style="margin:8px 0 0 0;font-size:12px;white-space:pre-wrap;">${data.server_info || ''}</pre>
      </div>`;
    } else {
      let msg = data.message || data.error || '未知错误';
      if (msg.toLowerCase().includes('authentication') || msg.includes('认证')) {
        msg += '<br><br>提示：请确认用户名是 <strong>root</strong>，且密码是服务器 root 密码，不是本系统的 admin 密码。';
      }
      resultEl.innerHTML = `<div class="alert alert-error" style="margin:0;">
        <strong>连接失败</strong><br>${msg}
      </div>`;
    }
  } catch (e) {
    resultEl.innerHTML = `<div class="alert alert-error" style="margin:0;">测试失败: ${e.message}</div>`;
  }
}

async function pushDeploy() {
  const config = getDeployFormConfig();
  const error = validateDeployConfig(config);
  if (error) {
    alert('部署前校验失败：\n' + error);
    return;
  }

  if (!confirm('确认将本地最新代码推送到云服务器？\n\n这将覆盖服务器上的项目代码并重启服务。')) return;

  const btn = document.getElementById('btn-deploy-push');
  const statusText = document.getElementById('deploy-status-text');
  const logCard = document.getElementById('deploy-log-card');
  const logEl = document.getElementById('deploy-log');

  btn.disabled = true;
  btn.innerHTML = '⏳ 部署中...';
  statusText.textContent = '正在部署，请耐心等待...';
  logCard.style.display = 'block';
  logEl.innerHTML = '正在初始化部署...\n';

  try {
    const res = await fetch('/api/deploy/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
      body: JSON.stringify(config),
    });
    const data = await res.json();

    if (data.log) {
      logEl.textContent = data.log;
      logEl.scrollTop = logEl.scrollHeight;
    }

    if (data.success) {
      btn.innerHTML = '✅ 部署成功';
      statusText.innerHTML = `<span style="color:var(--green);font-weight:600;">部署成功！耗时 ${data.duration.toFixed(1)} 秒，共 ${data.file_count} 个文件</span>`;
      logEl.innerHTML += '\n\n✅ 部署成功！请访问 http://121.41.98.55/ 验证。';
    } else {
      btn.innerHTML = '❌ 部署失败';
      statusText.innerHTML = `<span style="color:var(--red);font-weight:600;">部署失败</span>`;
      if (data.error) logEl.innerHTML += '\n\n❌ 错误: ' + data.error;
    }
  } catch (e) {
    btn.innerHTML = '❌ 部署失败';
    statusText.innerHTML = `<span style="color:var(--red);">请求失败: ${e.message}</span>`;
    logEl.innerHTML += '\n\n❌ 请求异常: ' + e.message;
  } finally {
    btn.disabled = false;
    setTimeout(() => { btn.innerHTML = '🚀 一键部署到云端'; }, 3000);
  }
}

// ===== 数据加载 (通过Django后端API) =====
async function loadDataFiles() {
  try {
    const [excelRes, dockRes] = await Promise.all([
      fetch('/api/data/excel').then(r => r.json()),
      fetch('/api/data/dock').then(r => r.json())
    ]);
    excelUploadData = excelRes || {};
    systemDockData = dockRes || {};

    // 同步更新上传状态：如果数据库中有数据，认为已上传成功
    if (Object.keys(excelUploadData).length > 0) {
      excelUploadState = { ...excelUploadState, loaded: true, success: true };
    }
    if (Object.keys(systemDockData).length > 0) {
      systemDockState = { ...systemDockState, loaded: true, success: true };
    }

    // 更新侧边栏显示
    const nav = document.getElementById('sidebarNav');
    if (nav) nav.innerHTML = renderSidebar();
  } catch (e) {
    console.log('Data files not loaded, using defaults', e);
  }
}

// 自动加载 admin 跑好的全部计算结果（落盘缓存），使查看权限账号也能直接看到 demo 数据
// 默认结果展示面板取“情景0/基础情景”，因此需要一次性加载多场景缓存，避免只展示最近一次计算。
async function loadAllCalcResults() {
  try {
    const resp = await fetch('/api/calc/results/all');
    const data = await resp.json();
    if (data && data.success) {
      CALC_RESULTS_MAP = data.results || {};
      // 默认活动结果优先取“情景0”，其次“基础情景”，再次后端最近一次
      const baseKey = CALC_RESULTS_MAP['情景0'] ? '情景0' : (CALC_RESULTS_MAP['基础情景'] ? '基础情景' : null);
      CALC_RESULT = (baseKey ? CALC_RESULTS_MAP[baseKey] : null) || CALC_RESULT || Object.values(CALC_RESULTS_MAP)[0] || null;
      console.log('[init] 已加载全部计算结果:', Object.keys(CALC_RESULTS_MAP), '活动情景:', CALC_RESULT?.selectedScenario);
    } else {
      // 回退：仅加载最近一次
      const resp2 = await fetch('/api/calc/results');
      const data2 = await resp2.json();
      if (data2 && data2.success) {
        CALC_RESULT = data2;
        const sc = data2.selectedScenario || '情景0';
        CALC_RESULTS_MAP[sc] = data2;
      }
    }
  } catch (e) {
    console.log('calc results not loaded', e);
  }
}

// 自动加载预实对比结果（落盘缓存），使查看权限账号也能看到预实分析 demo 数据
async function loadActualComparison() {
  try {
    const params = new URLSearchParams();
    if (AVE_SELECTED_PERIOD) params.set('period', AVE_SELECTED_PERIOD);
    params.set('scenario', AVE_SELECTED_SCENARIO || DASH_SELECTED_SCENARIO || '情景0');
    const url = '/api/actual/compare' + (params.toString() ? '?' + params.toString() : '');
    const resp = await fetch(url);
    const data = await resp.json();
    if (data && data.success) {
      actualVsExpectedState = {
        loaded: true,
        fileName: data.fileName,
        uploadTime: data.uploadTime,
        comparison: data.comparison,
      };
      if (!AVE_SELECTED_PERIOD && data.comparison?.selectedPeriod) {
        AVE_SELECTED_PERIOD = data.comparison.selectedPeriod;
      }
      console.log('[init] 已加载预实对比数据:', data.fileName, 'period:', data.comparison?.selectedPeriod);
    }
  } catch (e) {
    console.log('actual comparison not loaded', e);
  }
}

// 加载 admin 保存的结果展示面板快照；viewer 登录后默认展示该快照
async function loadDashboardSnapshot() {
  try {
    const resp = await fetch('/api/dashboard/snapshot');
    const data = await resp.json();
    if (data && data.success && data.snapshot) {
      DASHBOARD_SNAPSHOT = data.snapshot;
      // 对 viewer 应用快照中的面板状态
      if (isViewer() && DASHBOARD_SNAPSHOT.saved) {
        if (DASHBOARD_SNAPSHOT.scenario) DASH_SELECTED_SCENARIO = DASHBOARD_SNAPSHOT.scenario;
        if (DASHBOARD_SNAPSHOT.periodIdx !== undefined) DASH_FORECAST_PERIOD = String(DASHBOARD_SNAPSHOT.periodIdx);
        if (DASHBOARD_SNAPSHOT.chartMode) DASH_CHART_MODE = DASHBOARD_SNAPSHOT.chartMode;
        if (DASHBOARD_SNAPSHOT.unit) DISPLAY_UNIT = DASHBOARD_SNAPSHOT.unit;
        if (DASHBOARD_SNAPSHOT.calcResult) {
          const sc = DASHBOARD_SNAPSHOT.calcResult.selectedScenario || DASHBOARD_SNAPSHOT.scenario || '情景0';
          CALC_RESULTS_MAP[sc] = DASHBOARD_SNAPSHOT.calcResult;
          CALC_RESULT = DASHBOARD_SNAPSHOT.calcResult;
        }
      }
      console.log('[init] 已加载结果展示面板快照:', DASHBOARD_SNAPSHOT.scenario, DASHBOARD_SNAPSHOT.savedBy);
    }
    // 无有效快照时：结果总览默认预测时点选第一个预测时点（评估期下一个月），趋势默认月度
    if ((!DASHBOARD_SNAPSHOT || !DASHBOARD_SNAPSHOT.saved) && CALC_RESULT && CALC_RESULT.success) {
      const fs = CALC_RESULT.financialStatementsV2Merged || CALC_RESULT.financialStatementsV2;
      if (fs && fs.dates && fs.dates.length > 1 && DASH_FORECAST_PERIOD === '') {
        DASH_FORECAST_PERIOD = '1';
      }
    }
  } catch (e) {
    console.log('dashboard snapshot not loaded', e);
  }
}

// admin 点击「保存当前面板」后落盘快照
async function saveDashboardSnapshot() {
  const activeResult = getScenarioResult(DASH_SELECTED_SCENARIO);
  if (!activeResult || !activeResult.success) {
    alert('当前没有可用的计算结果，无法保存面板');
    return;
  }
  try {
    const payload = {
      scenario: DASH_SELECTED_SCENARIO || activeResult.selectedScenario || '情景0',
      periodIdx: DASH_FORECAST_PERIOD || '',
      chartMode: DASH_CHART_MODE,
      unit: DISPLAY_UNIT,
    };
    const resp = await fetch('/api/dashboard/snapshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN || '' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (data && data.success) {
      DASHBOARD_SNAPSHOT = data.snapshot;
      alert('结果展示面板已保存，viewer 账号将默认展示此面板');
    } else {
      alert('保存失败: ' + (data.error || '未知错误'));
    }
  } catch (e) {
    alert('保存失败: ' + e.message);
  }
}

// ===== Init =====
renderApp();
loadDataFiles();
loadAllCalcResults().then(() => loadDashboardSnapshot());
loadActualComparison();
fetchScenarios(); // 预加载场景元数据，确保多情景比对等页面能正确显示情景加压描述
