/* Explore (EDA): column profiles with per-column detail, correlation heatmap, raw data. */
(function () {
  const { h } = NX;
  let tab = 'columns', selected = null, selectedFor = null, page = 0;
  const PAGE = 25;

  const summary = (c) => c.kind === 'numeric' ? `mean ${NX.fmt.num(c.mean)}, range ${NX.fmt.num(c.min)} to ${NX.fmt.num(c.max)}`
    : c.kind === 'datetime' ? `${c.min} to ${c.max}` : c.top != null ? `most common: ${c.top} (${NX.fmt.pct(c.top_pct)})` : '';

  async function columnsTab(box, eda) {
    if (selectedFor !== NX.state.dsId || !eda.columns.some((c) => c.name === selected)) {
      selectedFor = NX.state.dsId;
      selected = NX.getTarget() && eda.columns.some((c) => c.name === NX.getTarget()) ? NX.getTarget() : eda.columns[0].name;
    }
    const detail = h('div', { class: 'sticky' });
    const rows = eda.columns.map((c) => h('tr', { class: 'clickable' + (c.name === selected ? ' selected' : ''), tabindex: '0',
      onclick: () => pick(c.name), onkeydown: (e) => { if (e.key === 'Enter') pick(c.name); } },
      h('td', null, h('b', null, c.name)), h('td', null, h('span', { class: 'badge ' + c.kind }, c.kind + (c.binary ? ' (binary)' : ''))),
      h('td', { class: 'num' }, NX.fmt.pct(c.missing_pct)), h('td', { class: 'num' }, c.unique.toLocaleString()), h('td', null, summary(c))));
    const tbl = h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
      h('thead', null, h('tr', null, h('th', null, 'Column'), h('th', null, 'Type'), h('th', { class: 'num' }, 'Missing'), h('th', { class: 'num' }, 'Unique'), h('th', null, 'Summary'))),
      h('tbody', null, rows)));
    box.replaceChildren(h('div', { class: 'split' }, tbl, detail));
    async function pick(name) {
      selected = name;
      NX.$$('tr.clickable', tbl).forEach((r, i) => r.classList.toggle('selected', eda.columns[i].name === name));
      await showDetail(detail, name);
    }
    await showDetail(detail, selected);
  }

  async function showDetail(box, name) {
    box.replaceChildren(NX.card(name, null, h('div', { class: 'loading' }, 'Loading…')));
    let d;
    try { d = await NX.api.get(NX.dsUrl('/column?name=' + encodeURIComponent(name))); }
    catch (e) { box.replaceChildren(NX.card(name, null, NX.empty(e.message))); return; }
    if (name !== selected) return;
    const p = d.profile, stats = [];
    if (d.kind === 'numeric') stats.push(['Mean', NX.fmt.num(p.mean)], ['Median', NX.fmt.num(p.median)], ['Std dev', NX.fmt.num(p.std)], ['Min', NX.fmt.num(p.min)], ['Max', NX.fmt.num(p.max)], ['Skew', d.skew == null ? 'n/a' : String(d.skew)]);
    else if (d.kind === 'datetime') stats.push(['From', d.range.min], ['To', d.range.max], ['Distinct', p.unique.toLocaleString()]);
    else stats.push(['Distinct', p.unique.toLocaleString()], ['Most common', p.top || 'n/a'], ['Share', NX.fmt.pct(p.top_pct)]);
    stats.push(['Missing', `${p.missing.toLocaleString()} (${NX.fmt.pct(p.missing_pct)})`]);
    let chart = null;
    if (d.kind === 'numeric' && d.hist.type !== 'empty') chart = NX.charts.hist(d.hist, { compact: true, title: `Distribution of ${name}` });
    else if (d.kind === 'datetime') chart = NX.charts.bars(d.by_period.labels, d.by_period.counts, { compact: true, horizontal: false });
    else if (d.counts) chart = NX.charts.bars(d.counts.labels, d.counts.counts, { compact: true, highlightFirst: true });
    const notes = [];
    if (d.suspicious_zeros) notes.push(h('div', { class: 'insight warn' }, h('span', { class: 'insight-ic' }, '!'), h('div', null, h('b', null, 'Zeros look like missing data'),
      h('p', null, `${d.suspicious_zeros.count.toLocaleString()} zeros (${d.suspicious_zeros.pct}%), but the smallest real value is ${d.suspicious_zeros.min_nonzero}. `, h('a', { class: 'link', href: '#/clean' }, 'Fix in Clean & prep')))));
    if (d.outliers && d.outliers.count) notes.push(h('p', { class: 'muted', style: { fontSize: '12.5px', marginTop: '8px' } },
      `${d.outliers.count.toLocaleString()} extreme value(s) (${NX.fmt.pct(d.outliers.pct)}) fall outside ${NX.fmt.num(d.outliers.low)} to ${NX.fmt.num(d.outliers.high)}.`));
    box.replaceChildren(NX.card(name, d.kind, h('div', { class: 'stat-grid' }, stats.map(([k, v]) => h('div', { class: 'stat' }, h('small', null, k), h('b', null, v)))),
      chart ? h('div', { class: 'chart-box' }, chart) : null, notes));
  }

  function correlationsTab(box, eda) {
    const c = eda.correlation;
    if (!c.available) { box.replaceChildren(NX.card('Correlations', null, NX.empty(c.reason))); return; }
    box.replaceChildren(h('div', { class: 'split' },
      NX.card('Correlation heatmap', 'Teal is positive, amber is negative. Darker means stronger.', h('div', { class: 'chart-box', style: { overflowX: 'auto' } }, NX.charts.heatmap(c.labels, c.matrix)),
        h('p', { class: 'heat-note' }, 'Correlation measures linear association only. It does not prove one column causes another.')),
      NX.card('Strongest pairs', null, NX.barRows(c.top_pairs.map((p) => ({ label: `${p.a} / ${p.b}`, pct: Math.abs(p.r) * 100, text: (p.r > 0 ? '+' : '') + p.r.toFixed(2), warn: p.r < 0 }))))));
  }

  async function dataTab(box) {
    box.replaceChildren(h('div', { class: 'loading' }, 'Loading rows…'));
    const d = await NX.api.get(NX.dsUrl(`/preview?offset=${page * PAGE}&limit=${PAGE}`));
    if (tab !== 'data' || !NX.isActive('explore')) return;
    const last = Math.min(d.total, (page + 1) * PAGE);
    box.replaceChildren(
      h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
        h('thead', null, h('tr', null, h('th', { class: 'num' }, '#'), d.columns.map((c) => h('th', null, c)))),
        h('tbody', null, d.rows.map((r, i) => h('tr', null, h('td', { class: 'num muted' }, d.offset + i + 1),
          r.map((v) => (v == null ? h('td', { class: 'nul' }, 'empty') : h('td', null, String(v))))))))),
      h('div', { class: 'row', style: { marginTop: '12px' } },
        h('button', { class: 'btn btn-secondary btn-sm', type: 'button', disabled: page === 0, onclick: () => { page--; dataTab(box); } }, 'Previous'),
        h('button', { class: 'btn btn-secondary btn-sm', type: 'button', disabled: last >= d.total, onclick: () => { page++; dataTab(box); } }, 'Next'),
        h('span', { class: 'muted' }, `Rows ${(d.offset + 1).toLocaleString()} to ${last.toLocaleString()} of ${d.total.toLocaleString()}`)));
  }

  NX.views.explore = {
    async render(root) {
      const eda = await NX.getEda();
      if (!NX.isActive('explore')) return;
      const box = h('div');
      const tabs = h('div', { class: 'tabs', role: 'tablist' }, [['columns', 'Columns'], ['correlations', 'Correlations'], ['data', 'Data']].map(([id, label]) =>
        h('button', { class: 'tab' + (tab === id ? ' active' : ''), type: 'button', role: 'tab', onclick: () => { tab = id; NX.views.explore.render(root); } }, label)));
      root.replaceChildren(NX.viewHead('Explore', `${eda.columns.length} columns profiled. Click a column to see its distribution.`), tabs, box);
      if (tab === 'columns') await columnsTab(box, eda);
      else if (tab === 'correlations') correlationsTab(box, eda);
      else await dataTab(box);
    },
  };
  NX.on('datasetchange', () => { page = 0; });
})();
