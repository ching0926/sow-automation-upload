// SOW 審查頁面邏輯。獨立於 frontend/js/app.js 維護，靠 window.REVIEW_MODE
// ('dri' | 'manager') 區分 dri.html / manager.html 兩個頁面該怎麼渲染同一份資料模型。
// 案例資料一律來自 backend/review.py 的 /api/review/cases/{job_code} 系列端點，
// 案例 job_code 從網址 ?jobcode= 讀取。

const TAB_ORDER = ['A', 'B', 'C'];
const TAB_LABEL = { A: '客戶脈絡與價值', B: '專案規劃與交付', C: '技術設計與架構' };

const FIELD_DEFS = {
  A: [
    { key: 'industryBackground', label: '產業背景', type: 'textarea' },
    { key: 'challenge', label: '面臨挑戰', type: 'textarea' },
    { key: 'solution', label: '解決方案', type: 'textarea' },
  ],
  B: [
    { key: 'owner', label: 'DRI 負責人', type: 'text' },
    { key: 'period', label: '專案期間', type: 'text' },
    { key: 'teamSize', label: '團隊總人數', type: 'text', unit: '人' },
    { key: 'manDays', label: '人天估算', type: 'text', unit: '人天' },
    { key: 'totalCost', label: '專案成本', type: 'text' },
    { key: 'deliverables', label: '結案交付與驗收', type: 'list' },
  ],
  C: [
    { key: 'coreFunctions', label: '核心功能設計', type: 'list' },
    { key: 'architecture', label: '底層技術架構節點', type: 'list' },
    { key: 'techStack', label: '技術堆疊', type: 'list' },
  ],
};

const STATUS_LABEL = {
  DRI_REVIEW: 'DRI 審查中',
  MANAGER_REVIEW: '主管審查中',
  RETURNED_TO_DRI: '已退回 DRI',
  PUBLISHED: '已發布',
};
const STATUS_CLASS = {
  DRI_REVIEW: '',
  MANAGER_REVIEW: 'status-manager',
  RETURNED_TO_DRI: 'status-returned',
  PUBLISHED: 'status-published',
};

const MODE = window.REVIEW_MODE === 'manager' ? 'manager' : 'dri';
const JOB_CODE = new URLSearchParams(location.search).get('jobcode');

const state = {
  tab: 'A',
  case: null,
  dirty: new Set(), // 例如 "A.challenge"、"A.kpis.0.value"，代表已編輯但尚未儲存
};

function escapeHtml(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, '&quot;');
}

function showToast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.remove('show'), 2400);
}

function fieldEditable() {
  return state.case.status === 'DRI_REVIEW' || state.case.status === 'RETURNED_TO_DRI';
}

function buildDraftPayload() {
  const d = state.case.detail;
  return {
    customerContext: {
      industryBackground: d.A.industryBackground.current,
      challenge: d.A.challenge.current,
      solution: d.A.solution.current,
      kpis: d.A.kpis.map((k) => ({ icon: k.icon, value: k.value.current, label: k.label.current })),
    },
    projectPlanning: {
      owner: d.B.owner.current,
      period: d.B.period.current,
      teamSize: d.B.teamSize.current,
      manDays: d.B.manDays.current,
      totalCost: d.B.totalCost.current,
      deliverables: d.B.deliverables.current,
    },
    technicalDesign: {
      coreFunctions: d.C.coreFunctions.current,
      architecture: d.C.architecture.current,
      techStack: d.C.techStack.current,
    },
  };
}

// ---------- render: topbar / meta / tabs ----------
function renderTopbar() {
  const pill = document.getElementById('status-pill');
  pill.textContent = STATUS_LABEL[state.case.status];
  pill.className = 'status-pill ' + (STATUS_CLASS[state.case.status] || '');

  const actionsHtml = MODE === 'dri'
    ? `<button class="btn btn-ghost" data-action="save">儲存</button>
       <button class="btn btn-primary" data-action="submit" ${fieldEditable() ? '' : 'disabled'}>送出 DRI 審查</button>`
    : `<button class="btn btn-ghost" data-action="return" ${state.case.status === 'MANAGER_REVIEW' ? '' : 'disabled'}>退回 DRI</button>
       <button class="btn btn-primary" data-action="approve" ${state.case.status === 'MANAGER_REVIEW' ? '' : 'disabled'}>核准並發布</button>`;
  document.getElementById('action-bar-top').innerHTML = actionsHtml;
  const bottomBar = document.getElementById('action-bar-bottom');
  if (bottomBar) bottomBar.innerHTML = actionsHtml;
}

