/* Reports: live preview of the printable report plus every export. */
(function () {
  const { h } = NX;
  NX.views.reports = {
    async render(root) {
      const t = NX.getTarget();
      const url = NX.dsUrl('/report') + (t ? `?target=${encodeURIComponent(t)}` : '');
      const frame = h('iframe', { class: 'report-frame', src: url, title: 'Report preview', loading: 'eager' });
      root.replaceChildren(
        NX.viewHead('Reports', 'A shareable analysis of this dataset. Use "Save as PDF" in the print dialog for a clean PDF.',
          h('a', { class: 'btn btn-secondary btn-sm', href: url, target: '_blank', rel: 'noopener' }, 'Open full page'),
          h('button', { class: 'btn btn-primary btn-sm', type: 'button', onclick: () => { try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch (e) { window.open(url, '_blank', 'noopener'); } } }, 'Print / Save as PDF'),
          h('a', { class: 'btn btn-secondary btn-sm', href: NX.dsUrl('/download.csv'), download: '' }, 'Download CSV'),
          h('a', { class: 'btn btn-secondary btn-sm', href: NX.dsUrl('/summary.json') + (t ? `?target=${encodeURIComponent(t)}` : ''), download: '' }, 'Download JSON')),
        frame);
    },
  };
})();
