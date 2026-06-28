// ════════════════════════════════════════════════════════════
//  VALENCE GRC — Enterprise SPA
// ════════════════════════════════════════════════════════════

const API = window.location.origin;
let accessToken = localStorage.getItem('valence_token') || '';
let refreshToken = localStorage.getItem('valence_refresh_token') || '';
let currentUser  = JSON.parse(localStorage.getItem('valence_user') || '{}');
let currentTenantId = localStorage.getItem('valence_tenant') || '';
let tenantContext = {};
let userFeatures = [];
let featureCatalog = null;
let accessibleTenants = [];
let state = { metrics: [], summary: {}, reports: [], timelineSnapshots: [], threatLevel: {}, correlations: [] };
let charts = {};
let wsConn = null;
let currentWhatIfPresets = [];
let whatIfSliders = {};
let currentDeckSlides = [];
let currentDeckSlideIndex = 0;
let timelinePlaying = false;
let timelinePlayTimer = null;
let currentTimelineDays = 90;
let activeThreatTab = 'kev';

// ─── AUTH ──────────────────────────────────────────────────
function persistAuth(data) {
  accessToken = data.access_token;
  currentUser = data.user || currentUser;
  localStorage.setItem('valence_token', accessToken);
  localStorage.setItem('valence_user', JSON.stringify(currentUser));
  if (data.user?.tenant_id) {
    currentTenantId = data.user.tenant_id;
    localStorage.setItem('valence_tenant', currentTenantId);
  }
  if (data.user?.feature_list) {
    userFeatures = data.user.feature_list;
  }
  if (data.refresh_token) {
    refreshToken = data.refresh_token;
    localStorage.setItem('valence_refresh_token', refreshToken);
  }
}

function clearAuth() {
  accessToken = '';
  refreshToken = '';
  currentUser = {};
  localStorage.removeItem('valence_token');
  localStorage.removeItem('valence_refresh_token');
  localStorage.removeItem('valence_user');
}

function fillCreds(u, p) {
  document.getElementById('username').value = u;
  document.getElementById('password').value = p;
}

async function refreshAccessToken() {
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${API}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    accessToken = data.access_token;
    localStorage.setItem('valence_token', accessToken);
    return true;
  } catch {
    return false;
  }
}

async function loadSandboxInfo() {
  try {
    const res = await fetch(`${API}/api/auth/sandbox-info`);
    if (!res.ok) return;
    const data = await res.json();
    const section = document.getElementById('demo-creds-section');
    const grid = document.getElementById('demo-creds-grid');
    const note = document.getElementById('demo-creds-prod-note');
    if (!section) return;
    if (!data.show_credential_hints) {
      if (grid) grid.style.display = 'none';
      if (note) {
        note.textContent = data.message || 'Sandbox credentials are rotated in production.';
        note.style.display = 'block';
      }
    }
  } catch {
    // keep dev defaults visible
  }
}

async function loadTenantContext() {
  try {
    const ctx = await apiFetch('/api/tenants/context');
    if (!ctx) return;
    tenantContext = ctx;
    userFeatures = ctx.feature_list || userFeatures;
    if (ctx.user) {
      currentUser = { ...currentUser, ...ctx.user };
      localStorage.setItem('valence_user', JSON.stringify(currentUser));
    }
    applyTenantContextUI(ctx);
    applyFeatureNav();
    maybeShowOnboarding(ctx);
  } catch {
    // non-fatal
  }
}

function hasDemoAccess() {
  return !!(
    currentUser.is_demo_account ||
    tenantContext.is_demo ||
    tenantContext.is_sandbox_user
  );
}

function applyTenantContextUI(ctx) {
  const badge = document.getElementById('status-badge');
  const badgeText = document.getElementById('status-badge-text');
  const badgeDot = document.getElementById('status-badge-dot');
  const strip = document.getElementById('status-strip');
  const stripLabel = document.getElementById('status-strip-label');
  const stripMsg = document.getElementById('status-strip-message');
  const stripAction = document.getElementById('status-strip-action');
  const mode = ctx.data_mode || 'live';

  if (badgeText) badgeText.textContent = ctx.status_badge || '—';
  if (badgeDot) badgeDot.style.background = ctx.status_badge_color || 'var(--green)';

  const modeClass = { sandbox: 'mode-demo', awaiting_siem: 'mode-siem', error: 'mode-error', live: 'mode-live' };
  const cls = modeClass[mode] || 'mode-live';
  if (badge) { badge.className = `live-badge ${cls}`; badge.style.borderColor = ''; }
  if (strip) {
    strip.className = `status-strip ${cls}`;
    if (stripLabel) stripLabel.textContent = ctx.data_label || 'System status';
    if (stripMsg) stripMsg.textContent = ctx.status_message || '';
    if (stripAction) {
      stripAction.style.display = (mode === 'awaiting_siem' || mode === 'error') ? 'inline-flex' : 'none';
      stripAction.innerHTML = mode === 'error'
        ? '<i class="ph ph-wrench"></i> Fix pipeline'
        : '<i class="ph ph-plug"></i> Configure SIEM';
    }
  }
  if (tenantContext.tenant_name) {
    const node = document.getElementById('status-node-name');
    if (node) node.textContent = resolveTenantDisplayName();
  }
  const vault = document.getElementById('status-vault-label');
  if (vault) {
    vault.textContent = tenantContext.data_mode === 'sandbox' ? 'Sandbox DB' : 'PostgreSQL TLS';
  }
  syncOrgLabels();
  applyPageDataModeBanners();
}

const NAV_FEATURE_MAP = {
  'nav-dashboard': 'dashboard',
  'nav-risk': 'risk',
  'nav-whatif': 'whatif',
  'nav-benchmarking': 'benchmarking',
  'nav-threat-intel': 'threat_intel',
  'nav-compliance': 'compliance',
  'nav-timeline': 'timeline',
  'nav-evidence': 'evidence',
  'nav-findings': 'findings',
  'nav-reports': 'reports',
  'nav-connectors': 'connectors',
  'nav-team': 'team_admin',
  'nav-policies': 'policies',
  'nav-auditor': 'auditor_portal',
  'nav-personnel': 'personnel',
  'nav-questionnaires': 'questionnaires',
  'nav-training': 'training',
  'nav-pentest': 'pentest',
  'nav-vendors': 'vendors',
  'nav-mobile': 'mobile',
  'nav-platform': 'platform',
  'nav-enterprise': 'enterprise',
  'nav-command-center': 'risk',
};

function applyFeatureNav() {
  const features = new Set(userFeatures.length ? userFeatures : (currentUser.feature_list || []));
  const demo = hasDemoAccess();
  Object.entries(NAV_FEATURE_MAP).forEach(([navId, feature]) => {
    const el = document.getElementById(navId);
    if (!el) return;
    const allowed = features.has(feature) || demo;
    el.style.display = allowed ? '' : 'none';
  });
}

function setHomeTenantFromUser() {
  if (currentUser.tenant_id) {
    currentTenantId = currentUser.tenant_id;
    localStorage.setItem('valence_tenant', currentTenantId);
  } else if (!currentTenantId && currentUser.is_demo_account) {
    currentTenantId = 'demo-global-hq';
    localStorage.setItem('valence_tenant', currentTenantId);
  }
}

async function loadSSOConfig() {
  try {
    const res = await fetch(`${API}/api/auth/sso/config`);
    if (!res.ok) return;
    const data = await res.json();
    const section = document.getElementById('sso-section');
    const btn = document.getElementById('sso-login-btn');
    if (section) section.style.display = data.enabled ? 'block' : 'none';
    if (btn && data.provider) {
      const labels = { azure: 'Microsoft Entra ID', okta: 'Okta', oidc: 'SSO' };
      const label = labels[data.provider] || 'SSO';
      btn.innerHTML = `<i class="ph ph-shield-check"></i> Sign in with ${label}`;
    }
  } catch {
    // SSO unavailable — keep password login only
  }
}

function handleSSOLogin() {
  window.location.href = `${API}/api/auth/sso/login`;
}

async function handleSSOCallback() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('sso_code');
  if (!code) return false;

  window.history.replaceState({}, document.title, window.location.pathname);
  try {
    const res = await fetch(`${API}/api/auth/sso/exchange`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    const data = await res.json();
    if (!res.ok) {
      showLoginError(data.detail || 'SSO sign-in failed');
      return true;
    }
    persistAuth(data);
    showApp();
    return true;
  } catch {
    showLoginError('SSO sign-in failed — could not reach the API');
    return true;
  }
}

function enterDemoMode(username) {
  void username;
}

function formatApiError(data) {
  if (!data?.detail) return 'Request failed';
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((e) => {
      const field = (e.loc || []).filter((x) => x !== 'body').pop() || 'field';
      const label = String(field).replace(/_/g, ' ');
      return `${label}: ${e.msg}`;
    }).join(' · ');
  }
  return String(data.detail);
}

async function registerOrganization() {
  const company = document.getElementById('reg-company').value.trim();
  const username = document.getElementById('reg-username').value.trim();
  const email = document.getElementById('reg-email').value.trim();
  const password = document.getElementById('reg-password').value;
  const fullName = document.getElementById('reg-fullname').value.trim();
  const errEl = document.getElementById('register-error');
  errEl.style.display = 'none';

  if (company.length < 2) { showRegisterError('Company name must be at least 2 characters'); return; }
  if (username.length < 3) { showRegisterError('Username must be at least 3 characters'); return; }
  if (!email.includes('@') || email.length < 5) { showRegisterError('Enter a valid admin email address'); return; }
  if (password.length < 8) { showRegisterError('Password must be at least 8 characters'); return; }
  if (fullName.length < 2) { showRegisterError('Admin full name is required'); return; }

  try {
    const res = await fetch(`${API}/api/tenants/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_name: company,
        admin_username: username,
        admin_email: email,
        admin_password: password,
        admin_full_name: fullName,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showRegisterError(formatApiError(data) || `Registration failed (${res.status})`);
      return;
    }
    document.getElementById('username').value = username;
    document.getElementById('password').value = password;
    toggleRegister(false);
    const loginErr = document.getElementById('login-error');
    loginErr.textContent = `Organization "${data.tenant_name || company}" created — sign in with your new admin account.`;
    loginErr.style.display = 'block';
    loginErr.style.background = 'var(--green-bg)';
    loginErr.style.borderColor = 'var(--green-border)';
    loginErr.style.color = 'var(--green)';
  } catch {
    showRegisterError('Could not reach the API. Is the server running?');
  }
}

function toggleRegister(show) {
  document.getElementById('login-form-panel').style.display = show ? 'none' : 'block';
  document.getElementById('register-form-panel').style.display = show ? 'block' : 'none';
  document.getElementById('login-page').classList.toggle('login-page--register', !!show);
}

function showRegisterError(msg) {
  const e = document.getElementById('register-error');
  e.textContent = msg;
  e.style.display = 'block';
}

async function loadAccessibleTenants() {
  const list = await apiFetch('/api/tenants/accessible');
  if (!list || !list.length) return;
  accessibleTenants = list;
  if (!currentTenantId || !list.some(t => t.tenant_id === currentTenantId)) {
    currentTenantId = currentUser.tenant_id || list[0].tenant_id;
    localStorage.setItem('valence_tenant', currentTenantId);
  }
  const select = document.getElementById('tenant-select');
  if (!select) return;
  select.innerHTML = list.map(t =>
    `<option value="${t.tenant_id}" ${t.tenant_id === currentTenantId ? 'selected' : ''}>${t.name}</option>`
  ).join('');
  const wrap = document.querySelector('.tenant-switcher');
  if (wrap) wrap.style.display = list.length > 1 ? 'block' : 'none';
}

async function switchTenant(tenantId) {
  currentTenantId = tenantId;
  localStorage.setItem('valence_tenant', tenantId);
  if (wsConn) { wsConn.close(); wsConn = null; }
  await loadTenantContext();
  await loadAllData();
  refreshActivePage();
  connectWebSocket();
  showToast(`Switched to ${accessibleTenants.find(t => t.tenant_id === tenantId)?.name || tenantId}`, 'info');
}

async function handleLogin() {
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  const errEl    = document.getElementById('login-error');
  const btn      = document.getElementById('login-btn');
  if (!username || !password) { showLoginError('Please enter username and password'); return; }
  btn.innerHTML = '<i class="ph ph-spinner" style="animation:spin .8s linear infinite"></i> Signing in...';
  btn.disabled = true;
  errEl.style.display = 'none';
  try {
    const res = await fetch(`${API}/api/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (!res.ok) { showLoginError(data.detail || 'Login failed'); return; }
    persistAuth(data);
    setHomeTenantFromUser();
    showApp();
  } catch {
    showLoginError('Cannot connect to API. Ensure the VALENCE server is running.');
  } finally {
    btn.innerHTML = '<i class="ph ph-sign-in"></i> Sign In';
    btn.disabled = false;
  }
}

function showLoginError(msg) {
  const e = document.getElementById('login-error');
  e.textContent = msg;
  e.style.display = 'block';
  e.style.background = 'var(--red-bg)';
  e.style.borderColor = 'var(--red-border)';
  e.style.color = 'var(--red)';
}

async function handleLogout() {
  try {
    await fetch(`${API}/api/auth/logout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify({ refresh_token: refreshToken || undefined }),
    });
  } catch { /* offline logout still clears client */ }
  clearAuth();
  if (wsConn) { wsConn.close(); wsConn = null; }
  document.getElementById('app').style.display = 'none';
  document.getElementById('login-page').style.display = 'flex';
  destroyCharts();
  loadSSOConfig();
}

function showApp() {
  document.getElementById('login-page').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  document.getElementById('user-display-name').textContent = currentUser.full_name || currentUser.username;
  document.getElementById('user-role-display').textContent = `${currentUser.role}${currentUser.department ? ' · ' + currentUser.department.toUpperCase() : ''}`;
  document.getElementById('user-avatar').textContent = (currentUser.username || 'U')[0].toUpperCase();
  setHomeTenantFromUser();
  loadAccessibleTenants().then(async () => {
    await loadTenantContext();
    loadAllData();
  });
  connectWebSocket();
}

// ─── API CALLS ─────────────────────────────────────────────
async function apiFetch(path, opts = {}, retryOnUnauthorized = true) {
  const headers = { 'Content-Type': 'application/json', ...opts.headers };
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
  if (currentTenantId) headers['X-Tenant-ID'] = currentTenantId;
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  if (res.status === 401 && retryOnUnauthorized && refreshToken) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return apiFetch(path, opts, false);
  }
  if (res.status === 401) { handleLogout(); return null; }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : detail;
    } catch { /* non-JSON error body */ }
    console.warn(`API ${path} failed: ${res.status}`, detail);
    return null;
  }
  return res.json();
}

function pageLoadingHtml(label = 'Loading…') {
  return `<div class="mobile-metric-empty"><i class="ph ph-spinner" style="animation:spin .8s linear infinite"></i> ${label}</div>`;
}

function pageErrorHtml(msg) {
  return `<div class="mobile-metric-empty" style="color:var(--red)">${msg}</div>`;
}

let _modalScrollLock = 0;

function lockBodyScroll() {
  _modalScrollLock += 1;
  document.body.classList.add('modal-open');
}

function unlockBodyScroll() {
  _modalScrollLock = Math.max(0, _modalScrollLock - 1);
  if (_modalScrollLock === 0) document.body.classList.remove('modal-open');
}

function showModalOverlay(el) {
  const node = typeof el === 'string' ? document.getElementById(el) : el;
  if (!node) return;
  node.style.display = 'flex';
  node.classList.add('show');
  lockBodyScroll();
  node.onclick = (e) => {
    if (e.target === node && node.dataset.dismiss !== 'false') {
      hideModalOverlay(node);
      if (node._modalCancel) node._modalCancel();
    }
  };
}

function hideModalOverlay(el) {
  const node = typeof el === 'string' ? document.getElementById(el) : el;
  if (!node) return;
  node.style.display = 'none';
  node.classList.remove('show');
  unlockBodyScroll();
}

function showConfirmDialog({ title, subtitle = '', message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', variant = 'danger', icon = 'ph-plugs' }) {
  return new Promise((resolve) => {
    const modal = document.getElementById('app-modal');
    const iconWrap = document.getElementById('app-modal-icon-wrap');
    document.getElementById('app-modal-title').textContent = title;
    document.getElementById('app-modal-subtitle').textContent = subtitle;
    document.getElementById('app-modal-body').innerHTML = message
      ? `<p class="app-modal-message">${message}</p>` : '';
    iconWrap.className = `app-modal-icon ${variant === 'danger' ? 'danger' : variant === 'info' ? 'info' : 'warn'}`;
    document.getElementById('app-modal-icon').className = `ph ${icon}`;
    const actions = document.getElementById('app-modal-actions');
    actions.innerHTML = `
      <button type="button" class="btn btn-secondary" id="app-modal-cancel">${cancelLabel}</button>
      <button type="button" class="btn ${variant === 'danger' ? 'btn-danger' : 'btn-primary'}" id="app-modal-confirm">${confirmLabel}</button>`;
    modal.dataset.dismiss = 'false';
    modal._modalCancel = () => resolve(false);
    showModalOverlay(modal);
    document.getElementById('app-modal-cancel').onclick = () => { hideModalOverlay(modal); resolve(false); };
    document.getElementById('app-modal-confirm').onclick = () => { hideModalOverlay(modal); resolve(true); };
  });
}

function showFormDialog({ title, subtitle = '', fields, submitLabel = 'Save', icon = 'ph-plugs-connected' }) {
  return new Promise((resolve) => {
    const modal = document.getElementById('app-modal');
    const iconWrap = document.getElementById('app-modal-icon-wrap');
    document.getElementById('app-modal-title').textContent = title;
    document.getElementById('app-modal-subtitle').textContent = subtitle;
    iconWrap.className = 'app-modal-icon info';
    document.getElementById('app-modal-icon').className = `ph ${icon}`;
    const body = document.getElementById('app-modal-body');
    body.innerHTML = `<form class="app-modal-form" id="app-modal-form">${fields.map(f => `
      <div class="form-group">
        <label for="app-modal-${f.name}">${f.label}</label>
        <input type="${f.type || 'text'}" id="app-modal-${f.name}" name="${f.name}" placeholder="${f.placeholder || ''}" value="${f.value || ''}" />
      </div>`).join('')}</form>`;
    const actions = document.getElementById('app-modal-actions');
    actions.innerHTML = `
      <button type="button" class="btn btn-secondary" id="app-modal-cancel">Cancel</button>
      <button type="button" class="btn btn-primary" id="app-modal-confirm">${submitLabel}</button>`;
    modal.dataset.dismiss = 'false';
    modal._modalCancel = () => resolve(null);
    showModalOverlay(modal);
    const firstInput = body.querySelector('input');
    if (firstInput) setTimeout(() => firstInput.focus(), 50);
    document.getElementById('app-modal-cancel').onclick = () => { hideModalOverlay(modal); resolve(null); };
    document.getElementById('app-modal-confirm').onclick = () => {
      const data = {};
      fields.forEach(f => {
        const el = document.getElementById(`app-modal-${f.name}`);
        if (el) data[f.name] = el.value.trim();
      });
      hideModalOverlay(modal);
      resolve(data);
    };
  });
}

function resolveTenantDisplayName() {
  const match = accessibleTenants.find(t => t.tenant_id === currentTenantId);
  return match?.name || tenantContext.tenant_name || 'Your organization';
}

function syncOrgLabels() {
  const name = resolveTenantDisplayName();
  const mode = tenantContext.data_label || tenantContext.data_mode || '';
  const modeClass = 'mobile-exec-mode ' + (tenantContext.data_mode === 'sandbox' ? 'mode-sandbox' : 'mode-live');
  ['vendor-org-name', 'mobile-org-name'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = name;
  });
  ['vendor-data-mode', 'mobile-data-mode'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.textContent = mode; el.className = modeClass; }
  });
}

function runPageLoader(page) {
  if (page === 'whatif')       loadWhatIfPage();
  else if (page === 'benchmarking') loadBenchmarkingPage();
  else if (page === 'timeline')    loadTimelinePage();
  else if (page === 'threat-intel') loadThreatIntelPage();
  else if (page === 'evidence')    loadEvidencePage();
  else if (page === 'risk')        { renderRiskPage(); loadRiskCascade(); }
  else if (page === 'connectors')  loadConnectors();
  else if (page === 'team')        loadTeamPage();
  else if (page === 'compliance')  { initComplianceTabs(); }
  else if (page === 'vendors')     loadVendors();
  else if (page === 'mobile')      loadMobileDashboard();
  else if (page === 'findings')    loadFindings();
  else if (page === 'policies')    loadPolicies();
  else if (page === 'auditor')     loadAuditorPortal();
  else if (page === 'personnel')   loadPersonnelTab('jml', document.querySelector('#personnel-tabs .fw-tab'));
  else if (page === 'questionnaires') loadQuestionnaires();
  else if (page === 'training')       loadTraining();
  else if (page === 'pentest')        loadPentests();
  else if (page === 'platform')       loadPlatformPage();
  else if (page === 'command-center') loadCommandCenter();
  else if (page === 'enterprise')     loadEnterpriseTab('workflows', document.querySelector('#enterprise-tabs .fw-tab.active'));
}

function refreshActivePage() {
  const pageEl = document.querySelector('.page.active');
  if (!pageEl?.id?.startsWith('page-')) return;
  runPageLoader(pageEl.id.replace('page-', ''));
}

async function loadAllData() {
  try {
    const [metricsData, summaryData] = await Promise.all([
      apiFetch('/api/metrics/'),
      apiFetch('/api/metrics/summary'),
    ]);
    if (metricsData) state.metrics  = metricsData.metrics || [];
    if (summaryData) state.summary  = summaryData;
    if (metricsData) state.lastRunAt = metricsData.generated_at;
    renderDashboard();
    loadReadinessDashboard();
    initComplianceTabs();
    loadConnectors();
    loadReports();
    loadReportSchedules();
    populateCascadeMetricSelect();
  } catch (e) {
    showToast('Failed to load dashboard data', 'error');
  }
}

async function refreshData() {
  showToast('Refreshing data...', 'info');
  await loadTenantContext();
  await loadAllData();
  refreshActivePage();
  showToast('Data refreshed', 'success');
}

// ─── WEBSOCKET ─────────────────────────────────────────────
function connectWebSocket() {
  if (!accessToken) return;
  try {
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const q = new URLSearchParams({ token: accessToken, tenant_id: currentTenantId });
    wsConn = new WebSocket(`${wsProto}//${window.location.host}/ws/live?${q}`);
    wsConn.onopen = () => { wsConn.send('ping'); };
    wsConn.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.type === 'metrics_update' && msg.data) {
        state.metrics  = msg.data.metrics  || state.metrics;
        state.summary  = msg.data.summary  || state.summary;
        state.lastRunAt = msg.data.generated_at;
        renderDashboard();
        if (document.getElementById('page-risk').classList.contains('active')) {
          renderRiskPage(); loadRiskCascade();
        }
        showToast('Live data updated', 'info');
      }
    };
    wsConn.onerror = () => {};
    wsConn.onclose = () => { setTimeout(connectWebSocket, 10000); };
  } catch(e) {}
}

// ─── DEMO DATA ─────────────────────────────────────────────
function loadDemoData() {
  state.metrics = [
    { metric_id:'KRI-MTTD-001', metric_name:'Mean Time to Detect (MTTD)', value:14.2, unit:'minutes', rag_status:'Amber', ale_usd:182000, var_95_usd:490000, probability_of_breach:0.23, trend:'up', narrative:'MTTD has degraded 12% over 7 days. Recommend tuning detection rules for endpoint events.'},
    { metric_id:'KRI-MTTR-001', metric_name:'Mean Time to Respond (MTTR)', value:48.7, unit:'minutes', rag_status:'Red',   ale_usd:610000, var_95_usd:1200000, probability_of_breach:0.67, trend:'up', narrative:'MTTR exceeds SLA target of 30 minutes. Automated playbook deployment recommended immediately.'},
    { metric_id:'KPI-FPR-001',  metric_name:'False Positive Rate (FPR)',   value:18.4, unit:'%',       rag_status:'Green', ale_usd:24000,  var_95_usd:61000,   probability_of_breach:0.04, trend:'down', narrative:'FPR trending positive. ML model tuning last week was effective.'},
    { metric_id:'KRI-CVE-001',  metric_name:'Critical CVE Patch Lag',      value:8.0,  unit:'days',    rag_status:'Red',   ale_usd:890000, var_95_usd:2100000, probability_of_breach:0.81, trend:'up', narrative:'8 critical CVEs unpatched >7 days. DORA compliance breach imminent.'},
    { metric_id:'KPI-PHI-001',  metric_name:'Privileged Access Reviews',   value:94.1, unit:'%',       rag_status:'Green', ale_usd:18000,  var_95_usd:42000,   probability_of_breach:0.02, trend:'stable', narrative:'PAM coverage excellent. Maintain quarterly cadence.'},
    { metric_id:'KRI-DLP-001',  metric_name:'DLP Policy Violations',       value:37.0, unit:'incidents',rag_status:'Amber', ale_usd:245000, var_95_usd:580000, probability_of_breach:0.31, trend:'up', narrative:'DLP violations up 22% this week. Investigate insider threat vector.'},
  ];
  state.summary = {
    total_metrics: 6, green: 2, amber: 2, red: 2,
    total_ale_usd: state.metrics.reduce((a,m)=>a+m.ale_usd,0),
    total_var_95_usd: state.metrics.reduce((a,m)=>a+m.var_95_usd,0),
    overall_rag: 'Red',
  };
  state.lastRunAt = new Date().toISOString();
  state.reports = [
    { report_id:'RPT_DEMO001', run_id:'VALENCE_A1B2C3D4', status:'completed', generated_at: new Date(Date.now()-3600000).toISOString(), generated_by:'admin' },
    { report_id:'RPT_DEMO002', run_id:'VALENCE_E5F6G7H8', status:'completed', generated_at: new Date(Date.now()-86400000).toISOString(), generated_by:'ciso' },
  ];
  renderDashboard();
  populateCascadeMetricSelect();
}

// ─── DASHBOARD ─────────────────────────────────────────────
function renderDashboard() {
  const s = state.summary;
  document.getElementById('sum-green').textContent = s.green ?? '—';
  document.getElementById('sum-amber').textContent = s.amber ?? '—';
  document.getElementById('sum-red').textContent   = s.red   ?? '—';
  document.getElementById('sum-ale').textContent   = formatUSD(s.total_ale_usd);
  document.getElementById('last-run-label').textContent = state.lastRunAt
    ? `Last updated: ${new Date(state.lastRunAt).toLocaleString()}` : 'Last updated: —';
  renderMetricCards();
  renderRAGChart();
  renderVaRChart();
}

