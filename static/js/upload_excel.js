// ===== Excel上传接口脚本 (v4.2 — 后端解析，raw body) =====
// 文件作为 raw binary body 发送，绕过 Django 6.0 multipart parser 问题

// Excel上传接口 - 上传状态
let excelUploadState = {
  loaded: false,
  fileName: '',
  uploadTime: '',
  sheetCount: 0,
  totalRows: 0,
  validationResults: {},
  data: {},
  evalDate: '',       // 用户选择的评估时点
  filteredRows: 0,    // 被筛选掉的行数
  forecastPeriods: 12, // 预测期数（月），影响合同组拼接的新合同组生成数量
};

// 预测期数选项
const FORECAST_PERIOD_OPTIONS = [
  { value: 1, label: '1个月' },
  { value: 3, label: '3个月' },
  { value: 6, label: '6个月' },
  { value: 12, label: '12个月（1年）' },
  { value: 16, label: '16个月' },
  { value: 24, label: '24个月（2年）' },
  { value: 36, label: '36个月（3年）' },
  { value: 60, label: '60个月（5年）' },
];

// Excel上传接口 - 发送文件到后端进行解析和校验（raw body 方式）
async function uploadExcelToBackend(file, evalDate, forecastPeriods) {
  const csrfToken = window.CSRF_TOKEN || '';
  try {
    const arrayBuffer = await file.arrayBuffer();
    const headers = {
      'X-CSRFToken': csrfToken,
      'X-File-Name': encodeURIComponent(file.name),
      'Content-Type': 'application/octet-stream',
    };
    if (evalDate) {
      headers['X-Eval-Date'] = evalDate;
    }
    if (forecastPeriods) {
      headers['X-Forecast-Periods'] = String(forecastPeriods);
    }
    const resp = await fetch('/api/upload/excel', {
      method: 'POST',
      headers: headers,
      body: arrayBuffer,
    });
    return await resp.json();
  } catch (err) {
    return { success: false, errors: ['网络错误: ' + err.message], sheetResults: {}, sheetData: {} };
  }
}

// Excel上传接口 - 处理上传文件
function handleExcelUpload(file) {
  // 检查是否已选择评估时点
  const evalDateInput = document.getElementById('excelEvalDate');
  const evalDate = evalDateInput ? evalDateInput.value : '';
  if (!evalDate) {
    alert('请先选择评估时点（年月日）再上传文件');
    return;
  }

  // 读取预测期数
  const forecastPeriodsInput = document.getElementById('excelForecastPeriods');
  const forecastPeriods = forecastPeriodsInput ? parseInt(forecastPeriodsInput.value, 10) : 12;

  const statusArea = document.getElementById('excelUploadArea');
  if (statusArea) {
    statusArea.innerHTML = '<div class="upload-loading">⏳ 正在上传文件到服务器进行解析...</div>';
  }

  uploadExcelToBackend(file, evalDate, forecastPeriods).then(data => {
    // 后端返回结构: { success, validation, sheetData, dbSaved, uploadId, message, evalDate, filteredRows }
    const vr = data.validation || { success: false, errors: [], warnings: [], sheetResults: {} };

    excelUploadState = {
      loaded: true,
      fileName: file.name,
      uploadTime: new Date().toLocaleString('zh-CN'),
      sheetCount: vr.sheetResults ? Object.keys(vr.sheetResults).length : 0,
      totalRows: data.totalRows || 0,
      success: vr.success || false,
      validationResults: vr,
      dbSaved: data.dbSaved || false,
      dbMessage: data.message || '',
      uploadId: data.uploadId,
      evalDate: data.evalDate || evalDate,
      filteredRows: data.filteredRows || 0,
      forecastPeriods: forecastPeriods,
    };

    // 【修复】用后端返回的（已按评估时点筛选过的）sheetData 同步更新预览数据
    // 此前仅更新了 excelUploadState 但未更新 excelUploadData，导致侧边栏预览仍显示旧数据
    if (data.sheetData && typeof data.sheetData === 'object' && Object.keys(data.sheetData).length > 0) {
      // 将后端返回的 {sheetName: {headers, rows, displayCols}} 映射为侧边栏期望的 {sheetName: {headers, rows, totalRows, displayCols}}
      const newData = {};
      for (const [name, info] of Object.entries(data.sheetData)) {
        const rowsArr = info.rows || [];
        newData[name] = {
          headers: info.headers || [],
          rows: rowsArr,
          totalRows: rowsArr.length,
          displayCols: info.displayCols || (info.headers || []).length,
        };
      }
      // 合并更新（不删除其他未包含的工作表，保持兼容性）
      excelUploadData = Object.assign({}, excelUploadData || {}, newData);
    }

    updateSidebarUploadStatus('excel', vr.success);
    // 重新渲染侧边栏以反映最新的行数
    const nav = document.getElementById('sidebarNav');
    if (nav) nav.innerHTML = renderSidebar();
    renderPage('excel-upload');
    setTimeout(() => initExcelUploadEvents(), 50);
  });
}