function renderMetaBar() {
  const c = state.case;
  const items = [
    { label: '案件名稱', value: c.title },
    { label: '產業', value: c.industry },
    { label: '上傳時間', value: c.uploadedAt },
  ];
  if (MODE === 'manager') {
    items.push({ label: 'DRI 提交時間', value: c.driSubmittedAt || '—' });
  }
  const bar = document.getElementById('meta-bar');
  bar.className = 'meta-bar' + (items.length > 4 ? ' meta-bar-5' : '');
  bar.innerHTML = items.map((i) => `<div class="meta-item"><span>${i.label}</span><strong>${escapeHtml(i.value)}</strong></div>`).join('');
}

function renderTabs() {
  document.getElementById('detail-tabs').innerHTML = TAB_ORDER.map((tab) => `
    <button class="tab-btn ${tab === state.tab ? 'active' : ''}" data-tab="${tab}">${TAB_LABEL[tab]}</button>`).join('');
}

// ---------- render: DRI 編輯模式欄位 ----------
function renderFieldDri(tab, def) {
  const f = state.case.detail[tab][def.key];
  const path = `${tab}.${def.key}`;
  const dirty = state.dirty.has(path);
  const ndaLocked = f.source === 'nda';
  const disabledAttr = (fieldEditable() && !ndaLocked) ? '' : 'disabled';
  const hint = def.type === 'list'
    ? '<span class="field-hint">（每行一項）</span>'
    : ndaLocked ? '<span class="field-hint">（依 NDA 工作站資料鎖定，不可編輯）</span>' : '';

  if (def.type === 'list') {
    const val = (f.current || []).join('\n');
    return `<div class="field-block ${dirty ? 'dirty' : ''}">
      <label class="field-label">${def.label} ${hint}</label>
      <textarea class="field-textarea" data-path="${path}" data-type="list" ${disabledAttr}>${escapeHtml(val)}</textarea>
    </div>`;
  }
  if (def.type === 'textarea') {
    return `<div class="field-block ${dirty ? 'dirty' : ''}">
      <label class="field-label">${def.label}</label>
      <textarea class="field-textarea" data-path="${path}" data-type="text" ${disabledAttr}>${escapeHtml(f.current)}</textarea>
    </div>`;
  }
  return `<div class="field-block ${dirty ? 'dirty' : ''}">
    <label class="field-label">${def.label} ${hint}</label>
    <div class="field-input-row">
      <input class="field-input" data-path="${path}" data-type="text" value="${escapeAttr(f.current)}" ${disabledAttr} />
      ${def.unit ? `<span class="field-unit">${def.unit}</span>` : ''}
    </div>
  </div>`;
}

function renderKpiSectionDri() {
  const disabledAttr = fieldEditable() ? '' : 'disabled';
  return `<div class="field-block">
    <label class="field-label">關鍵成效指標 (KPIs)</label>
    <div class="kpi-row">
      ${state.case.detail.A.kpis.map((k, i) => `
        <div class="kpi-card">
          <div class="kpi-icon">${k.icon}</div>
          <input class="kpi-value-input" data-kpi-idx="${i}" data-kpi-field="value" value="${escapeAttr(k.value.current)}" ${disabledAttr} />
          <input class="kpi-label-input" data-kpi-idx="${i}" data-kpi-field="label" value="${escapeAttr(k.label.current)}" ${disabledAttr} />
        </div>`).join('')}
    </div>
  </div>`;
}

