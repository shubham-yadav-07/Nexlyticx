/* NexlyticX frontend core.
   - NX.h() builds DOM with textContent only (never innerHTML), so dataset
     values and column names can never inject markup.
   - NX.api sends the X-NX header the server requires on state-changing calls. */
(function () {
  'use strict';
  const NX = (window.NX = { views: {}, cache: {}, state: { config: null, user: null, datasets: [], dsId: null, targets: {}, view: null } });
  const SVGNS = 'http://www.w3.org/2000/svg';

  // ------------------------------------------------------------ DOM
  function append(el, kids) {
    for (const k of kids) {
      if (k == null || k === false) continue;
      if (Array.isArray(k)) append(el, k);
      else el.append(k instanceof Node ? k : document.createTextNode(String(k)));
    }
  }
  function build(el, attrs, kids) {
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') el.setAttribute('class', v);
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    append(el, kids);
    return el;
  }
  NX.h = (tag, attrs, ...kids) => build(document.createElement(tag), attrs, kids);
  NX.svg = (tag, attrs, ...kids) => build(document.createElementNS(SVGNS, tag), attrs, kids);
  NX.$ = (sel, root = document) => root.querySelector(sel);
  NX.$$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  NX.clear = (el) => { el.replaceChildren(); return el; };

  const ICONS = {
    grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.2"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.2"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.2"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.2"/>',
    upload: '<path d="M12 15V4"/><path d="M7.5 8.5 12 4l4.5 4.5"/><path d="M4.5 15v3a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-3"/>',
    filter: '<path d="M4 5h16l-6 8v5.5l-4 2V13z"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m19.5 19.5-4.3-4.3"/>',
    chart: '<path d="M4 20V10"/><path d="M12 20V4"/><path d="M20 20v-7"/>',
    chat: '<path d="M4 5.5h16a1 1 0 0 1 1 1V15a1 1 0 0 1-1 1H9l-4.5 4V16H4a1 1 0 0 1-1-1V6.5a1 1 0 0 1 1-1Z"/>',
    doc: '<path d="M6 3.5h9l3.5 3.5V20a.7.7 0 0 1-.7.7H6a.7.7 0 0 1-.7-.7V4.2a.7.7 0 0 1 .7-.7Z"/><path d="M14.5 3.5V7a1 1 0 0 0 1 1H19"/><path d="M8.3 12h7.4M8.3 15h7.4M8.3 9h3.5"/>',
    shield: '<path d="M12 3.5 4.5 6v6.2c0 4.4 3.2 7.3 7.5 8.3 4.3-1 7.5-3.9 7.5-8.3V6L12 3.5Z"/><path d="m9 12 2 2 4-4"/>',
    user: '<circle cx="12" cy="8" r="3.8"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    send: '<path d="M4 12h15.5"/><path d="m13 5.5 6.5 6.5-6.5 6.5"/>',
    moon: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"/>',
    sun: '<circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.3M12 19.2v2.3M4.4 4.4l1.6 1.6M18 18l1.6 1.6M2.5 12h2.3M19.2 12h2.3M4.4 19.6 6 18M18 6l1.6-1.6"/>',
    lock: '<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
    sparkle: '<path d="M12 3.5 13.8 9l5.7 1.8-5.7 1.8L12 18l-1.8-5.4L4.5 10.8 10.2 9z"/>',
  };
  NX.icon = (name, cls) => {
    const s = document.createElementNS(SVGNS, 'svg');
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '1.7');
    s.setAttribute('stroke-linecap', 'round'); s.setAttribute('stroke-linejoin', 'round'); s.setAttribute('aria-hidden', 'true');
    if (cls) s.setAttribute('class', cls);
    s.innerHTML = ICONS[name] || ''; // static, trusted icon markup only
    return s;
  };

  // ------------------------------------------------------------ formatting
  const num = (n, d = 2) => {
    if (n == null || Number.isNaN(n)) return 'n/a';
    const a = Math.abs(n);
    if (a >= 1e6) return (n / 1e6).toFixed(2).replace(/\.?0+$/, '') + 'M';
    if (a >= 1e4) return Math.round(n).toLocaleString();
    return Number.isInteger(n) ? n.toLocaleString() : (+n.toFixed(d)).toLocaleString();
  };
  NX.fmt = {
    num,
    int: (n) => (n == null ? 'n/a' : Math.round(n).toLocaleString()),
    pct: (n, d = 1) => (n == null ? 'n/a' : `${(+n).toFixed(d).replace(/\.0+$/, '')}%`),
    ago(iso) {
      const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
      if (s < 60) return 'just now';
      if (s < 3600) return `${Math.floor(s / 60)} min ago`;
      if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
      return `${Math.floor(s / 86400)} d ago`;
    },
    initials: (name) => (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?',
  };
  NX.gradeClass = (grade, score) => (grade === 'Excellent' || grade === 'Good' ? 'ok' : grade === 'Fair' ? 'fair' : score >= 70 ? 'fair' : 'bad');

  NX.colors = () => {
    const cs = getComputedStyle(document.documentElement);
    const g = (n) => cs.getPropertyValue(n).trim();
    return { teal: g('--teal'), text: g('--text'), muted: g('--muted'), line: g('--line'), lineSoft: g('--line-soft'), paper: g('--paper'),
      amber: g('--amber'), red: g('--red'), contrast: g('--chart-contrast'), tint: g('--teal-tint'), canvas: g('--canvas') };
  };

  // ------------------------------------------------------------ events & toast
  NX.on = (name, fn) => document.addEventListener('nx:' + name, (e) => fn(e.detail));
  NX.emit = (name, detail) => document.dispatchEvent(new CustomEvent('nx:' + name, { detail }));
  let toastTimer;
  NX.toast = (msg, type) => {
    let t = document.getElementById('toast');
    if (!t) { t = NX.h('div', { id: 'toast', class: 'toast', role: 'status' }); document.body.append(t); }
    t.textContent = msg;
    t.classList.toggle('error', type === 'error');
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), type === 'error' ? 5200 : 3200);
  };

  // ------------------------------------------------------------ API
  class ApiError extends Error { constructor(msg, status) { super(msg); this.status = status; } }
  NX.ApiError = ApiError;
  async function request(method, url, body, form) {
    const opts = { method, credentials: 'same-origin', headers: { 'X-NX': '1' } };
    if (form) opts.body = form;
    else if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    let res;
    try { res = await fetch(url, opts); }
    catch (e) { throw new ApiError("Can't reach the server. Check your connection and try again.", 0); }
    const data = (res.headers.get('content-type') || '').includes('json') ? await res.json().catch(() => null) : null;
    if (!res.ok) {
      if (res.status === 401 && data && data.login_required && !location.pathname.startsWith('/login')) {
        location.href = '/login?next=' + encodeURIComponent(location.pathname);
      }
      let msg = data && data.detail;
      if (Array.isArray(msg) || typeof msg !== 'string') msg = res.status === 422 ? 'Please check what you entered and try again.' : `Something went wrong (${res.status}).`;
      throw new ApiError(msg, res.status);
    }
    return data;
  }
  NX.api = {
    get: (u) => request('GET', u),
    post: (u, b) => request('POST', u, b === undefined ? {} : b),
    del: (u) => request('DELETE', u),
    upload: (file) => { const f = new FormData(); f.append('file', file); return request('POST', '/api/datasets', undefined, f); },
  };

  // ------------------------------------------------------------ datasets & cached analyses
  NX.current = () => NX.state.datasets.find((d) => d.id === NX.state.dsId) || null;
  NX.getTarget = () => NX.state.targets[NX.state.dsId] || null;
  NX.setTarget = (t) => { NX.state.targets[NX.state.dsId] = t; };
  NX.isActive = (view) => NX.state.view === view;
  NX.go = (view) => { location.hash = '#/' + view; };

  NX.refreshDatasets = async () => {
    NX.state.datasets = (await NX.api.get('/api/datasets')).datasets;
    NX.emit('datasets');
    return NX.state.datasets;
  };
  NX.setDataset = (id) => {
    NX.state.dsId = id;
    if (id) sessionStorage.setItem('nx-ds', id); else sessionStorage.removeItem('nx-ds');
    NX.emit('datasetchange', id);
  };
  const cached = (key, fn) => (NX.cache[key] ||= fn().catch((e) => { delete NX.cache[key]; throw e; }));
  const dsUrl = (path) => `/api/datasets/${encodeURIComponent(NX.state.dsId)}${path}`;
  NX.dsUrl = dsUrl;
  NX.getOverview = () => { const t = NX.getTarget(); return cached(`ov:${NX.state.dsId}:${t}`, () => NX.api.get(dsUrl('/overview') + (t ? `?target=${encodeURIComponent(t)}` : ''))); };
  NX.getQuality = () => cached(`q:${NX.state.dsId}`, () => NX.api.get(dsUrl('/quality')));
  NX.getEda = () => cached(`eda:${NX.state.dsId}`, () => NX.api.get(dsUrl('/eda')));

  NX.afterUpload = async (res, message) => {
    await NX.refreshDatasets();
    NX.setDataset(res.dataset.id);
    NX.toast(message || `${res.dataset.name} is ready`);
    NX.go('workspace');
  };
  NX.uploadFile = async (file) => {
    if (!file) return;
    if (!/\.(csv|tsv|txt)$/i.test(file.name)) { NX.toast('Please choose a .csv file.', 'error'); return; }
    const cfg = NX.state.config;
    if (cfg && file.size > cfg.max_upload_mb * 1024 * 1024) { NX.toast(`That file is over the ${cfg.max_upload_mb} MB limit.`, 'error'); return; }
    try { NX.toast('Uploading and analysing…'); await NX.afterUpload(await NX.api.upload(file)); }
    catch (e) { NX.toast(e.message, 'error'); }
  };
  NX.loadSample = async () => {
    try { await NX.afterUpload(await NX.api.post('/api/datasets/sample'), 'Sample dataset loaded'); }
    catch (e) { NX.toast(e.message, 'error'); }
  };
  NX.deleteDataset = async (id) => {
    const d = NX.state.datasets.find((x) => x.id === id);
    if (!window.confirm(`Delete "${d ? d.name : 'this dataset'}"? This can't be undone.`)) return;
    try {
      await NX.api.del(`/api/datasets/${encodeURIComponent(id)}`);
      await NX.refreshDatasets();
      if (NX.state.dsId === id) NX.setDataset(NX.state.datasets.length ? NX.state.datasets[NX.state.datasets.length - 1].id : null);
      else NX.emit('datasetchange', NX.state.dsId);
      NX.toast('Dataset deleted');
    } catch (e) { NX.toast(e.message, 'error'); }
  };

  // ------------------------------------------------------------ small shared components
  NX.card = (title, caption, ...body) => NX.h('div', { class: 'card' },
    NX.h('div', { class: 'card-head' }, NX.h('div', null, NX.h('div', { class: 'card-title' }, title), caption ? NX.h('div', { class: 'card-caption' }, caption) : null)),
    ...body);
  NX.empty = (text) => NX.h('div', { class: 'card-empty' }, text);
  NX.viewHead = (title, sub, ...actions) => NX.h('div', { class: 'view-head' },
    NX.h('div', null, NX.h('h1', { class: 'view-title' }, title), sub ? NX.h('p', { class: 'view-sub' }, sub) : null),
    actions.length ? NX.h('div', { class: 'row' }, ...actions) : null);
  NX.barRows = (rows, opts = {}) => NX.h('div', null, rows.map((r) => NX.h('div', { class: 'barrow' },
    NX.h('span', { class: 'lbl', title: r.label }, r.label),
    NX.h('div', { class: 'bar-track' }, NX.h('div', { class: 'bar-fill' + (r.warn ? ' amber' : ''), style: { left: 0, width: Math.max(1.5, Math.min(100, r.pct)) + '%' } })),
    NX.h('span', { class: 'val' }, r.text))));
  NX.severityBadge = (s) => NX.h('span', { class: 'sev ' + s }, s);

  document.addEventListener('DOMContentLoaded', () => {
    NX.$$('[data-icon]').forEach((n) => n.replaceWith(NX.icon(n.dataset.icon, n.dataset.class || '')));
  });

  NX.pickFile = () => { const i = document.getElementById('file-input'); if (i) i.click(); };
})();
