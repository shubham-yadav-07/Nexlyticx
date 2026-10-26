/* Trust score: transparent data-quality scoring with the issues behind it. */
(function () {
  const { h } = NX;
  NX.views.trust = {
    async render(root) {
      const q = await NX.getQuality();
      if (!NX.isActive('trust')) return;
      const cls = NX.gradeClass(q.grade, q.score);
      const count = (s) => q.issues.filter((i) => i.severity === s).length;
      const summary = q.issues.length
        ? `${q.issues.length} issue${q.issues.length > 1 ? 's' : ''} found: ${count('high')} high, ${count('medium')} medium, ${count('low')} low severity.`
        : 'No issues found. This data is ready to analyse.';
      root.replaceChildren(
        NX.viewHead('Trust score', 'How much you can rely on this dataset before drawing conclusions from it.'),
        h('div', { class: 'card' }, h('div', { class: 'score-hero' },
          h('div', { class: 'gauge-wrap' }, NX.charts.gauge(q.score, q.grade)),
          h('div', null, h('span', { class: 'grade ' + cls }, q.grade), h('h2', { style: { fontFamily: 'var(--font-serif)', fontWeight: 500, fontSize: '22px', margin: '10px 0 6px' } }, summary),
            h('p', { class: 'muted', style: { maxWidth: '560px' } }, q.grade === 'Needs attention' && q.score >= 70
              ? 'The average looks healthy, but at least one serious problem can distort your results. Fix the high-severity items first.'
              : 'The score blends five quality dimensions, each calculated directly from the data.'),
            h('div', { class: 'row', style: { marginTop: '14px' } },
              h('button', { class: 'btn btn-primary btn-sm', type: 'button', onclick: () => NX.go('clean') }, q.issues.length ? 'Fix issues' : 'Open Clean & prep'),
              h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: () => NX.go('reports') }, 'View report')))),
          h('div', { class: 'dim-grid' }, q.dimensions.map((d) => h('div', { class: 'dim' }, h('div', { class: 'lbl' }, `${d.label} (${d.weight}%)`),
            h('div', { class: 'sc' }, d.score), NX.barRows([{ label: '', pct: d.score, text: '', warn: d.score < 80 }]).firstChild.children[1], h('small', null, d.detail)))),
          h('details', { class: 'how' }, h('summary', null, 'How the score is calculated'), h('ul', null,
            ['Completeness (25%): share of cells that are not empty.', 'Validity (30%): penalises placeholder zeros, such as a blood pressure of 0, which are really unknown values.',
              'Uniqueness (15%): share of rows that are not exact duplicates.', 'Consistency (15%): penalises constant columns and columns mixing numbers and text.',
              'Outliers (15%): share of numeric cells outside 1.5 x IQR.', 'Any high-severity issue caps the grade at "Needs attention", whatever the average.'].map((t) => h('li', null, t))))),
        h('div', { style: { height: '16px' } }),
        NX.card(`Issues (${q.issues.length})`, 'Sorted by severity', q.issues.length
          ? h('div', null, q.issues.map((i) => h('div', { class: 'issue' }, NX.severityBadge(i.severity), h('div', null, h('b', null, i.title), h('p', null, i.detail)),
            h('a', { class: 'link', href: '#/clean', style: { fontSize: '12.5px' } }, i.fix ? 'Fix' : '')))) : NX.empty('Nothing to report.')));
    },
  };
})();
