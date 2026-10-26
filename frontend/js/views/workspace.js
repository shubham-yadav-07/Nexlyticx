/* Workspace: KPIs, auto-generated findings, four charts and the docked copilot. */
(function () {
  const { h } = NX;

  function kpi(label, value, sub, subClass, href) {
    return h(href ? 'a' : 'div', { class: 'kpi', href: href || null },
      h('div', { class: 'kpi-label' }, label), h('div', { class: 'kpi-value' }, value),
      sub ? h('div', { class: 'kpi-sub ' + (subClass || '') }, sub) : null);
  }

  function distributionCard(ov) {
    const d = ov.charts.distribution;
    if (!d) return NX.card('Distribution', null, NX.empty('Pick a focus column to see its distribution.'));
    const title = `Distribution of ${d.column}`;
    if (d.kind === 'numeric') {
      return NX.card(title, 'How the values are spread', d.type === 'empty' ? NX.empty('No values.') : h('div', { class: 'chart-box' }, NX.charts.hist(d, { compact: true, title })));
    }
    return NX.card(title, `${d.total.toLocaleString()} records, ${d.distinct} distinct`, h('div', { class: 'chart-box' }, NX.charts.bars(d.labels, d.counts, { compact: true, title })));
  }

  function correlationCard(ov) {
    const c = ov.charts.correlation;
    const title = ov.target ? `What moves ${ov.target}` : 'Correlations';
    if (!c.available) return NX.card(title, null, NX.empty(c.reason));
    return NX.card(title, 'Pearson correlation, from -1 to +1',
      h('div', { class: 'chart-box' }, NX.charts.bars(c.results.map((r) => r.column), c.results.map((r) => r.r), { compact: true, signed: true, domain: [-1, 1], title })));
  }

  function qualityCard(ov) {
    const rows = ov.quality.per_column.map((c) => ({ label: c.column, total: (c.missing_pct || 0) + (c.zero_pct || 0) }))
      .filter((c) => c.total > 0).sort((a, b) => b.total - a.total).slice(0, 7);
    const body = rows.length ? NX.barRows(rows.map((r) => ({ label: r.label, pct: Math.min(100, r.total * 2), text: NX.fmt.pct(r.total), warn: r.total >= 5 })))
      : NX.empty('No missing or placeholder values found.');
    return NX.card('Data quality by column', 'Missing values plus suspicious zeros', body,
      h('a', { class: 'link', href: '#/trust', style: { marginTop: '10px', fontSize: '12.5px' } }, 'See the full trust score'));
  }

  function secondaryCard(ov) {
    const s = ov.charts.secondary;
    if (!s) return NX.card('Over time or by category', null, NX.empty('This dataset has no date or category column to chart.'));
    if (s.kind === 'trend') return NX.card(`${s.column} over time`, `Grouped by ${s.date}`, h('div', { class: 'chart-box' }, NX.charts.line(s.labels, s.values, { compact: true, title: `${s.column} over time` })));
    return NX.card(`${s.column} breakdown`, `${s.total.toLocaleString()} records`, h('div', { class: 'chart-box' }, NX.charts.bars(s.labels, s.counts, { compact: true, highlightFirst: true, title: `${s.column} breakdown` })));
  }

  function insightsCard(ov) {
    const ic = { warn: '!', good: '✓', info: 'i' };
    return NX.card('Key findings', 'Generated from your data, not guessed',
      h('div', null, ov.insights.map((i) => h('div', { class: 'insight ' + i.level },
        h('span', { class: 'insight-ic' }, ic[i.level] || 'i'), h('div', null, h('b', null, i.title), h('p', null, i.detail))))));
  }

  NX.views.workspace = {
    async render(root) {
      const ov = await NX.getOverview();
      if (!NX.isActive('workspace')) return;
      const p = ov.profile, q = ov.quality;
      const focus = h('div', { class: 'field', style: { margin: 0, minWidth: '200px' } },
        h('label', { for: 'focus-select' }, 'Focus column'),
        h('select', { id: 'focus-select', class: 'select', onchange: (e) => { NX.setTarget(e.target.value); NX.copilot.refresh(); NX.views.workspace.render(root); } },
          ov.target_options.map((c) => h('option', { value: c, selected: c === ov.target }, c))));
      const gc = NX.gradeClass(q.grade, q.score);
      root.replaceChildren(
        NX.viewHead('Workspace', ov.dataset.name, ov.target_options.length ? focus : null),
        h('div', { class: 'kpi-strip' },
          kpi('Rows', p.rows.toLocaleString()),
          kpi('Columns', String(p.columns), `${p.numeric} numeric, ${p.categorical} categorical`),
          kpi('Trust score', String(q.score), q.grade, gc === 'ok' ? 'good' : 'warn', '#/trust'),
          kpi('Missing cells', p.missing_cells.toLocaleString(), `${NX.fmt.pct(p.missing_pct)} of all cells`, p.missing_pct > 5 ? 'warn' : ''),
          kpi('Duplicate rows', p.duplicate_rows.toLocaleString(), p.duplicate_rows ? 'Remove in Clean & prep' : 'None found', p.duplicate_rows ? 'warn' : 'good'),
          kpi('Suspicious zeros', q.totals.invalid_cells.toLocaleString(), q.totals.invalid_cells ? 'Likely hidden missing data' : 'None found', q.totals.invalid_cells ? 'warn' : 'good', q.totals.invalid_cells ? '#/clean' : null)),
        h('div', { class: 'ws-grid' },
          h('div', { class: 'stack' }, insightsCard(ov),
            h('div', { class: 'charts-grid' }, distributionCard(ov), correlationCard(ov), qualityCard(ov), secondaryCard(ov))),
          h('div', { class: 'copilot-slot', id: 'ws-copilot-slot' })));
      NX.copilot.mount(NX.$('#ws-copilot-slot', root));
    },
  };
})();
