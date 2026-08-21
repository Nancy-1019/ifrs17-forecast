// ===== 系统对接接口脚本 (v4.2 — 后端解析，raw body) =====
// 文件作为 raw binary body 发送，绕过 Django 6.0 multipart parser 问题

// 系统对接接口 - 上传状态
let systemDockState = {
  loaded: false,
  fileName: '',
  uploadTime: '',
  sheetCount: 0,
  totalRows: 0,
  validationResults: {},
  data: {},
  evalDate: '',       // 用户选择的评估时点
  filteredRows: 0,    // 被筛选掉的行数
};

// 系统对接接口 - 发送文件到后端进行解析和校验（raw body 方式）
async function uploadDockToBackend(file, evalDate) {
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
    const resp = await fetch('/api/upload/dock', {
      method: 'POST',
      headers: headers,
      body: arrayBuffer,
    });
    return await resp.json();
  } catch (err) {
    return { success: false, errors: ['网络错误: ' + err.message], sheetResults: {}, sheetData: {} };
  }
}

// 系统对接接口 - 处理上传文件
function handleSystemDockUpload(file) {
  // 检查是否已选择评估时点
  const evalDateInput = document.getElementById('dockEvalDate');
  const evalDate = evalDateInput ? evalDateInput.value : '';
  if (!evalDate) {
    alert('请先选择评估时点（年月日）再上传文件');
    return;
  }

  const statusArea = document.getElementById('systemDockUploadArea');
  if (statusArea) {
    statusArea.innerHTML = '<div class="upload-loading">⏳ 正在上传文件到服务器进行解析...</div>';
  }

  uploadDockToBackend(file, evalDate).then(data => {
    const vr = data.validation || { success: false, errors: [], warnings: [], sheetResults: {} };

    systemDockState = {
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
    };

    // 【修复】用后端返回的（已按评估时点筛选过的）sheetData 同步更新预览数据
    if (data.sheetData && typeof data.sheetData === 'object' && Object.keys(data.sheetData).length > 0) {
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
      systemDockData = Object.assign({}, systemDockData || {}, newData);
    }

    updateSidebarUploadStatus('dock', vr.success);
    const nav = document.getElementById('sidebarNav');
    if (nav) nav.innerHTML = renderSidebar();
    renderPage('system-dock-upload');
    setTimeout(() => initSystemDockUploadEvents(), 50);
  });
}

// 系统对接接口 - 工作表规范（仅用于页面展示）
(function() {
  window.SYSTEM_DOCK_SPECS = {
    '合同组关键假设_现有业务': { headers: ['更新日期', '评估时点', '合同组ID', '预测组', '精算险类', '评估期开始业务预期写入时间（月）', '子合同组合名称', '合同组合名称', '业务标签', '业务类型', '应收保费', '应付IACF'], description: '现有业务合同组关键假设参数', category: '现有业务假设' },
    '系统期初余额表': { headers: ['更新日期', '评估时点', '预测维度', '业务类型', '精算险类', '待摊销保险收入', '未到期责任负债_非亏损部分_不含利净口径未赚', '待摊销获取现金流', '待摊销投资成分', 'UPR余额', '未到期责任负债_非亏损部分', '未到期责任负债_亏损部分', '未到期责任负债_亏损摊回', '已发生未决赔款负债_预期现金流', '已发生未决赔款负债_再保人不履约_预期现金流', '间接理赔费用负债_预期现金流', '已发生未决赔款负债_非金融风险调整', '已发生未决赔款负债_再保人不履约_非金融风险调整', '间接理赔费用负债_非金融风险调整', '已发生未决赔款负债_预期现金流现值', '已发生未决赔款负债_再保人不履约_预期现金流现值', '间接理赔费用负债_预期现金流现值', '已发生未决赔款负债_非金融风险调整现值', '已发生未决赔款负债_再保人不履约_非金融风险调整现值', '间接理赔费用负债_非金融风险调整现值', '保险合同收入', '赔付与费用_分解的投资成分', '赔付与费用_摊销的保险获取现金流', '亏损合同损益', '亏损摊回损益', '赔付与费用_已发生未决赔款负债提转差_预期现金流', '赔付与费用_已发生未决赔款负债提转差_非金融风险调整', '赔付与费用_间接理赔费用提转差_预期现金流', '赔付与费用_间接理赔费用提转差_非金融风险调整', 'IFIE_未到期_未到期计息', 'IFIE_已发生未决_已发生未决赔款负债计息_预期现金流', 'IFIE_已发生未决_已发生未决赔款负债计息_非金融风险调整', 'IFIE_已发生未决_间接理赔费用计息_预期现金流', 'IFIE_已发生未决_间接理赔费用计息_非金融风险调整', '摊回赔付与费用_已发生未决_再保人不履约_预期现金流', '摊回赔付与费用_已发生未决_再保人不履约_非金融风险调整', '现金流_支付的赔付与理赔费用', '现金流_支付的维持费用', '现金流_收到的保费', '现金流_支付的IACF', '签单保费_提前初始确认', '减值'], description: '系统期初各合同组余额表（47字段）', category: '期初数据' },
    '保费现金流模式_现有业务': { headers: ['更新日期', '评估时点', '数据类型', '预测组', '精算险类'], numericCols: 60, description: '现有业务保费现金流分配模式', category: '现有业务现金流' },
    'IACF现金流模式_现有业务': { headers: ['更新日期', '评估时点', '数据类型', '预测组', '精算险类'], numericCols: 60, description: '现有业务IACF现金流分配模式', category: '现有业务现金流' },
    '未到期赚取模式_现有业务': { headers: ['更新日期', '评估时点', '数据类型', '预测组', '精算险类', '业务类型'], numericCols: 60, description: '现有业务未到期责任赚取模式', category: '现有业务现金流' },
    '预期摊回比例_现有业务': { headers: ['更新日期', '评估时点', '预测组', '精算险类'], numericCols: 60, description: '现有业务预期摊回比例', category: '现有业务现金流' },
    '财务报表实际数': { headers: ['评估时点', '科目', '期末余额'], description: 'CAS25财务报表实际数', category: '财务报表' },
    '初始确认利率曲线': { headers: ['更新日期', '评估时点', '初始确认利率曲线', '月度远期'], contractCols: true, description: '各合同组初始确认利率曲线（月度远期利率）', category: '利率曲线' },
    '即期利率曲线': { headers: ['更新日期', '评估时点', '年度', '即期利率曲线'], description: '即期利率曲线（用于折现）', category: '利率曲线' }
  };
})();

