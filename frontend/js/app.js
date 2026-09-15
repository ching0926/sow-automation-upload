// ============================================================
// 角色累加顯示規則 —— 這是修正 ui_v1.png 錯誤的核心設定
// 客戶只看 A；PM 看 A+B；SA 看 A+B+C。案例面板一律用同一份
// case.detail = {A,B,C} 資料，依此表決定要渲染哪些頁籤，
// 絕不對任一角色寫窄化/獨立的內容，避免重現「PM 只看到 B、
// SA 只看到 C」的錯誤。
// ============================================================
const ROLE_SECTIONS = {
  customer: ['A'],
  pm: ['A', 'B'],
  sa: ['A', 'B', 'C'],
};
const TAB_LABEL_KEY = { A: 'tab_a', B: 'tab_b', C: 'tab_c' };

const state = {
  lang: localStorage.getItem('skb_lang') || 'zh',
  role: localStorage.getItem('skb_role') || 'pm',
  view: 'list',
  appliedFilters: { industry: [], skill: [] },
  stagedFilters: { industry: [], skill: [] },
  sort: 'new',
  page: 1,
  pageSize: 16,
  search: '',
  previewId: null,
  previewTab: 'A',
  favorites: new Set(JSON.parse(localStorage.getItem('skb_favorites') || '[]')),
  recent: JSON.parse(localStorage.getItem('skb_recent') || '[]'),
};
let openFilterDim = null;

const ROLE_OWNER = {
  customer: { name: 'Alex Johnson', emoji: '🙂' },
  pm: { name: 'Christine Wang', emoji: '👩‍💼' },
  sa: { name: 'Christine Wang', emoji: '👩‍💻' },
};

function persist() {
  localStorage.setItem('skb_lang', state.lang);
  localStorage.setItem('skb_role', state.role);
  localStorage.setItem('skb_favorites', JSON.stringify([...state.favorites]));
  localStorage.setItem('skb_recent', JSON.stringify(state.recent));
}

function caseById(id) { return CASES.find(c => c.id === Number(id)); }

function getFilterOptions() {
  return {
    industry: [...new Set(CASES.map(c => c.industry))],
    skill: [...new Set(CASES.flatMap(c => c.skills))],
  };
}

function optionLabel(dim, code) {
  if (dim === 'industry') return code;
  if (dim === 'skill') return L('skill', code, state.lang);
  return code;
}

function matchesFilters(c, f) {
  if (f.industry.length && !f.industry.includes(c.industry)) return false;
  if (f.skill.length && !f.skill.some(s => c.skills.includes(s))) return false;
  return true;
}

function matchesSearch(c) {
  const q = state.search.trim().toLowerCase();
  if (!q) return true;
  const hay = [c.title.zh, c.title.en, c.description.zh, c.description.en, c.industry].join(' ').toLowerCase();
  return hay.includes(q);
}

function getFilteredSorted() {
  let list = CASES.filter(c => matchesFilters(c, state.appliedFilters) && matchesSearch(c));
  list = list.slice().sort((a, b) => state.sort === 'new' ? b.date.localeCompare(a.date) : a.date.localeCompare(b.date));
  return list;
}

// ---------- static i18n ----------
function applyStaticI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(state.lang, el.getAttribute('data-i18n')); });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(state.lang, el.getAttribute('data-i18n-placeholder')); });
}