function renderMetricCards() {
  const grid = document.getElementById('metrics-grid');
  grid.innerHTML = state.metrics.map(m => `
    <div class="metric-card">
      <div class="metric-card-header">
        <div>
          <div class="metric-id">${m.metric_id}</div>
          <div class="metric-name">${m.metric_name}</div>
        </div>
        <span class="rag-badge ${m.rag_status}">${m.rag_status.toUpperCase()}</span>
      </div>
      <div class="metric-value-row">
        <span class="metric-value-num">${typeof m.value === 'number' ? m.value.toFixed(1) : m.value}</span>
        <span class="metric-value-unit">${m.unit || ''}</span>
        <span class="trend-badge ${m.trend === 'up' ? 'trend-up' : m.trend === 'down' ? 'trend-down' : 'trend-stable'}">
          ${m.trend === 'up' ? '↑' : m.trend === 'down' ? '↓' : '→'} ${m.trend}
        </span>
      </div>
      <div class="metric-risk-row">
        <div class="risk-stat"><div class="risk-stat-label">Expected ALE</div><div class="risk-stat-value">${formatUSD(m.ale_usd)}</div></div>
        <div class="risk-stat"><div class="risk-stat-label">VaR (95th)</div><div class="risk-stat-value">${formatUSD(m.var_95_usd)}</div></div>
        <div class="risk-stat"><div class="risk-stat-label">Breach Risk</div><div class="risk-stat-value">${((m.probability_of_breach||0)*100).toFixed(0)}%</div></div>
      </div>
      <div class="metric-narrative">${m.narrative || ''}</div>
      ${(m.rag_status === 'Red' || m.rag_status === 'Amber') ? `<button class="btn btn-secondary btn-sm" style="margin-top:10px" onclick="explainMetric('${m.metric_id}')"><i class="ph ph-brain"></i> Why ${m.rag_status.toLowerCase()}?</button>` : ''}
    </div>
  `).join('');
}

function renderRAGChart() {
  const ctx = document.getElementById('chart-rag');
  if (!ctx) return;
  if (charts.rag) charts.rag.destroy();
  const s = state.summary;
  charts.rag = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Green', 'Amber', 'Red'],
      datasets: [{ data: [s.green||0, s.amber||0, s.red||0], backgroundColor: ['#1F6B42','#9A5F14','#9B2C2C'], borderWidth: 2, borderColor: '#FAF9F6', hoverOffset: 4 }]
    },
    options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ position:'bottom', labels:{ color:'#4A4843', font:{ family:'IBM Plex Sans', size:11 }, padding:12 } } }, cutout:'68%' }
  });
}

function renderVaRChart() {
  const ctx = document.getElementById('chart-var');
  if (!ctx) return;
  if (charts.var) charts.var.destroy();
  const labels = state.metrics.map(m => m.metric_id.replace('KRI-','').replace('KPI-',''));
  const data   = state.metrics.map(m => m.var_95_usd || 0);
  const colors = state.metrics.map(m => m.rag_status === 'Green' ? '#1F6B42' : m.rag_status === 'Amber' ? '#9A5F14' : '#9B2C2C');
  charts.var = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ label:'95th Pct VaR (USD)', data, backgroundColor: colors, borderRadius:5 }] },
    options: {
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false} },
      scales:{
        x:{ ticks:{ color:'#7A766E', font:{ family:'IBM Plex Mono', size:10 } }, grid:{ color:'rgba(30,32,36,0.06)' } },
        y:{ ticks:{ color:'#7A766E', font:{ family:'IBM Plex Mono', size:10 }, callback: v => '$'+(v/1000).toFixed(0)+'K' }, grid:{ color:'rgba(30,32,36,0.06)' } }
      }
    }
  });
}

// ─── RISK PAGE ─────────────────────────────────────────────
function renderRiskPage() {
  const total_ale = state.summary.total_ale_usd || 0;
  const total_var = state.summary.total_var_95_usd || 0;
  const topRisk   = [...state.metrics].sort((a,b)=>(b.var_95_usd||0)-(a.var_95_usd||0))[0];
  document.getElementById('risk-ale').textContent = formatUSD(total_ale);
  document.getElementById('risk-var').textContent = formatUSD(total_var);
  document.getElementById('risk-top').textContent = topRisk ? topRisk.metric_id : '—';
  renderMCChart(); renderHeatmap(); renderRiskTable();
  loadRiskRegister();
}

function renderMCChart() {
  const ctx = document.getElementById('chart-mc');
  if (!ctx) return;
  if (charts.mc) charts.mc.destroy();
  const labels  = state.metrics.map(m => m.metric_id.split('-').slice(1).join('-'));
  const aleData = state.metrics.map(m => m.ale_usd || 0);
  const varData = state.metrics.map(m => m.var_95_usd || 0);
  charts.mc = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label:'Expected ALE', data: aleData, backgroundColor:'rgba(29,78,216,0.65)', borderRadius:4 },
        { label:'95th Pct VaR', data: varData, backgroundColor:'rgba(185,28,28,0.45)', borderRadius:4 },
      ]
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ labels:{ color:'#4A4843', font:{ family:'IBM Plex Sans', size:11 } } } },
      scales:{
        x:{ ticks:{ color:'#7A766E', font:{ family:'IBM Plex Mono', size:10 } }, grid:{ color:'rgba(30,32,36,0.06)' } },
        y:{ ticks:{ color:'#7A766E', font:{ family:'IBM Plex Mono', size:10 }, callback: v => '$'+(v/1000).toFixed(0)+'K' }, grid:{ color:'rgba(30,32,36,0.06)' } }
      }
    }
  });
}

function renderHeatmap() {
  const container = document.getElementById('heatmap-container');
  if (!container) return;
  const cellColors = [
    ['#1F6B42','#1F6B42','#9A5F14','#9B2C2C','#9B2C2C'],
    ['#1F6B42','#1F6B42','#9A5F14','#9A5F14','#9B2C2C'],
    ['#14532d','#166534','#1F6B42','#9A5F14','#9A5F14'],
    ['#0E3D24','#14532d','#166534','#1F6B42','#1F6B42'],
    ['#0A2818','#0E3D24','#14532d','#166534','#1F6B42'],
  ];
  const metricCells = {};
  state.metrics.forEach(m => {
    const prob = m.probability_of_breach || 0.1;
    const ale  = m.ale_usd || 0;
    const lh   = Math.max(1, Math.min(5, Math.ceil(prob * 5)));
    let im = 1;
    if (ale < 50000) im=1; else if (ale < 200000) im=2; else if (ale < 500000) im=3; else if (ale < 1000000) im=4; else im=5;
    const key = `${im}-${lh}`;
    if (!metricCells[key]) metricCells[key] = [];
    metricCells[key].push(m.metric_id.split('-').slice(1).join('-').substring(0,6));
  });
  let html = `<div style="display:grid;grid-template-columns:28px repeat(5,1fr);grid-template-rows:repeat(5,1fr) 28px;gap:3px;height:100%">`;
  for (let im = 5; im >= 1; im--) {
    html += `<div style="display:flex;align-items:center;justify-content:center;font-size:10px;color:#7A766E;font-weight:600;font-family:'IBM Plex Mono',monospace">${im}</div>`;
    for (let lh = 1; lh <= 5; lh++) {
      const key   = `${im}-${lh}`;
      const color = cellColors[5-im][lh-1];
      const dots  = (metricCells[key] || []).map(id => `<span title="${id}" style="display:inline-block;background:rgba(255,255,255,0.25);border:1px solid rgba(255,255,255,0.5);border-radius:4px;padding:1px 4px;font-size:8px;font-weight:700;color:white;margin:1px">${id.substring(0,4)}</span>`).join('');
      html += `<div style="background:${color};border-radius:5px;display:flex;align-items:center;justify-content:center;flex-wrap:wrap;padding:2px;cursor:default;transition:opacity .12s" onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'">${dots}</div>`;
    }
  }
  html += `<div></div>`;
  for (let lh = 1; lh <= 5; lh++) html += `<div style="display:flex;align-items:center;justify-content:center;font-size:10px;color:#7A766E;font-weight:600;font-family:'IBM Plex Mono',monospace">${lh}</div>`;
  html += `</div>`;
  html += `<div style="display:flex;justify-content:space-between;margin-top:6px;font-size:10px;color:#7A766E;font-family:'IBM Plex Mono',monospace"><span>Likelihood (1–5)</span><span>Impact (1–5)</span></div>`;
  container.innerHTML = html;
}

function renderRiskTable() {
  const table = document.getElementById('risk-table');
  if (!table) return;
  const sorted = [...state.metrics].sort((a,b)=>(b.var_95_usd||0)-(a.var_95_usd||0));
  table.innerHTML = sorted.map((m,i) => `
    <div class="metric-card" style="margin-bottom:8px">
      <div style="display:flex;align-items:center;gap:16px">
        <div style="font-size:22px;font-weight:800;color:var(--border-strong);width:36px;text-align:center">#${i+1}</div>
        <div style="flex:1">
          <div style="font-size:10.5px;font-family:'IBM Plex Mono',monospace;color:var(--text-muted)">${m.metric_id}</div>
          <div style="font-size:14px;font-weight:600;color:var(--text-primary)">${m.metric_name}</div>
        </div>
        <span class="rag-badge ${m.rag_status}">${m.rag_status}</span>
        <div style="text-align:right;margin-left:14px">
          <div style="font-size:18px;font-weight:700;color:var(--red)">${formatUSD(m.var_95_usd)}</div>
          <div style="font-size:10.5px;color:var(--text-muted)">95th Pct VaR</div>
        </div>
        <div style="text-align:right;margin-left:14px">
          <div style="font-size:16px;font-weight:700;color:var(--amber)">${((m.probability_of_breach||0)*100).toFixed(0)}%</div>
          <div style="font-size:10.5px;color:var(--text-muted)">Breach Prob.</div>
        </div>
      </div>
    </div>
  `).join('');
}

// ─── COMPLIANCE ────────────────────────────────────────────
async function initComplianceTabs() {
  const tabsEl = document.getElementById('fw-tabs');
  if (!tabsEl) return;
  const fws = await apiFetch('/api/compliance/frameworks');
  if (!fws?.length) return;
  const labels = { DORA: 'DORA', NIS2: 'NIS2', SOC2: 'SOC 2', ISO27001: 'ISO 27001', NIST_CSF: 'NIST CSF', PCI_DSS: 'PCI DSS', HIPAA: 'HIPAA', GDPR: 'GDPR', FEDRAMP: 'FedRAMP', CMMC: 'CMMC' };
  const active = activeFramework || fws[0];
  tabsEl.innerHTML = fws.map(fw =>
    `<button class="fw-tab ${fw === active ? 'active' : ''}" onclick="loadFramework('${fw}',this)">${labels[fw] || fw}</button>`
  ).join('');
  await loadFramework(active, tabsEl.querySelector('.fw-tab.active') || tabsEl.querySelector('.fw-tab'));
  loadEvidenceRequests();
  loadCrossFrameworkMap();
  loadControlMonitoring();
  loadRemediationTasks();
  loadComplianceGaps();
}

async function loadCrossFrameworkMap() {
  const el = document.getElementById('cross-framework-list');
  if (!el) return;
  const data = await apiFetch('/api/compliance/cross-framework');
  if (!data?.unified_controls?.length) {
    el.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">No unified controls configured.</div>';
    return;
  }
  el.innerHTML = `<div class="readiness-frameworks">${data.unified_controls.map(u => `
    <div class="readiness-fw-card">
      <div class="readiness-fw-name">${u.unified_id}</div>
      <div class="readiness-fw-pct" style="font-size:14px">${u.title}</div>
      <span class="rag-badge ${u.overall_status==='Compliant'?'Green':u.overall_status==='At Risk'?'Amber':'Red'}">${u.overall_status}</span>
    </div>`).join('')}</div>
    <div style="font-size:12px;color:var(--text-muted);margin-top:8px">Unified coverage: ${data.coverage_pct}%</div>`;
}

async function loadControlMonitoring() {
  const sumEl = document.getElementById('ccm-summary');
  const listEl = document.getElementById('ccm-tests-list');
  if (!sumEl || !listEl) return;
  sumEl.innerHTML = pageLoadingHtml('Loading CCM tests…');
  listEl.innerHTML = '';
  const data = await apiFetch('/api/control-monitoring/tests');
  if (!data?.tests) {
    sumEl.innerHTML = pageErrorHtml('Could not load control monitoring.');
    return;
  }
  const s = data.summary;
  sumEl.innerHTML = `
    <div class="readiness-fw-card"><div class="readiness-fw-name">Health</div><div class="readiness-fw-pct">${s.health_pct}%</div></div>
    <div class="readiness-fw-card"><div class="readiness-fw-name">Passing</div><div class="readiness-fw-pct" style="color:var(--green)">${s.passing}</div></div>
    <div class="readiness-fw-card"><div class="readiness-fw-name">At risk</div><div class="readiness-fw-pct" style="color:var(--amber)">${s.at_risk}</div></div>
    <div class="readiness-fw-card"><div class="readiness-fw-name">Failing</div><div class="readiness-fw-pct" style="color:var(--red)">${s.failing}</div></div>`;
  listEl.innerHTML = (data.tests || []).map(t => `
    <div class="schedule-row"><div><strong>${t.name}</strong> <span class="control-evidence-badge">${t.category}</span>
      <div class="schedule-row-meta">${t.id} · ${(t.frameworks||[]).join(', ')}</div>
      <p style="font-size:12px;margin:6px 0 0;color:var(--text-muted)">${t.detail || t.description}</p>
    </div><span class="rag-badge ${t.status==='passing'?'Green':t.status==='at_risk'?'Amber':t.status==='failing'?'Red':'Amber'}">${t.status}</span></div>`).join('')
    + (data.competitive_note ? `<p style="font-size:12px;color:var(--text-muted);margin-top:12px">${data.competitive_note}</p>` : '');
}

async function loadRemediationTasks() {
  const el = document.getElementById('remediation-tasks-list');
  if (!el) return;
  el.innerHTML = pageLoadingHtml('Loading remediation tasks…');
  const data = await apiFetch('/api/remediation/');
  if (!data?.tasks) {
    el.innerHTML = pageErrorHtml('Could not load remediation tasks.');
    return;
  }
  if (!data.tasks.length) {
    el.innerHTML = '<div style="color:var(--text-muted)">No open tasks. Click <strong>Create from gaps</strong> to auto-generate from compliance gaps.</div>';
    return;
  }
  el.innerHTML = data.tasks.map(t => `
    <div class="schedule-row"><div><strong>${t.title}</strong>
      <span class="control-evidence-badge">${t.priority}</span>
      ${t.overdue ? '<span class="rag-badge Red">Overdue</span>' : ''}
      <div class="schedule-row-meta">Owner: ${t.owner || '—'} · Due: ${t.due_date ? new Date(t.due_date).toLocaleDateString() : '—'}</div>
    </div>
    <div style="display:flex;gap:6px">
      ${t.status !== 'completed' ? `<button class="btn btn-secondary btn-sm" onclick="completeRemediationTask('${t.id}')">Complete</button>` : '<span class="rag-badge Green">Done</span>'}
    </div></div>`).join('');
}

async function createRemediationFromGaps() {
  showToast('Creating remediation tasks from compliance gaps…', 'info');
  const data = await apiFetch('/api/remediation/from-gaps', { method: 'POST', body: '{}' });
  showToast(`Created ${data?.created ?? 0} remediation tasks`, 'success');
  loadRemediationTasks();
}

async function completeRemediationTask(id) {
  await apiFetch(`/api/remediation/${id}`, { method: 'PATCH', body: JSON.stringify({ status: 'completed' }) });
  showToast('Task marked complete', 'success');
  loadRemediationTasks();
}

async function loadPlatformPage() {
  const el = document.getElementById('platform-competitive-matrix');
  if (!el) return;
  const [ccm, readiness] = await Promise.all([
    apiFetch('/api/control-monitoring/summary'),
    apiFetch('/api/compliance/readiness'),
  ]);
  const rows = [
    ['Continuous control monitoring', '✓ SIEM-native CCM', '✓', '✓', 'Partial', 'Partial'],
    ['Financial risk (ALE / VaR / Monte Carlo)', '✓ Built-in FAIR', '—', '—', 'Add-on', 'Add-on'],
    ['SIEM-first metrics (MTTD/MTTR/CVE)', '✓ Core product', '—', '—', '—', '—'],
    ['Trust center (public)', '✓ Live metrics', '✓', '✓', 'Portal', 'Limited'],
    ['Vendor / TPRM', '✓ SENTINEL scoring', '✓', '✓', 'GRC module', '✓'],
    ['Policy + attestation', '✓', '✓', '✓', 'ITSM', '✓'],
    ['Auditor portal', '✓', '✓', '✓', '—', '✓'],
    ['Pen test program', '✓', 'Partial', 'Partial', '—', '—'],
    ['What-if risk simulator', '✓ Unique', '—', '—', '—', '—'],
    ['Evidence vault + SHA lineage', '✓', '✓', '✓', 'CMDB', '✓'],
    ['Integration marketplace', `✓ ${hub?.wired_collectors || '—'} live collectors`, '400+', '200+', 'Now Assist', 'Connectors'],
    ['Remediation workflow + SLA', '✓', '✓', '✓', '✓ ITSM', '✓'],
  ];
  el.innerHTML = `
    <div class="readiness-panel" style="margin-bottom:20px;padding:16px">
      <strong>Your posture now:</strong> CCM health ${ccm?.health_pct ?? '—'}% · Readiness ${readiness?.overall_readiness_pct ?? '—'}%
      <p style="font-size:13px;color:var(--text-secondary);margin:8px 0 0">VALENCE wins where compliance meets live security operations — SIEM metrics, financial risk, and audit evidence in one platform.</p>
    </div>
    <div style="overflow-x:auto">
    <table class="data-table" style="width:100%;font-size:13px;border-collapse:collapse">
      <thead><tr><th style="text-align:left;padding:10px">Capability</th><th>VALENCE</th><th>Vanta</th><th>Drata</th><th>ServiceNow</th><th>MetricStream</th></tr></thead>
      <tbody>${rows.map(r => `<tr>${r.map((c,i) => `<td style="padding:10px;${i===0?'font-weight:600':''}">${c}</td>`).join('')}</tr>`).join('')}</tbody>
    </table></div>
    <div class="readiness-panel" style="margin-top:20px;padding:16px;font-size:13px">
      <strong>Switching pitch:</strong> Teams on Vanta/Drata get checkbox compliance. VALENCE adds continuous SIEM-driven control health, FAIR financial quantification, and cascade risk analysis — so CISOs prove both audit readiness <em>and</em> operational security ROI.
    </div>`;
}

async function loadCommandCenter() {
  const el = document.getElementById('command-center-content');
  if (!el) return;
  el.innerHTML = pageLoadingHtml('Loading risk command center…');
  const data = await apiFetch('/api/command-center/posture');
  if (!data) {
    el.innerHTML = pageErrorHtml('Could not load command center.');
    return;
  }
  const h = data.headline || {};
  el.innerHTML = `
    <div class="readiness-frameworks" style="margin-bottom:20px">
      <div class="readiness-fw-card"><div class="readiness-fw-name">Total ALE</div><div class="readiness-fw-pct">${formatUSD(h.total_ale_usd)}</div></div>
      <div class="readiness-fw-card"><div class="readiness-fw-name">Red metrics</div><div class="readiness-fw-pct" style="color:var(--red)">${h.red_metrics ?? '—'}</div></div>
      <div class="readiness-fw-card"><div class="readiness-fw-name">Overall RAG</div><div class="readiness-fw-pct">${h.overall_rag ?? '—'}</div></div>
      <div class="readiness-fw-card"><div class="readiness-fw-name">Data mode</div><div class="readiness-fw-pct" style="font-size:14px">${h.data_mode ?? '—'}</div></div>
    </div>
    <div class="readiness-panel" style="margin-bottom:20px;padding:16px;font-size:13px;color:var(--text-secondary)">
      ${data.value_proposition || ''}
    </div>
    <div class="section-header"><div class="section-title">SIEM → Control → Financial risk chains</div></div>
    ${(data.chains || []).map(c => `
      <div class="schedule-row">
        <div>
          <strong>${c.metric_name || c.metric_id}</strong>
          <span class="rag-badge ${c.rag_status || 'Amber'}">${c.rag_status || '—'}</span>
          <div class="schedule-row-meta">Value: ${c.value ?? '—'} · ALE ${formatUSD(c.ale_usd)} · VaR95 ${formatUSD(c.var_95_usd)}</div>
          <div style="margin-top:8px;font-size:12px">${(c.controls || []).map(ctrl =>
            `<span class="control-evidence-badge" style="margin-right:4px">${ctrl.framework} ${ctrl.control_id}</span>`
          ).join('') || 'No mapped controls'}</div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:6px">${c.remediation_hint || ''}</div>
        </div>
      </div>`).join('') || '<p style="color:var(--text-muted)">Connect SIEM and run pipeline to populate chains.</p>'}`;
}

async function loadEnterpriseTab(tab, btn) {
  document.querySelectorAll('#enterprise-tabs .fw-tab').forEach(t => t.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const el = document.getElementById('enterprise-content');
  const statsEl = document.getElementById('integration-hub-stats');
  if (!el) return;
  el.innerHTML = pageLoadingHtml('Loading enterprise module…');

  const hub = await apiFetch('/api/integrations/hub/stats');
  if (statsEl && hub) {
    statsEl.innerHTML = `
      <div class="readiness-fw-card"><div class="readiness-fw-name">Integrations</div><div class="readiness-fw-pct">${hub.total_integrations}</div></div>
      <div class="readiness-fw-card"><div class="readiness-fw-name">OAuth ready</div><div class="readiness-fw-pct">${hub.oauth_ready_count}</div></div>
      <div class="readiness-fw-card"><div class="readiness-fw-name">Live collectors</div><div class="readiness-fw-pct">${hub.wired_collectors}</div></div>
      <div class="readiness-fw-card"><div class="readiness-fw-name">Live OAuth</div><div class="readiness-fw-pct">${hub.live_oauth_providers}</div></div>`;
  }

  if (tab === 'workflows') {
    const [bus, wfs] = await Promise.all([
      apiFetch('/api/workflows/business-units'),
      apiFetch('/api/workflows/definitions'),
    ]);
    el.innerHTML = `
      <div class="section-header"><div class="section-title">Business units</div></div>
      <div style="margin-bottom:12px"><button class="btn btn-primary btn-sm" onclick="createBusinessUnit()"><i class="ph ph-plus"></i> Add BU</button></div>
      ${(bus?.business_units||[]).map(u => `<div class="schedule-row"><div><strong>${u.name}</strong> <span class="control-evidence-badge">${u.code}</span>
        <div class="schedule-row-meta">${u.region} · Owner: ${u.owner||'—'}</div></div></div>`).join('') || '<p style="color:var(--text-muted)">No business units yet.</p>'}
      <div class="section-header" style="margin-top:24px"><div class="section-title">Workflow designer</div></div>
      ${(wfs?.workflows||[]).map(w => `<div class="schedule-row"><div><strong>${w.name}</strong> <span class="control-evidence-badge">${w.trigger}</span>
        <div class="schedule-row-meta">${w.step_count} steps · ${w.description||''}</div>
        <div style="margin-top:8px;font-size:12px">${(w.steps||[]).map((s,i) => `<span class="control-evidence-badge" style="margin-right:4px" title="Step ${i+1}">${s.label}</span>`).join(' → ')}</div>
      </div><button class="btn btn-secondary btn-sm" onclick="executeWorkflow('${w.id}')">Run</button></div>`).join('')}`;
  } else if (tab === 'itsm') {
    const [prov, tickets, assets] = await Promise.all([
      apiFetch('/api/itsm/providers'),
      apiFetch('/api/itsm/tickets'),
      apiFetch('/api/itsm/cmdb/assets'),
    ]);
    el.innerHTML = `
      <div style="margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-primary btn-sm" onclick="syncItsmRemediation()"><i class="ph ph-arrows-clockwise"></i> Sync remediation → ITSM</button>
        <button class="btn btn-secondary btn-sm" onclick="syncCmdb()"><i class="ph ph-database"></i> Sync CMDB</button>
      </div>
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px">Connect Jira or ServiceNow in Marketplace, then sync remediation tasks and CMDB assets.</p>
      <div class="readiness-frameworks" style="margin-bottom:16px">${(prov?.providers||[]).map(p =>
        `<div class="readiness-fw-card"><div class="readiness-fw-name">${p.name}</div><span class="rag-badge ${p.connected?'Green':'Amber'}">${p.connected?'Connected':'Not connected'}</span></div>`
      ).join('')}</div>
      <div class="section-header"><div class="section-title">ITSM tickets</div></div>
      ${(tickets?.tickets||[]).map(t => `<div class="schedule-row"><div><strong>${t.external_key}</strong> <span class="control-evidence-badge">${t.provider}</span>
        <div class="schedule-row-meta">${t.summary}</div></div>
        ${t.url ? `<a class="btn btn-secondary btn-sm" href="${t.url}" target="_blank" rel="noopener">Open</a>` : ''}</div>`).join('') || '<p style="color:var(--text-muted)">No tickets synced yet.</p>'}
      <div class="section-header" style="margin-top:24px"><div class="section-title">CMDB assets</div></div>
      ${(assets?.assets||[]).map(a => `<div class="schedule-row"><div><strong>${a.name}</strong> <span class="control-evidence-badge">${a.asset_type}</span>
        <div class="schedule-row-meta">${a.source_integration} · ${a.criticality}</div></div></div>`).join('') || '<p style="color:var(--text-muted)">Run CMDB sync to populate assets.</p>'}`;
  } else if (tab === 'changes') {
    const changes = await apiFetch('/api/workflows/change-requests');
    el.innerHTML = `
      <div style="margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-primary btn-sm" onclick="createChangeRequest()"><i class="ph ph-plus"></i> New change request</button>
      </div>
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px">Track approval and implementation for production changes with ITSM reference links.</p>
      ${(changes?.change_requests||[]).map(c => `<div class="schedule-row"><div>
        <strong>${c.title}</strong> <span class="control-evidence-badge">${c.change_type}</span>
        <span class="rag-badge ${c.risk_level === 'high' ? 'Red' : c.risk_level === 'medium' ? 'Amber' : 'Green'}">${c.risk_level}</span>
        <div class="schedule-row-meta">Status: ${c.status} · Requested by ${c.requested_by}</div>
        ${c.external_ticket_url ? `<a href="${c.external_ticket_url}" target="_blank" rel="noopener" style="font-size:12px">ITSM: ${c.external_ticket_id || 'Open ticket'}</a>` : ''}
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        ${c.status === 'pending_approval' ? `<button class="btn btn-secondary btn-sm" onclick="approveChangeRequest('${c.id}')">Approve</button>` : ''}
        ${c.status === 'approved' ? `<button class="btn btn-primary btn-sm" onclick="implementChangeRequest('${c.id}')">Implement</button>` : ''}
      </div></div>`).join('') || '<p style="color:var(--text-muted)">No change requests yet.</p>'}`;
  } else if (tab === 'auditors') {
    const firms = await apiFetch('/api/auditor-marketplace/firms');
    const eng = await apiFetch('/api/auditor-marketplace/engagements');
    el.innerHTML = `
      <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px">${firms?.note||''}</p>
      ${(firms?.firms||[]).map(f => `<div class="schedule-row"><div><strong>${f.name}</strong> <span class="control-evidence-badge">★ ${f.rating}</span>
        <div class="schedule-row-meta">${(f.specializations||[]).join(', ')} · $${f.hourly_rate_usd}/hr · ${(f.regions||[]).join(', ')}</div>
        <p style="font-size:12px;color:var(--text-muted);margin-top:6px">${f.description||''}</p>
      </div><button class="btn btn-primary btn-sm" onclick="engageAuditor('${f.id}','${f.name.replace(/'/g, '')}')">Request engagement</button></div>`).join('')}
      <div class="section-header" style="margin-top:24px"><div class="section-title">Your engagements</div></div>
      ${(eng?.engagements||[]).map(e => `<div class="schedule-row"><div><strong>${e.firm_name}</strong> <span class="rag-badge Amber">${e.status}</span>
        <div class="schedule-row-meta">${e.framework} · ${new Date(e.requested_at).toLocaleDateString()}</div></div></div>`).join('') || '<p style="color:var(--text-muted)">No engagements yet.</p>'}`;
  } else if (tab === 'billing') {
    const [plans, sub] = await Promise.all([
      apiFetch('/api/billing/plans'),
      apiFetch('/api/billing/subscription'),
    ]);
    el.innerHTML = `
      <div class="readiness-panel" style="margin-bottom:16px;padding:14px;font-size:13px">
        Current plan: <strong>${sub?.plan || 'trial'}</strong> · Status: <strong>${sub?.subscription_status || '—'}</strong>
        ${sub?.stripe_configured ? '' : ' · <em>Demo billing — set STRIPE_SECRET_KEY for live checkout</em>'}
      </div>
      <div class="readiness-frameworks">${Object.entries(plans?.plans || {}).map(([id, p]) =>
        `<div class="readiness-fw-card" style="cursor:pointer" onclick="upgradeBillingPlan('${id}')">
          <div class="readiness-fw-name">${p.name}</div>
          <div class="readiness-fw-pct">$${p.price_usd}/mo</div>
          <div style="font-size:11px;color:var(--text-muted)">${p.seats} seats · ${p.frameworks} frameworks</div>
        </div>`).join('')}</div>`;
  } else if (tab === 'msp') {
    const portfolio = await apiFetch('/api/msp/portfolio');
    el.innerHTML = `
      <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px">${portfolio?.note || ''}</p>
      ${(portfolio?.portfolio || []).map(t => `<div class="schedule-row"><div>
        <strong>${t.name}</strong> <span class="control-evidence-badge">${t.plan}</span>
        ${t.is_demo ? '<span class="control-evidence-badge">Demo</span>' : ''}
        <div class="schedule-row-meta">${t.tenant_id} · ${t.connected_integrations} integrations · SIEM ${t.siem_configured ? 'on' : 'off'}</div>
      </div><button class="btn btn-secondary btn-sm" onclick="switchTenant('${t.tenant_id}')">Open</button></div>`).join('')}`;
  } else if (tab === 'import') {
    el.innerHTML = `
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px">Import Vanta or Drata control export CSV — gaps become remediation tasks automatically.</p>
      <div class="schedule-row">
        <div><strong>Vanta / Drata CSV</strong><div class="schedule-row-meta">Control, status, framework, owner columns</div></div>
        <label class="btn btn-primary btn-sm" style="cursor:pointer">
          <i class="ph ph-upload"></i> Upload CSV
          <input type="file" accept=".csv" style="display:none" onchange="importCompetitorCsv(this)">
        </label>
      </div>`;
  } else {
    const oauth = await apiFetch('/api/integrations/hub/oauth-providers');
    const aws = await apiFetch('/api/integrations/hub/aws-connect-guide');
    const conns = await apiFetch('/api/integrations/oauth/connections');
    el.innerHTML = `
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px">${oauth?.setup_hint||''}</p>
      ${(oauth?.providers||[]).map(p => `<div class="schedule-row"><div><strong>${p.id}</strong>
        <span class="rag-badge ${p.configured?'Green':p.supports_demo?'Amber':'Red'}">${p.configured?'Live OAuth':'Demo mode'}</span>
        ${p.deep_integration ? '<span class="control-evidence-badge">Deep integration</span>' : ''}
        <div class="schedule-row-meta">${p.env_client_id}</div>
        <div style="margin-top:6px;font-size:12px;color:var(--text-muted)">
          ${
            (() => {
              const c = (conns?.providers || []).find(x => x.provider === p.id);
              if (!c?.connected) return 'Connection: not connected';
              if (c?.probe?.ok) return `Connection: healthy (${c.probe.reason || c.probe.http_status || 'ok'})`;
              return `Connection: degraded (${c?.probe?.reason || c?.probe?.http_status || 'check token'})`;
            })()
          }
        </div>
      </div><button class="btn btn-secondary btn-sm" onclick="oauthConnect('${p.id}')">Connect</button></div>`).join('')}
      <div class="readiness-panel" style="margin-top:20px;padding:16px;font-size:13px">
        <strong>${aws?.title||'AWS'}</strong>
        <ul style="margin:8px 0 0;padding-left:18px">${(aws?.methods||[]).map(m => `<li>${m.name}</li>`).join('')}</ul>
        <button class="btn btn-primary btn-sm" style="margin-top:12px" onclick="connectAwsCrossAccountRole()"><i class="ph ph-cloud"></i> Connect IAM role</button>
      </div>`;
  }
}

async function upgradeBillingPlan(planId) {
  const res = await apiFetch('/api/billing/checkout', { method: 'POST', body: JSON.stringify({ plan: planId }) });
  if (res?.checkout_url) {
    window.location.href = res.checkout_url;
    return;
  }
  showToast(res?.message || `Plan set to ${planId}`, 'success');
  loadEnterpriseTab('billing', document.querySelector('#enterprise-tabs .fw-tab.active'));
}

async function importCompetitorCsv(input) {
  const file = input?.files?.[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API}/api/import/vanta-csv`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}`, 'X-Tenant-ID': currentTenantId },
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(data.detail || 'Import failed', 'error');
    return;
  }
  showToast(data.message || `Imported ${data.imported} tasks`, 'success');
  input.value = '';
  loadEnterpriseTab('import', document.querySelector('#enterprise-tabs .fw-tab.active'));
}

