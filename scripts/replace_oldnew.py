# -*- coding: utf-8 -*-
path = 'static/js/app.js'
with open(path, 'r', encoding='utf-8') as f:
    s = f.read()

start_marker = 'function renderOldNewBridgePage() {'
end_marker = '// ===== 预实对比模块 ====='
start = s.find(start_marker)
end = s.find(end_marker, start)
if start == -1 or end == -1:
    print('markers not found', start, end)
    raise SystemExit(1)

prefix = s[:start]
suffix = s[end:]

new_func = r'''function renderOldNewBridgePage() {
  const state = oldNewBridgeState;
  const data = state.data;
  const hasCalc = CALC_RESULT && CALC_RESULT.success;

  if (!hasCalc) {
    return `
<div class="page active">
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
  const periodSelector = data?.dates
    ? `<div style="display:inline-flex;align-items:center;gap:6px">
        <span style="font-size:13px;color:var(--text-sec)">预测时点:</span>
        ${renderCustomSelect('oldNewPeriodSel', [{ value: '', label: '评估时点' }].concat(periodOpts), state.selectedPeriod || '', 'oldNewPeriod')}
      </div>`
    : '';

  const hasError = state.loaded && state.error;
  const hasData = state.loaded && !state.error && data;
  const loadingClass = state.loading ? ' old-new-loading' : '';

  // KPI 卡片：无数据时显示占位符（-），避免加载前后卡片区域高度跳变造成闪烁
  const ns = hasData ? (data.newStandardKpis || {}) : {};
  const os = hasData ? (data.oldStandardKpis || {}) : {};
  const nsCards = `
    ${bridgeKpiCard('保险服务收入', fmtU(ns.insRev), '系统输出 YTD', 'blue')}
    ${bridgeKpiCard('承保利润', fmtU(ns.uwProfit), '系统输出 YTD', 'green')}
    ${bridgeKpiCard('净利润', fmtU(ns.netProfit), '系统输出 YTD', 'red')}
    ${bridgeKpiCard('综合成本率', (ns.combinedRatio != null ? ns.combinedRatio.toFixed(1) + '%' : '-'), '系统输出 YTD', 'orange')}
  `;
  const osCards = `
    ${bridgeKpiCard('保险业务收入', fmtU(os.insRev), '桥接表(旧准则)', 'blue')}
    ${bridgeKpiCard('承保利润', fmtU(os.uwProfit), '桥接表(旧准则)', 'green')}
    ${bridgeKpiCard('净利润', fmtU(os.netProfit), '桥接表(旧准则)', 'red')}
    ${bridgeKpiCard('综合成本率', (os.combinedRatio != null ? os.combinedRatio.toFixed(1) + '%' : '-'), '桥接表(旧准则)', 'orange')}
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
      <tr class="old-new-group" onclick="toggleOldNewGroup(${groupIdx})" style="cursor:pointer;background:var(--primary-bg);font-weight:600">
        <td style="min-width:200px"><button type="button" class="old-new-toggle" onclick="event.stopPropagation();toggleOldNewGroup(${groupIdx})">${expandIcon}</button> ${r.oldSubject || '-'}</td>
        <td class="num">${fmtU(r.oldValue)}</td>
        <td style="min-width:200px">${r.newSubject || '-'}</td>
        <td class="num">${fmtU(r.newValue)}</td>
        <td class="num" style="color:${diffColor}">${diffSign}${fmtU(r.diff)}</td>
      </tr>`;
    } else {
      const detailStyle = groupExpanded ? '' : 'style="display:none"';
      tbodyHtml += `
      <tr class="old-new-detail" data-group="${groupIdx}" ${detailStyle}>
        <td style="min-width:200px;padding-left:32px">${r.oldSubject || '-'}</td>
        <td class="num">${fmtU(r.oldValue)}</td>
        <td style="min-width:200px">${r.newSubject || '-'}</td>
        <td class="num">${fmtU(r.newValue)}</td>
        <td class="num" style="color:${diffColor}">${diffSign}${fmtU(r.diff)}</td>
      </tr>`;
    }
  });

  const errorBanner = hasError ? `<div class="alert alert-warning" style="margin-top:14px">${state.error}</div>` : '';

  return `
<div class="page active">
  <div class="page-header"><h2>新旧预测比对</h2><p>IFRS4 旧准则 vs IFRS17 新准则预测结果对比 — 预测时点：${hasData ? (data.period || '-') : '-'}</p></div>
  ${oldNewControlsCard(scenarioSelector, periodSelector, true)}

  <div style="margin-bottom:8px;font-size:13px;font-weight:600;color:var(--text-sec)">新准则（IFRS17）指标 — 系统输出（${hasData ? (data.period || '-') : '-'}</div>
  <div class="kpi-grid">${nsCards}</div>
  <div style="margin:14px 0 8px;font-size:13px;font-weight:600;color:var(--text-sec)">旧准则（IFRS4）指标 — 桥接表 Excel（C/D 列，单期参考）</div>
  <div class="kpi-grid">${osCards}</div>

  <div class="alert alert-info" style="margin-top:14px">
    <strong>说明：</strong>新准则预测直接取系统输出（财务报表 YTD 对应科目）；旧准则预测以桥接表科目关系为基准、按新准则输出拟合生成（差异控制在 ±3% 以内，保持同一大类下勾稽关系）。差异 = 新准则系统输出 − 旧准则。旧准则承保利润按「保险合同收入−保险合同支出」估算、净利润按「营业利润」估算。
  </div>

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
              <th>新准则预测(系统输出)</th>
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

'''

with open(path, 'w', encoding='utf-8') as f:
    f.write(prefix + new_func + suffix)
print('replaced', start, end)