// ---------- render: 主管審查模式欄位（內容 + 變更記錄） ----------
function renderFieldManager(tab, def) {
  const f = state.case.detail[tab][def.key];
  const isList = def.type === 'list';
  const currentDisplay = isList ? (f.current || []).join('、') : f.current;
  const originalDisplay = isList ? (f.original || []).join('、') : f.original;
  const hasDiff = JSON.stringify(f.current) !== JSON.stringify(f.original);
  const ndaLocked = f.source === 'nda';

  return `<div class="field-row">
    <div class="field-block readonly">
      <label class="field-label">${def.label}</label>
      <div class="section-card"><p>${escapeHtml(currentDisplay)}</p></div>
    </div>
    <div class="changelog-card">
      <div class="changelog-title">變更記錄</div>
      ${ndaLocked ? `
        <div class="diff-none">此數值採用 NDA 工作站申請的權威資料，與 DRI 編輯無關</div>
      ` : `
        <div class="changelog-time">DRI 修改於 ${f.savedAt || '—'}</div>
        ${hasDiff ? `
          <div class="diff-before"><span class="diff-label">原內容：</span>${escapeHtml(originalDisplay)}</div>
          <div class="diff-after"><span class="diff-label">修改後：</span>${escapeHtml(currentDisplay)}</div>
        ` : '<div class="diff-none">無修改</div>'}
      `}
    </div>
  </div>`;
}

function renderKpiSectionManager() {
  const kpis = state.case.detail.A.kpis;
  return `<div class="field-row">
    <div class="field-block readonly">
      <label class="field-label">關鍵成效指標 (KPIs)</label>
      <div class="kpi-row">
        ${kpis.map((k) => `
          <div class="kpi-card">
            <div class="kpi-icon">${k.icon}</div>
            <div class="kpi-value">${escapeHtml(k.value.current)}</div>
            <div class="kpi-label">${escapeHtml(k.label.current)}</div>
          </div>`).join('')}
      </div>
    </div>
    <div class="changelog-card">
      <div class="changelog-title">變更記錄</div>
      ${kpis.map((k, i) => {
        const hasDiff = k.value.current !== k.value.original || k.label.current !== k.label.original;
        return `<div class="kpi-changelog-item">
          <div class="diff-label-inline">KPI ${i + 1}｜DRI 修改於 ${k.savedAt || '—'}</div>
          ${hasDiff ? `
            <div class="diff-before"><span class="diff-label">原內容：</span>${escapeHtml(k.value.original)} ${escapeHtml(k.label.original)}</div>
            <div class="diff-after"><span class="diff-label">修改後：</span>${escapeHtml(k.value.current)} ${escapeHtml(k.label.current)}</div>
          ` : '<div class="diff-none">無修改</div>'}
        </div>`;
      }).join('')}
    </div>
  </div>`;
}

function renderContent() {
  const tab = state.tab;
  const el = document.getElementById('review-content');
  let html = `<div class="section-heading">${TAB_LABEL[tab]}</div>`;
  if (MODE === 'dri') {
    html += FIELD_DEFS[tab].map((def) => renderFieldDri(tab, def)).join('');
    if (tab === 'A') html += renderKpiSectionDri();
  } else {
    html += FIELD_DEFS[tab].map((def) => renderFieldManager(tab, def)).join('');
    if (tab === 'A') html += renderKpiSectionManager();
  }
  el.innerHTML = html;
}

function renderComments() {
  const panel = document.getElementById('comment-panel');
  if (!panel) return;
  const comments = state.case.comments || [];
  const list = comments.length
    ? comments.map((c) => `
      <div class="comment-item">
        <div class="changelog-time">${c.authorRole === 'DRI' ? 'DRI' : '主管'}・${escapeHtml(c.authorName || '—')}・${escapeHtml(c.createdAt || '')}</div>
        <div class="diff-after">${escapeHtml(c.body)}</div>
      </div>`).join('')
    : '<div class="diff-none">尚無留言</div>';
  const form = `
    <div class="field-block" style="margin-top:14px;">
      <textarea class="field-textarea small" id="comment-input" placeholder="輸入留言…"></textarea>
      <div class="action-bar" style="margin-top:8px;">
        <button class="btn btn-primary" data-action="comment">送出留言</button>
      </div>
    </div>`;
  panel.innerHTML = '<div class="comment-panel-title">留言記錄</div>' + list + form;
}

function render() {
  renderTopbar();
  renderMetaBar();
  renderTabs();
  renderContent();
  renderComments();
}