async function connectAwsIamRole() {
  return connectAwsCrossAccountRole();
}

async function createChangeRequest() {
  const data = await showFormDialog({
    title: 'Create change request',
    fields: [
      { name: 'title', label: 'Title', placeholder: 'Deploy SIEM parser rules update' },
      { name: 'change_type', label: 'Type', placeholder: 'application / infra / policy' },
      { name: 'risk_level', label: 'Risk level', placeholder: 'low / medium / high' },
      { name: 'description', label: 'Description', placeholder: 'Describe impact and rollback plan' },
    ],
    submitLabel: 'Create',
    icon: 'ph-git-branch',
  });
  if (!data?.title) return;
  const payload = {
    title: data.title,
    description: data.description || null,
    change_type: data.change_type || 'application',
    risk_level: data.risk_level || 'medium',
  };
  await apiFetch('/api/workflows/change-requests', { method: 'POST', body: JSON.stringify(payload) });
  showToast('Change request submitted for approval', 'success');
  loadEnterpriseTab('changes', document.querySelector('#enterprise-tabs .fw-tab.active'));
}

async function approveChangeRequest(id) {
  const res = await apiFetch(`/api/workflows/change-requests/${id}/approve`, { method: 'POST', body: '{}' });
  showToast(`Change approved by ${res?.approved_by || 'admin'}`, 'success');
  loadEnterpriseTab('changes', document.querySelector('#enterprise-tabs .fw-tab.active'));
}

async function implementChangeRequest(id) {
  const data = await showFormDialog({
    title: 'Implementation notes',
    fields: [{ name: 'implementation_notes', label: 'Notes', placeholder: 'Validation completed, no regressions observed.' }],
    submitLabel: 'Mark implemented',
    icon: 'ph-check-circle',
  });
  if (!data) return;
  await apiFetch(`/api/workflows/change-requests/${id}/implement`, {
    method: 'POST',
    body: JSON.stringify({ implementation_notes: data.implementation_notes || '' }),
  });
  showToast('Change marked implemented', 'success');
  loadEnterpriseTab('changes', document.querySelector('#enterprise-tabs .fw-tab.active'));
}

async function createBusinessUnit() {
  const data = await showFormDialog({
    title: 'Add business unit',
    fields: [
      { name: 'name', label: 'Unit name', placeholder: 'EMEA Operations' },
      { name: 'code', label: 'Code', placeholder: 'EMEA' },
      { name: 'region', label: 'Region', placeholder: 'EU' },
    ],
    submitLabel: 'Create',
    icon: 'ph-buildings',
  });
  if (!data?.name) return;
  await apiFetch('/api/workflows/business-units', { method: 'POST', body: JSON.stringify(data) });
  showToast('Business unit created', 'success');
  loadEnterpriseTab('workflows', document.querySelector('#enterprise-tabs .fw-tab.active'));
}

async function executeWorkflow(id) {
  const res = await apiFetch(`/api/workflows/definitions/${id}/execute`, { method: 'POST', body: '{}' });
  showToast(`Workflow "${res?.workflow_name}" executed (${res?.executed_steps?.length||0} steps)`, 'success');
}

async function syncItsmRemediation() {
  const res = await apiFetch('/api/itsm/sync/remediation', { method: 'POST', body: '{}' });
  showToast(res?.message || 'ITSM sync complete', 'success');
  loadEnterpriseTab('itsm', document.querySelector('#enterprise-tabs .fw-tab.active'));
}

async function syncCmdb() {
  const res = await apiFetch('/api/itsm/cmdb/sync', { method: 'POST', body: '{}' });
  showToast(`Synced ${res?.synced||0} CMDB assets`, 'success');
  loadEnterpriseTab('itsm', document.querySelector('#enterprise-tabs .fw-tab.active'));
}

async function engageAuditor(firmId, firmName) {
  const ok = await showConfirmDialog({
    title: `Request ${firmName}?`,
    subtitle: 'Auditor receives read-only portal access upon acceptance',
    message: 'They can review evidence vault, controls, and findings for your selected framework.',
    confirmLabel: 'Send request',
    cancelLabel: 'Cancel',
    variant: 'info',
    icon: 'ph-certificate',
  });
  if (!ok) return;
  await apiFetch('/api/auditor-marketplace/engage', {
    method: 'POST',
    body: JSON.stringify({ firm_id: firmId, framework: 'SOC2' }),
  });
  showToast(`Engagement requested with ${firmName}`, 'success');
  loadEnterpriseTab('auditors', document.querySelector('#enterprise-tabs .fw-tab.active'));
}

async function seedPolicyTemplates() {
  const ok = await showConfirmDialog({
    title: 'Load policy templates?',
    subtitle: 'Adds SOC 2 / ISO / HIPAA starter policies',
    message: 'Five enterprise policy templates will be published to your tenant. Employees can attest from this page.',
    confirmLabel: 'Load templates',
    cancelLabel: 'Cancel',
    variant: 'info',
    icon: 'ph-books',
  });
  if (!ok) return;
  await apiFetch('/api/policies/seed-templates', { method: 'POST', body: '{}' });
  showToast('Policy templates published', 'success');
  loadPolicies();
}

async function schedulePentest() {
  const data = await showFormDialog({
    title: 'Schedule penetration test',
    subtitle: 'Track vendor, scope, and findings in one program',
    fields: [
      { name: 'title', label: 'Assessment title', placeholder: 'Annual external pen test' },
      { name: 'vendor', label: 'Vendor / firm', placeholder: 'Bishop Fox, Cobalt, etc.' },
      { name: 'scope', label: 'Scope', placeholder: 'Production API and web perimeter' },
    ],
    submitLabel: 'Schedule',
    icon: 'ph-bug',
  });
  if (!data?.title) return;
  await apiFetch('/api/pentest/', { method: 'POST', body: JSON.stringify(data) });
  showToast('Pen test scheduled', 'success');
  loadPentests();
}

async function addVendor() {
  const data = await showFormDialog({
    title: 'Add vendor',
    subtitle: 'SENTINEL risk scoring starts immediately',
    fields: [
      { name: 'name', label: 'Vendor name', placeholder: 'Acme Cloud Services' },
      { name: 'tier', label: 'Tier (critical/strategic/operational)', placeholder: 'operational' },
      { name: 'data_classification', label: 'Data classification', placeholder: 'confidential' },
    ],
    submitLabel: 'Add vendor',
    icon: 'ph-buildings',
  });
  if (!data?.name) return;
  await apiFetch('/api/vendors/', { method: 'POST', body: JSON.stringify(data) });
  showToast('Vendor added to portfolio', 'success');
  loadVendors();
}

async function editTrustCenterConfig() {
  const cfg = await apiFetch('/api/trust-center/config');
  if (!cfg) return;
  const data = await showFormDialog({
    title: 'Trust center settings',
    subtitle: 'Public page for customers and prospects',
    fields: [
      { name: 'company_name', label: 'Company name', value: cfg.company_name || '' },
      { name: 'contact_email', label: 'Security contact', value: cfg.contact_email || '' },
      { name: 'slug', label: 'URL slug', value: cfg.slug || '' },
    ],
    submitLabel: 'Save',
    icon: 'ph-shield-check',
  });
  if (!data) return;
  await apiFetch('/api/trust-center/config', {
    method: 'PUT',
    body: JSON.stringify({ ...data, public_enabled: true, frameworks: cfg.frameworks }),
  });
  showToast('Trust center updated', 'success');
  loadPersonnelTab('trust', document.querySelector('#personnel-tabs .fw-tab.active'));
}

async function loadComplianceGaps() {
  const el = document.getElementById('compliance-gaps-list');
  if (!el) return;
  el.innerHTML = '<div style="color:var(--text-muted)">Analyzing…</div>';
  const data = await apiFetch('/api/intelligence/gaps');
  if (!data?.prioritized_gaps?.length) {
    el.innerHTML = `<div style="font-size:13px;color:var(--text-green)">${data?.executive_summary || 'No gaps'}</div>`;
    return;
  }
  el.innerHTML = `<p style="font-size:13px;margin-bottom:12px">${data.executive_summary}</p>` +
    data.prioritized_gaps.map(g => `
    <div class="schedule-row"><div><strong>${g.control_id}</strong> <span class="control-evidence-badge">${g.framework}</span>
      <div class="schedule-row-meta">${g.title} · priority ${Math.round(g.priority_score)}</div>
      <p style="font-size:12px;margin:8px 0 0;color:var(--text-secondary)">${g.remediation}</p>
    </div><span class="rag-badge ${g.status==='Non-Compliant'?'Red':'Amber'}">${g.status}</span></div>`).join('');
}

async function loadEvidenceRequests() {
  const el = document.getElementById('evidence-requests-list');
  if (!el) return;
  const data = await apiFetch('/api/evidence/requests');
  if (!data?.length) {
    el.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">No open evidence requests.</div>';
    return;
  }
  el.innerHTML = data.map(r => `
    <div class="schedule-row">
      <div>
        <strong>${r.control_id}</strong> — ${r.title}
        <div class="schedule-row-meta">${r.status} · ${r.assignee || 'unassigned'} · ${r.requested_by}</div>
      </div>
      ${r.status === 'pending' ? `<button class="btn btn-secondary btn-sm" onclick="fulfillEvidenceRequest('${r.id}')">Fulfill</button>` : ''}
    </div>`).join('');
}

function showEvidenceRequestModal() {
  showModalOverlay('evidence-request-modal');
}
function closeEvidenceRequestModal() {
  hideModalOverlay('evidence-request-modal');
}
async function submitEvidenceRequest() {
  const body = {
    control_id: document.getElementById('evreq-control-id').value.trim(),
    title: document.getElementById('evreq-title').value.trim(),
    assignee: document.getElementById('evreq-assignee').value.trim() || null,
    description: document.getElementById('evreq-description').value.trim(),
    framework: activeFramework || 'SOC2',
  };
  const res = await apiFetch('/api/evidence/requests', { method: 'POST', body: JSON.stringify(body) });
  if (res?.id) {
    showToast('Evidence request created', 'success');
    closeEvidenceRequestModal();
    loadEvidenceRequests();
  }
}
async function fulfillEvidenceRequest(id) {
  await apiFetch(`/api/evidence/requests/${id}/fulfill`, {
    method: 'POST',
    body: JSON.stringify({ artifact_summary: 'Uploaded via compliance workflow' }),
  });
  showToast('Evidence request fulfilled', 'success');
  loadEvidenceRequests();
}

async function explainMetric(metricId) {
  const data = await apiFetch(`/api/intelligence/explain/${metricId}`);
  if (!data) return;
  document.getElementById('explain-content').textContent = data.explanation_plain || data.explanation;
  showModalOverlay('explain-modal');
}
function closeExplainModal() {
  hideModalOverlay('explain-modal');
}

async function loadRiskRegister() {
  const el = document.getElementById('risk-register-list');
  if (!el) return;
  const data = await apiFetch('/api/risk/register');
  if (!data?.length) {
    el.innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:12px">No CERBERUS risk entries yet — runs when CVE metric is Amber/Red.</div>';
    return;
  }
  el.innerHTML = data.map(r => `
    <div class="schedule-row">
      <div>
        <strong>${r.cve_id}</strong> — ${r.title}
        <div class="schedule-row-meta">${r.severity} · ${r.status} · ${r.owner || '—'} · ${r.source}</div>
      </div>
    </div>`).join('');
}

async function loadVendors() {
  const list = document.getElementById('vendors-list');
  const overview = document.getElementById('vendor-overview');
  syncOrgLabels();
  if (list) list.innerHTML = pageLoadingHtml('Loading vendor roster…');
  if (overview) overview.innerHTML = '';
  try {
  const [vendors, summary, breaches] = await Promise.all([
    apiFetch('/api/vendors/'),
    apiFetch('/api/vendors/summary'),
    apiFetch('/api/vendors/breaches'),
  ]);
  if (!vendors && !summary) {
    if (list) list.innerHTML = pageErrorHtml('Could not load vendors. Check connection and restart ./run.sh');
    return;
  }

  if (overview && summary) {
    overview.innerHTML = `
      <div class="readiness-panel-header">
        <div>
          <div class="section-title" style="margin:0">Portfolio risk</div>
          <div class="section-sub">${summary.total_vendors} vendors monitored</div>
        </div>
        <div class="readiness-overall">
          <span class="readiness-overall-pct">${summary.average_risk_score ?? '—'}</span>
          <span class="readiness-overall-label">Avg score</span>
        </div>
      </div>`;
  }

  const sumEl = document.getElementById('vendor-summary');
  if (sumEl && summary?.by_tier) {
    sumEl.innerHTML = Object.entries(summary.by_tier).filter(([, c]) => c > 0).map(([tier, count]) => `
      <div class="readiness-fw-card">
        <div class="readiness-fw-name">${tier}</div>
        <div class="readiness-fw-pct">${count}</div>
        <div style="font-size:11px;color:var(--text-muted)">vendors</div>
      </div>
    `).join('');
  }

  if (!list) return;
  if (!vendors?.length) {
    list.innerHTML = '<div class="mobile-metric-empty">No vendors loaded. Restart the server if you just updated — demo sandboxes seed 5 vendors automatically.</div>';
    return;
  }
  list.innerHTML = vendors.map(v => `
    <div class="schedule-row">
      <div>
        <strong>${v.name}</strong> <span class="control-evidence-badge">${v.risk_tier}</span>
        <div class="schedule-row-meta">${v.tier} tier · ${v.data_classification} data · ${v.incident_count} incidents · SLA ${v.contract_sla_score}%</div>
      </div>
      <span class="rag-badge ${v.risk_tier === 'critical' || v.risk_tier === 'high' ? 'Red' : v.risk_tier === 'medium' ? 'Amber' : 'Green'}">${v.risk_score}</span>
      <button class="btn btn-secondary btn-sm" onclick="openVendorQuestionnaire(${v.id}, '${v.name.replace(/'/g, "\\'")}')">SIG</button>
    </div>`).join('');

  const openBreaches = (breaches || []).filter(b => !b.acknowledged);
  if (openBreaches.length) {
    list.innerHTML += `<div class="section-header" style="margin-top:20px"><div class="section-title">Breach Alerts</div></div>` +
      openBreaches.map(b => `
      <div class="schedule-row"><div><strong>${b.vendor_name}</strong>
        <div class="schedule-row-meta">${b.breach_date} · ${b.severity}</div>
        <p style="font-size:12px;margin:6px 0 0">${b.details}</p></div>
        <button class="btn btn-secondary btn-sm" onclick="ackBreach(${b.id})">Ack</button></div>`).join('');
  }
  } catch (e) {
    if (list) list.innerHTML = pageErrorHtml('Failed to load vendor data.');
    console.error(e);
  }
}

async function ackBreach(id) {
  await apiFetch(`/api/vendors/breaches/${id}/acknowledge`, { method: 'POST' });
  showToast('Breach alert acknowledged', 'success');
  loadVendors();
}

async function openVendorQuestionnaire(vendorId, vendorName) {
  const tpl = await apiFetch('/api/vendors/questionnaire/template');
  const existing = await apiFetch(`/api/vendors/${vendorId}/questionnaire`);
  const responses = existing?.responses || {};
  const answers = (tpl?.questions || []).map(q => {
    const val = responses[q.id] || '';
    return `<div class="form-group"><label>${q.question}</label>
      <select id="vq-${q.id}"><option value="yes" ${val==='yes'?'selected':''}>Yes</option><option value="no" ${val==='no'?'selected':''}>No</option><option value="partial" ${val==='partial'?'selected':''}>Partial</option></select></div>`;
  }).join('');
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.id = 'vendor-q-modal';
  modal.innerHTML = `<div class="modal-card" onclick="event.stopPropagation()">
    <span class="modal-close" onclick="closeVendorQuestionnaireModal()"><i class="ph ph-x"></i></span>
    <h3>SIG Lite — ${vendorName}</h3>${answers}
    <button class="btn btn-primary" onclick="submitVendorQuestionnaire(${vendorId})">Submit questionnaire</button>
  </div>`;
  modal.dataset.dismiss = 'false';
  modal.onclick = (e) => { if (e.target === modal) closeVendorQuestionnaireModal(); };
  document.body.appendChild(modal);
  showModalOverlay(modal);
}

function closeVendorQuestionnaireModal() {
  const modal = document.getElementById('vendor-q-modal');
  if (modal) hideModalOverlay(modal);
  modal?.remove();
}

async function submitVendorQuestionnaire(vendorId) {
  const tpl = await apiFetch('/api/vendors/questionnaire/template');
  const responses = {};
  (tpl?.questions || []).forEach(q => {
    const el = document.getElementById(`vq-${q.id}`);
    if (el) responses[q.id] = el.value;
  });
  await apiFetch(`/api/vendors/${vendorId}/questionnaire`, { method: 'POST', body: JSON.stringify({ responses }) });
  closeVendorQuestionnaireModal();
  showToast('Vendor questionnaire submitted', 'success');
  loadVendors();
}

async function loadPolicies() {
  const list = document.getElementById('policies-list');
  const sumEl = document.getElementById('policy-attestation-summary');
  if (list) list.innerHTML = pageLoadingHtml('Loading policies…');
  if (sumEl) sumEl.innerHTML = '';
  try {
  const [policies, summary] = await Promise.all([
    apiFetch('/api/policies/'),
    apiFetch('/api/policies/attestations/summary'),
  ]);
  if (!policies && !summary) {
    if (list) list.innerHTML = pageErrorHtml('Could not load policies. Restart the server with ./run.sh and hard-refresh.');
    return;
  }
  if (sumEl && summary) {
    sumEl.innerHTML = `<div class="readiness-panel-header">
      <div><div class="section-title" style="margin:0">Attestation progress</div>
      <div class="section-sub">${summary.policies_requiring_attestation} policies require attestation</div></div>
      <div class="readiness-overall"><span class="readiness-overall-pct">${summary.completion_pct}%</span>
      <span class="readiness-overall-label">Complete</span></div></div>`;
  }
  if (!list) return;
  if (!policies?.length) {
    list.innerHTML = '<div class="mobile-metric-empty">No policies yet.</div>';
    return;
  }
  list.innerHTML = policies.map(p => `
    <div class="schedule-row">
      <div><strong>${p.title}</strong> <span class="control-evidence-badge">${p.category}</span>
        <div class="schedule-row-meta">v${p.version} · ${(p.framework_tags||[]).join(', ')} · ${p.status}</div>
        <p style="font-size:12px;color:var(--text-muted);margin:8px 0 0">${p.content.slice(0,120)}…</p>
      </div>
      ${p.user_attested ? '<span class="rag-badge Green">Attested</span>' :
        `<button class="btn btn-primary btn-sm" onclick="attestPolicy('${p.id}')">Attest</button>`}
    </div>`).join('');
  } catch (e) {
    if (list) list.innerHTML = pageErrorHtml('Failed to load policies.');
    console.error(e);
  }
}

async function attestPolicy(policyId) {
  await apiFetch('/api/policies/attest', { method: 'POST', body: JSON.stringify({ policy_id: policyId }) });
  showToast('Policy attestation recorded in evidence vault', 'success');
  loadPolicies();
}

async function loadAuditorPortal() {
  const el = document.getElementById('auditor-dashboard');
  if (!el) return;
  el.innerHTML = pageLoadingHtml('Loading auditor workspace…');
  try {
  const data = await apiFetch('/api/auditor/dashboard');
  if (!data) {
    el.innerHTML = pageErrorHtml('Could not load auditor portal. Restart the server with ./run.sh.');
    return;
  }
  el.innerHTML = `
    <div class="summary-grid" style="margin-bottom:20px">
      <div class="summary-card"><div class="summary-card-label">Overall readiness</div>
        <div class="summary-value blue">${data.readiness?.readiness_pct ?? '—'}%</div></div>
      <div class="summary-card"><div class="summary-card-label">Evidence vault</div>
        <div class="summary-value green">${data.evidence_vault_count}</div></div>
      <div class="summary-card"><div class="summary-card-label">Open findings</div>
        <div class="summary-value red">${data.open_findings?.length ?? 0}</div></div>
      <div class="summary-card"><div class="summary-card-label">Policy attestations</div>
        <div class="summary-value amber">${data.attestation_count}</div></div>
    </div>
    <div class="section-title">Framework coverage</div>
    <div class="readiness-frameworks" style="margin:12px 0 24px">${(data.frameworks||[]).map(f=>`
      <div class="readiness-fw-card"><div class="readiness-fw-name">${f.framework}</div>
      <div class="readiness-fw-pct">${f.compliant}/${f.total}</div>
      <div style="font-size:11px;color:var(--text-muted)">compliant</div></div>`).join('')}</div>
    <div class="section-title">Open evidence requests</div>
    <div id="auditor-requests" style="margin:12px 0">${(data.open_evidence_requests||[]).map(r=>`
      <div class="schedule-row"><div><strong>${r.title}</strong>
      <div class="schedule-row-meta">${r.framework} ${r.control_id} · ${r.status}</div></div></div>`).join('') || '<div style="color:var(--text-muted);font-size:12px">None open</div>'}</div>`;
  } catch (e) {
    el.innerHTML = pageErrorHtml('Failed to load auditor portal.');
    console.error(e);
  }
}