// Excel上传接口 - 渲染上传页面（规范定义留在JS用于页面展示）
(function() {
  // 工作表规范（仅用于页面展示字段说明，不再用于校验）
  window.EXCEL_UPLOAD_SPECS = {
    '基本信息': { headers: ['更新日期', '更新人员', '评估时点', '预测期数'], description: '模型基础参数配置', category: '基本信息' },
    '对应关系配置表': { headers: ['评估时点', '预测组', '子合同组合名称', '合同组合名称', '精算险类', '业务类型', '签单年', '预测维度'], description: '合同组与合同组合映射关系', category: '基本信息' },
    '压力情景配置表': { headers: ['评估时点', '情景', '情景描述', '预测月份', '原保险保费增长', '预期赔付率上升', '预期费用率上升', '即期利率变动', '权益类资产下跌', '投资性不动产价格下跌', '关注及不良类固收违约', '其他固收违约', '外汇不利影响', '黄金等大宗商品下跌'], description: '压力情景参数配置', category: '基本信息' },
    '合同组拼接': { headers: ['新业务预测组', '新业务预测组名称ID', '现有业务预测组', '现有业务预测组名称ID', '预测组ID', '预测组', '评估期开始业务预期写入时间（月）', '合同组合名称', '子合同组合名称', '业务类型', '精算险类'], description: '新业务与现有业务合同组拼接关系', category: '基本信息' },
    '生效保费_新业务': { headers: ['更新日期', '评估时点', '预测组'], numericCols: 60, description: '各合同组新业务生效保费（按月）', category: '新业务假设' },
    '签单保费_新业务': { headers: ['更新日期', '评估时点', '预测组'], numericCols: 60, description: '各合同组新业务签单保费（按月）', category: '新业务假设' },
    '新增应收保费减值': { headers: ['更新日期', '评估时点', '数据类型', '精算险类'], numericCols: 60, description: '各精算险类新增应收保费减值（按月）', category: '新业务假设' },
    '跟单获取费用或净额结算比例_新业务': { headers: ['更新日期', '评估时点', '预测组', '业务类型', '精算险类'], numericCols: 60, description: '各合同组新业务跟单获取费用或净额结算比例（按月）', category: '新业务假设' },
    '非跟单获取费用比例_新业务': { headers: ['更新日期', '评估时点', '精算险类'], numericCols: 60, description: '各精算险类新业务非跟单获取费用比例（按月）', category: '新业务假设' },
    '保费现金流模式_新业务': { headers: ['更新日期', '评估时点', '数据类型', '精算险类'], numericCols: 60, description: '新业务保费现金流分配模式', category: '新业务现金流' },
    'IACF现金流模式_新业务': { headers: ['更新日期', '评估时点', '数据类型', '精算险类'], numericCols: 60, description: '新业务IACF现金流分配模式', category: '新业务现金流' },
    '未到期赚取模式_新业务': { headers: ['更新日期', '评估时点', '数据类型', '预测组'], numericCols: 60, description: '新业务未到期责任赚取模式', category: '新业务现金流' },
    '预期摊回比例_新业务': { headers: ['更新日期', '评估时点', '精算险类'], numericCols: 60, description: '新业务预期摊回比例（按月）', category: '新业务比率假设' },
    '预期赔付率': { headers: ['更新日期', '评估时点', '预测组', '精算险类'], numericCols: 60, description: '各合同组预期赔付率假设', category: '新业务比率假设' },
    '维持费用率': { headers: ['更新日期', '评估时点', '精算险类'], numericCols: 60, description: '各精算险类维持费用率假设', category: '新业务比率假设' },
    '未到期间接理赔费用率': { headers: ['更新日期', '评估时点', '精算险类'], numericCols: 60, description: '未到期间接理赔费用率', category: '新业务比率假设' },
    '未决间接理赔费用率': { headers: ['更新日期', '评估时点', '精算险类'], numericCols: 60, description: '未决赔款间接理赔费用率', category: '新业务比率假设' },
    '风险调整比例': { headers: ['更新日期', '评估时点', '精算险类', '未决风险调整%', '未到期风险调整%'], description: '各精算险类风险调整比例参数', category: '新业务假设' },
    '再保人不履约风险': { headers: ['更新日期', '评估时点', '精算险类'], numericCols: 60, description: '再保人违约风险调整参数', category: '新业务比率假设' },
    '投资成分比例': { headers: ['更新日期', '评估时点', '预测组', '精算险类', '业务类型'], numericCols: 60, description: '各合同组投资成分分解比例（按月）', category: '新业务比率假设' },
    '未到期赔付模式': { headers: ['更新日期', '评估时点', '数据类型', '精算险类'], numericCols: 60, description: '未到期赔付分配模式', category: '新业务现金流' },
    '未决赔付模式': { headers: ['更新日期', '评估时点', '数据类型', '精算险类'], numericCols: 60, description: '未决赔款赔付分配模式', category: '新业务现金流' },
    '实际赔付比例': { headers: ['更新日期', '评估时点', '数据类型', '精算险类'], numericCols: 60, description: '实际赔付比例数据', category: '新业务现金流' },
    '费用输入项': { headers: ['更新日期', '评估时点', '数据类型（增加利润为正，减少利润为负）'], numericCols: 60, description: '费用类输入项（调整手续费、复效保费、手续费及佣金支出等）', category: '其他' },
    '其他输入项': { headers: ['更新日期', '评估时点', '数据类型'], numericCols: 60, description: '其他输入参数（提取保费准备金、利息收入、投资收益等）', category: '其他' }
  };
})();