// 系统对接接口 - 渲染上传页面
function renderSystemDockUploadPage() {
  const state = systemDockState;
  const specs = window.SYSTEM_DOCK_SPECS;
  const sheetNames = Object.keys(specs);

  let html = `
  <div class="page active">
    <div class="page-header">
      <h2>系统对接接口</h2>
      <p>上传系统对接格式输入数据 — 共${sheetNames.length}个工作表 | Python后端解析校验</p>
    </div>
    
    <div class="alert alert-info">
      <strong>接口说明：</strong>此接口用于上传系统对接格式的输入数据，文件发送到Python后端由openpyxl解析并校验。
      上传后将自动校验工作表名称和字段名，校验通过后数据存入数据库。
      <br><strong>后续规划：</strong>此接口未来将替换为从DataWorks数据中台自动接数。
    </div>

    <div class="card">
      <div class="card-header">
        <h3>评估时点选择</h3>
        <span class="status-tag pending">必选</span>
      </div>
      <div class="card-body">
        <div class="form-group" style="max-width:300px">
          <label for="dockEvalDate">评估时点（年月日）</label>
          <input type="date" id="dockEvalDate" value="${state.evalDate || ''}" 
                 style="padding:10px 12px;font-size:14px;border:2px solid var(--primary);border-radius:8px">
        </div>
        <p style="margin-top:8px;font-size:12px;color:var(--text-sec)">
          ⚠️ 请先选择评估时点，系统将仅上传该时点的数据行
        </p>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3>文件上传</h3>
        ${state.loaded ? `<span class="status-tag done">已上传</span>` : `<span class="status-tag pending">未上传</span>`}
      </div>
      <div class="card-body">
        <div class="upload-area" id="systemDockUploadArea">
          <div class="upload-icon">🔗</div>
          <div class="upload-text">点击或拖拽文件到此处上传</div>
          <div class="upload-hint">支持 .xlsx 格式 | 文件应包含${sheetNames.length}个工作表 | Python后端解析</div>
          <input type="file" id="systemDockFileInput" accept=".xlsx,.xls" style="display:none">
        </div>
        ${state.loaded ? `
        <div class="upload-info">
          <div class="info-row"><span class="label">评估时点</span><span class="value" style="color:var(--primary)">${state.evalDate || '-'}</span></div>
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
      <td class="num">${spec.numericCols || (spec.contractCols ? '合同组列' : 0)}</td>
      <td class="text-muted">${spec.description}</td>
    </tr>`;
  }
  html += `</tbody></table></div></div></div>
  </div>`;

  return html;
}

// 系统对接接口 - 初始化上传事件
function initSystemDockUploadEvents() {
  const area = document.getElementById('systemDockUploadArea');
  const input = document.getElementById('systemDockFileInput');
  if (!area || !input) return;

  area.addEventListener('click', () => {
    const evalDateInput = document.getElementById('dockEvalDate');
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
    const evalDateInput = document.getElementById('dockEvalDate');
    if (evalDateInput && !evalDateInput.value) {
      alert('请先在上方选择评估时点（年月日）');
      evalDateInput.focus();
      return;
    }
    if (e.dataTransfer.files.length > 0) handleSystemDockUpload(e.dataTransfer.files[0]);
  });
  input.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleSystemDockUpload(e.target.files[0]);
  });
}