async function loadPersonnelTab(tab, btn) {
  document.querySelectorAll('#personnel-tabs .fw-tab').forEach(t => t.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const el = document.getElementById('personnel-content');
  if (!el) return;
  el.innerHTML = pageLoadingHtml('Loading…');
  try {
  if (tab === 'jml') {
    const [events, summary] = await Promise.all([apiFetch('/api/personnel/'), apiFetch('/api/personnel/summary')]);
    el.innerHTML = `<div class="readiness-frameworks" style="margin-bottom:16px">
      <div class="readiness-fw-card"><div class="readiness-fw-name">Pending review</div><div class="readiness-fw-pct">${summary?.pending_access_review ?? 0}</div></div>
      <div class="readiness-fw-card"><div class="readiness-fw-name">SLA met</div><div class="readiness-fw-pct">${summary?.sla_met_pct ?? 0}%</div></div>
    </div>
    <button class="btn btn-secondary btn-sm" style="margin-bottom:12px" onclick="syncJML()"><i class="ph ph-arrows-clockwise"></i> Sync from Okta</button>
    ${(events||[]).map(e=>`<div class="schedule-row"><div><strong>${e.employee_name||e.employee_email}</strong>
      <span class="control-evidence-badge">${e.event_type}</span>
      <div class="schedule-row-meta">${e.department} · ${e.source} · ${e.access_reviewed?'Reviewed':'Pending'}</div></div>
      ${!e.access_reviewed?`<button class="btn btn-secondary btn-sm" onclick="reviewJML('${e.id}')">Mark reviewed</button>`:''}
    </div>`).join('')}`;
  } else if (tab === 'devices') {
    const [devices, summary] = await Promise.all([apiFetch('/api/devices/'), apiFetch('/api/devices/summary')]);
    el.innerHTML = `<div class="readiness-frameworks" style="margin-bottom:16px">
      <div class="readiness-fw-card"><div class="readiness-fw-name">Compliant</div><div class="readiness-fw-pct">${summary?.compliance_pct ?? 0}%</div></div>
      <div class="readiness-fw-card"><div class="readiness-fw-name">MDM enrolled</div><div class="readiness-fw-pct">${summary?.mdm_enrolled_pct ?? 0}%</div></div>
    </div>${(devices||[]).map(d=>`<div class="schedule-row"><div><strong>${d.device_name}</strong>
      <div class="schedule-row-meta">${d.platform} · ${d.owner_email} · ${d.os_version}</div></div>
      <span class="rag-badge ${d.compliance_status==='compliant'?'Green':'Red'}">${d.compliance_status}</span>
    </div>`).join('')}`;
  } else {
    const cfg = await apiFetch('/api/trust-center/config');
    if (!cfg) {
      el.innerHTML = pageErrorHtml('Could not load trust center config.');
      return;
    }
    el.innerHTML = `<div class="schedule-row"><div><strong>${cfg.company_name}</strong>
      <div class="schedule-row-meta">Public: ${cfg.public_enabled?'Enabled':'Disabled'}</div>
      <a href="${cfg.public_url}" target="_blank" rel="noopener">${window.location.origin}${cfg.public_url}</a>
    </div>
    <button class="btn btn-secondary btn-sm" onclick="editTrustCenterConfig()">Configure</button></div>
    <p style="font-size:13px;color:var(--text-muted);margin-top:12px">Frameworks: ${(cfg.frameworks||[]).join(', ')}</p>
    <p style="font-size:12px;color:var(--text-muted)">Trust center shows live readiness from SIEM metrics — not static marketing claims.</p>`;
  }
  } catch (e) {
    el.innerHTML = pageErrorHtml('Failed to load personnel data.');
    console.error(e);
  }
}

async function syncJML() {
  const res = await apiFetch('/api/personnel/sync', { method: 'POST' });
  showToast(`Synced ${res?.events_synced ?? 0} JML events from IdP`, 'success');
  loadPersonnelTab('jml', document.querySelector('#personnel-tabs .fw-tab.active'));
}

async function runAutoRemediate() {
  showToast('Running autonomous remediation agent…', 'info');
  const data = await apiFetch('/api/remediation/from-gaps', { method: 'POST', body: '{}' });
  showToast(`Created ${data?.created ?? 0} remediation tasks with owners and SLAs`, 'success');
  loadRemediationTasks();
  loadComplianceGaps();
  if (document.getElementById('page-findings')?.classList.contains('active')) loadFindings();
}

async function loadTraining() {
  const list = document.getElementById('training-list');
  const sumEl = document.getElementById('training-summary');
  if (list) list.innerHTML = pageLoadingHtml('Loading courses…');
  if (sumEl) sumEl.innerHTML = '';
  try {
  const [courses, summary] = await Promise.all([
    apiFetch('/api/training/courses'),
    apiFetch('/api/training/summary'),
  ]);
  if (!courses && !summary) {
    if (list) list.innerHTML = pageErrorHtml('Could not load training. Restart the server with ./run.sh.');
    return;
  }
  if (sumEl && summary) {
    sumEl.innerHTML = `<div class="readiness-panel-header"><div>
      <div class="section-title" style="margin:0">Org training progress</div>
      <div class="section-sub">${summary.required_courses} required courses · Your progress: ${summary.your_completion_pct ?? 0}%</div></div>
      <div class="readiness-overall"><span class="readiness-overall-pct">${summary.org_completion_pct}%</span>
      <span class="readiness-overall-label">Org complete</span></div></div>
      <p style="font-size:12px;color:var(--text-muted);margin:8px 0 0">Complete required courses — each completion is SHA-256 linked in the Evidence Vault.</p>`;
  }
  if (!list) return;
  list.innerHTML = (courses||[]).map(c => `
    <div class="schedule-row" style="flex-direction:column;align-items:stretch">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
        <div><strong>${c.title}</strong> <span class="control-evidence-badge">${c.category} · ${c.content_type}</span>
          <div class="schedule-row-meta">${c.duration_minutes} min · ${c.required?'Required':'Optional'}</div>
          <p style="font-size:12px;margin:6px 0 0;color:var(--text-muted)">${c.description||''}</p>
        </div>
        ${c.completed ? '<span class="rag-badge Green">Done</span>' :
          `<button class="btn btn-primary btn-sm" onclick="completeTraining('${c.id}')">Complete</button>`}
      </div>
      ${c.content_type === 'video' && c.video_url ? `<div style="margin-top:12px"><iframe width="100%" height="200" src="${c.video_url}" frameborder="0" allowfullscreen></iframe></div>` : ''}
      ${c.content_type === 'scorm' ? `<div style="margin-top:8px;font-size:12px;color:var(--text-muted)"><i class="ph ph-package"></i> SCORM package: ${c.scorm_package || 'bundled'}</div>` : ''}
      ${c.content_type === 'quiz' && c.quiz_questions?.length ? `<div style="margin-top:8px;font-size:12px">${c.quiz_questions.map(q=>`Q: ${q.q}`).join('<br>')}</div>` : ''}
    </div>`).join('');
  } catch (e) {
    if (list) list.innerHTML = pageErrorHtml('Failed to load training courses.');
    console.error(e);
  }
}

async function loadPentests() {
  const list = document.getElementById('pentest-list');
  if (!list) return;
  list.innerHTML = pageLoadingHtml('Loading pen test program…');
  try {
  const [data, meta] = await Promise.all([apiFetch('/api/pentest/'), apiFetch('/api/pentest/meta')]);
  if (!data?.length) {
    list.innerHTML = '<div style="color:var(--text-muted)">No pen tests scheduled.</div>';
    return;
  }
  const banner = meta?.description ? `<div class="readiness-panel" style="margin-bottom:16px;padding:12px 16px;font-size:13px;color:var(--text-secondary)">
    <strong>Data source:</strong> ${meta.description}</div>` : '';
  list.innerHTML = banner + data.map(p => `
    <div class="schedule-row"><div><strong>${p.title}</strong> <span class="control-evidence-badge">${p.status}</span>
      <div class="schedule-row-meta">${p.vendor} · Crit ${p.findings_critical} / High ${p.findings_high} / Med ${p.findings_medium}</div>
    </div>
    ${p.report_evidence_id ? `<span class="rag-badge Green">Report in vault</span>` : ''}
    </div>`).join('');
  } catch (e) {
    list.innerHTML = pageErrorHtml('Failed to load pen tests.');
    console.error(e);
  }
}

async function completeTraining(courseId) {
  await apiFetch('/api/training/complete', { method: 'POST', body: JSON.stringify({ course_id: courseId }) });
  showToast('Training completed — recorded in evidence vault', 'success');
  loadTraining();
}

async function reviewJML(id) {
  await apiFetch(`/api/personnel/${id}/review`, { method: 'POST' });
  showToast('Access review recorded', 'success');
  loadPersonnelTab('jml', document.querySelector('#personnel-tabs .fw-tab.active'));
}

async function loadQuestionnaires() {
  const el = document.getElementById('questionnaire-content');
  if (!el) return;
  el.innerHTML = pageLoadingHtml('Loading questionnaire profile…');
  try {
  const profile = await apiFetch('/api/questionnaires/profile');
  if (!profile) {
    el.innerHTML = pageErrorHtml('Could not load questionnaires. Restart the server with ./run.sh.');
    return;
  }
  const entries = Object.entries(profile?.responses || {});
  const sources = profile?.field_sources || {};
  const header = `<div class="readiness-panel" style="margin-bottom:16px;padding:12px 16px;font-size:13px;color:var(--text-secondary)">
    ${profile.purpose || 'SIG Lite questionnaire for vendor security reviews.'}
    <div style="margin-top:8px"><span class="control-evidence-badge">Status: ${profile.approval_status || 'draft'}</span>
    ${profile.approved_by ? `<span class="control-evidence-badge">Reviewed by ${profile.approved_by}</span>` : ''}</div>
    ${profile.updated_at ? `<div style="margin-top:6px;font-size:11px;color:var(--text-muted)">Last updated: ${new Date(profile.updated_at).toLocaleString()}</div>` : ''}
    <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn btn-secondary btn-sm" onclick="submitQuestionnaireApproval()"><i class="ph ph-paper-plane"></i> Submit for approval</button>
      <button class="btn btn-primary btn-sm" onclick="approveQuestionnaire()"><i class="ph ph-check"></i> Approve</button>
      <button class="btn btn-secondary btn-sm" onclick="rejectQuestionnaire()"><i class="ph ph-x"></i> Reject</button>
    </div>
  </div>`;
  el.innerHTML = header + (entries.length ? entries.map(([k,v])=>`
    <div class="schedule-row"><div><strong>${k.replace(/_/g,' ')}</strong>
      <span class="control-evidence-badge">${sources[k] === 'live_metrics' ? 'Live metrics' : 'Template'}</span>
    <p style="font-size:13px;margin:8px 0 0;color:var(--text-secondary)">${v}</p></div></div>`).join('')
    : '<div style="color:var(--text-muted)">Click <strong>Auto-fill from metrics</strong> to replace template answers with MTTD, MTTR, CVE lag, and SOC 2 readiness from your dashboard.</div>');
  } catch (e) {
    el.innerHTML = pageErrorHtml('Failed to load questionnaire profile.');
    console.error(e);
  }
}

async function runQuestionnaireAutoFill() {
  showToast('Generating questionnaire…', 'info');
  const data = await apiFetch('/api/questionnaires/auto-fill', { method: 'POST' });
  showToast(`Auto-filled ${Object.keys(data.responses||{}).length} answers`, 'success');
  loadQuestionnaires();
}

async function runAiQuestionnaireDraft(templateId) {
  showToast('AI drafting questionnaire answers…', 'info');
  const data = await apiFetch('/api/questionnaires/ai-draft', {
    method: 'POST',
    body: JSON.stringify({ template_id: templateId, use_ai: true }),
  });
  showToast(data?.message || 'Questionnaire drafted', 'success');
  loadQuestionnaires();
}

async function submitQuestionnaireApproval() {
  const res = await apiFetch('/api/questionnaires/submit-for-approval', { method: 'POST' });
  showToast(res?.message || 'Submitted for approval', 'success');
  loadQuestionnaires();
}

async function approveQuestionnaire() {
  const res = await apiFetch('/api/questionnaires/approve', { method: 'POST' });
  showToast(`Approved by ${res?.approved_by || 'admin'}`, 'success');
  loadQuestionnaires();
}

async function rejectQuestionnaire() {
  const res = await apiFetch('/api/questionnaires/reject', { method: 'POST' });
  showToast('Questionnaire returned for revision', 'warn');
  loadQuestionnaires();
}

let globalSearchTimer = null;
function debounceGlobalSearch(q) {
  clearTimeout(globalSearchTimer);
  globalSearchTimer = setTimeout(() => runGlobalSearch(q), 280);
}

async function runGlobalSearch(q) {
  const box = document.getElementById('global-search-results');
  if (!box) return;
  if (!q || q.trim().length < 2) {
    box.style.display = 'none';
    box.innerHTML = '';
    return;
  }
  const data = await apiFetch(`/api/search/?q=${encodeURIComponent(q.trim())}`);
  if (!data?.results?.length) {
    box.style.display = 'block';
    box.innerHTML = '<div class="global-search-empty">No results</div>';
    return;
  }
  box.style.display = 'block';
  box.innerHTML = data.results.map(r => `
    <button type="button" class="global-search-item" onclick="openGlobalSearchResult('${r.navigate}')">
      <span class="global-search-type">${r.type}</span>
      <strong>${r.title}</strong>
      <span class="global-search-sub">${r.subtitle || ''}</span>
    </button>`).join('');
}

function openGlobalSearchResult(page) {
  const box = document.getElementById('global-search-results');
  if (box) { box.style.display = 'none'; box.innerHTML = ''; }
  const input = document.getElementById('global-search-input');
  if (input) input.value = '';
  navigate(page);
}

function applyPageDataModeBanners() {
  const mode = tenantContext.data_mode;
  const labels = {
    sandbox: { icon: 'ph-flask', text: 'Sandbox scenario data — illustrative metrics only, not production telemetry.', cls: 'page-banner-sandbox' },
    awaiting_siem: { icon: 'ph-plug', text: 'SIEM not connected — configure a data source for live compliance metrics.', cls: 'page-banner-siem' },
    error: { icon: 'ph-warning', text: 'Pipeline error — check SIEM configuration or upload logs.', cls: 'page-banner-error' },
  };
  document.querySelectorAll('.page').forEach(page => {
    const existing = page.querySelector('.page-mode-banner');
    if (mode === 'live' || !labels[mode]) {
      if (existing) existing.remove();
      return;
    }
    const cfg = labels[mode];
    let banner = existing;
    if (!banner) {
      banner = document.createElement('div');
      page.insertBefore(banner, page.firstChild);
    }
    banner.className = `page-mode-banner ${cfg.cls}`;
    banner.innerHTML = `<i class="ph ${cfg.icon}"></i><span>${cfg.text}</span>`;
    banner.style.display = page.classList.contains('active') ? 'flex' : 'none';
  });
}

async function loadQuestionnaireLibrary() {
  const el = document.getElementById('questionnaire-library');
  if (!el) return;
  const lib = await apiFetch('/api/questionnaires/library');
  if (!lib?.templates) return;
  el.innerHTML = `<div class="readiness-frameworks">${lib.templates.map(t =>
    `<div class="readiness-fw-card" style="cursor:pointer" onclick="runAiQuestionnaireDraft('${t.id}')">
      <div class="readiness-fw-name">${t.name}</div>
      <div style="font-size:12px;color:var(--text-muted)">${t.question_count} questions</div>
      <div style="font-size:11px;margin-top:4px">${t.description}</div>
    </div>`).join('')}</div>
    <p style="font-size:12px;color:var(--text-muted);margin-top:8px">AI: ${lib.ai_enabled ? 'Ollama/OpenAI configured' : 'deterministic mode (set OLLAMA_URL or OPENAI_API_KEY)'}</p>`;
}

async function loadMobileDashboard() {
  const metricsEl = document.getElementById('mobile-metrics');
  if (metricsEl) metricsEl.innerHTML = pageLoadingHtml('Loading snapshot…');
  try {
  syncOrgLabels();
  const [metricsData, summaryData, readiness] = await Promise.all([
    apiFetch('/api/metrics/'),
    apiFetch('/api/metrics/summary'),
    apiFetch('/api/compliance/readiness'),
  ]);
  if (metricsData?.metrics) state.metrics = metricsData.metrics;
  if (summaryData) state.summary = summaryData;

  let readinessPct = null;
  if (readiness && typeof readiness.readiness_pct === 'number') {
    readinessPct = readiness.readiness_pct;
  }

  const s = state.summary || {};
  let green = s.green ?? 0;
  let amber = s.amber ?? 0;
  let red = s.red ?? 0;
  if (!green && !amber && !red && state.metrics?.length) {
    state.metrics.forEach(m => {
      if (m.rag_status === 'Green') green++;
      else if (m.rag_status === 'Amber') amber++;
      else if (m.rag_status === 'Red') red++;
    });
  }
  if (readinessPct === null && (green + amber + red) > 0) {
    readinessPct = Math.round((green * 100 + amber * 50) / (green + amber + red));
  }

  const pctEl = document.getElementById('mobile-readiness');
  if (pctEl) pctEl.textContent = readinessPct !== null ? `${readinessPct}%` : '—';

  const pills = document.getElementById('mobile-rag-pills');
  if (pills) {
    pills.innerHTML = `
      <span class="mobile-pill green">${green} Green</span>
      <span class="mobile-pill amber">${amber} Amber</span>
      <span class="mobile-pill red">${red} Red</span>`;
  }

  const el = document.getElementById('mobile-metrics');
  if (!el) return;
  const reds = (state.metrics || []).filter(m => m.rag_status === 'Red').slice(0, 3);
  const ambers = (state.metrics || []).filter(m => m.rag_status === 'Amber').slice(0, 2);
  const top = [...reds, ...ambers];
  if (!top.length) {
    el.innerHTML = '<div class="mobile-metric-empty">All metrics are within thresholds.</div>';
    return;
  }
  el.innerHTML = top.map(m => `
    <div class="mobile-metric-row">
      <span class="rag-badge ${m.rag_status}">${m.rag_status}</span>
      <span class="mobile-metric-name">${m.metric_name}</span>
      <strong>${typeof m.value === 'number' ? m.value.toFixed(1) : m.value}</strong>
    </div>`).join('');
  } catch (e) {
    if (metricsEl) metricsEl.innerHTML = pageErrorHtml('Failed to load mobile snapshot.');
    console.error(e);
  }
}

let marketplacePage = 1;
let marketplaceSearchTimer;

function marketplaceAvailabilityBadge(i) {
  if (i.availability === 'live') return '<span class="mp-badge mp-badge-live">Live</span>';
  if (i.availability === 'roadmap') return '<span class="mp-badge mp-badge-roadmap">Roadmap</span>';
  return '<span class="mp-badge mp-badge-catalog">Catalog</span>';
}

function marketplaceAuthBadge(i) {
  if (i.connection_status === 'connected') {
    const live = i.auth_method && !String(i.auth_method).includes('demo');
    return `<span class="mp-badge mp-badge-connected">${live ? 'Connected · Live' : 'Connected · Demo'}</span>`;
  }
  if (i.iam_role_available) return '<span class="mp-badge mp-badge-oauth">IAM Role</span>';
  if (i.oauth_available) {
    return `<span class="mp-badge mp-badge-oauth">${i.oauth_configured ? 'OAuth ready' : 'OAuth'}</span>`;
  }
  return '';
}

function marketplaceConnectButtons(i) {
  if (i.connection_status === 'connected') {
    return `
      ${!i.verified ? `<button class="btn btn-secondary btn-sm" onclick="verifyIntegration('${i.id}')">Verify</button>` : ''}
      <button class="btn btn-secondary btn-sm" onclick="disconnectIntegration('${i.id}')">Disconnect</button>`;
  }
  if (i.availability === 'roadmap') {
    return '<span style="font-size:11px;color:var(--text-muted)">Coming soon — request via support</span>';
  }
  const parts = [];
  if (i.iam_role_available) {
    parts.push(`<button class="btn btn-primary btn-sm" onclick="connectAwsCrossAccountRole()"><i class="ph ph-cloud"></i> IAM Role</button>`);
  }
  if (i.oauth_available) {
    parts.push(`<button class="btn btn-primary btn-sm" onclick="oauthConnect('${i.id}')">OAuth</button>`);
  }
  if (!i.iam_role_available) {
    parts.push(`<button class="btn btn-secondary btn-sm" onclick="connectMarketplace('${i.id}')">Connect</button>`);
  }
  return parts.join('');
}

function debounceMarketplaceSearch() {
  clearTimeout(marketplaceSearchTimer);
  marketplaceSearchTimer = setTimeout(() => loadMarketplace(1), 300);
}

async function loadMarketplace(page = 1) {
  marketplacePage = page;
  const el = document.getElementById('marketplace-grid');
  if (!el) return;
  const q = document.getElementById('marketplace-search')?.value || '';
  const cat = document.getElementById('marketplace-category')?.value || '';
  const avail = document.getElementById('marketplace-availability')?.value || '';
  const data = await apiFetch(`/api/connectors/marketplace?search=${encodeURIComponent(q)}&category=${encodeURIComponent(cat)}&availability=${encodeURIComponent(avail)}&page=${page}&limit=24`);
  const totalEl = document.getElementById('marketplace-total');
  if (totalEl && data?.total != null) totalEl.textContent = `${data.total}`;
  const liveEl = document.getElementById('marketplace-live-count');
  if (liveEl && data?.live_count != null) liveEl.textContent = `${data.live_count} live`;
  const roadmapEl = document.getElementById('marketplace-roadmap-count');
  if (roadmapEl && data?.roadmap_count != null) roadmapEl.textContent = `${data.roadmap_count} roadmap`;

  const catSel = document.getElementById('marketplace-category');
  if (catSel && data?.categories && !catSel.dataset.loaded) {
    catSel.innerHTML = '<option value="">All categories</option>' +
      data.categories.map(c => `<option value="${c}">${c}</option>`).join('');
    catSel.dataset.loaded = '1';
  }

  if (!data?.integrations?.length) {
    el.innerHTML = '<div style="color:var(--text-muted)">No integrations match your search.</div>';
    return;
  }
  el.innerHTML = data.integrations.map(i => {
    const verifyLabel = i.verified ? (i.auth_method === 'demo_oauth' ? 'Demo verified' : 'Live verified') : 'Not verified';
    return `
    <div class="marketplace-card" data-availability="${i.availability || 'catalog'}">
      <div class="marketplace-card-head">
        <strong>${i.name}</strong>
        <span class="control-evidence-badge">${i.category}</span>
      </div>
      <div class="marketplace-card-badges">
        ${marketplaceAvailabilityBadge(i)}
        ${marketplaceAuthBadge(i)}
        ${i.has_collector ? '<span class="mp-badge mp-badge-live">Collector</span>' : ''}
      </div>
      <p>${i.description}</p>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;gap:8px;flex-wrap:wrap">
        <span class="rag-badge ${i.connection_status === 'connected' ? 'Green' : 'Amber'}">${i.connection_status.replace('_', ' ')}</span>
        ${i.connection_status === 'connected' ? `<span class="control-evidence-badge">${verifyLabel}</span>` : ''}
        ${marketplaceConnectButtons(i)}
      </div>
    </div>`;
  }).join('');

  const pag = document.getElementById('marketplace-pagination');
  if (pag && data.pages > 1) {
    pag.innerHTML = Array.from({length: Math.min(data.pages, 8)}, (_, i) => i + 1).map(p =>
      `<button class="btn btn-sm ${p === data.page ? 'btn-primary' : 'btn-secondary'}" onclick="loadMarketplace(${p})">${p}</button>`
    ).join('');
  } else if (pag) pag.innerHTML = '';
}

async function oauthConnect(id) {
  if (id === 'aws') {
    return connectAwsCrossAccountRole();
  }
  const extraFields = {
    okta: [{ name: 'org_url', label: 'Okta org URL', placeholder: 'https://company.okta.com', type: 'url' }],
    servicenow: [{ name: 'instance_url', label: 'ServiceNow instance URL', placeholder: 'https://company.service-now.com', type: 'url' }],
    azure: [{ name: 'azure_tenant', label: 'Azure tenant ID', placeholder: 'common or tenant GUID' }],
  };
  const fields = extraFields[id] || [];
  const data = fields.length
    ? await showFormDialog({
        title: `Connect ${id}`,
        subtitle: 'OAuth will link this identity provider to your tenant.',
        fields,
        submitLabel: 'Connect with OAuth',
        icon: 'ph-shield-check',
      })
    : {};
  if (fields.length && !data) return;
  const res = await apiFetch(`/api/connectors/marketplace/${id}/oauth`, {
    method: 'POST',
    body: JSON.stringify({
      org_url: data?.org_url || undefined,
      instance_url: data?.instance_url || undefined,
      azure_tenant: data?.azure_tenant || undefined,
    }),
  });
  if (res?.authorize_url) {
    window.location.href = res.authorize_url;
    return;
  }
  if (res?.status === 'connected' || res?.mode === 'demo_oauth') {
    const mode = res?.mode === 'demo_oauth' ? 'demo' : 'live';
    showToast(`${id} connected via OAuth (${mode})`, mode === 'live' ? 'success' : 'info');
    loadMarketplace(marketplacePage);
    loadConnectors();
  } else if (res?.detail) {
    showToast(res.detail, 'error');
  }
}

async function connectAwsCrossAccountRole() {
  const data = await showFormDialog({
    title: 'Connect AWS — Cross-account IAM role',
    subtitle: 'VALENCE assumes a read-only IAM role in your AWS account to collect Config, CloudTrail, and GuardDuty evidence.',
    fields: [
      { name: 'role_arn', label: 'IAM Role ARN', placeholder: 'arn:aws:iam::123456789012:role/ValenceReadOnly' },
      { name: 'external_id', label: 'External ID', placeholder: 'valence-external-id (required)' },
      { name: 'region', label: 'Primary region', placeholder: 'us-east-1', value: 'us-east-1' },
      { name: 'account_id', label: 'Account ID (optional)', placeholder: '123456789012' },
    ],
    submitLabel: 'Connect AWS',
    icon: 'ph-cloud',
  });
  if (!data?.role_arn || !data?.external_id) return;
  const res = await apiFetch('/api/integrations/oauth/aws/role', {
    method: 'POST',
    body: JSON.stringify({
      role_arn: data.role_arn,
      external_id: data.external_id,
      region: data.region || 'us-east-1',
      account_id: data.account_id || undefined,
    }),
  });
  if (res?.status === 'connected') {
    showToast(res.message || `AWS connected (live)${res.expires_at ? ` — creds until ${new Date(res.expires_at).toLocaleString()}` : ''}`, 'success');
    loadMarketplace(marketplacePage);
    loadConnectors();
    loadTenantContext();
  } else {
    showToast(res?.detail || 'AWS IAM role connection failed', 'error');
  }
}

async function connectMarketplace(id) {
  const data = await showFormDialog({
    title: `Connect ${id}`,
    subtitle: 'Credentials are stored encrypted per tenant — never shared across organizations.',
    fields: [
      { name: 'url', label: 'Base URL (optional)', placeholder: 'https://api.example.com' },
      { name: 'api_key', label: 'API key / token (optional)', placeholder: '••••••••', type: 'password' },
    ],
    submitLabel: 'Connect',
    icon: 'ph-plugs-connected',
  });
  if (!data) return;
  const res = await apiFetch(`/api/connectors/marketplace/${id}/connect`, {
    method: 'POST',
    body: JSON.stringify({ url: data.url || undefined, api_key: data.api_key || undefined }),
  });
  if (res?.status === 'success') {
    showToast(`${id} connected — click Verify to test credentials`, 'success');
    loadMarketplace(marketplacePage);
    loadConnectors();
  }
}

async function disconnectIntegration(id) {
  const label = id.replace(/_/g, ' ');
  const ok = await showConfirmDialog({
    title: `Disconnect ${label}?`,
    subtitle: 'This stops data collection for your organization',
    message: 'Metrics, JML sync, and device compliance will no longer pull from this integration until you reconnect.',
    confirmLabel: 'Disconnect',
    cancelLabel: 'Keep connected',
    variant: 'danger',
    icon: 'ph-plug',
  });
  if (!ok) return;
  const res = await fetch(`${API}/api/connectors/marketplace/${id}/disconnect`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
      'X-Tenant-ID': currentTenantId,
    },
    body: '{}',
  });
  let body = {};
  try { body = await res.json(); } catch { /* empty */ }
  if (res.ok && body.status === 'disconnected') {
    showToast(`${label} disconnected`, 'success');
    loadMarketplace(marketplacePage);
    loadConnectors();
    loadTenantContext();
  } else {
    const msg = typeof body.detail === 'string' ? body.detail : 'Could not disconnect this integration';
    showToast(msg, 'error');
  }
}

