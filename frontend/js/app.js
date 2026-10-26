/* App shell: boot, router, top bar, sidebar account area. */
(function () {
  'use strict';
  const { h } = NX;
  const NEEDS_DATA = new Set(['workspace', 'clean', 'explore', 'visualize', 'copilot', 'trust', 'reports']);
  const VIEWS = ['workspace', 'upload', 'clean', 'explore', 'visualize', 'copilot', 'trust', 'reports', 'account'];
  let token = 0;

  // ---------------------------------------------------------------- top bar & sidebar
  function renderTopbar() {
    const sel = NX.$('#ds-select'), meta = NX.$('#topbar-meta'), list = NX.state.datasets, cur = NX.current();
    NX.clear(sel);
    list.forEach((d) => sel.append(h('option', { value: d.id, selected: d.id === NX.state.dsId }, d.name)));
    sel.hidden = !list.length;
    meta.textContent = cur ? `${cur.rows.toLocaleString()} rows, ${cur.columns} columns` : '';
    NX.$('#export-btn').disabled = !cur;
  }

  function renderSidebarAccount() {
    const u = NX.state.user, cfg = NX.state.config, box = NX.$('#sidebar-account');
    NX.$('#privacy-note').textContent = u ? 'Your datasets are saved privately to your account. Delete them any time.'
      : `Guest data stays in server memory and is deleted after ${cfg.session_ttl_minutes} minutes of inactivity.`;
    box.replaceChildren(
      h('a', { class: 'account-row', href: '#/account' }, h('div', { class: 'avatar' }, u ? NX.fmt.initials(u.name) : 'G'),
        h('div', { class: 'account-text' }, h('div', { class: 'account-name' }, u ? u.name : 'Guest session'), h('div', { class: 'account-sub' }, u ? u.email : 'Sign in to save your work'))),
      u ? h('button', { class: 'signout', type: 'button', onclick: NX.logout }, 'Sign out')
        : h('a', { class: 'signout', href: '/login?next=/app' }, 'Sign in or create account'));
  }

  function renderGuestBanner() {
    const box = NX.$('#guest-banner');
    box.hidden = !!NX.state.user;
    if (NX.state.user) return;
    box.replaceChildren(h('span', null, `You're using a guest session. Data is deleted after ${NX.state.config.session_ttl_minutes} minutes of inactivity.`),
      h('span', null, h('a', { href: '/signup' }, 'Create a free account'), ' to save your datasets.'));
  }

  async function updateBadge() {
    const badge = NX.$('#clean-badge');
    badge.hidden = true;
    if (!NX.state.dsId) return;
    try {
      const q = await NX.getQuality();
      const n = q.issues.filter((i) => i.severity !== 'low').length;
      badge.textContent = n; badge.hidden = !n;
    } catch (e) { /* non-critical */ }
  }

  // ---------------------------------------------------------------- routing
  function currentName() {
    const m = location.hash.match(/^#\/([a-z]+)/);
    const name = m && VIEWS.includes(m[1]) ? m[1] : null;
    return name || (NX.state.dsId ? 'workspace' : 'upload');
  }

  function emptyState(root) {
    root.replaceChildren(h('div', { class: 'empty-state' }, h('h2', null, 'Start with a dataset'),
      h('p', null, 'Upload a CSV and this page fills in automatically: a clean-up plan, exploratory charts, a trust score and a copilot that answers questions about your data.'),
      h('div', { class: 'row', style: { justifyContent: 'center' } }, h('button', { class: 'btn btn-primary', type: 'button', onclick: NX.pickFile }, 'Upload a CSV'),
        h('button', { class: 'btn btn-secondary', type: 'button', onclick: NX.loadSample }, 'Use the sample dataset'))));
  }

  async function route() {
    const name = currentName();
    const my = ++token;
    NX.state.view = name;
    NX.$$('.view').forEach((v) => v.classList.toggle('active', v.id === 'view-' + name));
    NX.$$('.nav-item').forEach((a) => { const on = a.dataset.view === name; a.classList.toggle('active', on); if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    const root = NX.$('#view-' + name);
    if (NEEDS_DATA.has(name) && !NX.state.dsId) { emptyState(root); return; }
    root.replaceChildren(h('div', { class: 'loading' }, 'Loading…'));
    try { await NX.views[name].render(root); }
    catch (e) {
      if (my !== token) return;
      if (e.status === 404 && NX.state.dsId) {      // dataset expired or removed
        NX.toast('That dataset is no longer available.', 'error');
        await NX.refreshDatasets();
        NX.setDataset(NX.state.datasets.length ? NX.state.datasets[NX.state.datasets.length - 1].id : null);
        return;
      }
      root.replaceChildren(h('div', { class: 'error-panel', role: 'alert' }, e.message || 'Something went wrong.',
        h('div', { style: { marginTop: '10px' } }, h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: route }, 'Try again'))));
    }
  }

  // ---------------------------------------------------------------- boot
  async function boot() {
    let cfg, me;
    try { [cfg, me] = await Promise.all([NX.api.get('/api/config'), NX.api.get('/api/auth/me')]); }
    catch (e) { document.body.replaceChildren(h('div', { class: 'empty-state' }, h('h2', null, "We couldn't start the app"), h('p', null, e.message), h('button', { class: 'btn btn-primary', onclick: () => location.reload() }, 'Reload'))); return; }
    if (me.require_login && !me.user) { location.href = '/login?next=/app'; return; }
    NX.state.config = cfg; NX.state.user = me.user;
    renderSidebarAccount(); renderGuestBanner();

    await NX.refreshDatasets();
    const saved = sessionStorage.getItem('nx-ds');
    const list = NX.state.datasets;
    NX.state.dsId = list.some((d) => d.id === saved) ? saved : list.length ? list[list.length - 1].id : null;
    if (!NX.state.dsId && new URLSearchParams(location.search).get('sample') === '1') {
      try { const r = await NX.api.post('/api/datasets/sample'); await NX.refreshDatasets(); NX.state.dsId = r.dataset.id; } catch (e) { NX.toast(e.message, 'error'); }
    }
    if (sessionStorage.getItem('nx-adopted')) { NX.toast(`Welcome! ${sessionStorage.getItem('nx-adopted')} dataset(s) from your guest session were saved to your account.`); sessionStorage.removeItem('nx-adopted'); }
    if (NX.state.dsId) sessionStorage.setItem('nx-ds', NX.state.dsId);

    renderTopbar(); updateBadge();
    window.addEventListener('hashchange', route);
    NX.on('datasetchange', () => { renderTopbar(); updateBadge(); route(); });
    NX.on('datasets', renderTopbar);
    document.addEventListener('nx:themechange', route);
    NX.$('#ds-select').addEventListener('change', (e) => NX.setDataset(e.target.value));
    NX.$('#export-btn').addEventListener('click', () => NX.go('reports'));
    NX.$('#upload-btn').addEventListener('click', NX.pickFile);
    NX.$('#file-input').addEventListener('change', (e) => { NX.uploadFile(e.target.files[0]); e.target.value = ''; });
    route();
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