// ---------- actions ----------
async function saveAll() {
  try {
    state.case = await apiSaveDraft(JOB_CODE, buildDraftPayload());
    state.dirty.clear();
    render();
    showToast('已儲存');
  } catch (e) {
    showToast(e.message || '儲存失敗');
  }
}

async function submitReview() {
  try {
    // 先存檔，避免 DRI 忘記按「儲存」就直接送出，導致最後一次編輯遺失
    await apiSaveDraft(JOB_CODE, buildDraftPayload());
    state.case = await apiSubmitReview(JOB_CODE);
    state.dirty.clear();
    render();
    showToast('已送出主管審查');
  } catch (e) {
    showToast(e.message || '送出失敗');
  }
}

async function returnToDri() {
  if (!confirm('確定要退回給 DRI 修改嗎？')) return;
  const reason = prompt('退回理由（選填，留空可直接送出）：', '');
  if (reason === null) return;
  try {
    state.case = await apiReturnToDri(JOB_CODE, { comment: reason || undefined });
    render();
    showToast('已退回 DRI 修改');
  } catch (e) {
    showToast(e.message || '退回失敗');
  }
}

async function approveAndPublish() {
  if (!confirm('確定要核准並發布到案例庫嗎？')) return;
  try {
    state.case = await apiApprove(JOB_CODE);
    render();
    showToast('已核准並發布至案例庫');
  } catch (e) {
    showToast(e.message || '核准失敗');
  }
}

async function submitComment() {
  const input = document.getElementById('comment-input');
  const text = input.value.trim();
  if (!text) {
    showToast('請先輸入留言內容');
    return;
  }
  try {
    state.case = await apiAddComment(JOB_CODE, { authorRole: MODE === 'dri' ? 'DRI' : 'MANAGER', body: text });
    render();
    showToast('已送出留言');
  } catch (e) {
    showToast(e.message || '留言送出失敗');
  }
}

// ---------- init ----------
async function init() {
  if (!JOB_CODE) {
    document.getElementById('review-content').innerHTML = '<div class="section-heading">缺少案例 Job Code，請確認連結是否完整。</div>';
    return;
  }

  document.getElementById('review-content').innerHTML = '<div class="section-heading">載入中…</div>';
  try {
    state.case = await apiGetReviewCase(JOB_CODE);
  } catch (e) {
    document.getElementById('review-content').innerHTML = `<div class="section-heading">載入失敗：${escapeHtml(e.message)}</div>`;
    return;
  }
  render();
}

// ---------- events ----------
document.addEventListener('DOMContentLoaded', () => {
  init();

  document.addEventListener('input', (e) => {
    const t_ = e.target;
    if (t_.dataset.path) {
      const [tab, key] = t_.dataset.path.split('.');
      const f = state.case.detail[tab][key];
      f.current = t_.dataset.type === 'list'
        ? t_.value.split('\n').map((s) => s.trim()).filter(Boolean)
        : t_.value;
      state.dirty.add(t_.dataset.path);
      const block = t_.closest('.field-block');
      if (block) block.classList.add('dirty');
      return;
    }
    if (t_.dataset.kpiIdx !== undefined) {
      const idx = Number(t_.dataset.kpiIdx);
      state.case.detail.A.kpis[idx][t_.dataset.kpiField].current = t_.value;
      state.dirty.add(`A.kpis.${idx}.${t_.dataset.kpiField}`);
    }
  });

  document.addEventListener('click', (e) => {
    const tabBtn = e.target.closest('.tab-btn');
    if (tabBtn) { state.tab = tabBtn.dataset.tab; renderTabs(); renderContent(); return; }

    const actionBtn = e.target.closest('[data-action]');
    if (actionBtn && !actionBtn.disabled) {
      const action = actionBtn.dataset.action;
      if (action === 'save') saveAll();
      if (action === 'submit') submitReview();
      if (action === 'return') returnToDri();
      if (action === 'approve') approveAndPublish();
      if (action === 'comment') submitComment();
      return;
    }

    if (e.target.id === 'back-btn') {
      if (window.history.length > 1) window.history.back();
      else alert('這是 Demo 頁面，尚未串接實際返回目標。');
    }
  });
});
