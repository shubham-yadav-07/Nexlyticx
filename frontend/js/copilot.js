/* Copilot chat panel. One instance, mounted into whichever view shows it.
   Conversations are kept per dataset for the life of the page. */
(function () {
  'use strict';
  const { h } = NX;
  const threads = {};      // datasetId -> [{role, ...}]
  const greeting = {};     // datasetId -> promise
  let panel, threadEl, inputEl, sendBtn, subEl, busy = false;

  function chartBlock(spec) {
    if (!spec) return null;
    try {
      const svg = NX.charts.fromSpec(spec, { compact: true });
      return h('div', { class: 'mini-chart' }, spec.title ? h('div', { class: 't' }, spec.title) : null, svg);
    } catch (e) { return null; }
  }

  function botNode(d) {
    const label = d.confidence_label || '';
    const chipClass = d.confidence ? 'chip confidence' : /^not stat|^no analysis/i.test(label) ? 'chip warn' : 'chip confidence';
    return h('div', { class: 'msg-bot' },
      h('div', { class: d.intent === 'help' ? 'msg-text plain' : 'msg-text' }, d.answer),
      d.intent === 'help' || !label ? null : h('div', { class: 'chip-row' },
        h('span', { class: chipClass }, label),
        (d.evidence || []).slice(0, 3).map((e) => h('span', { class: 'chip' }, e))),
      chartBlock(d.chart),
      d.suggestions && d.suggestions.length ? h('div', { class: 'suggest-row' },
        d.suggestions.map((s) => h('button', { type: 'button', class: 'suggest', onclick: () => ask(s) }, s))) : null);
  }

  function render() {
    if (!panel) return;
    const id = NX.state.dsId;
    NX.clear(threadEl);
    const ds = NX.current();
    subEl.textContent = ds ? (NX.getTarget() ? `Focus: ${NX.getTarget()}` : ds.name) : 'No dataset';
    inputEl.disabled = !id; sendBtn.disabled = !id || busy;
    if (!id) { threadEl.append(h('div', { class: 'msg-text plain' }, 'Load a dataset and ask me anything about it.')); return; }
    (threads[id] || []).forEach((m) => {
      if (m.role === 'user') threadEl.append(h('div', { class: 'msg-user' }, m.text));
      else if (m.role === 'thinking') threadEl.append(h('div', { class: 'thinking' }, 'Analysing your data…'));
      else threadEl.append(botNode(m.data));
    });
    threadEl.scrollTop = threadEl.scrollHeight;
  }

  async function ensureGreeting() {
    const id = NX.state.dsId;
    if (!id || (threads[id] && threads[id].length)) return;
    threads[id] = [];
    greeting[id] = NX.api.post('/api/copilot/ask', { dataset_id: id, question: 'help', target: NX.getTarget() })
      .then((d) => { d.answer = `I've loaded ${NX.current() ? NX.current().name : 'your data'}. ` + d.answer; threads[id].unshift({ role: 'bot', data: d }); })
      .catch(() => {});
    await greeting[id];
    if (id === NX.state.dsId) render();
  }

  async function ask(question) {
    const id = NX.state.dsId;
    question = (question || '').trim();
    if (!id || busy || !question) return;
    busy = true;
    const t = (threads[id] = threads[id] || []);
    t.push({ role: 'user', text: question }, { role: 'thinking' });
    if (t.length > 60) t.splice(0, t.length - 60);
    render();
    let reply;
    try { reply = await NX.api.post('/api/copilot/ask', { dataset_id: id, question, target: NX.getTarget() }); }
    catch (e) { reply = { answer: e.message, intent: 'error', evidence: [], confidence: null, confidence_label: 'Could not answer', chart: null, suggestions: [] }; }
    const i = t.findIndex((m) => m.role === 'thinking');
    if (i >= 0) t.splice(i, 1, { role: 'bot', data: reply });
    busy = false;
    if (id === NX.state.dsId) render();
  }

  function build() {
    threadEl = h('div', { class: 'copilot-thread', 'aria-live': 'polite' });
    inputEl = h('input', { class: 'input', type: 'text', maxlength: 500, placeholder: 'Ask about your data…', 'aria-label': 'Ask the copilot',
      onkeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); send(); } } });
    sendBtn = h('button', { class: 'send-btn', type: 'button', 'aria-label': 'Send', onclick: send }, NX.icon('send'));
    subEl = h('div', { class: 'copilot-sub' });
    panel = h('div', { class: 'copilot-panel' },
      h('div', { class: 'copilot-head' }, h('div', { class: 'copilot-title' }, h('span', { class: 'live-dot' }), 'Copilot'), subEl),
      threadEl, h('div', { class: 'copilot-input-row' }, inputEl, sendBtn));
  }
  function send() { const q = inputEl.value; inputEl.value = ''; ask(q); }

  NX.copilot = {
    mount(slot) { if (!panel) build(); slot.append(panel); render(); ensureGreeting(); },
    refresh() { if (panel) { render(); ensureGreeting(); } },
    ask,
    forget(id) { delete threads[id]; },
  };
  NX.on('datasetchange', () => NX.copilot.refresh());
})();
