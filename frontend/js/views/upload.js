/* Upload data: drag-and-drop zone and the list of datasets in this session / account. */
(function () {
  const { h } = NX;
  const SRC = { upload: 'Uploaded', sample: 'Sample', cleaned: 'Cleaned' };

  function dropzone() {
    const cfg = NX.state.config;
    const dz = h('div', { class: 'dropzone', role: 'button', tabindex: '0', onclick: NX.pickFile,
      onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); NX.pickFile(); } } },
      NX.icon('upload'), h('div', { class: 'big' }, 'Drop a CSV file here, or click to browse'),
      h('div', { class: 'muted' }, `Up to ${cfg.max_upload_mb} MB and ${cfg.max_rows.toLocaleString()} rows. Comma, semicolon and tab separated files all work.`));
    ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
    dz.addEventListener('drop', (e) => NX.uploadFile(e.dataTransfer.files[0]));
    return dz;
  }

  function table() {
    const list = NX.state.datasets;
    if (!list.length) return NX.empty('No datasets yet. Upload a file or try the sample.');
    const rows = list.slice().reverse().map((d) => h('tr', { class: d.id === NX.state.dsId ? 'selected' : '' },
      h('td', null, h('b', null, d.name)),
      h('td', { class: 'num' }, d.rows.toLocaleString()), h('td', { class: 'num' }, String(d.columns)),
      h('td', null, h('span', { class: 'badge' }, SRC[d.source] || d.source)),
      h('td', null, d.saved ? 'Saved to account' : 'This session only'),
      h('td', null, NX.fmt.ago(d.created_at)),
      h('td', null, h('div', { class: 'row', style: { gap: '6px', flexWrap: 'nowrap' } },
        h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: () => { NX.setDataset(d.id); NX.go('workspace'); } }, 'Open'),
        h('a', { class: 'btn btn-ghost btn-sm', href: `/api/datasets/${encodeURIComponent(d.id)}/download.csv`, download: '' }, 'CSV'),
        h('button', { class: 'btn btn-danger btn-sm', type: 'button', onclick: () => NX.deleteDataset(d.id) }, 'Delete')))));
    return h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
      h('thead', null, h('tr', null, ['Name', 'Rows', 'Columns', 'Source', 'Storage', 'Added', ''].map((t, i) => h('th', { class: i === 1 || i === 2 ? 'num' : '' }, t)))),
      h('tbody', null, rows)));
  }

  NX.views.upload = {
    async render(root) {
      const cfg = NX.state.config, member = !!NX.state.user;
      root.replaceChildren(
        NX.viewHead('Upload data', 'Bring in a CSV to profile, clean, explore and ask questions about.'),
        h('div', { class: 'stack' }, dropzone(),
          h('div', { class: 'row' }, h('span', { class: 'muted' }, 'No file handy?'),
            h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: NX.loadSample }, 'Try the sample retail dataset')),
          NX.card('Your datasets', member ? `Saved privately to your account (up to ${cfg.max_saved_datasets}). Delete any of them at any time.`
            : `Guest datasets stay in memory and are deleted after ${cfg.session_ttl_minutes} minutes of inactivity.`, table())));
    },
  };
})();