// Excel上传接口 - 渲染上传页面
function renderExcelUploadPage() {
  const state = excelUploadState;
  const specs = window.EXCEL_UPLOAD_SPECS;
  const sheetNames = Object.keys(specs);

  let html = `
  <div class="page active">
    <div class="page-header">
      <h2>Excel上传接口</h2>
      <p>上传Excel格式输入数据 — 共${sheetNames.length}个工作表 | Python后端解析校验</p>
    </div>
    
    <div class="alert alert-info">
      <strong>接口说明：</strong>此接口用于上传Excel格式的输入数据，文件发送到Python后端由openpyxl解析并校验。
      上传后将自动校验工作表名称和字段名，校验通过后数据存入数据库。
      <br><strong>后续规划：</strong>此接口未来将替换为从DataWorks数据中台自动接数。
    </div>

    <div class="card">
      <div class="card-header">
        <h3>参数配置</h3>
        <span class="status-tag pending">必选</span>
      </div>
      <div class="card-body">
        <div style="display:flex;gap:24px;flex-wrap:wrap">
          <div class="form-group" style="max-width:300px">
            <label for="excelEvalDate">评估时点（年月日）</label>
            <input type="date" id="excelEvalDate" value="${state.evalDate || ''}" 
                   style="padding:10px 12px;font-size:14px;border:2px solid var(--primary);border-radius:8px">
            <p style="margin-top:4px;font-size:12px;color:var(--text-sec)">
              ⚠️ 系统将仅上传该时点的数据行
            </p>
          </div>
          <div class="form-group" style="max-width:300px">
            <label for="excelForecastPeriods">预测期数（月）</label>
            <input type="hidden" id="excelForecastPeriods" value="${state.forecastPeriods || 12}">
            <div class="fp-cdd-wrap" style="width:100%">
              ${renderCustomSelect('excel-forecast-periods-cdd', FORECAST_PERIOD_OPTIONS, state.forecastPeriods || 12, 'excelForecastPeriods')}
            </div>
            <p style="margin-top:4px;font-size:12px;color:var(--text-sec)">
              📊 影响合同组拼接的新合同组生成数量，决定预测结果的时间跨度
            </p>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3>文件上传</h3>
        ${state.loaded ? `<span class="status-tag done">已上传</span>` : `<span class="status-tag pending">未上传</span>`}
      </div>
      <div class="card-body">
        <div class="upload-area" id="excelUploadArea">
          <div class="upload-icon">📁</div>
          <div class="upload-text">点击或拖拽文件到此处上传</div>
          <div class="upload-hint">支持 .xlsx 格式 | 文件应包含${sheetNames.length}个工作表 | Python后端解析</div>
          <input type="file" id="excelFileInput" accept=".xlsx,.xls" style="display:none">
        </div>
        ${state.loaded ? `
        <div class="upload-info">
          <div class="info-row"><span class="label">评估时点</span><span class="value" style="color:var(--primary)">${state.evalDate || '-'}</span></div>
          <div class="info-row"><span class="label">预测期数</span><span class="value" style="color:var(--primary)">${state.forecastPeriods || 12} 个月</span></div>
          <div class="info-row"><span class="label">文件名</span><span class="value">${state.fileName}</span></div>
          <div class="info-row"><span class="label">上传时间</span><span class="value">${state.uploadTime}</span></div>
          <div class="info-row"><span class="label">工作表数</span><span class="value">${state.sheetCount} / ${sheetNames.length}</span></div>
          <div class="info-row"><span class="label">数据行数</span><span class="value">${state.totalRows.toLocaleString()} 行</span></div>
          ${state.filteredRows > 0 ? `<div class="info-row"><span class="label">筛选过滤</span><span class="value" style="color:var(--warning)">已过滤 ${state.filteredRows} 行非匹配数据</span></div>` : ''}
          <div class="info-row"><span class="label">校验状态</span><span class="value">${state.success ? '<span class="text-success">全部通过</span>' : '<span class="text-danger">存在错误</span>'}</span></div>
          ${state.dbSaved !== undefined ? `<div class="info-row"><span class="label">数据库</span><span class="value">${state.dbSaved ? '<span class="text-success">已入库 ✓</span>' : '<span class="text-danger">未入库 ✗</span>'} ${state.dbMessage || ''}</span></div>` : ''}
        </div>` : ''}
      </div>
    </div>
  `;

  // 校验结果
  if (state.loaded && state.validationResults) {
    const vr = state.validationResults;
    const sr = vr.sheetResults || {};
    
    if (vr.errors && vr.errors.length > 0) {
      html += `
      <div class="card">
        <div class="card-header"><h3 style="color:var(--danger)">校验错误</h3></div>
        <div class="card-body">
          ${vr.errors.map(e => `<div class="validation-error">❌ ${e}</div>`).join('')}
        </div>
      </div>`;
    }

    if (vr.warnings && vr.warnings.length > 0) {
      html += `
      <div class="card">
        <div class="card-header"><h3 style="color:var(--warning)">校验警告</h3></div>
        <div class="card-body">
          ${vr.warnings.map(w => `<div class="validation-warning">⚠️ ${w}</div>`).join('')}
        </div>
      </div>`;
    }

    html += `
    <div class="card">
      <div class="card-header"><h3>工作表校验明细</h3></div>
      <div class="card-body">
        <div class="table-wrapper">
          <table class="data-table">
            <thead><tr><th>工作表名称</th><th>类别</th><th>说明</th><th>数据行数</th><th>校验状态</th><th>错误数</th></tr></thead>
            <tbody>`;

    for (const [name, spec] of Object.entries(specs)) {
      const result = sr[name] || { valid: false, rowCount: 0, errors: [] };
      const errCount = result.errors ? result.errors.length : 0;
      html += `<tr>
        <td class="font-600">${name}</td>
        <td>${spec.category}</td>
        <td class="text-muted">${spec.description}</td>
        <td class="num">${(result.rowCount || 0).toLocaleString()}</td>
        <td>${result.valid ? '<span class="status-tag done">通过</span>' : '<span class="status-tag" style="background:#FFF1F0;color:#FF4D4F;border:1px solid #FFCCC7">失败</span>'}</td>
        <td class="num${errCount > 0 ? ' negative' : ''}">${errCount}</td>
      </tr>`;
    }

    html += `</tbody></table></div></div></div>`;

    const errorSheets = Object.entries(sr).filter(([_, r]) => r.headerErrors && r.headerErrors.length > 0);
    if (errorSheets.length > 0) {
      html += `
      <div class="card">
        <div class="card-header"><h3 style="color:var(--danger)">字段错误详情</h3></div>
        <div class="card-body">
          <div class="table-wrapper">
            <table class="data-table">
              <thead><tr><th>工作表</th><th>列位置</th><th>期望字段</th><th>实际字段</th><th>错误描述</th></tr></thead>
              <tbody>`;
      for (const [sheetName, result] of errorSheets) {
        for (const err of result.headerErrors) {
          html += `<tr>
            <td class="font-600">${sheetName}</td>
            <td class="num">${err.position > 0 ? '第' + err.position + '列' : '-'}</td>
            <td>${err.expected}</td>
            <td class="text-danger">${err.actual}</td>
            <td class="text-danger">${err.message}</td>
          </tr>`;
        }
      }
      html += `</tbody></table></div></div></div>`;
    }
  }

  // 字段规范说明
  html += `
    <div class="card">
      <div class="card-header"><h3>字段规范说明</h3></div>
      <div class="card-body">
        <div class="table-wrapper">
          <table class="data-table">
            <thead><tr><th>工作表</th><th>类别</th><th>文本字段</th><th>数值列数</th><th>说明</th></tr></thead>
            <tbody>`;
  for (const [name, spec] of Object.entries(specs)) {
    const textFields = spec.headers.join(', ');
    html += `<tr>
      <td class="font-600">${name}</td>
      <td>${spec.category}</td>
      <td style="max-width:400px;word-break:break-all">${textFields}</td>
      <td class="num">${spec.numericCols || 0}</td>
      <td class="text-muted">${spec.description}</td>
    </tr>`;
  }
  html += `</tbody></table></div></div></div>
  </div>`;

  return html;
}

// Excel上传接口 - 初始化上传事件
function initExcelUploadEvents() {
  const area = document.getElementById('excelUploadArea');
  const input = document.getElementById('excelFileInput');
  if (!area || !input) return;

  area.addEventListener('click', () => {
    const evalDateInput = document.getElementById('excelEvalDate');
    if (evalDateInput && !evalDateInput.value) {
      alert('请先在上方选择评估时点（年月日）');
      evalDateInput.focus();
      return;
    }
    input.click();
  });
  area.addEventListener('dragover', (e) => { e.preventDefault(); area.classList.add('dragover'); });
  area.addEventListener('dragleave', () => area.classList.remove('dragover'));
  area.addEventListener('drop', (e) => {
    e.preventDefault();
    area.classList.remove('dragover');
    const evalDateInput = document.getElementById('excelEvalDate');
    if (evalDateInput && !evalDateInput.value) {
      alert('请先在上方选择评估时点（年月日）');
      evalDateInput.focus();
      return;
    }
    if (e.dataTransfer.files.length > 0) handleExcelUpload(e.dataTransfer.files[0]);
  });
  input.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleExcelUpload(e.target.files[0]);
  });
}