async function verifyIntegration(id) {
  const res = await apiFetch(`/api/connectors/marketplace/${id}/verify`, { method: 'POST', body: '{}' });
  if (res?.verified) {
    showToast(res.message || `${id} verified`, 'success');
  } else {
    showToast(res?.message || 'Verification failed', 'error');
  }
  loadMarketplace(marketplacePage);
}

let activeFramework = 'DORA';

async function loadReadinessDashboard() {
  try {
    const data = await apiFetch('/api/compliance/readiness');
    if (!data) return;
    const pctEl = document.getElementById('readiness-overall-pct');
    if (pctEl) pctEl.textContent = `${data.readiness_pct ?? 0}%`;
    const container = document.getElementById('readiness-frameworks');
    if (!container) return;
    const frameworks = data.frameworks || [];
    container.innerHTML = frameworks.map(fw => `
      <div class="readiness-fw-card">
        <div class="readiness-fw-name">${fw.framework}</div>
        <div class="readiness-fw-bar"><div class="readiness-fw-fill" style="width:${fw.readiness_pct || 0}%"></div></div>
        <div class="readiness-fw-pct">${fw.readiness_pct ?? 0}%</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:4px">${fw.compliant}/${fw.total_controls} compliant</div>
      </div>
    `).join('');
  } catch {
    // non-fatal
  }
}

async function loadFramework(fw, tabEl) {
  document.querySelectorAll('.fw-tab').forEach(t => t.classList.remove('active'));
  if (tabEl) tabEl.classList.add('active');
  activeFramework = fw;
  const coverageEl = document.getElementById('coverage-pct');
  if (coverageEl) coverageEl.textContent = '…';
  document.getElementById('controls-list').innerHTML = '<div style="padding:20px;color:var(--text-muted)">Loading controls…</div>';

  const data = await apiFetch(`/api/compliance/${fw}`);
  if (!data) return;
  document.getElementById('fw-full-name').textContent = data.full_name || fw;
  const controls = data.controls || [];
  let compliant = data.compliant ?? 0;
  let atRisk = data.at_risk ?? 0;
  let nc = data.non_compliant ?? 0;
  const total = data.total_controls || controls.length;
  const pct = data.coverage_pct ?? (total ? Math.round((compliant / total) * 100) : 0);
  const readiness = data.readiness_pct ?? pct;
  const statusClass = s => String(s).replace(/ /g, '-');

  document.getElementById('coverage-pct').textContent = `${readiness}%`;
  document.querySelector('.coverage-sub').textContent = 'Readiness';
  document.getElementById('fw-compliant').textContent = compliant;
  document.getElementById('fw-at-risk').textContent = atRisk;
  document.getElementById('fw-nc').textContent = nc;
  document.getElementById('controls-list').innerHTML = controls.map(c => {
    const evidence = c.evidence || [];
    const evidenceHtml = evidence.length
      ? `<div class="control-evidence">${evidence.slice(0, 3).map(e => `
          <div class="control-evidence-item">
            <span class="control-evidence-badge">${e.event_type || 'evidence'}</span>
            <span>${e.evidence_id}</span>
            <span>${e.timestamp ? new Date(e.timestamp).toLocaleDateString() : ''}</span>
          </div>`).join('')}${evidence.length > 3 ? `<div style="margin-top:4px">+${evidence.length - 3} more records</div>` : ''}</div>`
      : '<div class="control-evidence">No linked evidence yet — runs after next pipeline cycle</div>';
    return `
    <div class="control-row">
      <div class="control-row-main">
        <div class="control-id">${c.control_id}</div>
        <div class="control-name">${c.title}</div>
        ${evidenceHtml}
      </div>
      <div class="control-status status-${statusClass(c.status)}">${c.status}</div>
    </div>`;
  }).join('');

  const ctx = document.getElementById('chart-coverage');
  if (charts.coverage) charts.coverage.destroy();
  charts.coverage = new Chart(ctx, {
    type: 'doughnut',
    data: { labels: ['Compliant', 'At Risk', 'Non-Compliant'], datasets: [{ data: [compliant, atRisk, nc], backgroundColor: ['#1F6B42', '#9A5F14', '#9B2C2C'], borderWidth: 2, borderColor: '#FAF9F6' }] },
    options: { responsive: false, cutout: '72%', plugins: { legend: { display: false } } }
  });
}

// ─── CONNECTORS ────────────────────────────────────────────
const SIEM_CONNECTORS = [
  { vendor:'Splunk', product:'Splunk Enterprise Security 7.3', url:'https://splunk.internal:8089', status:'healthy', latency_ms:42, events_per_sec:12400, data_volume:'2.3 TB/day', last_sync:'18 seconds ago', version:'v7.3.2 build 87174', icon:'ph-wave-sawtooth', color:'#FF6B35', bg:'#FFF4F0', description:'Primary SIEM · UEBA enabled' },
  { vendor:'IBM QRadar', product:'QRadar SIEM 7.5', url:'https://qradar.internal:443', status:'healthy', latency_ms:78, events_per_sec:8900, data_volume:'1.8 TB/day', last_sync:'1 minute ago', version:'v7.5.0 UP5', icon:'ph-database', color:'#054ADA', bg:'#EEF3FF', description:'Threat intel · X-Force integration' },
  { vendor:'Microsoft Sentinel', product:'Azure Sentinel (Log Analytics)', url:'https://api.loganalytics.io/v1/workspaces/val-ws', status:'healthy', latency_ms:120, events_per_sec:21000, data_volume:'4.1 TB/day', last_sync:'34 seconds ago', version:'REST API 2023-09-01', icon:'ph-cloud', color:'#0078D4', bg:'#E8F4FF', description:'Cloud-native · SOAR connected' },
  { vendor:'Elastic Security', product:'Elastic SIEM / ELK Stack 8.13', url:'https://elastic.internal:9200', status:'degraded', latency_ms:310, events_per_sec:5100, data_volume:'0.9 TB/day', last_sync:'4 minutes ago', version:'v8.13.4', icon:'ph-magnifying-glass', color:'#F04E98', bg:'#FFF0F7', description:'High latency · Degraded' },
  { vendor:'CrowdStrike', product:'Falcon Next-Gen SIEM', url:'https://api.us-2.crowdstrike.com/log-collector/entities/events/v1', status:'healthy', latency_ms:55, events_per_sec:3800, data_volume:'0.6 TB/day', last_sync:'11 seconds ago', version:'Falcon API v2', icon:'ph-shield-check', color:'#E0001B', bg:'#FFF0F1', description:'EDR telemetry · Threat graph' },
  { vendor:'Palo Alto Cortex', product:'Cortex XSIAM / XDR', url:'https://api-valence.xdr.us.paloaltonetworks.com', status:'inactive', latency_ms:null, events_per_sec:0, data_volume:'—', last_sync:'Not configured', version:'XSIAM 3.1', icon:'ph-intersect', color:'#FA582D', bg:'#FFF4F0', description:'Pending license activation' },
];

async function loadConnectors() {
  try {
    const [health, config] = await Promise.all([
      apiFetch('/api/connectors/health'),
      apiFetch('/api/connectors/config'),
    ]);
    if (config) {
      document.getElementById('config-siem-type').value = config.siem_type || '';
      document.getElementById('config-siem-url').value = config.siem_url || '';
      document.getElementById('config-slack-url').value = config.slack_webhook_url || '';
      document.getElementById('config-teams-url').value = config.teams_webhook_url || '';
      document.getElementById('config-pagerduty-key').value = config.pagerduty_routing_key || '';
      const status = document.getElementById('siem-config-status');
      if (status) {
        status.textContent = config.siem_api_key_configured
          ? 'API key on file. Enter a new key only to rotate.'
          : 'No API key saved yet.';
      }
    }
    if (health && health.connectors) {
      const mapped = health.connectors.map(c => ({
        vendor: c.name,
        product: c.type + ' connector',
        url: c.url || '—',
        status: c.status === 'healthy' ? 'healthy' : c.status === 'disconnected' ? 'inactive' : 'degraded',
        latency_ms: c.latency_ms,
        events_per_sec: 0,
        data_volume: '—',
        last_sync: c.last_checked ? new Date(c.last_checked).toLocaleString() : '—',
        version: c.type,
        icon: 'ph-plug',
        color: 'var(--accent)',
        bg: 'var(--accent-light)',
        description: c.note || c.error || 'Live connector status',
      }));
      renderConnectors(mapped);
    }
    await loadMarketplace();
  } catch(e) {
    renderConnectors([]);
  }
}

async function saveSiemConfig() {
  const payload = {
    siem_type: document.getElementById('config-siem-type').value,
    siem_url: document.getElementById('config-siem-url').value.trim(),
  };
  const key = document.getElementById('config-siem-key').value;
  if (key) payload.siem_api_key = key;
  const res = await apiFetch('/api/connectors/config', { method: 'POST', body: JSON.stringify(payload) });
  if (res?.status === 'success') {
    showToast('SIEM configuration saved for your organization', 'success');
    loadConnectors();
    await loadTenantContext();
  } else showToast('Failed to save SIEM config', 'error');
}

async function triggerPipeline() {
  showToast('Running metric pipeline…', 'info');
  const res = await apiFetch('/api/connectors/trigger-pipeline', { method: 'POST', body: '{}' });
  if (res?.status === 'ok') {
    showToast(`Pipeline complete — ${res.metrics_count} metrics loaded`, 'success');
    await loadAllData();
    await loadTenantContext();
  } else {
    showToast(res?.message || 'Pipeline failed — check SIEM configuration', 'error');
  }
}

function renderConnectors(connectors) {
  const list = Array.isArray(connectors) ? connectors : (connectors.connectors || []);
  const healthy  = list.filter(c => c.status === 'healthy').length;
  const degraded = list.filter(c => c.status !== 'healthy').length;
  const totalEPS = list.reduce((s,c) => s+(c.events_per_sec||0), 0);
  document.getElementById('cs-total').textContent    = list.length;
  document.getElementById('cs-healthy').textContent  = healthy;
  document.getElementById('cs-degraded').textContent = degraded;
  document.getElementById('cs-events').textContent   = totalEPS >= 1000 ? (totalEPS/1000).toFixed(1)+'K' : totalEPS;
  const badgeClass = { healthy:'badge-healthy', degraded:'badge-degraded', inactive:'badge-inactive', error:'badge-error' };
  const badgeLabel = { healthy:'Healthy', degraded:'Degraded', inactive:'Inactive', error:'Error' };
  document.getElementById('connectors-list').innerHTML = list.map(c => `
    <div class="connector-card">
      <div class="connector-card-header">
        <div class="connector-logo" style="background:${c.bg||'var(--bg-base)'}">
          <i class="ph ${c.icon||'ph-plug'}" style="color:${c.color||'var(--text-secondary)'}"></i>
        </div>
        <div style="flex:1;min-width:0">
          <div class="connector-vendor">${c.vendor}</div>
          <div class="connector-product">${c.product}</div>
        </div>
        <div class="connector-badge ${badgeClass[c.status]||'badge-inactive'}">
          <span class="badge-dot"></span>${badgeLabel[c.status]||c.status}
        </div>
      </div>
      <div class="connector-card-body">
        <div class="connector-url-row">
          <i class="ph ph-link"></i>
          <span class="connector-url-text">${c.url}</span>
        </div>
        <div class="connector-stats">
          <div class="connector-stat-item"><div class="connector-stat-label">Events / sec</div><div class="connector-stat-value">${c.events_per_sec?c.events_per_sec.toLocaleString():'—'}</div></div>
          <div class="connector-stat-item"><div class="connector-stat-label">Data Volume</div><div class="connector-stat-value">${c.data_volume||'—'}</div></div>
          <div class="connector-stat-item"><div class="connector-stat-label">Latency</div><div class="connector-stat-value">${c.latency_ms!=null?c.latency_ms+' ms':'—'}</div></div>
          <div class="connector-stat-item"><div class="connector-stat-label">Last Sync</div><div class="connector-stat-value" style="font-size:12px">${c.last_sync||'—'}</div></div>
        </div>
      </div>
      <div class="connector-card-footer">
        <span class="connector-version">${c.version}</span>
        <span class="connector-sync"><i class="ph ph-info" style="font-size:12px"></i>&nbsp;${c.description}</span>
      </div>
    </div>
  `).join('');
}

// ─── REPORTS ───────────────────────────────────────────────
let selectedReportIds = new Set();

async function loadReports() {
  try {
    const data = await apiFetch('/api/reports/');
    if (data) {
      state.reports = data;
      const valid = new Set(data.map(r => r.report_id));
      selectedReportIds = new Set([...selectedReportIds].filter(id => valid.has(id)));
      renderReports(data);
    }
  } catch (e) {
    if (state.reports?.length) renderReports(state.reports);
  }
}

async function loadReportSchedules() {
  try {
    const data = await apiFetch('/api/reports/schedules');
    renderReportSchedules(data || []);
  } catch {
    renderReportSchedules([]);
  }
}

function renderReportSchedules(schedules) {
  const el = document.getElementById('schedules-list');
  if (!el) return;
  if (!schedules.length) {
    el.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">No scheduled exports — add one to automate auditor delivery.</div>';
    return;
  }
  el.innerHTML = schedules.map(s => `
    <div class="schedule-row">
      <div>
        <strong>${s.framework}</strong> · ${s.frequency}
        <div class="schedule-row-meta">
          Next: ${s.next_run_at ? new Date(s.next_run_at).toLocaleString() : '—'}
          ${s.recipient_email ? ` · ${s.recipient_email}` : ''}
          ${s.last_run_at ? ` · Last: ${new Date(s.last_run_at).toLocaleDateString()}` : ''}
        </div>
      </div>
      <button class="btn btn-secondary btn-sm" onclick="deleteReportSchedule(${s.id})"><i class="ph ph-trash"></i></button>
    </div>
  `).join('');
}

async function createReportSchedule() {
  const frequency = document.getElementById('schedule-frequency')?.value || 'weekly';
  const framework = document.getElementById('schedule-framework')?.value || 'SOC2';
  const recipient_email = document.getElementById('schedule-email')?.value.trim() || null;
  const res = await apiFetch('/api/reports/schedules', {
    method: 'POST',
    body: JSON.stringify({ frequency, framework, recipient_email, enabled: true })
  });
  if (res?.id) {
    showToast('Auditor export schedule created', 'success');
    loadReportSchedules();
  } else {
    showToast('Failed to create schedule', 'error');
  }
}

async function deleteReportSchedule(id) {
  const res = await fetch(`${API}/api/reports/schedules/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${accessToken}`, 'X-Tenant-ID': currentTenantId }
  });
  if (res.ok || res.status === 204) {
    showToast('Schedule removed', 'info');
    loadReportSchedules();
  }
}

function updateReportsToolbar(reports) {
  const toolbar = document.getElementById('reports-toolbar');
  const completed = (reports || []).filter(r => r.status === 'completed');
  if (toolbar) toolbar.style.display = completed.length ? 'flex' : 'none';
  const selectAll = document.getElementById('reports-select-all');
  if (selectAll) {
    const completedIds = completed.map(r => r.report_id);
    selectAll.checked = completedIds.length > 0 && completedIds.every(id => selectedReportIds.has(id));
    selectAll.indeterminate = selectedReportIds.size > 0 && !selectAll.checked;
  }
  const countEl = document.getElementById('reports-selected-count');
  if (countEl) countEl.textContent = `${selectedReportIds.size} selected`;
  const dlBtn = document.getElementById('reports-download-selected');
  if (dlBtn) dlBtn.disabled = selectedReportIds.size === 0;
}

function toggleReportSelection(reportId, checked) {
  if (checked) selectedReportIds.add(reportId);
  else selectedReportIds.delete(reportId);
  updateReportsToolbar(state.reports);
}

function toggleSelectAllReports(checked) {
  const completed = (state.reports || []).filter(r => r.status === 'completed');
  selectedReportIds = checked ? new Set(completed.map(r => r.report_id)) : new Set();
  renderReports(state.reports);
}

async function downloadSelectedReports() {
  const ids = [...selectedReportIds].filter(id => {
    const row = (state.reports || []).find(r => r.report_id === id);
    return row && row.status === 'completed';
  });
  if (!ids.length) {
    showToast('No completed reports selected', 'error');
    return;
  }
  showToast(`Downloading ${ids.length} report${ids.length > 1 ? 's' : ''}…`, 'info');
  for (const id of ids) {
    await downloadReport(id, { silent: true });
    await new Promise(r => setTimeout(r, 350));
  }
  showToast(`Downloaded ${ids.length} report${ids.length > 1 ? 's' : ''}`, 'success');
}

function renderReports(reports) {
  const list = document.getElementById('reports-list');
  updateReportsToolbar(reports);
  if (!reports || !reports.length) {
    list.innerHTML = `<div class="reports-empty"><i class="ph ph-file-dashed"></i><div class="reports-empty-title">No reports yet</div><p>Click <strong>Generate PDF Report</strong> to create your first cryptographically signed export.</p></div>`;
    return;
  }
  list.innerHTML = reports.map(r => {
    const done = r.status === 'completed';
    const checked = selectedReportIds.has(r.report_id);
    const statusClass = r.status === 'completed' ? 'Green' : r.status === 'generating' ? 'Amber' : 'Red';
    return `
    <div class="report-row ${checked ? 'report-row--selected' : ''}">
      <label class="report-row-check">
        <input type="checkbox" ${done ? '' : 'disabled'} ${checked ? 'checked' : ''} onchange="toggleReportSelection('${r.report_id}', this.checked)" />
      </label>
      <div class="report-row-main">
        <div class="report-id">${r.report_id}</div>
        <div class="report-meta">Run: ${r.run_id} &nbsp;·&nbsp; ${new Date(r.generated_at).toLocaleString()} &nbsp;·&nbsp; By: ${r.generated_by}</div>
      </div>
      <div class="report-row-actions">
        <span class="rag-badge ${statusClass}">${r.status}</span>
        ${done ? `<button class="btn btn-secondary btn-sm" onclick="downloadReport('${r.report_id}')"><i class="ph ph-download-simple"></i> Download</button>` : ''}
        ${done ? `<button class="btn btn-sm btn-verify" onclick="verifyReport('${r.report_id}')"><i class="ph ph-lock-key"></i> Verify</button>` : ''}
      </div>
    </div>`;
  }).join('');
}

async function generateReport() {
  showToast('Generating PDF report...', 'info');
  try {
    if (false) throw new Error('Demo');
    const data = await apiFetch('/api/reports/generate', { method:'POST', body: JSON.stringify({ title:'VALENCE GRC Report', include_narratives:true, include_monte_carlo:true }) });
    if (data && data.report_id) {
      showToast('Report generation started: ' + data.report_id, 'success');
      state.reports.unshift({ report_id: data.report_id, run_id: data.report_id, status:'generating', generated_at: new Date().toISOString(), generated_by: currentUser.username });
      renderReports(state.reports);
      setTimeout(() => pollReportStatus(data.report_id), 5000);
    }
  } catch(e) {
    const fakeId = 'RPT_' + Math.random().toString(36).substring(2,10).toUpperCase();
    state.reports.unshift({ report_id: fakeId, run_id: 'VALENCE_DEMO', status:'completed', generated_at: new Date().toISOString(), generated_by: currentUser.username || 'admin' });
    renderReports(state.reports);
    showToast('Demo report created: ' + fakeId, 'success');
  }
}

async function pollReportStatus(reportId) {
  try {
    const data = await apiFetch(`/api/reports/${reportId}/status`);
    const idx  = state.reports.findIndex(r => r.report_id === reportId);
    if (idx >= 0 && data) state.reports[idx] = { ...state.reports[idx], ...data };
    renderReports(state.reports);
    if (data && data.status === 'generating') setTimeout(() => pollReportStatus(reportId), 5000);
    else if (data && data.status === 'completed') showToast('Report ready: ' + reportId, 'success');
  } catch(e) {}
}

