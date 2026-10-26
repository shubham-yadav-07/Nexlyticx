/* Copilot page: the chat at full size, with ideas to try and an honest note on how answers are made. */
(function () {
  const { h } = NX;

  async function ideas() {
    const [eda, ov] = await Promise.all([NX.getEda(), NX.getOverview()]);
    const num = eda.columns.filter((c) => c.kind === 'numeric' && !c.binary).map((c) => c.name);
    const cat = eda.columns.filter((c) => c.kind === 'categorical' || c.binary).map((c) => c.name);
    const date = eda.columns.some((c) => c.kind === 'datetime');
    const t = ov.target, tNum = t && eda.columns.find((c) => c.name === t && c.kind === 'numeric');
    const other = num.find((n) => n !== t) || num[0];
    const group = (t && cat.includes(t)) ? t : cat[0];
    return [
      ['Drivers', tNum ? `What affects ${t}?` : null],
      ['Compare groups', group && other ? `Compare ${other} by ${group}` : null],
      ['Distribution', num[0] ? `Show the distribution of ${num[0]}` : null],
      ['Averages', num[0] ? `What is the average ${num[0]}?` : null],
      ['Seasonality', date && num[0] ? `Is ${num[0]} seasonal?` : null],
      ['Trend', date && num[0] ? `Is ${num[0]} trending over time?` : null],
      ['Quality', 'Which columns have missing values?'],
      ['Outliers', 'Are there any outliers?'],
      ['Overview', 'Give me a summary of this data'],
    ].filter((x) => x[1]);
  }

  NX.views.copilot = {
    async render(root) {
      const list = await ideas();
      if (!NX.isActive('copilot')) return;
      const slot = h('div', { style: { height: 'calc(100vh - 190px)', minHeight: '480px' } });
      root.replaceChildren(NX.viewHead('Copilot', 'Ask in plain English. Every answer is calculated from your data with real statistical tests.'),
        h('div', { class: 'split' }, slot, h('div', { class: 'stack' },
          NX.card('Ideas to try', 'Built from your column names', h('div', { class: 'suggest-row' },
            list.map(([k, q]) => h('button', { class: 'suggest', type: 'button', onclick: () => NX.copilot.ask(q) }, h('b', { style: { display: 'block', fontSize: '11px', color: 'var(--muted)', fontWeight: 500 } }, k), q)))),
          NX.card('How answers are produced', null, h('ul', { class: 'result-log', style: { fontSize: '12.5px' } },
            ['It reads which of your columns you mention, then picks the matching analysis.', 'Numbers come from pandas and SciPy, never from a language model.',
              'Tests show their p-value. Plain calculations are labelled "Exact calculation".', 'It cannot see outside your file, so it will not explain why something happened in the real world.']
              .map((t) => h('li', null, t)))))));
      NX.copilot.mount(slot);
    },
  };
})();
