/* Clean & prep: review detected issues, queue fixes into a plan, apply it to
   create a new cleaned copy. The original dataset is never modified. */
(function () {
  const { h } = NX;
  let plan = [], planFor = null, lastResult = null;
  const PRIORITY = { zeros_to_nan: 0, drop_duplicates: 1, cap_outliers: 2, drop_missing_rows: 3, fill_missing: 4, drop_columns: 5 };
  const OPS = [['fill_missing', 'Fill missing values'], ['zeros_to_nan', 'Treat zeros as missing'], ['cap_outliers', 'Cap extreme values'],
    ['drop_duplicates', 'Remove duplicate rows'], ['drop_missing_rows', 'Remove rows with missing values'], ['drop_columns', 'Drop a column']];

  const key = (op) => JSON.stringify([op.type, [...(op.columns || [])].sort(), op.strategy || null, op.value ?? null]);
  const inPlan = (op) => plan.some((p) => key(p) === key(op));
  function add(ops) {
    ops.forEach((op) => { if (!inPlan(op)) plan.push(op); });
    plan.sort((a, b) => PRIORITY[a.type] - PRIORITY[b.type]);
  }
  function expand(fix) {
    // A zero placeholder has to become "missing" first, then be filled, to fully repair the column.
    if (fix.type === 'zeros_to_nan') return [fix, { type: 'fill_missing', columns: fix.columns, strategy: 'median' }];
    return [fix];
  }
  function describe(op) {
    const cols = op.columns && op.columns.length ? op.columns.join(', ') : 'all applicable columns';
    switch (op.type) {
      case 'drop_duplicates': return 'Remove duplicate rows';
      case 'zeros_to_nan': return `Treat zeros as missing in ${cols}`;
      case 'cap_outliers': return `Cap extreme values in ${cols}`;
      case 'drop_columns': return `Drop column ${cols}`;
      case 'drop_missing_rows': return op.columns && op.columns.length ? `Remove rows missing ${cols}` : 'Remove rows with any missing value';
      default: return `Fill missing values in ${cols} with ${op.strategy === 'constant' ? `"${op.value}"` : op.strategy}`;
    }
  }

  function resultCard() {
    const r = lastResult;
    if (!r || r.dataset.id !== NX.state.dsId) return null;
    const better = r.after.score - r.before.score;
    return h('div', { class: 'card result-card', style: { marginBottom: '16px' } },
      h('div', { class: 'card-title' }, 'Cleaning complete'),
      h('div', { class: 'card-caption' }, `Saved as a new dataset: ${r.dataset.name}. Your original is untouched.`),
      h('div', { class: 'delta', style: { margin: '12px 0' } }, h('span', null, r.before.score), h('span', { class: 'arrow' }, '→'),
        h('span', { style: { color: 'var(--teal-deep)' } }, r.after.score),
        h('span', { class: 'muted', style: { fontSize: '13px', fontFamily: 'var(--font-sans)' } }, `trust score (${better >= 0 ? '+' : ''}${better.toFixed(1)}), ${r.after.rows.toLocaleString()} rows`)),
      h('ul', { class: 'result-log' }, r.log.map((l) => h('li', { class: l.startsWith('Caution') ? 'warn' : '' }, l))),
      h('div', { class: 'row' },
        h('a', { class: 'btn btn-primary btn-sm', href: NX.dsUrl('/download.csv'), download: '' }, 'Download cleaned CSV'),
        h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: () => NX.go('reports') }, 'View report'),
        h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: () => { lastResult = null; NX.views.clean.redraw(); } }, 'Dismiss')));
  }

  function issuesCard(q) {
    const recommended = q.issues.filter((i) => i.fix && ['fill_missing', 'zeros_to_nan', 'drop_duplicates', 'drop_missing_rows'].includes(i.fix.type));
    const rows = q.issues.map((i) => {
      const ops = i.fix ? expand(i.fix) : [];
      const added = ops.length && ops.every(inPlan);
      return h('div', { class: 'issue' }, NX.severityBadge(i.severity),
        h('div', null, h('b', null, i.title), h('p', null, i.detail)),
        i.fix ? h('button', { class: 'btn btn-secondary btn-sm', type: 'button', disabled: added, onclick: () => { add(ops); NX.views.clean.redraw(); } }, added ? 'Added' : 'Add fix')
          : h('span', { class: 'muted', style: { fontSize: '12px' } }, 'Review manually'));
    });
    return NX.card(`Issues found (${q.issues.length})`, `Trust score ${q.score} / 100, ${q.grade}`,
      q.issues.length ? h('div', null, rows) : NX.empty('Nothing to fix. This dataset looks clean.'),
      recommended.length ? h('div', { style: { marginTop: '14px' } },
        h('button', { class: 'btn btn-primary btn-sm', type: 'button', onclick: () => { recommended.forEach((i) => add(expand(i.fix))); NX.views.clean.redraw(); } }, 'Add all recommended fixes')) : null);
  }

  function customForm(eda) {
    const cols = eda.columns, numeric = cols.filter((c) => c.kind === 'numeric').map((c) => c.name);
    const opSel = h('select', { class: 'select', 'aria-label': 'Step type' }, OPS.map(([v, l]) => h('option', { value: v }, l)));
    const colSel = h('select', { class: 'select', 'aria-label': 'Column' });
    const stratSel = h('select', { class: 'select', 'aria-label': 'Fill with' }, ['median', 'mean', 'mode', 'zero', 'constant'].map((s) => h('option', { value: s }, s === 'zero' ? 'zero' : s === 'constant' ? 'a fixed value…' : s)));
    const valInput = h('input', { class: 'input', type: 'text', placeholder: 'Value', 'aria-label': 'Fixed value' });
    const fColumn = h('div', { class: 'field' }, h('label', null, 'Column'), colSel);
    const fStrat = h('div', { class: 'field' }, h('label', null, 'Fill with'), stratSel);
    const fVal = h('div', { class: 'field' }, h('label', null, 'Value'), valInput);
    function sync() {
      const t = opSel.value;
      const noCol = t === 'drop_duplicates';
      const options = (t === 'zeros_to_nan' || t === 'cap_outliers') ? numeric : cols.map((c) => c.name);
      NX.clear(colSel);
      if (t !== 'drop_columns') colSel.append(h('option', { value: '' }, 'All applicable'));
      options.forEach((c) => colSel.append(h('option', { value: c }, c)));
      fColumn.hidden = noCol; fStrat.hidden = t !== 'fill_missing'; fVal.hidden = t !== 'fill_missing' || stratSel.value !== 'constant';
    }
    opSel.addEventListener('change', sync); stratSel.addEventListener('change', sync); sync();
    const addBtn = h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: () => {
      const op = { type: opSel.value, columns: colSel.value && opSel.value !== 'drop_duplicates' ? [colSel.value] : [] };
      if (op.type === 'drop_columns' && !op.columns.length) return NX.toast('Choose a column to drop.', 'error');
      if (op.type === 'fill_missing') { op.strategy = stratSel.value; if (op.strategy === 'constant') { if (!valInput.value.trim()) return NX.toast('Enter a value to fill with.', 'error'); op.value = valInput.value.trim(); } }
      add([op]); NX.views.clean.redraw();
    } }, 'Add step');
    return h('details', { class: 'how', style: { marginTop: '14px' } }, h('summary', null, 'Add a custom step'),
      h('div', { style: { marginTop: '12px' } }, h('div', { class: 'field' }, h('label', null, 'Step'), opSel), fColumn, fStrat, fVal, addBtn));
  }

  function planCard(eda) {
    const apply = h('button', { class: 'btn btn-primary', type: 'button', disabled: !plan.length, style: { width: '100%', marginTop: '6px' }, onclick: async (e) => {
      e.target.disabled = true; e.target.textContent = 'Cleaning…';
      try {
        const res = await NX.api.post(NX.dsUrl('/clean'), { ops: plan });
        lastResult = res; plan = [];
        await NX.refreshDatasets(); NX.setDataset(res.dataset.id);
        NX.toast('Cleaned copy created');
      } catch (err) { NX.toast(err.message, 'error'); NX.views.clean.redraw(); }
    } }, 'Apply cleaning plan');
    return NX.card('Cleaning plan', 'Steps run top to bottom and produce a new copy.',
      plan.length ? h('div', null, plan.map((op, i) => h('div', { class: 'plan-item' }, h('span', { class: 'n' }, i + 1), h('span', { style: { flex: 1 } }, describe(op)),
        h('button', { class: 'btn btn-ghost btn-sm', type: 'button', 'aria-label': 'Remove step', onclick: () => { plan.splice(i, 1); NX.views.clean.redraw(); } }, '✕'))))
        : h('p', { class: 'muted', style: { fontSize: '13px', marginBottom: '10px' } }, 'No steps yet. Add fixes from the issue list, or build your own.'),
      apply, customForm(eda));
  }

  NX.views.clean = {
    _root: null,
    async render(root) {
      this._root = root;
      if (planFor !== NX.state.dsId) { plan = []; planFor = NX.state.dsId; }
      const [q, eda] = await Promise.all([NX.getQuality(), NX.getEda()]);
      if (!NX.isActive('clean')) return;
      this._q = q; this._eda = eda;
      this.draw();
    },
    draw() {
      const root = this._root;
      root.replaceChildren(NX.viewHead('Clean & prep', 'Fix the problems that quietly distort results. Every step is explained, and your original data is never changed.'),
        resultCard(), h('div', { class: 'split' }, issuesCard(this._q), planCard(this._eda)));
    },
    redraw() { if (this._q) this.draw(); },
  };
})();