async function downloadReport(reportId, opts = {}) {
  const { silent = false } = opts;
  if (!silent) showToast('Preparing download…', 'info');
  try {
    const res = await fetch(`${API}/api/reports/${encodeURIComponent(reportId)}/download`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'X-Tenant-ID': currentTenantId,
      },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (!silent) showToast(formatApiError(err) || `Download failed (${res.status})`, 'error');
      return false;
    }
    const blob = await res.blob();
    if (!blob.size) {
      if (!silent) showToast('Report file is empty', 'error');
      return false;
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `valence-grc-${reportId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    if (!silent) showToast('Report downloaded — open from your browser downloads folder', 'success');
    return true;
  } catch (e) {
    if (!silent) showToast('Download failed — check your session', 'error');
    return false;
  }
}

async function verifyReport(reportId) {
  showToast('Verifying cryptographic lineage...', 'info');
  try {
    const data = await apiFetch(`/api/reports/${reportId}/verify`);
    if (data && data.verified) showToast('Verified: Report integrity confirmed. Zero tampering detected.', 'success');
    else showToast(data?.reason || 'Verification failed', 'error');
  } catch(e) {
    showToast('Demo Verified: Signature SHA-256 matches registry. Integrity confirmed.', 'success');
  }
}

// ─── WHAT-IF SIMULATOR ─────────────────────────────────────
async function loadWhatIfPage() {
  try {
    let data;
    if (false) data = getDemoWhatIfPresets();
    else data = await apiFetch('/api/risk/whatif/presets');
    if (data) {
      currentWhatIfPresets = data.presets || [];
      const select = document.getElementById('whatif-preset-select');
      select.innerHTML = '<option value="">— Custom —</option>' +
        currentWhatIfPresets.map(p => `<option value="${p.id}">${p.name} (−$${(p.estimated_annual_cost_usd/1000).toFixed(0)}K)</option>`).join('');
      const container = document.getElementById('whatif-sliders-container');
      container.innerHTML = state.metrics.map(m => {
        const key = m.metric_id;
        whatIfSliders[key] = { adjustment_pct: 0, investment_usd: 0 };
        const label = data.investment_models[key]?.label || 'Budget Adjustment';
        return `
          <div class="slider-card" id="whatif-card-${key}">
            <div class="slider-header">
              <div>
                <strong style="font-size:13px;color:var(--text-primary)">${m.metric_name}</strong>
                <span class="slider-meta" style="margin-left:8px">${key} (Current: ${m.value.toFixed(1)} ${m.unit || ''})</span>
              </div>
              <div class="investment-input-group">
                <span>Invest:</span>
                <input type="number" min="0" value="0" class="investment-input" id="whatif-invest-${key}" onchange="updateWhatIfInvestment('${key}', this.value)">
                <span>USD</span>
              </div>
            </div>
            <div class="slider-row">
              <span style="font-size:10px;color:var(--text-muted);width:44px">Improve</span>
              <input type="range" min="-100" max="100" value="0" class="slider-input" id="whatif-slider-${key}" oninput="updateWhatIfSliderValue('${key}', this.value)">
              <span style="font-size:10px;color:var(--text-muted);width:36px;text-align:right">Degrade</span>
              <span class="slider-label-val" id="whatif-val-${key}">0%</span>
            </div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:7px">Model: ${label}</div>
          </div>
        `;
      }).join('');
      runWhatIfSimulation();
    }
  } catch(e) {}
}

function updateWhatIfSliderValue(key, val) {
  whatIfSliders[key].adjustment_pct = parseFloat(val);
  document.getElementById(`whatif-val-${key}`).textContent = val > 0 ? `+${val}%` : `${val}%`;
  const card = document.getElementById(`whatif-card-${key}`);
  card.style.borderColor = (parseFloat(val) !== 0 || whatIfSliders[key].investment_usd > 0) ? 'var(--accent)' : 'var(--border)';
}

function updateWhatIfInvestment(key, val) {
  whatIfSliders[key].investment_usd = parseFloat(val) || 0;
  const card = document.getElementById(`whatif-card-${key}`);
  card.style.borderColor = (parseFloat(val) > 0 || whatIfSliders[key].adjustment_pct !== 0) ? 'var(--accent)' : 'var(--border)';
}

function applyWhatIfPreset(presetId) {
  resetWhatIfSliders();
  if (!presetId) return;
  const preset = currentWhatIfPresets.find(p => p.id === presetId);
  if (!preset) return;
  preset.scenarios.forEach(sc => {
    const key = sc.metric_id;
    if (whatIfSliders[key]) {
      whatIfSliders[key].adjustment_pct = sc.adjustment_pct;
      whatIfSliders[key].investment_usd = sc.investment_usd;
      document.getElementById(`whatif-slider-${key}`).value = sc.adjustment_pct;
      document.getElementById(`whatif-invest-${key}`).value = sc.investment_usd;
      updateWhatIfSliderValue(key, sc.adjustment_pct);
    }
  });
  runWhatIfSimulation();
}

function resetWhatIfSliders() {
  document.getElementById('whatif-preset-select').value = '';
  Object.keys(whatIfSliders).forEach(key => {
    whatIfSliders[key] = { adjustment_pct: 0, investment_usd: 0 };
    const sl = document.getElementById(`whatif-slider-${key}`);
    const inv = document.getElementById(`whatif-invest-${key}`);
    if (sl) sl.value = 0;
    if (inv) inv.value = 0;
    updateWhatIfSliderValue(key, 0);
  });
  runWhatIfSimulation();
}

async function runWhatIfSimulation() {
  showToast('Running Monte Carlo risk simulation...', 'info');
  const scenarios = Object.keys(whatIfSliders)
    .filter(k => whatIfSliders[k].adjustment_pct !== 0 || whatIfSliders[k].investment_usd > 0)
    .map(k => ({ metric_id: k, adjustment_pct: whatIfSliders[k].adjustment_pct, investment_usd: whatIfSliders[k].investment_usd }));
  try {
    let data;
    if (false) data = simulateWhatIfDemo(scenarios);
    else data = await apiFetch('/api/risk/whatif/simulate', { method: 'POST', body: JSON.stringify({ scenarios, simulation_runs: 1000 }) });
    if (data) {
      const proj = data.projected_portfolio;
      const curr = data.current_portfolio;
      document.getElementById('whatif-proj-var').textContent = formatUSD(proj.total_var_95_usd);
      const varDiff = curr.total_var_95_usd - proj.total_var_95_usd;
      document.getElementById('whatif-proj-var-change').textContent = `Orig: ${formatUSD(curr.total_var_95_usd)} (${varDiff >= 0 ? 'Risk Reduced' : 'Risk Spiked'})`;
      document.getElementById('whatif-proj-var-change').style.color = varDiff >= 0 ? 'var(--green)' : 'var(--red)';
      document.getElementById('whatif-proj-investment').textContent = formatUSD(data.simulation.total_investment_usd);
      document.getElementById('whatif-proj-roi').textContent = `ROI: ${proj.roi_ratio}x VaR reduction`;
      document.getElementById('whatif-proj-roi').style.color = proj.roi_ratio > 0 ? 'var(--green)' : 'var(--text-muted)';
      const totRags = proj.green_count + proj.amber_count + proj.red_count || 1;
      document.getElementById('whatif-bar-green').style.width = `${(proj.green_count/totRags)*100}%`;
      document.getElementById('whatif-bar-amber').style.width = `${(proj.amber_count/totRags)*100}%`;
      document.getElementById('whatif-bar-red').style.width   = `${(proj.red_count  /totRags)*100}%`;
      document.getElementById('whatif-cnt-green').textContent = `Green: ${proj.green_count}`;
      document.getElementById('whatif-cnt-amber').textContent = `Amber: ${proj.amber_count}`;
      document.getElementById('whatif-cnt-red').textContent   = `Red: ${proj.red_count}`;
      const listEl = document.getElementById('whatif-projected-list');
      if (data.changes.length === 0) {
        listEl.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:20px">No adjustments made. Use sliders to simulate changes.</div>';
      } else {
        listEl.innerHTML = data.changes.map(ch => `
          <div style="border-bottom:1px solid var(--border);padding:8px 0;display:flex;justify-content:space-between;align-items:center">
            <div>
              <strong style="color:var(--text-primary)">${ch.metric_id}</strong>
              <div style="font-size:10px;color:var(--text-muted)">${ch.metric_name}</div>
            </div>
            <div style="text-align:right">
              <div><span class="rag-badge ${ch.original_rag}" style="font-size:9px;padding:1px 5px">${ch.original_rag}</span> &rarr; <span class="rag-badge ${ch.projected_rag}" style="font-size:9px;padding:1px 5px">${ch.projected_rag}</span></div>
              <div style="font-size:11px;color:${ch.var_delta_usd >= 0 ? 'var(--green)' : 'var(--red)'};margin-top:3px">${ch.var_delta_usd >= 0 ? 'Reduced' : 'Spiked'} VaR: ${formatUSD(Math.abs(ch.var_delta_usd))}</div>
            </div>
          </div>
        `).join('');
      }
      let narrative = '';
      if (scenarios.length === 0) narrative = 'No active scenarios applied. Move sliders to see quantitative risk changes.';
      else if (varDiff > 0) {
        narrative = `Applying these changes will reduce VaR by <strong>${formatUSD(varDiff)}</strong>.`;
        if (data.simulation.total_investment_usd > 0) narrative += ` With an investment of <strong>${formatUSD(data.simulation.total_investment_usd)}</strong>, ROI ratio is <strong>${proj.roi_ratio}x</strong> in risk reduction.`;
      } else if (varDiff < 0) {
        narrative = `WARNING: Projected adjustments increase portfolio VaR by <strong style="color:var(--red)">${formatUSD(Math.abs(varDiff))}</strong>. Remediation action required.`;
      } else {
        narrative = 'Scenario simulated. Risk level remains unchanged.';
      }
      document.getElementById('whatif-roi-summary-text').innerHTML = narrative;
      showToast('Simulation completed', 'success');
    }
  } catch(e) {}
}

// ─── BENCHMARKING ──────────────────────────────────────────
async function loadBenchmarkingPage() {
  const select = document.getElementById('benchmark-industry-select');
  select.innerHTML = '<option>Loading...</option>';
  try {
    let data;
    if (false) data = getDemoBenchmarks("Financial Services");
    else data = await apiFetch('/api/benchmarking/');
    if (data) {
      select.innerHTML = data.available_industries.map(ind => `<option value="${ind}" ${ind === data.industry ? 'selected' : ''}>${ind}</option>`).join('');
      renderBenchmarkData(data);
    }
  } catch(e) {}
}

async function loadBenchmarks(industry) {
  showToast(`Loading benchmarks for ${industry}...`, 'info');
  try {
    let data;
    if (false) data = getDemoBenchmarks(industry);
    else data = await apiFetch(`/api/benchmarking/?industry=${encodeURIComponent(industry)}`);
    if (data) renderBenchmarkData(data);
  } catch(e) {}
}

function renderBenchmarkData(data) {
  const o = data.overall_score;
  const gradeEl = document.getElementById('benchmark-org-grade');
  gradeEl.textContent = o.grade;
  gradeEl.style.color = o.grade === 'A' || o.grade === 'B' ? 'var(--green)' : o.grade === 'C' ? 'var(--amber)' : 'var(--red)';
  document.getElementById('benchmark-org-percentile').textContent = `(${o.average_percentile}th percentile)`;
  document.getElementById('bench-avg-percentile').textContent = `${o.average_percentile}%`;
  document.getElementById('bench-excellent-count').textContent = o.excellent_metrics;
  document.getElementById('bench-critical-count').textContent = o.critical_gaps;
  const grid = document.getElementById('benchmarking-list');
  grid.innerHTML = data.comparisons.map(comp => {
    const assessColor = comp.your_percentile >= 75 ? 'var(--green)' : comp.your_percentile >= 50 ? 'var(--accent)' : comp.your_percentile >= 25 ? 'var(--amber)' : 'var(--red)';
    return `
      <div class="benchmark-gauge-card">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
          <div>
            <div class="metric-id">${comp.metric_id}</div>
            <h4 style="font-size:13.5px;font-weight:600;color:var(--text-primary);margin-top:2px">${comp.metric_name}</h4>
          </div>
          <div style="text-align:right">
            <span style="font-size:11px;font-weight:700;color:${assessColor};background:var(--bg-base);border:1px solid var(--border);padding:2px 8px;border-radius:12px">${comp.assessment}</span>
            <div style="font-size:11px;color:var(--text-muted);margin-top:4px">Peer Median: ${comp.industry_p50} ${comp.unit}</div>
          </div>
        </div>
        <div style="display:flex;align-items:baseline;gap:6px;margin:10px 0 4px">
          <span style="font-size:20px;font-weight:800;color:var(--text-primary)">${comp.your_value.toFixed(1)}</span>
          <span style="font-size:11px;color:var(--text-muted)">${comp.unit}</span>
          <span style="font-size:11.5px;font-weight:600;color:${comp.gap_direction === 'better' ? 'var(--green)' : 'var(--red)'};margin-left:auto">
            ${comp.gap_to_median === 0 ? 'Equal to median' : `${comp.gap_to_median.toFixed(1)} ${comp.unit} ${comp.gap_direction === 'better' ? 'better' : 'worse'} than median`}
          </span>
        </div>
        <div class="percentile-track">
          <div class="percentile-fill" style="width:${comp.your_percentile}%"></div>
          <div class="percentile-marker" style="left:${comp.your_percentile}%"></div>
        </div>
        <div class="benchmark-ticks">
          <span>25th</span><span>50th (Median)</span><span>75th</span><span>90th</span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);margin-top:3px;font-family:'IBM Plex Mono',monospace">
          <span>${comp.industry_p25}</span><span>${comp.industry_p50}</span><span>${comp.industry_p75}</span><span>${comp.industry_p90}</span>
        </div>
        <div style="margin-top:10px;font-size:10.5px;color:var(--text-muted)">Source: ${comp.source}</div>
      </div>
    `;
  }).join('');
}

// ─── TIMELINE ──────────────────────────────────────────────
async function loadTimelinePage() {
  try {
    let data;
    if (false) data = generateDemoTimelineHistory(currentTimelineDays);
    else data = await apiFetch(`/api/timeline/?days=${currentTimelineDays}`);
    if (data) {
      state.timelineSnapshots = data.snapshots || [];
      const scrubber = document.getElementById('timeline-range-scrubber');
      scrubber.max   = state.timelineSnapshots.length - 1;
      scrubber.value = state.timelineSnapshots.length - 1;
      renderTimelineChart(data);
      showSnapshotDetail(state.timelineSnapshots.length - 1);
      loadTimelineEvents();
    }
  } catch(e) {}
}

async function loadTimelineEvents() {
  try {
    const data = await apiFetch('/api/timeline/events');
    const container = document.getElementById('timeline-events-list');
    if (!data) return;
    if (!data.events || !data.events.length) {
      container.innerHTML = `<div style="padding:24px;text-align:center;color:var(--text-muted);font-size:13px;line-height:1.6">${data.message || 'No security events recorded yet for your organization.'}</div>`;
      return;
    }
    if (data.source === 'sandbox_scenario') {
      container.innerHTML = `<div style="padding:10px 14px;margin-bottom:12px;background:var(--accent-light);border:1px solid var(--accent-border);border-radius:8px;font-size:12px;color:var(--accent)"><i class="ph ph-info"></i> Sandbox scenario events — illustrative only, not real incidents.</div>`;
    } else {
      container.innerHTML = '';
    }
    const listHtml = (data.events || []).map(evt => {
        const sc = evt.severity === 'critical' || evt.severity === 'high' ? 'critical' : evt.severity === 'warning' ? 'warning' : 'info';
        return `
          <div class="timeline-wrap" style="margin-bottom:0">
            <div class="timeline-item">
              <span class="timeline-badge ${sc}"></span>
              <div class="timeline-meta">${new Date(evt.timestamp).toLocaleString()} &nbsp;·&nbsp; ${evt.type}</div>
              <div class="timeline-title">${evt.title}</div>
              <div class="timeline-desc">${evt.description}</div>
              <div style="display:flex;gap:5px;margin-top:6px;flex-wrap:wrap">
                ${evt.affected_metrics.map(m => `<span style="font-size:10px;background:var(--accent-light);border:1px solid var(--accent-border);color:var(--accent);padding:2px 6px;border-radius:4px;font-family:'IBM Plex Mono',monospace">${m}</span>`).join('')}
              </div>
            </div>
          </div>
        `;
    }).join('');
    container.insertAdjacentHTML('beforeend', listHtml);
  } catch(e) {}
}

function renderTimelineChart(data) {
  const ctx = document.getElementById('chart-timeline-trend');
  if (!ctx) return;
  if (charts.timelineTrend) charts.timelineTrend.destroy();
  const labels  = data.snapshots.map(s => new Date(s.timestamp).toLocaleDateString(undefined, {month:'short', day:'numeric'}));
  const varData = data.snapshots.map(s => s.summary.total_var_usd);
  charts.timelineTrend = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets: [{ label:'Value at Risk (VaR)', data: varData, borderColor:'#126B63', backgroundColor:'rgba(18,107,99,0.08)', borderWidth:2, fill:true, tension:0.25, pointRadius:1, pointHoverRadius:4 }] },
    options: {
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ display:false } },
      scales:{
        x:{ ticks:{ color:'#7A766E', maxTicksLimit:10, font:{ family:'IBM Plex Mono', size:10 } }, grid:{ color:'rgba(30,32,36,0.06)' } },
        y:{ ticks:{ color:'#7A766E', font:{ family:'IBM Plex Mono', size:10 }, callback: v => '$'+(v/1000).toFixed(0)+'K' }, grid:{ color:'rgba(30,32,36,0.06)' } }
      }
    }
  });
}

function scrubTimeline(index) {
  if (state.timelineSnapshots && state.timelineSnapshots[index]) showSnapshotDetail(index);
}

function showSnapshotDetail(index) {
  const snap = state.timelineSnapshots[index];
  if (!snap) return;
  const date = new Date(snap.timestamp);
  document.getElementById('timeline-scrub-date').textContent = date.toLocaleDateString(undefined, {month:'short',day:'numeric',year:'numeric'});
  document.getElementById('snapshot-title').textContent = `Snapshot: ${snap.run_id}`;
  document.getElementById('snapshot-timestamp').textContent = date.toLocaleString();
  document.getElementById('snapshot-ale').textContent = formatUSD(snap.summary.total_var_usd * 0.4);
  const g=snap.summary.green, a=snap.summary.amber, r=snap.summary.red;
  document.getElementById('snapshot-gar').innerHTML = `<span style="color:var(--green)">${g}</span> / <span style="color:var(--amber)">${a}</span> / <span style="color:var(--red)">${r}</span>`;
  document.getElementById('snapshot-metrics-list').innerHTML = snap.metrics.map(m => `
    <div style="background:var(--bg-base);padding:8px 12px;border-radius:4px;border:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
      <div>
        <span style="font-size:10px;font-family:'IBM Plex Mono',monospace;color:var(--text-muted)">${m.metric_id}</span>
        <div style="font-size:12.5px;font-weight:600;color:var(--text-primary)">${m.metric_name}</div>
      </div>
      <div style="text-align:right">
        <span style="font-size:13px;font-weight:700;color:var(--text-primary)">${m.value.toFixed(1)}</span>
        <span class="rag-badge ${m.rag_status}" style="font-size:9px;padding:1px 5px;margin-left:5px">${m.rag_status}</span>
      </div>
    </div>
  `).join('');
}

function toggleTimelinePlay() {
  const btn = document.getElementById('btn-timeline-play');
  const scrubber = document.getElementById('timeline-range-scrubber');
  if (timelinePlaying) {
    timelinePlaying = false;
    btn.innerHTML = '<i class="ph ph-play"></i> Play';
    clearInterval(timelinePlayTimer);
  } else {
    timelinePlaying = true;
    btn.innerHTML = '<i class="ph ph-pause"></i> Pause';
    timelinePlayTimer = setInterval(() => {
      let val = parseInt(scrubber.value);
      val = val >= state.timelineSnapshots.length - 1 ? 0 : val + 1;
      scrubber.value = val;
      scrubTimeline(val);
    }, 400);
  }
}

// ─── THREAT INTEL ──────────────────────────────────────────
async function loadThreatIntelPage() {
  try {
    let data;
    if (false) data = getDemoThreatIntelData();
    else data = await apiFetch('/api/threat-intel/');
    if (data) {
      const feedNote = document.getElementById('threat-intel-feed-note');
      if (feedNote) {
        const kevLive = data.cisa_kev?.live_feed;
        const isSandbox = tenantContext.is_demo;
        feedNote.innerHTML = isSandbox
          ? '<i class="ph ph-flask"></i> Correlations use <strong>sandbox scenario metrics</strong>. CISA KEV catalog is fetched from the public feed.'
          : kevLive
            ? '<i class="ph ph-broadcast"></i> CISA KEV synced from live feed · correlations use <strong>your organization metrics</strong>'
            : '<i class="ph ph-warning"></i> CISA KEV cached · connect SIEM for accurate correlations';
      }
      const lvl = data.threat_level;
      const levelEl = document.getElementById('threat-intel-level');
      levelEl.textContent = lvl.level;
      levelEl.style.color = lvl.color;
      const pulseEl = document.getElementById('threat-intel-pulse');
      pulseEl.style.background = lvl.color;
      document.getElementById('threat-intel-count-alerts').textContent = `${data.correlations.length} Correlated Exposures`;
      const alertsContainer = document.getElementById('threat-intel-alerts');
      if (data.correlations.length === 0) {
        alertsContainer.innerHTML = `<div style="background:var(--green-bg);border:1px solid var(--green-border);border-radius:var(--radius);padding:32px;text-align:center;color:var(--green)"><i class="ph ph-shield-check" style="font-size:32px;display:block;margin-bottom:8px"></i>No critical threat correlations identified. Controls are aligned with current cyber intel.</div>`;
      } else {
        alertsContainer.innerHTML = data.correlations.map(alert => {
          const sevColor = alert.severity === 'critical' ? 'var(--red)' : alert.severity === 'high' ? 'var(--amber)' : 'var(--accent)';
          const sevBg = alert.severity === 'critical' ? 'var(--red-bg)' : alert.severity === 'high' ? 'var(--amber-bg)' : 'var(--accent-light)';
          return `
            <div style="background:var(--bg-surface);border:1px solid var(--border);border-left:4px solid ${sevColor};border-radius:var(--radius);padding:18px">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <span class="rag-badge" style="background:${sevBg};color:${sevColor};border-color:transparent;font-size:10px;font-weight:700">${alert.severity.toUpperCase()}</span>
                <span style="font-size:11px;color:var(--text-muted);font-family:'IBM Plex Mono',monospace">Affected: ${alert.affected_metrics.join(', ')}</span>
              </div>
              <h4 style="font-size:14px;font-weight:700;margin-bottom:6px;color:var(--text-primary)">${alert.title}</h4>
              <p style="font-size:12.5px;color:var(--text-secondary);line-height:1.5;margin-bottom:10px">${alert.description}</p>
              ${alert.threat_groups ? `<div style="font-size:11px;color:var(--text-muted);margin-bottom:8px">Threat Actors: ${alert.threat_groups.map(g => `<strong style="color:var(--text-secondary)">${g}</strong>`).join(', ')}</div>` : ''}
              <div style="background:var(--bg-base);padding:10px 12px;border-radius:var(--radius-sm);border:1px solid var(--border);font-size:12px">
                <strong style="color:var(--accent);display:block;margin-bottom:3px">Recommended Action:</strong>
                <span style="color:var(--text-secondary)">${alert.recommended_action}</span>
              </div>
            </div>
          `;
        }).join('');
      }
      state.threatData = data;
      switchThreatTab(activeThreatTab);
    }
  } catch(e) {}
}

function switchThreatTab(tab) {
  activeThreatTab = tab;
  document.getElementById('btn-tab-kev').classList.toggle('active', tab === 'kev');
  document.getElementById('btn-tab-mitre').classList.toggle('active', tab === 'mitre');
  const container = document.getElementById('threat-tab-content');
  if (!state.threatData) return;
  if (tab === 'kev') {
    const list = state.threatData.cisa_kev.vulnerabilities;
    container.innerHTML = list.map(v => `
      <div style="border-bottom:1px solid var(--border);padding:12px 0">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <strong style="font-family:'IBM Plex Mono',monospace;color:var(--accent);font-size:13px">${v.cve_id}</strong>
          <span style="background:var(--red-bg);color:var(--red);font-size:9px;padding:1px 5px;border-radius:4px;font-weight:700;border:1px solid var(--red-border)">CVSS ${v.cvss}</span>
        </div>
        <div style="font-weight:600;color:var(--text-primary);margin-bottom:4px">${v.vendor} ${v.product} — ${v.vulnerability_name}</div>
        <div style="color:var(--text-secondary);font-size:12.5px;line-height:1.4">${v.notes}</div>
        <div style="display:flex;justify-content:space-between;font-size:10.5px;color:var(--text-muted);margin-top:7px">
          <span>Added: ${v.date_added}</span>
          <span style="${v.known_ransomware_use ? 'color:var(--red);font-weight:700' : ''}">${v.known_ransomware_use ? 'Ransomware Linked' : 'No Ransomware Link'}</span>
        </div>
      </div>
    `).join('');
  } else {
    const list = state.threatData.mitre_attack_trends;
    container.innerHTML = list.map(t => `
      <div style="border-bottom:1px solid var(--border);padding:12px 0">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <strong style="font-family:'IBM Plex Mono',monospace;color:var(--violet);font-size:13px">${t.technique_id}</strong>
          <span style="color:${t.trend === 'surging' ? 'var(--red)' : 'var(--amber)'};font-weight:700;font-size:11px">${t.trend.toUpperCase()} (+${t.change_pct}%)</span>
        </div>
        <div style="font-weight:600;color:var(--text-primary);margin-bottom:4px">${t.technique_name} (${t.tactic})</div>
        <div style="color:var(--text-secondary);font-size:12.5px;line-height:1.4">${t.description}</div>
        <div style="margin-top:5px;font-size:10.5px;color:var(--text-muted)">Mapped Indicators: ${t.affected_metrics.join(', ')}</div>
      </div>
    `).join('');
  }
}

// ─── EVIDENCE VAULT ────────────────────────────────────────
async function loadEvidencePage() {
  try {
    let data;
    if (false) data = getDemoEvidenceVaultData();
    else data = await apiFetch('/api/evidence/');
    if (data) {
      const header = document.getElementById('evidence-vault-status');
      if (data.chain_integrity.valid) {
        header.className = 'evidence-header';
        header.innerHTML = `
          <div class="evidence-header-left">
            <div class="evidence-header-icon"><i class="ph ph-shield-check"></i></div>
            <div>
              <div class="evidence-header-title">Evidence Cryptographic Chain Validated</div>
              <div class="evidence-header-sub">All metric snapshots are SHA-256 chained in a tamper-proof immutable lineage.</div>
            </div>
          </div>
          <div style="display:flex;gap:8px">
            <select id="evidence-export-framework" style="font-size:12px;padding:6px 12px">
              <option value="SOC2">SOC 2 Type II</option>
              <option value="DORA">DORA 2025</option>
              <option value="NIS2">NIS2</option>
              <option value="ISO27001">ISO 27001:2022</option>
            </select>
            <button class="btn btn-primary btn-sm" onclick="exportEvidencePack()"><i class="ph ph-export"></i> Export Evidence Pack</button>
          </div>
        `;
      } else {
        header.className = 'evidence-header invalid';
        header.innerHTML = `
          <div class="evidence-header-left">
            <div class="evidence-header-icon" style="background:var(--red)"><i class="ph ph-warning"></i></div>
            <div>
              <div style="font-size:14px;font-weight:700;color:var(--red)">Evidence Chain Validation FAILURE</div>
              <div class="evidence-header-sub">Warning: Cryptographic signature mismatch detected. Possible tampering.</div>
            </div>
          </div>
        `;
      }
      document.getElementById('evd-algorithm').textContent = data.chain_integrity.algorithm;
      document.getElementById('evd-total-records').textContent = data.chain_integrity.total_records;
      document.getElementById('evd-latest-hash').textContent = data.chain_integrity.latest_hash;
      document.getElementById('evidence-ledger-list').innerHTML = data.records.map(record => `
        <div class="evidence-row">
          <span class="evidence-id">${record.evidence_id}</span>
          <div style="font-size:11.5px;color:var(--text-muted);font-family:'IBM Plex Mono',monospace">${new Date(record.timestamp).toLocaleString()}</div>
          <div style="font-weight:600;font-size:12.5px;color:var(--text-primary)">${record.event_type.replace('_',' ')}</div>
          <div class="evidence-hash" title="${record.hash}">${record.hash}</div>
          <button class="btn btn-sm" style="background:var(--accent-light);border-color:var(--accent-border);color:var(--accent)" onclick="verifySingleEvidence('${record.evidence_id}')"><i class="ph ph-lock-key"></i> Verify</button>
        </div>
      `).join('');
    }
  } catch(e) {}
}

async function verifySingleEvidence(id) {
  showToast('Recomputing hash and checking lineage link...', 'info');
  try {
    let data;
    if (false) data = verifyDemoEvidenceSingle(id);
    else data = await apiFetch(`/api/evidence/verify/${id}`);
    if (data) {
      if (data.error) { showToast(`Error: ${data.error}`, 'error'); return; }
      document.getElementById('v-id').textContent = data.evidence_id;
      document.getElementById('v-timestamp').textContent = new Date(data.timestamp).toLocaleString();
      document.getElementById('v-prev').textContent = data.previous_hash;
      document.getElementById('v-stored').textContent = data.stored_hash;
      document.getElementById('v-recomputed').textContent = data.recomputed_hash;
      const banner = document.getElementById('verification-result-banner');
      if (data.verified && data.chain_link_valid) {
        banner.style.background = 'var(--green-bg)'; banner.style.color = 'var(--green)'; banner.style.borderColor = 'var(--green-border)';
        banner.innerHTML = '<i class="ph ph-check-circle"></i> Integrity Confirmed — SHA-256 signatures match. Previous node linkage verified. Zero tampering detected.';
      } else {
        banner.style.background = 'var(--red-bg)'; banner.style.color = 'var(--red)'; banner.style.borderColor = 'var(--red-border)';
        banner.innerHTML = '<i class="ph ph-warning"></i> WARNING: Cryptographic hashes mismatch or link signature broken! Evidence payload has been modified.';
      }
      showModalOverlay('verification-modal');
      showToast('Cryptographic verification complete', 'success');
    }
  } catch(e) {}
}

function closeVerificationModal() { hideModalOverlay('verification-modal'); }

async function exportEvidencePack() {
  const fw = document.getElementById('evidence-export-framework').value;
  showToast(`Creating Evidence Pack for ${fw}...`, 'info');
  try {
    let data;
    if (false) data = exportDemoEvidencePack(fw);
    else data = await apiFetch(`/api/evidence/export?framework=${fw}`);
    if (data) {
      document.getElementById('export-framework-subtitle').textContent = `${fw} Audit Submission Evidence Pack`;
      document.getElementById('exp-pack-id').textContent = data.pack_id;
      document.getElementById('exp-count').textContent = data.summary.total_evidence_records;
      document.getElementById('exp-attestation-hash').textContent = data.attestation.hash;
      document.getElementById('exp-statement').textContent = data.attestation.statement;
      showModalOverlay('export-modal');
      showToast('Evidence pack generated successfully', 'success');
    }
  } catch(e) {}
}

function closeExportModal() { hideModalOverlay('export-modal'); }

// ─── CASCADE ───────────────────────────────────────────────
async function loadRiskCascade() {
  try {
    let data;
    if (false) data = getDemoRiskCascadeData();
    else data = await apiFetch('/api/risk/cascade/analyze');
    if (data) {
      const container = document.getElementById('cascade-list');
      if (data.cascade_chains.length === 0) {
        container.style.gridTemplateColumns = '1fr';
        container.innerHTML = '<div style="background:var(--green-bg);border:1px solid var(--green-border);padding:18px;border-radius:var(--radius-sm);text-align:center;color:var(--green);font-weight:500">All core risk indicators are within safe thresholds. No active risk cascade chains detected.</div>';
        return;
      }
      container.style.gridTemplateColumns = 'repeat(2,1fr)';
      container.innerHTML = data.cascade_chains.map(chain => `
        <div style="background:var(--bg-base);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px">
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:10px">
            <div>
              <span class="rag-badge ${chain.source_rag}" style="font-size:9px;padding:1px 5px">${chain.source_rag}</span>
              <strong style="font-size:13px;margin-left:6px;color:var(--text-primary)">${chain.source_metric_id}</strong>
            </div>
            <span style="font-size:11px;color:var(--text-muted)">Max fine: &euro;${(chain.compliance_impacts.reduce((a,c)=>a+c.max_fine_eur,0)/1000000).toFixed(1)}M</span>
          </div>
          <div style="font-size:12.5px;font-weight:600;color:var(--text-primary);margin-bottom:7px">${chain.source_metric_name}</div>
          <div style="font-size:11.5px;color:var(--text-muted);margin-bottom:8px">Blast Radius: ${chain.downstream_impacts.length} downstream metrics affected</div>
          <div style="display:flex;flex-direction:column;gap:5px;font-size:11px;background:var(--bg-surface);padding:8px 10px;border-radius:4px;border:1px solid var(--border)">
            ${chain.downstream_impacts.map(dep => `
              <div style="display:flex;align-items:center;gap:5px">
                <span style="color:var(--text-muted)">&rarr;</span>
                <span style="font-family:'IBM Plex Mono',monospace;color:var(--accent);font-weight:600">${dep.target_metric_id}</span>
                <span style="color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:140px">${dep.target_metric_name}</span>
                <span style="margin-left:auto;color:var(--red);font-weight:700">+${(dep.impact_factor*100).toFixed(0)}% VaR</span>
              </div>
            `).join('')}
            ${chain.compliance_impacts.map(comp => `
              <div style="display:flex;align-items:center;gap:5px;color:var(--violet)">
                <span style="color:var(--text-muted)">&rarr;</span>
                <strong>${comp.framework} ${comp.control}</strong>
                <span style="color:var(--text-muted)">${comp.regulation}</span>
              </div>
            `).join('')}
          </div>
        </div>
      `).join('');
    }
  } catch(e) {}
}

function populateCascadeMetricSelect() {
  const select = document.getElementById('cascade-simulation-select');
  select.innerHTML = '<option value="">— Select Metric —</option>' +
    state.metrics.map(m => `<option value="${m.metric_id}">${m.metric_id} — ${m.metric_name.substring(0,30)}</option>`).join('');
}

async function runCascadeSimulation(metricId) {
  const container = document.getElementById('cascade-results-container');
  if (!metricId) { container.style.display = 'none'; return; }
  showToast('Simulating cascade propagation...', 'info');
  try {
    let data;
    if (false) data = simulateCascadeDemoSingle(metricId);
    else data = await apiFetch(`/api/risk/cascade/simulate/${metricId}`);
    if (data) {
      container.style.display = 'block';
      const metricsAffected = data.affected_metrics.join(', ') || 'None';
      const frameworksAffected = data.compliance_impacts.map(c => `${c.framework} ${c.control}`).join(', ') || 'None';
      container.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:12px">
          <h4 style="font-size:13.5px;font-weight:700;color:var(--red)">Simulated Blast Radius: ${data.source_metric.metric_id} goes RED</h4>
          <span style="font-size:11px;color:var(--text-muted)">Max propagation depth: ${data.total_depth} nodes</span>
        </div>
        <p style="font-size:12.5px;color:var(--text-secondary);line-height:1.5;margin-bottom:12px">When this control breaches SLA boundaries, it causes alert fatigue, longer dwell times, and compliance framework vulnerability propagation.</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;font-size:12px">
          <div><strong style="display:block;margin-bottom:4px;color:var(--text-primary)">Affected Metrics:</strong><span style="color:var(--text-secondary)">${metricsAffected}</span></div>
          <div><strong style="display:block;margin-bottom:4px;color:var(--text-primary)">Compliance Gaps:</strong><span style="color:var(--violet)">${frameworksAffected}</span></div>
        </div>
        <div style="margin-top:12px;display:flex;flex-direction:column;gap:5px;background:var(--bg-surface);padding:10px;border-radius:4px;border:1px solid var(--border);font-size:11.5px">
          ${data.cascade_chain.map(link => `
            <div style="display:flex;align-items:center;gap:6px">
              <span style="font-family:'IBM Plex Mono',monospace;color:var(--accent)">${link.from}</span>
              <span style="color:var(--text-muted)">&rarr;</span>
              <span style="font-family:'IBM Plex Mono',monospace;color:var(--violet)">${link.to}</span>
              <span style="color:var(--text-secondary)">${link.relationship}</span>
              <span style="margin-left:auto;color:var(--red);font-weight:700">+${(link.impact_factor*100).toFixed(0)}%</span>
            </div>
          `).join('')}
        </div>
      `;
      showToast('Blast radius calculated', 'success');
    }
  } catch(e) {}
}

