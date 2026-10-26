/* Visualize: build histogram, bar, scatter and line charts from any columns. */
(function () {
  const { h } = NX;
  let spec = null, specFor = null, svgNow = null;
  const TYPES = [['histogram', 'Histogram'], ['bar', 'Bar'], ['scatter', 'Scatter'], ['line', 'Line']];
  const AGGS = ['mean', 'sum', 'median', 'min', 'max', 'count'];

  function defaults(type, cols) {
    const num = cols.filter((c) => c.kind === 'numeric').map((c) => c.name);
    const tgt = NX.getTarget() && num.includes(NX.getTarget()) ? NX.getTarget() : num[0];
    const other = num.find((n) => n !== tgt) || num[0];
    const date = (cols.find((c) => c.kind === 'datetime') || {}).name;
    const cat = (cols.find((c) => c.kind === 'categorical' && c.unique <= 30) || {}).name;
    if (type === 'histogram') return { type, x: tgt };
    if (type === 'bar') return { type, x: cat || (cols.find((c) => c.unique <= 12) || cols[0]).name, y: null, agg: 'mean' };
    if (type === 'scatter') return { type, x: other, y: tgt };
    return { type, x: date || null, y: tgt, agg: 'sum' };
  }

  function controls(cols, redraw) {
    const num = cols.filter((c) => c.kind === 'numeric'), all = cols;
    const opts = (list, withNone) => [withNone ? h('option', { value: '' }, withNone) : null, list.map((c) => h('option', { value: c.name }, c.name))];
    const sel = (id, label, list, value, none, onchange) => h('div', { class: 'field' }, h('label', { for: id }, label),
      h('select', { id, class: 'select', onchange: (e) => onchange(e.target.value || null) }, opts(list, none).flat().filter(Boolean).map((o) => { if (o.value === (value || '')) o.selected = true; return o; })));
    const t = spec.type;
    const xList = t === 'bar' ? all : t === 'line' ? cols.filter((c) => c.kind === 'datetime' || c.kind === 'numeric') : num;
    const yList = num;
    return h('div', null,
      h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Chart type'),
        h('div', { class: 'seg', role: 'group' }, TYPES.map(([v, l]) => h('button', { type: 'button', class: v === t ? 'active' : '', onclick: () => { spec = defaults(v, cols); redraw(true); } }, l)))),
      sel('vx', t === 'histogram' ? 'Column' : 'X axis', xList, spec.x, t === 'line' ? 'Row order' : null, (v) => { spec.x = v; redraw(); }),
      t === 'histogram' ? null : sel('vy', t === 'bar' ? 'Measure (optional)' : 'Y axis', yList, spec.y, t === 'bar' ? 'Count of rows' : null, (v) => { spec.y = v; redraw(); }),
      (t === 'bar' && spec.y) || (t === 'line' && spec.x && (cols.find((c) => c.name === spec.x) || {}).kind === 'datetime')
        ? h('div', { class: 'field' }, h('label', { for: 'vagg' }, 'Combine values with'),
          h('select', { id: 'vagg', class: 'select', onchange: (e) => { spec.agg = e.target.value; redraw(); } }, AGGS.map((a) => h('option', { value: a, selected: a === spec.agg }, a)))) : null,
      t === 'histogram' ? h('div', { class: 'field' }, h('label', { for: 'vbins' }, `Bins: ${spec.bins || 20}`),
        h('input', { id: 'vbins', type: 'range', min: 5, max: 60, value: spec.bins || 20, oninput: (e) => { spec.bins = +e.target.value; e.target.previousSibling.textContent = `Bins: ${spec.bins}`; }, onchange: () => redraw() })) : null);
  }

  async function draw(out, title, note) {
    NX.clear(out); note.textContent = '';
    out.append(h('div', { class: 'loading' }, 'Drawing…'));
    try {
      const body = Object.fromEntries(Object.entries(spec).filter(([, v]) => v != null && v !== ''));
      const d = await NX.api.post(NX.dsUrl('/chart'), body);
      let svg;
      if (d.type === 'histogram') svg = NX.charts.hist(d, { xlabel: d.x, ylabel: 'Count', title: d.title });
      else if (d.type === 'bar') svg = NX.charts.bars(d.labels, d.values, { xlabel: d.x, ylabel: d.ylabel, title: d.title, highlightFirst: true });
      else if (d.type === 'scatter') svg = NX.charts.scatter(d.points, { fit: d.fit, xlabel: d.x, ylabel: d.y, title: d.title });
      else svg = NX.charts.line(d.labels, d.values, { xlabel: d.x, ylabel: d.ylabel, title: d.title });
      svgNow = svg; title.textContent = d.title;
      out.replaceChildren(svg);
      if (d.type === 'scatter') note.textContent = d.r == null ? '' : `Correlation r = ${d.r > 0 ? '+' : ''}${d.r}, n = ${d.n.toLocaleString()}. The dashed line is the best linear fit. Correlation is not causation.`;
      else if (d.type === 'bar' && d.labels.length >= 15) note.textContent = 'Showing the top groups only.';
    } catch (e) { svgNow = null; title.textContent = 'Chart'; out.replaceChildren(NX.empty(e.message)); }
  }

  NX.views.visualize = {
    async render(root) {
      const eda = await NX.getEda();
      if (!NX.isActive('visualize')) return;
      const cols = eda.columns;
      if (!spec || specFor !== NX.state.dsId) { spec = defaults('histogram', cols); specFor = NX.state.dsId; }
      if (spec.type === 'histogram' && !spec.x) { root.replaceChildren(NX.viewHead('Visualize', null), NX.card('No numeric columns', null, NX.empty('Charts need at least one numeric column.'))); return; }
      const title = h('div', { class: 'card-title' }, 'Chart'), note = h('p', { class: 'heat-note' }), out = h('div', { class: 'chart-box' });
      const ctl = h('div');
      const redraw = (rebuild) => { if (rebuild) ctl.replaceChildren(controls(cols, redraw)); draw(out, title, note); };
      ctl.append(controls(cols, redraw));
      root.replaceChildren(NX.viewHead('Visualize', 'Pick columns and a chart type. The chart updates as you change them.'),
        h('div', { class: 'split wide-left' }, NX.card('Chart settings', null, ctl),
          h('div', { class: 'card' }, h('div', { class: 'card-head' }, title,
            h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: () => svgNow ? NX.charts.exportPNG(svgNow, `${(spec.y || spec.x || 'chart')}.png`) : NX.toast('Nothing to download yet.', 'error') }, 'Download PNG')),
            out, note)));
      draw(out, title, note);
    },
  };
  NX.on('datasetchange', () => { spec = null; });
})();