function renderTopbarDynamic() {
  const roleSel = document.getElementById('role-select');
  [...roleSel.options].forEach(opt => { opt.textContent = t(state.lang, `role_${opt.value}`); });
  roleSel.value = state.role;
  document.getElementById('user-role').textContent = t(state.lang, `role_${state.role}`);
  document.getElementById('user-name').textContent = ROLE_OWNER[state.role].name;
  document.querySelector('.user-avatar').textContent = ROLE_OWNER[state.role].emoji;
  document.querySelectorAll('.topnav-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.view === state.view));
}

function showView(activeId) {
  ['view-list', 'view-favorites', 'view-recent'].forEach(id => {
    document.getElementById(id).classList.toggle('hidden', id !== activeId);
  });
}

// ---------- filter bar ----------
function renderFilterBar() {
  const opts = getFilterOptions();
  const dims = ['industry', 'skill'];
  const labelKeys = { industry: 'filter_industry', skill: 'filter_skill' };
  const html = dims.map(dim => {
    const selected = state.stagedFilters[dim];
    const chips = selected.map(v => `<span class="chip" data-chip-dim="${dim}" data-chip-value="${v}">${optionLabel(dim, v)}<span class="chip-x" data-remove-dim="${dim}" data-remove-value="${v}">✕</span></span>`).join('');
    const options = opts[dim].map(v => `
      <label class="filter-option">
        <input type="checkbox" data-dim="${dim}" value="${v}" ${selected.includes(v) ? 'checked' : ''}/>
        <span>${optionLabel(dim, v)}</span>
      </label>`).join('');
    return `
      <div class="filter-group">
        <label class="filter-label">${t(state.lang, labelKeys[dim])}</label>
        <div class="filter-box" data-box-dim="${dim}">
          <div class="filter-chips">${chips}</div>
          <span class="caret">▾</span>
        </div>
        <div class="filter-panel ${openFilterDim === dim ? '' : 'hidden'}" data-panel-dim="${dim}">${options}</div>
      </div>`;
  }).join('');
  document.getElementById('filter-groups').innerHTML = html;
}

// ---------- case card ----------
function renderCard(c) {
  const fav = state.favorites.has(c.id);
  const selectedCls = state.previewId === c.id ? 'selected' : '';
  return `
    <div class="case-card ${selectedCls}" data-card-id="${c.id}">
      <div class="card-top">
        <div class="card-icon">${c.icon}</div>
        <div class="card-industry">${c.industry}</div>
        <button class="star-btn ${fav ? 'active' : ''}" data-star-id="${c.id}">${fav ? '★' : '☆'}</button>
      </div>
      <div class="card-title">${c.title[state.lang]}</div>
      <div class="card-desc">${c.description[state.lang]}</div>
      <div class="card-date">${c.date}</div>
    </div>`;
}

function renderGridInto(containerId, list) {
  const el = document.getElementById(containerId);
  el.classList.toggle('grid-collapsed', !!state.previewId && containerId === 'case-grid');
  el.innerHTML = list.length ? list.map(renderCard).join('') : '';
}

// ---------- list view ----------
function renderListView() {
  const filtered = getFilteredSorted();
  const totalPages = Math.max(1, Math.ceil(filtered.length / state.pageSize));
  state.page = Math.min(state.page, totalPages);
  const start = (state.page - 1) * state.pageSize;
  const pageItems = filtered.slice(start, start + state.pageSize);

  document.getElementById('result-count').textContent = t(state.lang, 'total_count', filtered.length);
  renderGridInto('case-grid', pageItems);
  renderPagination(totalPages, filtered.length);
}

function renderPagination(totalPages, totalCount) {
  const el = document.getElementById('pagination');
  if (totalCount === 0) { el.innerHTML = ''; return; }
  let pageBtns = '';
  for (let i = 1; i <= totalPages; i++) {
    pageBtns += `<button class="page-btn ${i === state.page ? 'active' : ''}" data-page="${i}">${i}</button>`;
  }
  el.innerHTML = `
    <button class="page-nav" data-page-nav="prev" ${state.page === 1 ? 'disabled' : ''}>‹</button>
    ${pageBtns}
    <button class="page-nav" data-page-nav="next" ${state.page === totalPages ? 'disabled' : ''}>›</button>
    <span class="page-of">${t(state.lang, 'page_of', state.page, totalPages)}</span>
    <select id="page-size-select">
      ${[8, 16, 24].map(n => `<option value="${n}" ${n === state.pageSize ? 'selected' : ''}>${n} ${t(state.lang, 'page_size_suffix')}</option>`).join('')}
    </select>`;
}

// ---------- favorites / recent views ----------
function renderFavoritesView() {
  const list = CASES.filter(c => state.favorites.has(c.id));
  document.getElementById('favorites-count').textContent = t(state.lang, 'total_count', list.length);
  renderGridInto('favorites-grid', list);
  document.getElementById('favorites-empty').classList.toggle('hidden', list.length > 0);
}

function renderRecentView() {
  const list = state.recent.map(id => caseById(id)).filter(Boolean);
  document.getElementById('recent-count').textContent = t(state.lang, 'total_count', list.length);
  renderGridInto('recent-grid', list);
  document.getElementById('recent-empty').classList.toggle('hidden', list.length > 0);
}

function addToRecent(id) {
  state.recent = [id, ...state.recent.filter(x => x !== id)].slice(0, 20);
  persist();
}

// ---------- 角色累加內容：每個 tab 回傳 {sections:[{id,titleKey,body}]} ----------
function sectionsTabA(c) {
  const a = c.detail.A;
  return [
    { id: 'sec-industry-bg', titleKey: 'a_industry_bg', body: `<div class="section-card"><p>${a.industryBackground[state.lang]}</p></div>` },
    { id: 'sec-pain', titleKey: 'a_pain', body: `<div class="section-card"><p>${a.challenge[state.lang]}</p></div>` },
    { id: 'sec-aws-solution', titleKey: 'a_aws_solution', body: `<div class="section-card"><p>${a.solution[state.lang]}</p></div>` },
    {
      id: 'sec-benefits', titleKey: 'a_benefits', body: `
      <div class="kpi-row">
        ${a.kpis.map(k => `
          <div class="kpi-card">
            <div class="kpi-icon">${k.icon}</div>
            <div class="kpi-value">${k.value}</div>
            <div class="kpi-label">${k.label[state.lang]}</div>
          </div>`).join('')}
      </div>`,
    },
  ];
}

function sectionsTabB(c) {
  const b = c.detail.B;
  const statusRow = b.status
    ? `<div class="overview-item">🚦 <span>${t(state.lang, 'b_status')}</span><strong>${LABELS.status[b.status] ? LABELS.status[b.status][state.lang] : b.status}</strong></div>`
    : '';
  const sections = [
    {
      id: 'sec-dri', titleKey: 'b_dri', body: `
      <div class="overview-row">
        <div class="overview-item">👤 <span>${t(state.lang, 'b_dri')}</span><strong>${b.owner}</strong></div>
        <div class="overview-item">📅 <span>${t(state.lang, 'b_period')}</span><strong>${b.period}</strong></div>
        ${statusRow}
      </div>`,
    },
    {
      id: 'sec-team', titleKey: 'b_team', body: `
      <div class="team-row">
        <div class="team-chip">👥 ${state.lang === 'zh' ? '團隊總人數' : 'Total'} <strong>${b.teamSize} ${t(state.lang, 'b_person_unit')}</strong></div>
        ${(b.team || []).map(m => `<div class="team-chip">👤 ${L('role', m.role, state.lang)} <strong>${m.count}</strong></div>`).join('')}
      </div>`,
    },
    {
      id: 'sec-manday', titleKey: 'b_manday', body: `
      <div class="kpi-row kpi-row-single">
        <div class="kpi-card">
          <div class="kpi-icon">🗓️</div>
          <div class="kpi-value">${b.cost.manDays} ${t(state.lang, 'b_manday_unit')}</div>
          <div class="kpi-label">${t(state.lang, 'b_manday')}</div>
        </div>
      </div>`,
    },
    {
      id: 'sec-projcost', titleKey: 'b_projcost', body: `
      <div class="kpi-row kpi-row-single">
        <div class="kpi-card">
          <div class="kpi-icon">💰</div>
          <div class="kpi-value">${b.cost.total}</div>
          <div class="kpi-label">${t(state.lang, 'b_projcost')}</div>
        </div>
      </div>`,
    },
  ];
  if ((b.wbs || []).length) {
    sections.push({
      id: 'sec-wbs', titleKey: 'b_wbs', body: `
      <div class="wbs-row">
        ${b.wbs.map(w => `
          <div class="wbs-item ${w.ongoing ? 'ongoing' : ''}">
            <div class="wbs-phase">${L('wbsPhase', w.phase, state.lang)}</div>
            <div class="wbs-weeks">${w.weeks} ${state.lang === 'zh' ? '週' : 'wk'}</div>
            <div class="wbs-date">${w.date}</div>
          </div>`).join('')}
      </div>`,
    });
  }
  sections.push({
    id: 'sec-closing', titleKey: 'b_closing', body: `
      <ul class="bullet-list">${(b.deliverables || []).map(d => `<li>✔ ${L('deliverable', d, state.lang)}</li>`).join('')}</ul>`,
  });
  return sections;
}

const MODULE_NODES = ['ai_portal', 'n8n_workflow', 'claude_bedrock'];

function sectionsTabC(c) {
  const cc = c.detail.C;
  const keywords = [
    ...c.serviceCategory.map(s => L('service', s, state.lang)),
    ...c.useCase.map(s => L('usecase', s, state.lang)),
    ...c.skills.map(s => L('skill', s, state.lang)),
    c.industry,
  ];
  const modules = cc.architecture.filter(n => MODULE_NODES.includes(n));
  const sections = [
    {
      id: 'sec-corefunc', titleKey: 'c_corefunctions', body: `
      <div class="chip-row">${cc.coreFunctions.map(x => `<span class="tag tag-purple">${L('corefunction', x, state.lang)}</span>`).join('')}</div>`,
    },
  ];
  if (modules.length) {
    sections.push({
      id: 'sec-modules', titleKey: 'c_modules', body: `
      <div class="arch-row">
        ${modules.map(node => `
          <div class="arch-box">
            <div class="arch-name">${L('archNode', node, state.lang)} ${state.lang === 'zh' ? '模組' : 'Module'}</div>
            <ul>${(LABELS.archNodeDetail[node] ? LABELS.archNodeDetail[node][state.lang] : []).map(d => `<li>${d}</li>`).join('')}</ul>
          </div>`).join('')}
      </div>`,
    });
  }
  sections.push(
    {
      id: 'sec-techarch', titleKey: 'c_techarch', body: `
      <div class="arch-row">
        ${cc.architecture.map((node, i) => `
          ${i > 0 ? '<div class="arch-arrow">→</div>' : ''}
          <div class="arch-box">
            <div class="arch-name">${L('archNode', node, state.lang)}</div>
            <ul>${(LABELS.archNodeDetail[node] ? LABELS.archNodeDetail[node][state.lang] : []).map(d => `<li>${d}</li>`).join('')}</ul>
          </div>`).join('')}
      </div>
      <div class="chip-row" style="margin-top:10px">${cc.techStack.map(x => `<span class="tag tag-blue">${LABELS.techstack[x] || x}</span>`).join('')}</div>`,
    },
    {
      id: 'sec-keywords', titleKey: 'c_keywords', body: `
      <div class="chip-row">${keywords.map(k => `<span class="tag tag-gray">${k}</span>`).join('')}</div>`,
    },
  );
  return sections;
}

function sectionsForTab(c, tab) {
  if (tab === 'A') return sectionsTabA(c);
  if (tab === 'B') return sectionsTabB(c);
  if (tab === 'C') return sectionsTabC(c);
  return [];
}

// ---------- 案例面板（整併預覽與完整內容） ----------
function renderPanel() {
  const drawer = document.getElementById('preview-drawer');
  if (!state.previewId) {
    drawer.classList.add('hidden');
    drawer.classList.remove('fullscreen');
    drawer.innerHTML = '';
    return;
  }
  const c = caseById(state.previewId);
  const fav = state.favorites.has(c.id);
  const visibleSections = ROLE_SECTIONS[state.role];
  if (!visibleSections.includes(state.previewTab)) state.previewTab = visibleSections[0];

  const tabsHtml = visibleSections.length > 1 ? `
    <div class="detail-tabs" id="detail-tabs">
      ${visibleSections.map(sec => `<button class="tab-btn ${sec === state.previewTab ? 'active' : ''}" data-tab="${sec}">${t(state.lang, TAB_LABEL_KEY[sec])}</button>`).join('')}
    </div>` : '';

  const sections = sectionsForTab(c, state.previewTab);
  const quicklinksHtml = `<div class="quicklinks">${sections.map(s => `<button class="quicklink-btn" data-scrollto="${s.id}">${t(state.lang, s.titleKey)}</button>`).join('')}</div>`;
  const contentHtml = sections.map(s => `<div class="panel-section" id="${s.id}"><div class="section-title standalone">${t(state.lang, s.titleKey)}</div>${s.body}</div>`).join('');

  const isFullscreen = drawer.classList.contains('fullscreen');
  const headerBtns = isFullscreen
    ? `<button class="icon-btn back" id="preview-back-btn">‹ ${t(state.lang, 'panel_back')}</button>
       <button class="icon-btn" id="preview-close-x">✕</button>`
    : `<button class="icon-btn" id="preview-fullscreen-btn">⛶</button>
       <button class="icon-btn" id="preview-close-x">✕</button>`;

  drawer.classList.remove('hidden');
  drawer.innerHTML = `
    <div class="preview-header">
      ${headerBtns}
    </div>
    <div class="preview-body">
      <div class="reading-column">
        <div class="preview-icon-row">
          <div class="preview-icon">${c.icon}</div>
          <div class="preview-industry">${c.industry}</div>
          <button class="star-btn ${fav ? 'active' : ''}" data-star-id="${c.id}" style="margin-left:auto">${fav ? '★' : '☆'}</button>
        </div>
        <h2 class="preview-title">${c.title[state.lang]}</h2>
        <p class="preview-desc">${c.description[state.lang]}</p>
        <div class="preview-meta">
          <span>${t(state.lang, 'preview_uploaded')}：${c.date}</span>
          <span>${t(state.lang, 'preview_creator')}：${c.creator}</span>
        </div>
        <div class="role-hint">ℹ️ ${I18N[state.lang].role_scope_hint[state.role]}</div>
        ${tabsHtml}
        <div class="panel-content" id="panel-content">
          ${quicklinksHtml}
          ${contentHtml}
        </div>
      </div>
    </div>`;
}

// ---------- master render ----------
function render() {
  applyStaticI18n();
  renderTopbarDynamic();
  renderFilterBar();
  if (state.view === 'list') { showView('view-list'); renderListView(); }
  if (state.view === 'favorites') { showView('view-favorites'); renderFavoritesView(); }
  if (state.view === 'recent') { showView('view-recent'); renderRecentView(); }
  renderPanel();
}

// ---------- events ----------
function openPanel(id) {
  state.previewId = Number(id);
  addToRecent(Number(id));
  render();
}
function closePanel() { state.previewId = null; render(); }
function toggleFavorite(id) {
  id = Number(id);
  if (state.favorites.has(id)) state.favorites.delete(id); else state.favorites.add(id);
  persist();
  render();
}

document.addEventListener('DOMContentLoaded', async () => {
  try {
    await loadCases();
  } catch (err) {
    console.error(err);
  }
  render();

  document.addEventListener('click', (e) => {
    const t_ = e.target;

    // top nav
    const navBtn = t_.closest('.topnav-btn');
    if (navBtn) { state.view = navBtn.dataset.view; render(); return; }

    // lang toggle
    if (t_.id === 'lang-btn') {
      state.lang = state.lang === 'zh' ? 'en' : 'zh';
      persist(); render(); return;
    }

    // filter box open/close
    const box = t_.closest('.filter-box');
    if (box) { openFilterDim = openFilterDim === box.dataset.boxDim ? null : box.dataset.boxDim; renderFilterBar(); return; }

    // chip remove
    const removeBtn = t_.closest('.chip-x');
    if (removeBtn) {
      const dim = removeBtn.dataset.removeDim, val = removeBtn.dataset.removeValue;
      state.stagedFilters[dim] = state.stagedFilters[dim].filter(v => v !== val);
      renderFilterBar(); return;
    }

    // filter clear all
    if (t_.id === 'filter-clear') {
      state.stagedFilters = { industry: [], skill: [] };
      state.appliedFilters = { industry: [], skill: [] };
      state.page = 1;
      render(); return;
    }
    // filter apply
    if (t_.id === 'filter-apply') {
      state.appliedFilters = JSON.parse(JSON.stringify(state.stagedFilters));
      state.page = 1; openFilterDim = null;
      render(); return;
    }

    // star toggle
    const starBtn = t_.closest('.star-btn');
    if (starBtn) { toggleFavorite(starBtn.dataset.starId); return; }

    // pagination
    const pageBtn = t_.closest('.page-btn');
    if (pageBtn) { state.page = Number(pageBtn.dataset.page); render(); return; }
    const pageNav = t_.closest('.page-nav');
    if (pageNav && !pageNav.disabled) {
      state.page += pageNav.dataset.pageNav === 'prev' ? -1 : 1;
      render(); return;
    }

    // panel controls
    if (t_.id === 'preview-close-x') { closePanel(); return; }
    if (t_.id === 'preview-fullscreen-btn') { document.getElementById('preview-drawer').classList.add('fullscreen'); renderPanel(); return; }
    if (t_.id === 'preview-back-btn') { document.getElementById('preview-drawer').classList.remove('fullscreen'); renderPanel(); return; }
    const tabBtn = t_.closest('.tab-btn');
    if (tabBtn) { state.previewTab = tabBtn.dataset.tab; renderPanel(); return; }
    const quicklinkBtn = t_.closest('.quicklink-btn');
    if (quicklinkBtn) {
      const target = document.getElementById(quicklinkBtn.dataset.scrollto);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }

    // card click -> open panel (ignore clicks on star, already handled above)
    const card = t_.closest('.case-card');
    if (card) { openPanel(card.dataset.cardId); return; }

    // close open filter panel when clicking elsewhere
    if (!t_.closest('.filter-group') && openFilterDim) { openFilterDim = null; renderFilterBar(); }
  });

  document.addEventListener('change', (e) => {
    const t_ = e.target;
    if (t_.matches('[data-dim]')) {
      const dim = t_.dataset.dim, val = t_.value;
      const set = new Set(state.stagedFilters[dim]);
      t_.checked ? set.add(val) : set.delete(val);
      state.stagedFilters[dim] = [...set];
      renderFilterBar(); return;
    }
    if (t_.id === 'role-select') { state.role = t_.value; persist(); render(); return; }
    if (t_.id === 'sort-select') { state.sort = t_.value; render(); return; }
    if (t_.id === 'page-size-select') { state.pageSize = Number(t_.value); state.page = 1; render(); return; }
  });

  document.getElementById('search-input').addEventListener('input', (e) => {
    state.search = e.target.value;
    state.page = 1;
    render();
  });
});