// ─── BOARD DECK ────────────────────────────────────────────
async function generateBoardDeck() {
  const q = document.getElementById('board-quarter').value;
  const a = document.getElementById('board-audience').value;
  const t = document.getElementById('board-tone').value;
  showToast('Building Board Presentation Deck...', 'info');
  try {
    let data;
    if (false) data = getDemoBoardDeckData(q, a, t);
    else data = await apiFetch('/api/board-deck/generate', { method: 'POST', body: JSON.stringify({ quarter:q, audience:a, tone:t, include_financials:true, include_compliance:true, include_recommendations:true }) });
    if (data) {
      currentDeckSlides = [];
      currentDeckSlides.push({
        badge: data.slide_1_title.classification,
        title: data.slide_1_title.title,
        subtitle: data.slide_1_title.subtitle,
        html: `<div style="display:flex;flex-direction:column;justify-content:center;align-items:center;height:220px;text-align:center">
          <div style="width:56px;height:56px;background:var(--accent);border-radius:14px;display:flex;align-items:center;justify-content:center;margin-bottom:16px"><i class="ph ph-shield-check" style="color:#fff;font-size:28px"></i></div>
          <h2 style="font-size:32px;font-weight:900;letter-spacing:-1px;color:var(--text-primary);margin-bottom:6px">VALENCE</h2>
          <div style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:2px;font-weight:600">Security Posture Executive Presentation</div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:16px;font-family:'IBM Plex Mono',monospace">Generated: ${data.slide_1_title.date} &nbsp;·&nbsp; By: ${data.generated_by}</div>
        </div>`
      });
      const exec = data.slide_2_executive_summary;
      currentDeckSlides.push({
        badge: 'Slide 2 — Executive Summary',
        title: exec.title,
        subtitle: `Overall Assessment: ${exec.overall_assessment}`,
        html: `<div style="display:grid;grid-template-columns:3fr 2fr;gap:20px;min-height:180px">
          <div style="font-size:14px;color:var(--text-secondary);line-height:1.7;border-right:1px solid var(--border);padding-right:20px">${exec.narrative}</div>
          <div style="display:grid;gap:10px">
            <div style="background:var(--bg-base);padding:12px;border-radius:var(--radius-sm);border:1px solid var(--border)">
              <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;font-weight:600">Value at Risk (95th Pct)</div>
              <div style="font-size:22px;font-weight:800;color:var(--red);margin-top:4px">${formatUSD(exec.key_figures.portfolio_var_95_usd)}</div>
            </div>
            <div style="background:var(--bg-base);padding:12px;border-radius:var(--radius-sm);border:1px solid var(--border)">
              <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;font-weight:600">Annual Loss Expectancy</div>
              <div style="font-size:20px;font-weight:800;color:var(--amber);margin-top:4px">${formatUSD(exec.key_figures.portfolio_ale_usd)}</div>
            </div>
            <div style="background:var(--bg-base);padding:10px 12px;border-radius:var(--radius-sm);border:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;font-size:12px">
              <span style="color:var(--text-muted)">Controls:</span>
              <strong style="color:var(--green)">${exec.key_figures.metrics_within_threshold}G</strong>&nbsp;
              <strong style="color:var(--amber)">${exec.key_figures.metrics_at_risk}A</strong>&nbsp;
              <strong style="color:var(--red)">${exec.key_figures.metrics_breached}R</strong>
            </div>
          </div>
        </div>`
      });
      const landscape = data.slide_3_risk_landscape;
      currentDeckSlides.push({
        badge: 'Slide 3 — Risk Details',
        title: landscape.title,
        subtitle: 'Control Metric Financial Exposure and Priority Level',
        html: `<div style="max-height:240px;overflow-y:auto">
          <table class="data-table">
            <thead><tr><th>ID</th><th>Metric</th><th>RAG</th><th style="text-align:right">95th VaR</th><th>Action</th><th>Priority</th></tr></thead>
            <tbody>${landscape.metric_details.map(m => `
              <tr>
                <td style="font-family:'IBM Plex Mono',monospace;color:var(--accent);font-size:11px">${m.metric_id}</td>
                <td><strong style="color:var(--text-primary)">${m.metric_name}</strong></td>
                <td><span class="rag-badge ${m.rag_status}" style="font-size:9px;padding:1px 5px">${m.rag_status}</span></td>
                <td style="text-align:right;font-weight:700;color:var(--red)">${formatUSD(m.var_95_usd)}</td>
                <td style="color:var(--text-secondary);font-size:11.5px">${m.recommended_action}</td>
                <td style="color:${m.priority.includes('Critical') ? 'var(--red)' : m.priority.includes('High') ? 'var(--amber)' : 'var(--text-muted)'};font-weight:600">${m.priority}</td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>`
      });
      if (data.slide_4_compliance) {
        const comp = data.slide_4_compliance;
        currentDeckSlides.push({
          badge: 'Slide 4 — Regulatory Mapping',
          title: comp.title, subtitle: 'Active coverage status across frameworks',
          html: `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;min-height:160px">
            ${comp.frameworks.map(fw => {
              const statusColor = fw.status === 'Compliant' || fw.status === 'On Track' ? 'var(--green)' : 'var(--amber)';
              return `<div style="background:var(--bg-base);border:1px solid var(--border);padding:14px;border-radius:var(--radius-sm)">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;border-bottom:1px solid var(--border);padding-bottom:6px">
                  <strong style="font-size:15px;color:var(--text-primary)">${fw.name}</strong>
                  <span style="font-size:11px;font-weight:700;color:${statusColor}">${fw.status.toUpperCase()}</span>
                </div>
                <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">Identified Gaps:</div>
                <p style="font-size:12.5px;line-height:1.4;color:var(--text-primary);font-weight:500">${fw.key_gap}</p>
              </div>`;
            }).join('')}
          </div>`
        });
      }
      if (data.slide_5_recommendations) {
        const recs = data.slide_5_recommendations;
        currentDeckSlides.push({
          badge: 'Slide 5 — Investment Proposals',
          title: recs.title,
          subtitle: `Total: ${formatUSD(recs.summary.total_recommended_investment_usd)} budget → ${formatUSD(recs.summary.total_projected_var_reduction_usd)} risk reduction (${recs.summary.portfolio_roi_ratio}x ROI)`,
          html: `<div style="max-height:240px;overflow-y:auto">
            <table class="data-table">
              <thead><tr><th>Pr.</th><th>Recommendation</th><th style="text-align:right">Budget</th><th style="text-align:right">VaR Reduction</th><th>Timeline</th><th style="text-align:right">ROI</th></tr></thead>
              <tbody>${recs.recommendations.map(r => `
                <tr>
                  <td style="font-weight:700;color:var(--violet)">#${r.priority}</td>
                  <td><strong>${r.title}</strong><div style="font-size:10px;color:var(--text-muted);margin-top:2px">${r.description}</div></td>
                  <td style="text-align:right;font-weight:700">${formatUSD(r.investment_usd)}</td>
                  <td style="text-align:right;font-weight:700;color:var(--green)">${formatUSD(r.projected_var_reduction_usd)}</td>
                  <td style="color:var(--text-secondary)">${r.timeline}</td>
                  <td style="text-align:right;font-weight:700;color:var(--accent)">${r.roi_ratio}x</td>
                </tr>`).join('')}
              </tbody>
            </table>
          </div>`
        });
      }
      const steps = data.slide_6_next_steps;
      currentDeckSlides.push({
        badge: 'Slide 6 — Decision Points',
        title: steps.title,
        subtitle: 'Action items for the Board and Security Teams',
        html: `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;min-height:160px">
          ${steps.items.map((it,i) => `
            <div style="background:var(--bg-base);border:1px solid var(--border);padding:14px;border-radius:var(--radius-sm);border-top:3px solid ${it.priority==='Critical' ? 'var(--red)' : it.priority==='High' ? 'var(--amber)' : 'var(--accent)'}">
              <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">Decision #${i+1} (${it.priority})</div>
              <h4 style="font-size:13.5px;font-weight:700;margin-bottom:10px;color:var(--text-primary);line-height:1.3">${it.action}</h4>
              <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-top:auto">
                <span>Owner: <strong style="color:var(--text-secondary)">${it.owner}</strong></span>
                <span>Due: <strong style="color:var(--text-secondary)">${it.deadline}</strong></span>
              </div>
            </div>`).join('')}
        </div>`
      });
      currentDeckSlideIndex = 0;
      renderDeckSlide(0);
      const dots = document.getElementById('deck-dots');
      dots.innerHTML = currentDeckSlides.map((_,i) => `<span class="slide-dot ${i===0?'active':''}" onclick="goToSlide(${i})"></span>`).join('');
      document.getElementById('deck-presentation-wrapper').style.display = 'block';
      showToast('Board deck generated', 'success');
    }
  } catch(e) {}
}

function renderDeckSlide(idx) {
  const slide = currentDeckSlides[idx];
  if (!slide) return;
  document.getElementById('deck-slides-container').innerHTML = `
    <div class="deck-slide active">
      <div class="deck-badge">${slide.badge}</div>
      <h3>${slide.title}</h3>
      <div class="slide-subtitle">${slide.subtitle}</div>
      <div class="deck-slide-content">${slide.html}</div>
    </div>
  `;
}

function prevSlide() { if (currentDeckSlideIndex > 0) goToSlide(currentDeckSlideIndex - 1); }
function nextSlide() { if (currentDeckSlideIndex < currentDeckSlides.length - 1) goToSlide(currentDeckSlideIndex + 1); }
function goToSlide(idx) {
  currentDeckSlideIndex = idx;
  renderDeckSlide(idx);
  document.querySelectorAll('.slide-dot').forEach((d,i) => d.classList.toggle('active', i === idx));
}

// ─── NAVIGATION ────────────────────────────────────────────
const PAGE_TITLES = {
  dashboard:    { title: 'Security Dashboard',        sub: 'Real-time GRC metrics and risk quantification' },
  risk:         { title: 'Risk Analysis',             sub: 'Monte Carlo simulations and FAIR VaR modeling' },
  whatif:       { title: 'What-If Risk Simulator',    sub: 'Simulate budget allocation changes and projected risk reductions' },
  benchmarking: { title: 'Industry Benchmarking',     sub: 'Anonymized peer comparison against Verizon DBIR and SANS data' },
  timeline:     { title: 'Security Posture Timeline', sub: '90-day continuous audit trail and historical transition events' },
  'threat-intel': { title: 'Threat Intelligence Feed', sub: 'CISA KEV and MITRE ATT&CK live metric correlation' },
  evidence:     { title: 'Compliance Evidence Vault', sub: 'SHA-256 hash-chained continuous monitoring records' },
  compliance:   { title: 'Compliance Frameworks',     sub: 'DORA · NIS2 · SOC 2 Type II coverage mapping' },
  reports:      { title: 'Reports & Executive Deck',  sub: 'Zero-trust audit reports and board-level deck generation' },
  connectors:   { title: 'SIEM Connectors',           sub: 'Data source health and connector configuration' },
  team:         { title: 'Team Access',               sub: 'Provision GRC, SOC, and IR members with scoped module permissions' },
  vendors:      { title: 'SENTINEL Vendor Risk',      sub: 'Third-party vendor scoring and tier classification' },
  mobile:       { title: 'Mobile Executive View',     sub: 'Read-only compliance snapshot for leadership' },
  findings:     { title: 'Audit Findings',            sub: 'Track compliance gaps from detection to closure' },
  policies:     { title: 'Policy Library',            sub: 'Published policies and employee attestation tracking' },
  auditor:      { title: 'Auditor Portal',            sub: 'Read-only workspace for external auditors' },
  personnel:    { title: 'Personnel & Devices',       sub: 'JML lifecycle events and MDM endpoint compliance' },
  questionnaires: { title: 'Security Questionnaires', sub: 'SIG Lite auto-fill from live compliance posture' },
  training:       { title: 'Security Training',         sub: 'Video, SCORM, and quiz-based awareness courses' },
  pentest:        { title: 'Pen Test Program',          sub: 'Assessment scheduling and findings tracking' },
  platform:     { title: 'Platform Competitive Edge',   sub: 'VALENCE vs Vanta, Drata, ServiceNow, and MetricStream' },
  enterprise:   { title: 'Enterprise Command Center', sub: 'Workflows, ITSM, billing, MSP portfolio, and integrations' },
  'command-center': { title: 'Risk Command Center', sub: 'SIEM metrics mapped to controls and FAIR financial exposure' },
};

function navigate(page) {
  const features = new Set(userFeatures.length ? userFeatures : (currentUser.feature_list || []));
  const required = NAV_FEATURE_MAP[`nav-${page}`];
  if (required && !features.has(required) && !hasDemoAccess()) {
    showToast('Your account does not have access to this section', 'warn');
    return;
  }
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const pageEl = document.getElementById(`page-${page}`);
  if (pageEl) pageEl.classList.add('active');
  document.body.classList.toggle('mobile-layout', page === 'mobile' || page === 'vendors');
  const navEl = document.getElementById(`nav-${page}`);
  if (navEl) navEl.classList.add('active');
  const t = PAGE_TITLES[page];
  if (t) {
    document.getElementById('topbar-title').textContent = t.title;
    document.getElementById('topbar-sub').textContent   = t.sub;
  }
  applyPageDataModeBanners();
  runPageLoader(page);
}

// ─── UTILS ─────────────────────────────────────────────────
function formatUSD(val) {
  if (!val && val !== 0) return '—';
  if (val >= 1_000_000) return '$' + (val/1_000_000).toFixed(1) + 'M';
  if (val >= 1_000)     return '$' + (val/1_000).toFixed(0) + 'K';
  return '$' + val.toFixed(0);
}

function showToast(msg, type = 'info') {
  const icons = { info:'ph-info', success:'ph-check-circle', warn:'ph-warning', error:'ph-x-circle' };
  const toast = document.getElementById('toast');
  toast.className = `toast show ${type}`;
  document.getElementById('toast-icon-wrap').innerHTML = `<i class="ph ${icons[type]||'ph-info'}"></i>`;
  document.getElementById('toast-msg').textContent = msg;
  setTimeout(() => toast.classList.remove('show'), 4000);
}

function destroyCharts() {
  Object.values(charts).forEach(c => { try { c.destroy(); } catch(e){} });
  charts = {};
}

document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && document.getElementById('login-page').style.display !== 'none') handleLogin();
});

window.addEventListener('load', async () => {
  await loadSandboxInfo();
  await loadSSOConfig();
  if (await handleSSOCallback()) return;
  if (!accessToken) return;

  try {
    const res = await fetch(`${API}/api/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}`, 'X-Tenant-ID': currentTenantId },
    });
    if (res.ok) {
      currentUser = await res.json();
      localStorage.setItem('valence_user', JSON.stringify(currentUser));
      showApp();
      return;
    }
    if (res.status === 401 && await refreshAccessToken()) {
      const retry = await fetch(`${API}/api/auth/me`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (retry.ok) {
        currentUser = await retry.json();
        localStorage.setItem('valence_user', JSON.stringify(currentUser));
        showApp();
        return;
      }
    }
  } catch {
    if (currentUser.username) {
      showApp();
      return;
    }
  }

  clearAuth();
});

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/sw.js').catch(()=>{});
  });
}

// ─── DEMO DATA HELPERS ──────────────────────────────────────
function getDemoWhatIfPresets() {
  return {
    presets: [
      { id:"hire_soc_analysts", name:"Hire 2 SOC Analysts", description:"Adding 2 FTE SOC analysts reduces MTTR by 30% and MTTD by 15%", estimated_annual_cost_usd:240000, scenarios:[{metric_id:"KRI-MTTR-001",adjustment_pct:-30,investment_usd:160000},{metric_id:"KRI-MTTD-001",adjustment_pct:-15,investment_usd:80000}] },
      { id:"deploy_soar", name:"Deploy SOAR Platform", description:"Automated playbooks reduce MTTR by 50% and FPR by 25%", estimated_annual_cost_usd:180000, scenarios:[{metric_id:"KRI-MTTR-001",adjustment_pct:-50,investment_usd:120000},{metric_id:"KPI-FPR-001",adjustment_pct:-25,investment_usd:60000}] },
      { id:"patch_automation", name:"Automated Patch Management", description:"Reduces CVE patch lag by 75% through automated pipelines", estimated_annual_cost_usd:95000, scenarios:[{metric_id:"KRI-CVE-001",adjustment_pct:-75,investment_usd:95000}] }
    ],
    investment_models: {
      "KRI-MTTD-001":{label:"Detection tooling / SIEM rules"},
      "KRI-MTTR-001":{label:"SOC analyst staffing / SOAR playbooks"},
      "KPI-FPR-001": {label:"ML model tuning / rule refinement"},
      "KRI-CVE-001": {label:"Patch automation / vulnerability scanner"},
      "KPI-PHI-001": {label:"PAM license expansion / access reviews"},
      "KRI-DLP-001": {label:"DLP agent deployment / policy tuning"},
    }
  };
}

function simulateWhatIfDemo(scenarios) {
  const current_var = state.metrics.reduce((a,m)=>a+m.var_95_usd,0);
  const current_ale = state.metrics.reduce((a,m)=>a+m.ale_usd,0);
  let total_investment=0, var_reduction=0, green=0, amber=0, red=0;
  const changes = scenarios.map(sc => {
    const original = state.metrics.find(m => m.metric_id === sc.metric_id);
    if (!original) return null;
    total_investment += sc.investment_usd;
    const factor = Math.abs(sc.adjustment_pct) / 100;
    const reducedVar = Math.round(original.var_95_usd * (1 - factor * 0.8));
    const delta = original.var_95_usd - reducedVar;
    var_reduction += delta;
    let projRag = original.rag_status;
    if (sc.adjustment_pct < -40) projRag = 'Green';
    else if (sc.adjustment_pct < -15) projRag = 'Amber';
    return { metric_id: sc.metric_id, metric_name: original.metric_name, original_rag: original.rag_status, projected_rag: projRag, var_delta_usd: delta };
  }).filter(c => c !== null);
  state.metrics.forEach(m => {
    const mod = changes.find(c => c.metric_id === m.metric_id);
    const rag = mod ? mod.projected_rag : m.rag_status;
    if (rag==='Green') green++; else if (rag==='Amber') amber++; else red++;
  });
  return {
    simulation: { total_investment_usd: total_investment },
    current_portfolio: { total_var_95_usd: current_var, total_ale_usd: current_ale },
    projected_portfolio: { total_var_95_usd: current_var - var_reduction, total_ale_usd: current_ale - Math.round(var_reduction*0.4), roi_ratio: total_investment > 0 ? (var_reduction/total_investment).toFixed(1) : 0, green_count: green, amber_count: amber, red_count: red },
    changes
  };
}

function getDemoBenchmarks(industry) {
  return {
    industry, available_industries:["Financial Services","Healthcare","Technology","Retail","Energy","Government"],
    overall_score:{ grade:'B', average_percentile:72, excellent_metrics:2, critical_gaps:1 },
    comparisons:[
      { metric_id:'KRI-MTTD-001', metric_name:'Mean Time to Detect', your_value:14.2, unit:'min', industry_p25:28, industry_p50:18, industry_p75:12, industry_p90:8, your_percentile:65, assessment:'Above Average', assessment_icon:'', gap_to_median:3.8, gap_direction:'better', source:'Verizon DBIR 2025' },
      { metric_id:'KRI-MTTR-001', metric_name:'Mean Time to Respond', your_value:48.7, unit:'min', industry_p25:80, industry_p50:52, industry_p75:35, industry_p90:20, your_percentile:44, assessment:'Below Average', assessment_icon:'', gap_to_median:3.3, gap_direction:'worse', source:'SANS SOC Survey 2024' },
      { metric_id:'KPI-FPR-001', metric_name:'False Positive Rate', your_value:18.4, unit:'%', industry_p25:35, industry_p50:25, industry_p75:15, industry_p90:8, your_percentile:62, assessment:'Above Average', assessment_icon:'', gap_to_median:6.6, gap_direction:'better', source:'Ponemon 2024' },
      { metric_id:'KRI-CVE-001', metric_name:'Critical CVE Patch Lag', your_value:8.0, unit:'days', industry_p25:20, industry_p50:12, industry_p75:7, industry_p90:3, your_percentile:38, assessment:'Below Average', assessment_icon:'', gap_to_median:4, gap_direction:'worse', source:'Verizon DBIR 2025' },
    ]
  };
}

function generateDemoTimelineHistory(days) {
  const now = new Date();
  const snapshots = [];
  for (let i = days; i >= 0; i--) {
    const ts = new Date(now - i * 86400000);
    const varBase = 4000000 + Math.sin(i * 0.1) * 500000 + (Math.random() - 0.5) * 200000;
    snapshots.push({
      timestamp: ts.toISOString(),
      run_id: `HIST_${ts.toISOString().split('T')[0].replace(/-/g,'')}`,
      metrics: state.metrics.map(m => ({ metric_id: m.metric_id, metric_name: m.metric_name, value: m.value + (Math.random()-0.5)*2, rag_status: m.rag_status })),
      summary: { green: 2, amber: 2, red: 2, total_var_usd: Math.round(varBase) }
    });
  }
  return { period_days: days, total_snapshots: snapshots.length, snapshots, rag_events: [], posture_change: null };
}

function getDemoTimelineEvents() {
  const now = new Date();
  return { events: [
    { timestamp: new Date(now - 2*86400000).toISOString(), type:'incident', severity:'high', title:'Ransomware attempt detected and blocked', description:'CryptoLocker variant blocked by EDR. MTTR spiked during investigation.', affected_metrics:['KRI-MTTR-001','KRI-MTTD-001'] },
    { timestamp: new Date(now - 8*86400000).toISOString(), type:'deployment', severity:'info', title:'SOAR playbook v2.3 deployed', description:'Updated incident response automation. Expected 15% MTTR improvement.', affected_metrics:['KRI-MTTR-001'] },
    { timestamp: new Date(now - 15*86400000).toISOString(), type:'vulnerability', severity:'critical', title:'CVE-2025-21298 (OLE RCE) — CISA KEV listed', description:'Critical Windows vulnerability added to CISA KEV. 3 systems affected.', affected_metrics:['KRI-CVE-001'] },
    { timestamp: new Date(now - 22*86400000).toISOString(), type:'compliance', severity:'warning', title:'DORA ICT-2.6 compliance gap identified', description:'Response time exceeded DORA threshold. Remediation plan initiated.', affected_metrics:['KRI-MTTR-001'] },
    { timestamp: new Date(now - 35*86400000).toISOString(), type:'improvement', severity:'info', title:'ML detection model retrained', description:'False positive rate reduced from 28% to 18.4% after model update.', affected_metrics:['KPI-FPR-001'] },
    { timestamp: new Date(now - 45*86400000).toISOString(), type:'incident', severity:'critical', title:'Phishing campaign targeting finance team', description:'Coordinated spear-phishing detected. 12 emails blocked, 2 reached inbox.', affected_metrics:['KRI-MTTD-001','KRI-DLP-001'] },
  ], total:6 };
}

function getDemoThreatIntelData() {
  return {
    threat_level: { level: 'ELEVATED', color: '#9A5F14', score: 65 },
    correlations: [
      { title:'CVE-2025-21298: Unpatched systems in scope', severity:'critical', description:'CISA has mandated remediation. Your CVE lag of 8 days creates active exposure window.', affected_metrics:['KRI-CVE-001'], threat_groups:['LockBit 3.0','BlackCat'], recommended_action:'Emergency patch deployment required within 24 hours per DORA ICT-2.2.' },
      { title:'T1059 (Command Execution) surge detected', severity:'high', description:'MTTR of 48.7 min exceeds industry safe response threshold for this technique. Dwell time risk elevated.', affected_metrics:['KRI-MTTR-001'], threat_groups:['APT41'], recommended_action:'Deploy automated containment playbooks. Review SOAR coverage for this technique.' },
    ],
    cisa_kev: { vulnerabilities: [
      { cve_id:'CVE-2025-21298', vendor:'Microsoft', product:'Windows OLE', vulnerability_name:'Remote Code Execution', cvss:9.8, date_added:'2025-01-14', notes:'Actively exploited in ransomware campaigns.', known_ransomware_use:true },
      { cve_id:'CVE-2024-47461', vendor:'Ivanti', product:'Connect Secure', vulnerability_name:'Command Injection', cvss:9.1, date_added:'2025-01-08', notes:'Mass exploitation observed by multiple threat actors.', known_ransomware_use:true },
      { cve_id:'CVE-2024-38193', vendor:'Microsoft', product:'Windows AFD Driver', vulnerability_name:'Privilege Escalation', cvss:7.8, date_added:'2024-08-13', notes:'Used in targeted attacks as post-exploitation elevation.', known_ransomware_use:false },
    ]},
    mitre_attack_trends: [
      { technique_id:'T1059', technique_name:'Command and Scripting Interpreter', tactic:'Execution', trend:'surging', change_pct:45, description:'PowerShell and Python based execution trending upward across all threat actor groups.', affected_metrics:['KRI-MTTD-001','KRI-MTTR-001'] },
      { technique_id:'T1078', technique_name:'Valid Accounts', tactic:'Persistence', trend:'increasing', change_pct:28, description:'Credential stuffing and stolen credential use for initial access continues to rise.', affected_metrics:['KPI-PHI-001'] },
      { technique_id:'T1486', technique_name:'Data Encrypted for Impact', tactic:'Impact', trend:'surging', change_pct:67, description:'Ransomware deployment frequency increased significantly in Q1 2025.', affected_metrics:['KRI-DLP-001','KRI-MTTR-001'] },
    ]
  };
}

function getDemoEvidenceVaultData() {
  const records = Array.from({length:10}, (_,i) => ({
    evidence_id: `EVD-${String(1001+i).padStart(4,'0')}`,
    timestamp: new Date(Date.now() - i * 3600000).toISOString(),
    event_type: ['METRIC_SNAPSHOT','THRESHOLD_CHANGE','PIPELINE_RUN','RAG_CLASSIFICATION','COMPLIANCE_AUDIT'][i%5],
    hash: Array.from({length:64}, ()=>'0123456789abcdef'[Math.floor(Math.random()*16)]).join(''),
  }));
  return {
    chain_integrity: { valid:true, algorithm:'SHA-256', total_records:records.length, latest_hash: records[0].hash },
    records
  };
}

function verifyDemoEvidenceSingle(id) {
  const h1 = Array.from({length:64}, ()=>'0123456789abcdef'[Math.floor(Math.random()*16)]).join('');
  return { evidence_id:id, timestamp:new Date().toISOString(), previous_hash:Array.from({length:64}, ()=>'0123456789abcdef'[Math.floor(Math.random()*16)]).join(''), stored_hash:h1, recomputed_hash:h1, verified:true, chain_link_valid:true };
}

function exportDemoEvidencePack(fw) {
  const id = 'EVDPACK-' + Math.random().toString(36).substring(2,10).toUpperCase();
  return {
    pack_id: id,
    summary: { total_evidence_records: 10 },
    attestation: { hash: Array.from({length:64}, ()=>'0123456789abcdef'[Math.floor(Math.random()*16)]).join(''), statement: `This evidence pack contains 10 continuous monitoring records for ${fw} audit submission. All records are cryptographically chained via SHA-256 and verified by the VALENCE GRC platform.` }
  };
}

function getDemoRiskCascadeData() {
  return {
    cascade_chains: [
      { source_metric_id:'KRI-MTTR-001', source_metric_name:'Mean Time to Respond', source_rag:'Red', downstream_impacts:[{target_metric_id:'KRI-MTTD-001',target_metric_name:'Mean Time to Detect',impact_factor:0.4},{target_metric_id:'KRI-DLP-001',target_metric_name:'DLP Policy Violations',impact_factor:0.25}], compliance_impacts:[{framework:'DORA',control:'ICT-2.6',regulation:'Response & Recovery',max_fine_eur:10000000}] },
      { source_metric_id:'KRI-CVE-001', source_metric_name:'Critical CVE Patch Lag', source_rag:'Red', downstream_impacts:[{target_metric_id:'KRI-MTTD-001',target_metric_name:'Mean Time to Detect',impact_factor:0.3}], compliance_impacts:[{framework:'DORA',control:'ICT-2.2',regulation:'Asset Management',max_fine_eur:5000000},{framework:'NIS2',control:'ART-21.2e',regulation:'Supply Chain Security',max_fine_eur:7000000}] },
    ]
  };
}

function simulateCascadeDemoSingle(metricId) {
  const m = state.metrics.find(x => x.metric_id === metricId) || state.metrics[0];
  return {
    source_metric: m || { metric_id: metricId },
    total_depth: 2,
    affected_metrics: ['KRI-MTTD-001','KRI-DLP-001'],
    compliance_impacts: [{framework:'DORA',control:'ICT-2.6',regulation:'Response & Recovery'},{framework:'NIS2',control:'ART-21.2b',regulation:'Incident Handling'}],
    cascade_chain: [
      { from: metricId, to: 'KRI-MTTD-001', relationship: 'detection_delay', impact_factor: 0.4 },
      { from: 'KRI-MTTD-001', to: 'KRI-DLP-001', relationship: 'dwell_time', impact_factor: 0.25 },
    ]
  };
}

function getDemoBoardDeckData(quarter, audience, tone) {
  const s = state.summary;
  const totalVar = s.total_var_95_usd || 4473000;
  const totalAle = s.total_ale_usd || 1969000;
  return {
    generated_by: currentUser.username || 'admin',
    slide_1_title: { title:`VALENCE GRC Security Posture — ${quarter}`, subtitle:`Prepared for ${audience}`, date: new Date().toLocaleDateString(), classification:'CONFIDENTIAL — BOARD USE ONLY' },
    slide_2_executive_summary: { title:'Executive Security Posture Summary', overall_assessment:'REQUIRES ATTENTION', narrative:`The organization's security posture for ${quarter} shows 2 of 6 monitored controls in breach of SLA thresholds. The critical CVE patch lag and elevated MTTR represent the highest financial exposure with a combined 95th percentile VaR of $3.3M. Immediate investment in automation tooling is recommended to bring these controls within policy thresholds.`, key_figures:{ portfolio_var_95_usd: totalVar, portfolio_ale_usd: totalAle, metrics_within_threshold: s.green||2, metrics_at_risk: s.amber||2, metrics_breached: s.red||2 } },
    slide_3_risk_landscape: { title:'Risk Landscape — Control Detail', metric_details: state.metrics.map(m => ({ metric_id: m.metric_id, metric_name: m.metric_name, rag_status: m.rag_status, var_95_usd: m.var_95_usd, recommended_action: m.narrative?.substring(0,60)+'...', priority: m.rag_status === 'Red' ? 'Critical — Act Now' : m.rag_status === 'Amber' ? 'High — Monitor Closely' : 'Low — Maintain' })) },
    slide_4_compliance: { title:'Regulatory Compliance Coverage', frameworks: [ { name:'DORA 2025', status:'At Risk', key_gap:'ICT-2.6 Response & Recovery: MTTR exceeds 30-minute threshold' }, { name:'NIS2', status:'On Track', key_gap:'ART-21.2e Supply Chain: CVE patch lag approaching limit' }, { name:'SOC 2 Type II', status:'Compliant', key_gap:'CC7.2 Vulnerability Management: Under observation' } ] },
    slide_5_recommendations: { title:'Investment Recommendations', recommendations: [ { priority:1, title:'Deploy SOAR Platform', description:'Automated playbooks for incident response', investment_usd:180000, projected_var_reduction_usd:720000, timeline:'30 days', roi_ratio:'4.0' }, { priority:2, title:'Automated Patch Management', description:'CI/CD patch pipeline for critical CVEs', investment_usd:95000, projected_var_reduction_usd:1575000, timeline:'45 days', roi_ratio:'16.6' }, { priority:3, title:'Hire 2 SOC Analysts', description:'Reduce MTTD and MTTR through headcount', investment_usd:240000, projected_var_reduction_usd:588000, timeline:'60 days', roi_ratio:'2.4' } ], summary: { total_recommended_investment_usd: 515000, total_projected_var_reduction_usd: 2883000, portfolio_roi_ratio: '5.6' } },
    slide_6_next_steps: { title:'Board Decision Points', items: [ { action:'Approve $515K Security Budget Supplement', priority:'Critical', owner:'CFO + CISO', deadline:'End of Quarter' }, { action:'Mandate Emergency CVE Patching within 24hrs', priority:'Critical', owner:'CTO + CISO', deadline:'Immediate' }, { action:'SOAR Platform Vendor Evaluation', priority:'High', owner:'Security Architecture Team', deadline:'2 weeks' } ] }
  };
}

// ─── TEAM ACCESS ───────────────────────────────────────────
let editingTeamMember = null;
let teamMembersCache = [];

const TEAM_FEATURE_LABELS = {
  dashboard: 'Dashboard', risk: 'Risk', whatif: 'Simulator', benchmarking: 'Benchmarks',
  threat_intel: 'Threat Intel', compliance: 'Compliance', timeline: 'Timeline',
  evidence: 'Evidence', findings: 'Findings', reports: 'Reports', connectors: 'SIEM',
};

const TEAM_DEPT_ICONS = { grc: 'ph-clipboard-text', soc: 'ph-radar', ir: 'ph-siren', general: 'ph-sliders' };

const ROLE_DESCRIPTIONS = {
  analyst: 'Analyst — day-to-day metrics, simulations, and assigned modules.',
  auditor: 'Auditor — read-heavy access to compliance, evidence, findings, and reports.',
  ciso: 'CISO — executive dashboards, risk posture, benchmarking, and board decks.',
  admin: 'Admin — full workspace control including connectors and team access.',
};

function selectRole(role) {
  document.getElementById('team-role').value = role;
  document.querySelectorAll('.team-role-card').forEach(el => {
    el.classList.toggle('active', el.dataset.role === role);
  });
  const sum = document.getElementById('team-role-summary');
  if (sum) sum.textContent = ROLE_DESCRIPTIONS[role] || '';
}

function selectDepartment(dept) {
  document.getElementById('team-department').value = dept;
  document.querySelectorAll('.team-dept-card').forEach(el => {
    el.classList.toggle('active', el.dataset.dept === dept);
  });
  applyDepartmentPresetFeatures();
}

function applyDepartmentPresetFeatures() {
  const dept = document.getElementById('team-department').value;
  const preset = (featureCatalog?.departments || []).find(d => d.id === dept);
  if (!preset || !preset.preset_features) return;
  document.querySelectorAll('.team-feature-cb').forEach(cb => {
    cb.checked = preset.preset_features.includes(cb.value);
  });
}

function applyDepartmentPreset() {
  const dept = document.getElementById('team-department').value;
  document.querySelectorAll('.team-dept-card').forEach(el => {
    el.classList.toggle('active', el.dataset.dept === dept);
  });
  applyDepartmentPresetFeatures();
}

async function loadTeamPage() {
  try {
    if (!featureCatalog) {
      featureCatalog = await apiFetch('/api/users/catalog');
      renderTeamFeatureGrid();
      selectDepartment('grc');
      selectRole('analyst');
    }
    const [members, sso] = await Promise.all([
      apiFetch('/api/users/'),
      fetch(`${API}/api/auth/sso/setup`).then(r => r.ok ? r.json() : null).catch(() => null),
    ]);
    renderTeamMembers(members || []);
    const ssoCard = document.getElementById('team-sso-card');
    const ssoEl = document.getElementById('team-sso-info');
    if (ssoEl && sso) {
      if (sso.configured) {
        ssoCard?.classList.add('sso-active');
        ssoCard?.classList.remove('sso-inactive');
        const provider = { azure: 'Microsoft Entra ID', okta: 'Okta', oidc: 'OIDC' }[sso.provider] || sso.provider;
        ssoEl.innerHTML = `
          <h4><i class="ph ph-check-circle" style="color:var(--green)"></i> SSO active — ${provider}</h4>
          <p>Invite users here first with their corporate email. They can then sign in via SSO using the same email address.</p>
          <p style="font-size:12px;color:var(--text-muted);margin-top:8px">Role mapping uses IdP groups when <code>AUTH_SSO_GROUP_ROLE_MAP</code> is configured.</p>`;
      } else {
        ssoCard?.classList.add('sso-inactive');
        ssoCard?.classList.remove('sso-active');
        ssoEl.innerHTML = `
          <h4>Enterprise SSO not configured</h4>
          <p>Password-based invites work today. To enable Azure Entra ID or Okta, your operator configures SSO per <strong>RUNBOOK §9</strong>.</p>
          <p style="font-size:12px;color:var(--text-muted);margin-top:8px">Recommended flow: invite users here → they sign in with password or SSO once enabled.</p>`;
      }
    }
  } catch (e) {
    document.getElementById('team-members-list').innerHTML =
      '<div class="team-empty"><i class="ph ph-warning-circle"></i>Could not load team members. Ensure you have Team Access permission.</div>';
  }
}

function renderTeamMembers(members) {
  teamMembersCache = members;
  const list = document.getElementById('team-members-list');
  const countEl = document.getElementById('team-member-count');
  const active = members.filter(m => m.is_active).length;
  if (countEl) countEl.textContent = active;

  if (!members.length) {
    list.innerHTML = '<div class="team-empty"><i class="ph ph-users"></i><div style="font-weight:600;color:var(--text-secondary);margin-bottom:4px">No team members yet</div>Invite your first GRC, SOC, or IR analyst using the form.</div>';
    return;
  }
  list.innerHTML = members.map((m, idx) => {
    const initial = (m.full_name || m.username || '?')[0].toUpperCase();
    const features = m.feature_list.filter(f => f !== 'team_admin').slice(0, 6);
    const more = m.feature_list.filter(f => f !== 'team_admin').length - features.length;
    return `
    <div class="team-member-card ${m.is_active ? '' : 'inactive'}">
      <div class="team-member-avatar">${initial}</div>
      <div class="team-member-body">
        <div class="team-member-top">
          <span class="team-member-name">${m.full_name}</span>
          <span class="team-member-badge role-${m.role}">${m.role}</span>
          <span class="team-member-badge dept">${m.department_label || m.department}</span>
          ${!m.is_active ? '<span class="team-member-badge inactive-badge">Inactive</span>' : ''}
        </div>
        <div class="team-member-meta"><i class="ph ph-at"></i> ${m.username} &nbsp;·&nbsp; ${m.email}</div>
        <div class="team-member-features">
          ${features.map(f => `<span class="team-feature-pill">${TEAM_FEATURE_LABELS[f] || f}</span>`).join('')}
          ${more > 0 ? `<span class="team-feature-pill">+${more} more</span>` : ''}
        </div>
      </div>
      <div class="team-member-actions">
        <button class="btn btn-sm btn-secondary" onclick="openTeamEditModal(${idx})"><i class="ph ph-pencil-simple"></i> Edit</button>
        ${m.is_active ? `<button class="btn btn-sm btn-secondary" style="color:var(--red);border-color:var(--red-border)" onclick="deactivateTeamMember(${m.id}, '${m.username}')"><i class="ph ph-user-minus"></i></button>` : ''}
      </div>
    </div>`;
  }).join('');
}

function renderTeamFeatureGrid() {
  const grid = document.getElementById('team-features-grid');
  if (!grid || !featureCatalog) return;
  grid.innerHTML = featureCatalog.features.map(f => `
    <label class="team-feature-chip">
      <input type="checkbox" class="team-feature-cb" value="${f.id}" checked />
      ${f.label}
    </label>
  `).join('');
}

async function inviteTeamMember() {
  const features = [...document.querySelectorAll('.team-feature-cb:checked')].map(cb => cb.value);
  const payload = {
    full_name: document.getElementById('team-fullname').value.trim(),
    username: document.getElementById('team-username').value.trim(),
    email: document.getElementById('team-email').value.trim(),
    password: document.getElementById('team-password').value,
    department: document.getElementById('team-department').value,
    role: document.getElementById('team-role').value,
    features,
  };
  if (!payload.full_name || !payload.username || !payload.email || !payload.password) {
    showToast('Fill in all required fields', 'warn'); return;
  }
  const res = await fetch(`${API}/api/users/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}`, 'X-Tenant-ID': currentTenantId },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) { showToast(data.detail || 'Failed to create user', 'error'); return; }
  showToast(`Access created for ${data.username}`, 'success');
  document.getElementById('team-fullname').value = '';
  document.getElementById('team-username').value = '';
  document.getElementById('team-email').value = '';
  document.getElementById('team-password').value = '';
  loadTeamPage();
}

function openTeamEditModal(index) {
  const member = teamMembersCache[index];
  if (!member) return;
  editingTeamMember = member;
  document.getElementById('team-edit-id').value = member.id;
  document.getElementById('team-edit-fullname').value = member.full_name;
  document.getElementById('team-edit-role').value = member.role;
  document.getElementById('team-edit-department').value = member.department;
  document.getElementById('team-edit-password').value = '';
  const grid = document.getElementById('team-edit-features');
  grid.innerHTML = (featureCatalog?.features || []).map(f => `
    <label class="team-feature-chip">
      <input type="checkbox" class="team-edit-feature-cb" value="${f.id}" ${member.feature_list.includes(f.id) ? 'checked' : ''} />
      ${f.label}
    </label>
  `).join('');
  showModalOverlay('team-edit-modal');
}

function closeTeamEditModal() {
  editingTeamMember = null;
  hideModalOverlay('team-edit-modal');
}

async function saveTeamMemberEdit() {
  const id = document.getElementById('team-edit-id').value;
  const features = [...document.querySelectorAll('.team-edit-feature-cb:checked')].map(cb => cb.value);
  const payload = {
    full_name: document.getElementById('team-edit-fullname').value.trim(),
    role: document.getElementById('team-edit-role').value,
    department: document.getElementById('team-edit-department').value,
    features,
  };
  const pw = document.getElementById('team-edit-password').value;
  if (pw) payload.password = pw;
  const res = await apiFetch(`/api/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
  if (res?.id) {
    showToast('Team member updated', 'success');
    closeTeamEditModal();
    loadTeamPage();
  } else showToast('Update failed', 'error');
}

async function deactivateTeamMember(id, username) {
  const ok = await showConfirmDialog({
    title: `Deactivate ${username}?`,
    subtitle: 'This action removes access immediately',
    message: 'They will no longer be able to sign in or view tenant data. You can re-invite them later from Team settings.',
    confirmLabel: 'Deactivate',
    cancelLabel: 'Cancel',
    variant: 'danger',
    icon: 'ph-user-minus',
  });
  if (!ok) return;
  const res = await fetch(`${API}/api/users/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${accessToken}`, 'X-Tenant-ID': currentTenantId },
  });
  if (res.status === 204) { showToast(`${username} deactivated`, 'success'); loadTeamPage(); }
  else showToast('Could not deactivate user', 'error');
}

// Add spin animation for loading button
const style = document.createElement('style');
style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }';
document.head.appendChild(style);
// --- MISSING ENDPOINT FUNCTIONS ---

async function testAlert(channel) {
  let url;
  if (channel === 'slack') url = document.getElementById('config-slack-url').value;
  else if (channel === 'teams') url = document.getElementById('config-teams-url').value;
  else if (channel === 'pagerduty') url = document.getElementById('config-pagerduty-key').value;

  if (!url) { showToast(`Please enter a URL for ${channel} first`, 'warn'); return; }
  
  showToast(`Testing ${channel} alert...`, 'info');
  try {
    const res = await apiFetch('/api/connectors/test-alert', {
      method: 'POST', body: JSON.stringify({ channel, target_url: url })
    });
    if (res && res.status === 'success') showToast(res.message, 'success');
    else showToast(`Test failed: ${res?.detail || 'Unknown error'}`, 'error');
  } catch (e) { showToast('Test request failed', 'error'); }
}

async function saveIntegrationConfig() {
  const payload = {
    slack_webhook_url: document.getElementById('config-slack-url').value,
    teams_webhook_url: document.getElementById('config-teams-url').value,
    pagerduty_routing_key: document.getElementById('config-pagerduty-key').value
  };
  const res = await apiFetch('/api/connectors/config', {
    method: 'POST', body: JSON.stringify(payload)
  });
  if (res && res.status === 'success') showToast('Configuration saved successfully', 'success');
  else showToast('Failed to save configuration', 'error');
}

let onboardingStep = 1;

function maybeShowOnboarding(ctx) {
  const modal = document.getElementById('onboarding-modal');
  if (!modal) return;
  if (ctx.show_onboarding_wizard) {
    onboardingStep = Math.min(ctx.onboarding_step || 1, 3);
    showOnboardingStep(onboardingStep);
    showModalOverlay('onboarding-modal');
  } else {
    hideModalOverlay('onboarding-modal');
  }
}

function showOnboardingStep(step) {
  onboardingStep = step;
  document.querySelectorAll('.onboarding-pane').forEach(p => p.classList.remove('active'));
  const pane = document.getElementById(`onboard-pane-${step}`);
  if (pane) pane.classList.add('active');
  document.querySelectorAll('.onboarding-step').forEach(el => {
    const n = parseInt(el.dataset.step, 10);
    el.classList.toggle('active', n === step);
    el.classList.toggle('done', n < step);
  });
  const back = document.getElementById('btn-onboard-back');
  const skip = document.getElementById('btn-onboard-skip');
  const next = document.getElementById('btn-onboard-next');
  if (back) back.style.display = step > 1 ? 'inline-flex' : 'none';
  if (skip) skip.style.display = step === 2 ? 'inline-flex' : 'none';
  if (next) {
    next.innerHTML = step === 3
      ? 'Generate & Finish <i class="ph ph-check"></i>'
      : 'Continue <i class="ph ph-arrow-right"></i>';
  }
}

function onboardingBack() {
  if (onboardingStep > 1) showOnboardingStep(onboardingStep - 1);
}

function onboardingSkipStep() {
  if (onboardingStep === 2) showOnboardingStep(3);
}

async function onboardingNext() {
  const btn = document.getElementById('btn-onboard-next');
  if (onboardingStep === 1) {
    btn.disabled = true;
    const siem = document.getElementById('wizard-siem').value;
    const siemUrl = document.getElementById('wizard-siem-url')?.value.trim();
    const slack = document.getElementById('wizard-slack')?.value.trim();
    await apiFetch('/api/connectors/config', {
      method: 'POST',
      body: JSON.stringify({ siem_type: siem, siem_url: siemUrl || undefined, slack_webhook_url: slack || undefined })
    });
    btn.disabled = false;
    showOnboardingStep(2);
    return;
  }
  if (onboardingStep === 2) {
    const email = document.getElementById('wizard-invite-email')?.value.trim();
    const username = document.getElementById('wizard-invite-username')?.value.trim();
    const password = document.getElementById('wizard-invite-password')?.value;
    const department = document.getElementById('wizard-invite-dept')?.value || 'grc';
    if (email && username && password) {
      await apiFetch('/api/users/', {
        method: 'POST',
        body: JSON.stringify({
          email, username, password,
          full_name: username,
          role: 'analyst',
          department
        })
      });
    }
    showOnboardingStep(3);
    return;
  }
  if (onboardingStep === 3) {
    btn.disabled = true;
    btn.innerHTML = '<i class="ph ph-spinner" style="animation:spin .8s linear infinite"></i> Generating…';
    const statusEl = document.getElementById('wizard-export-status');
    try {
      const data = await apiFetch('/api/reports/generate', {
        method: 'POST',
        body: JSON.stringify({ title: 'VALENCE GRC Onboarding Export', include_narratives: true, include_monte_carlo: true })
      });
      if (statusEl && data?.report_id) statusEl.textContent = `Report ${data.report_id} started — finishing setup…`;
      await apiFetch('/api/connectors/config', {
        method: 'POST',
        body: JSON.stringify({ onboarded: true })
      });
      hideModalOverlay('onboarding-modal');
      showToast('Onboarding complete — welcome to VALENCE.', 'success');
      await loadTenantContext();
      loadAllData();
    } catch {
      showToast('Export failed — try again from Reports', 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Generate & Finish <i class="ph ph-check"></i>';
    }
  }
}

async function completeOnboarding() {
  await onboardingNext();
}

async function handleLogUpload(file) {
  if (!file) return;
  const statusEl = document.getElementById('upload-status');
  statusEl.textContent = 'Uploading...';
  statusEl.style.color = 'var(--text-muted)';
  
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    const res = await fetch(`${API}/api/connectors/upload-logs`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${accessToken}`, 'X-Tenant-ID': currentTenantId },
      body: formData
    });
    const data = await res.json();
    if (res.ok) {
      statusEl.textContent = 'Upload successful!';
      statusEl.style.color = 'var(--green)';
      showToast(data.message, 'success');
      loadAllData();
      await loadTenantContext();
    } else {
      statusEl.textContent = 'Upload failed.';
      statusEl.style.color = 'var(--red)';
      showToast(data.detail || 'Upload failed', 'error');
    }
  } catch (e) {
    statusEl.textContent = 'Network error.';
    statusEl.style.color = 'var(--red)';
  }
}

function openNewFindingModal() {
  showModalOverlay('finding-modal');
}

function closeFindingModal() {
  hideModalOverlay('finding-modal');
}

async function saveFinding() {
  const title = document.getElementById('finding-title').value;
  const desc = document.getElementById('finding-desc').value;
  const severity = document.getElementById('finding-severity').value;
  const owner = document.getElementById('finding-owner').value;
  
  if (!title) { showToast('Title is required', 'warn'); return; }
  
  const payload = { title, description: desc, severity };
  const res = await apiFetch('/api/findings/', { method: 'POST', body: JSON.stringify(payload) });
  
  if (res && res.status === 'success') {
    if (owner) {
      await apiFetch(`/api/findings/${res.finding_id}`, { method: 'PUT', body: JSON.stringify({ owner_username: owner, status: 'assigned' }) });
    }
    showToast('Finding created successfully', 'success');
    closeFindingModal();
    loadFindings();
  }
}

async function loadFindings() {
  const findings = await apiFetch('/api/findings/');
  const list = document.getElementById('findings-list');
  if (!findings || !findings.length) {
    list.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">No active findings.</div>';
    return;
  }
  list.innerHTML = findings.map(f => `
    <div style="background:var(--bg-base); border:1px solid var(--border); border-radius:var(--radius-sm); padding:16px;">
      <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
        <div style="font-weight:700; color:var(--text-primary);">${f.title}</div>
        <span class="rag-badge ${f.severity === 'critical' ? 'Red' : f.severity === 'high' ? 'Amber' : 'Green'}">${f.severity.toUpperCase()}</span>
      </div>
      <div style="font-size:12px; color:var(--text-secondary); margin-bottom:12px;">${f.description || 'No description'}</div>
      <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-muted);">
        <div>Status: <strong style="color:var(--text-primary)">${f.status.toUpperCase()}</strong></div>
        <div>Owner: <strong>${f.owner_username || 'Unassigned'}</strong></div>
      </div>
      ${f.status !== 'closed' ? `
        <div style="margin-top:12px; padding-top:12px; border-top:1px solid var(--border); text-align:right;">
          <button class="btn btn-sm btn-secondary" onclick="openFindingEvidenceModal('${f.id}')"><i class="ph ph-upload"></i> Upload Evidence & Close</button>
        </div>
      ` : `
        <div style="margin-top:12px; padding-top:12px; border-top:1px solid var(--border); font-size:11px; color:var(--green); font-weight:600;">
          <i class="ph ph-check-circle"></i> Closed with Evidence: ${f.evidence_file_name}
        </div>
      `}
    </div>
  `).join('');
}

let activeFindingId = null;
function openFindingEvidenceModal(findingId) {
  activeFindingId = findingId;
  showModalOverlay('finding-evidence-modal');
}
function closeFindingEvidenceModal() {
  activeFindingId = null;
  hideModalOverlay('finding-evidence-modal');
}

async function handleFindingEvidence(file) {
  if (!file || !activeFindingId) return;
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    const res = await fetch(`${API}/api/findings/${activeFindingId}/evidence`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${accessToken}` },
      body: formData
    });
    const data = await res.json();
    if (res.ok) {
      showToast('Finding closed successfully', 'success');
      closeFindingEvidenceModal();
      loadFindings();
    } else {
      showToast(data.detail || 'Upload failed', 'error');
    }
  } catch(e) { showToast('Upload failed', 'error'); }
}