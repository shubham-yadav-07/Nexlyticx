/* Hand-built SVG charts. Colours are resolved from the active theme at draw
   time, so each chart is also a standalone image (used for PNG export). */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const FONT = 'IBM Plex Sans, Segoe UI, Arial, sans-serif';

  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, s, attrs) {
    const t = el('text', Object.assign({ x, y }, attrs), parent);
    t.textContent = s;
    return t;
  }
  const clip = (s, n) => { s = String(s); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
  function fmt(n) {
    if (n == null || Number.isNaN(n)) return '';
    if (Math.abs(n) < 0.005) return '0';
    const a = Math.abs(n);
    if (a >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
    if (a >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
    if (a >= 1e4) return Math.round(n / 1e3) + 'k';
    if (a >= 1000) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'k';
    if (Number.isInteger(n)) return String(n);
    if (a >= 100) return n.toFixed(0);
    if (a >= 10) return n.toFixed(1);
    return n.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
  }
  function ticks(min, max, count) {
    if (min === max) max = min + 1;
    const step0 = (max - min) / Math.max(1, count);
    const mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const n = step0 / mag;
    const step = (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
    const out = [];
    for (let v = Math.floor(min / step) * step; v <= max + step * 0.5 && out.length < 20; v += step) out.push(+v.toFixed(10));
    return out;
  }
  function root(w, h, label) {
    const svg = el('svg', { viewBox: `0 0 ${w} ${h}`, role: 'img', 'aria-label': label || 'chart', 'font-family': FONT, 'font-size': 11 });
    return svg;
  }
  function dims(o) { return o.compact ? { w: 360, h: 190, fs: 10.5 } : { w: 760, h: 380, fs: 11.5 }; }

  function yGrid(svg, c, a) {
    // a: {x0,x1,y0,y1,min,max,n,fs}
    const ts = ticks(a.min, a.max, a.n);
    const top = ts[ts.length - 1];
    const bottom = ts[0];
    const Y = (v) => a.y1 - ((v - bottom) / (top - bottom || 1)) * (a.y1 - a.y0);
    ts.forEach((v) => {
      el('line', { x1: a.x0, x2: a.x1, y1: Y(v), y2: Y(v), stroke: c.lineSoft, 'stroke-width': 1 }, svg);
      text(svg, a.x0 - 6, Y(v) + 3.5, fmt(v), { 'text-anchor': 'end', fill: c.muted, 'font-size': a.fs });
    });
    return { Y, top, bottom };
  }
  function axisTitles(svg, c, o, d, ml, mt, W, H) {
    if (o.xlabel && !o.compact) text(svg, ml + W / 2, d.h - 6, o.xlabel, { 'text-anchor': 'middle', fill: c.muted, 'font-size': d.fs });
    if (o.ylabel && !o.compact) {
      const t = text(svg, 14, mt + H / 2, o.ylabel, { 'text-anchor': 'middle', fill: c.muted, 'font-size': d.fs });
      t.setAttribute('transform', `rotate(-90 14 ${mt + H / 2})`);
    }
  }

  // ---------------------------------------------------------------- histogram
  function hist(data, o = {}) {
    const c = NX.colors(), d = dims(o);
    const svg = root(d.w, d.h, o.title || 'Histogram');
    const ml = o.compact ? 38 : 56, mr = 10, mt = 10, mb = o.compact ? 24 : 48;
    const W = d.w - ml - mr, H = d.h - mt - mb;
    const counts = data.counts || [];
    const ymax = Math.max(1, ...counts);
    const g = yGrid(svg, c, { x0: ml, x1: ml + W, y0: mt, y1: mt + H, min: 0, max: ymax, n: 4, fs: d.fs });
    const discrete = data.type === 'discrete' || data.hist_type === 'discrete' || (!data.edges && data.labels);
    const n = counts.length || 1;
    if (discrete) {
      const bw = W / n;
      counts.forEach((v, i) => {
        const h = (v / g.top) * H;
        const r = el('rect', { x: ml + i * bw + bw * 0.15, y: mt + H - h, width: bw * 0.7, height: Math.max(h, 0.5), rx: 2, fill: c.teal }, svg);
        el('title', {}, r).textContent = `${data.labels[i]}: ${v}`;
        if (n <= 14 || i % Math.ceil(n / 12) === 0) text(svg, ml + i * bw + bw / 2, mt + H + 15, clip(data.labels[i], 7), { 'text-anchor': 'middle', fill: c.muted, 'font-size': d.fs });
      });
    } else {
      const e0 = data.edges[0], e1 = data.edges[data.edges.length - 1], span = e1 - e0 || 1;
      counts.forEach((v, i) => {
        const x = ml + ((data.edges[i] - e0) / span) * W;
        const w = ((data.edges[i + 1] - data.edges[i]) / span) * W;
        const h = (v / g.top) * H;
        const r = el('rect', { x: x + 0.5, y: mt + H - h, width: Math.max(w - 1, 0.5), height: Math.max(h, 0.5), rx: 1.5, fill: c.teal }, svg);
        el('title', {}, r).textContent = `${fmt(data.edges[i])} to ${fmt(data.edges[i + 1])}: ${v}`;
      });
      ticks(e0, e1, o.compact ? 4 : 7).filter((t) => t >= e0 - 1e-9 && t <= e1 + 1e-9).forEach((t) => {
        const x = ml + ((t - e0) / span) * W;
        el('line', { x1: x, x2: x, y1: mt + H, y2: mt + H + 4, stroke: c.line }, svg);
        text(svg, x, mt + H + 16, fmt(t), { 'text-anchor': 'middle', fill: c.muted, 'font-size': d.fs });
      });
    }
    el('line', { x1: ml, x2: ml + W, y1: mt + H, y2: mt + H, stroke: c.line }, svg);
    axisTitles(svg, c, o, d, ml, mt, W, H);
    return svg;
  }

  // ---------------------------------------------------------------- bars
  function bars(labels, values, o = {}) {
    const c = NX.colors(), d = dims(o);
    const n = labels.length;
    const longest = Math.max(0, ...labels.map((l) => String(l).length));
    const horizontal = o.horizontal !== undefined ? o.horizontal : n > 6 || longest > 9 || o.signed;
    const svg = root(d.w, d.h, o.title || 'Bar chart');
    const colorOf = (v, i) => (o.signed ? (v >= 0 ? c.teal : c.amber) : o.highlightFirst && i === 0 ? c.contrast : c.teal);
    const vf = o.valueFmt || ((v) => (o.signed ? (v > 0 ? '+' : '') + fmt(v) : fmt(v)));

    if (horizontal) {
      const ml = Math.min(o.compact ? 110 : 170, Math.max(56, longest * (o.compact ? 5.6 : 6.4) + 10)), mr = 42, mt = 6, mb = o.compact ? 6 : 34;
      const rowH = Math.min(o.compact ? 26 : 34, (d.h - mt - mb) / Math.max(1, n));
      const H = rowH * n, W = d.w - ml - mr;
      svg.setAttribute('viewBox', `0 0 ${d.w} ${Math.max(60, H + mt + mb)}`);
      const lo = o.domain ? o.domain[0] : Math.min(0, ...values), hi = o.domain ? o.domain[1] : Math.max(0, ...values, 1e-9);
      const X = (v) => ml + ((v - lo) / (hi - lo || 1)) * W;
      if (!o.compact || o.signed) {
        el('line', { x1: X(0), x2: X(0), y1: mt, y2: mt + H, stroke: c.line }, svg);
      }
      values.forEach((v, i) => {
        const y = mt + i * rowH, bh = rowH * 0.62;
        const x0 = X(Math.min(0, v)), x1 = X(Math.max(0, v));
        el('rect', { x: Math.min(x0, x1), y: y + (rowH - bh) / 2, width: Math.max(Math.abs(x1 - x0), 1.5), height: bh, rx: 2.5, fill: colorOf(v, i) }, svg);
        text(svg, ml - 8, y + rowH / 2 + 3.5, clip(labels[i], o.compact ? 16 : 24), { 'text-anchor': 'end', fill: c.text, 'font-size': d.fs });
        const right = v >= 0;
        text(svg, right ? x1 + 5 : x0 - 5, y + rowH / 2 + 3.5, vf(v), { 'text-anchor': right ? 'start' : 'end', fill: c.muted, 'font-size': d.fs - 0.5 });
        el('title', {}, svg.lastChild).textContent = `${labels[i]}: ${v}`;
      });
      if (o.xlabel && !o.compact) text(svg, ml + W / 2, H + mt + 24, o.xlabel, { 'text-anchor': 'middle', fill: c.muted, 'font-size': d.fs });
      return svg;
    }

    const rot = n > 7 || longest > 8;
    const ml = o.compact ? 38 : 56, mr = 10, mt = 14, mb = rot ? (o.compact ? 46 : 70) : (o.compact ? 26 : 56);
    const W = d.w - ml - mr, H = d.h - mt - mb;
    const mx = Math.max(...values, 1e-9), mn = Math.min(0, ...values);
    const g = yGrid(svg, c, { x0: ml, x1: ml + W, y0: mt, y1: mt + H, min: mn, max: mx, n: 4, fs: d.fs });
    const bw = W / n;
    const every = Math.max(1, Math.ceil(n / (o.compact ? 8 : 16)));
    values.forEach((v, i) => {
      const y1 = g.Y(v), y0 = g.Y(0);
      const r = el('rect', { x: ml + i * bw + bw * 0.16, y: Math.min(y1, y0), width: bw * 0.68, height: Math.max(Math.abs(y0 - y1), 1), rx: 2.5, fill: colorOf(v, i) }, svg);
      el('title', {}, r).textContent = `${labels[i]}: ${v}`;
      if (i % every) return;
      const lx = ml + i * bw + bw / 2, ly = mt + H + 15;
      const t = text(svg, lx, ly, clip(labels[i], rot ? 12 : 9), { 'text-anchor': rot ? 'end' : 'middle', fill: c.muted, 'font-size': d.fs });
      if (rot) t.setAttribute('transform', `rotate(-35 ${lx} ${ly - 3})`);
    });
    el('line', { x1: ml, x2: ml + W, y1: g.Y(0), y2: g.Y(0), stroke: c.line }, svg);
    axisTitles(svg, c, o, d, ml, mt, W, H);
    return svg;
  }

  // ---------------------------------------------------------------- line
  function line(labels, values, o = {}) {
    const c = NX.colors(), d = dims(o);
    const svg = root(d.w, d.h, o.title || 'Line chart');
    const ml = o.compact ? 40 : 58, mr = 12, mt = 12, mb = o.compact ? 24 : 48;
    const W = d.w - ml - mr, H = d.h - mt - mb;
    const clean = values.filter((v) => v != null);
    const lo = Math.min(...clean), hi = Math.max(...clean);
    const pad = (hi - lo) * 0.08 || 1;
    const g = yGrid(svg, c, { x0: ml, x1: ml + W, y0: mt, y1: mt + H, min: lo - pad > 0 && lo >= 0 ? Math.max(0, lo - pad) : lo - pad, max: hi + pad, n: 4, fs: d.fs });
    const n = values.length;
    const X = (i) => ml + (n === 1 ? W / 2 : (i / (n - 1)) * W);
    const pts = values.map((v, i) => (v == null ? null : [X(i), g.Y(v)])).filter(Boolean);
    if (pts.length > 1) {
      el('path', { d: `M${pts[0][0]},${mt + H} ` + pts.map((p) => `L${p[0]},${p[1]}`).join(' ') + ` L${pts[pts.length - 1][0]},${mt + H} Z`, fill: c.teal, opacity: 0.12 }, svg);
      el('polyline', { points: pts.map((p) => p.join(',')).join(' '), fill: 'none', stroke: c.teal, 'stroke-width': 2.2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
    }
    values.forEach((v, i) => {
      if (v == null || (n > 60 && i !== n - 1)) return;
      const dot = el('circle', { cx: X(i), cy: g.Y(v), r: i === n - 1 ? 3.6 : 2.2, fill: c.teal }, svg);
      el('title', {}, dot).textContent = `${labels[i]}: ${fmt(v)}`;
    });
    const k = o.compact ? 3 : 5;
    for (let j = 0; j < Math.min(k, n); j++) {
      const i = n === 1 ? 0 : Math.round((j / (Math.min(k, n) - 1 || 1)) * (n - 1));
      text(svg, X(i), mt + H + 16, clip(labels[i], 10), { 'text-anchor': j === 0 ? 'start' : j === Math.min(k, n) - 1 ? 'end' : 'middle', fill: c.muted, 'font-size': d.fs });
    }
    el('line', { x1: ml, x2: ml + W, y1: mt + H, y2: mt + H, stroke: c.line }, svg);
    axisTitles(svg, c, o, d, ml, mt, W, H);
    return svg;
  }

  // ---------------------------------------------------------------- scatter
  function scatter(points, o = {}) {
    const c = NX.colors(), d = dims(o);
    const svg = root(d.w, d.h, o.title || 'Scatter plot');
    const ml = o.compact ? 40 : 58, mr = 12, mt = 12, mb = o.compact ? 24 : 48;
    const W = d.w - ml - mr, H = d.h - mt - mb;
    const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
    const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
    const xp = (xmax - xmin) * 0.05 || 1, yp = (ymax - ymin) * 0.05 || 1;
    const g = yGrid(svg, c, { x0: ml, x1: ml + W, y0: mt, y1: mt + H, min: ymin - yp, max: ymax + yp, n: 4, fs: d.fs });
    const xt = ticks(xmin - xp, xmax + xp, o.compact ? 4 : 7);
    const xlo = xt[0], xhi = xt[xt.length - 1];
    const X = (v) => ml + ((v - xlo) / (xhi - xlo || 1)) * W;
    xt.forEach((t) => {
      el('line', { x1: X(t), x2: X(t), y1: mt, y2: mt + H, stroke: c.lineSoft }, svg);
      text(svg, X(t), mt + H + 16, fmt(t), { 'text-anchor': 'middle', fill: c.muted, 'font-size': d.fs });
    });
    points.forEach((p) => el('circle', { cx: X(p[0]), cy: g.Y(p[1]), r: o.compact ? 2 : 2.8, fill: c.teal, opacity: 0.5 }, svg));
    if (o.fit && o.fit.slope != null) {
      const y = (x) => o.fit.slope * x + o.fit.intercept;
      el('line', { x1: X(xmin), y1: g.Y(y(xmin)), x2: X(xmax), y2: g.Y(y(xmax)), stroke: c.contrast, 'stroke-width': 2, 'stroke-dasharray': '6 4' }, svg);
    }
    el('line', { x1: ml, x2: ml + W, y1: mt + H, y2: mt + H, stroke: c.line }, svg);
    axisTitles(svg, c, o, d, ml, mt, W, H);
    return svg;
  }

  // ---------------------------------------------------------------- correlation heatmap
  function heatmap(labels, matrix) {
    const c = NX.colors();
    const n = labels.length;
    const s = Math.max(26, Math.min(48, Math.floor(600 / n)));
    const longest = Math.max(...labels.map((l) => l.length));
    const ml = Math.min(150, longest * 6.4 + 12), mt = Math.min(120, longest * 4.2 + 14);
    const w = ml + n * s + 10, h = mt + n * s + 10;
    const svg = root(w, h, 'Correlation heatmap');
    labels.forEach((l, i) => {
      text(svg, ml - 7, mt + i * s + s / 2 + 3.5, clip(l, 22), { 'text-anchor': 'end', fill: c.text, 'font-size': 11 });
      const x = ml + i * s + s / 2;
      const t = text(svg, x, mt - 7, clip(l, 22), { 'text-anchor': 'start', fill: c.text, 'font-size': 11 });
      t.setAttribute('transform', `rotate(-45 ${x} ${mt - 7})`);
    });
    matrix.forEach((row, i) => row.forEach((v, j) => {
      const val = v == null ? 0 : v;
      const r = el('rect', { x: ml + j * s + 1, y: mt + i * s + 1, width: s - 2, height: s - 2, rx: 3, fill: val >= 0 ? c.teal : c.amber, opacity: Math.max(0.06, Math.abs(val)) }, svg);
      el('title', {}, r).textContent = `${labels[i]} vs ${labels[j]}: r = ${v == null ? 'n/a' : v.toFixed(2)}`;
      if (s >= 30 && i !== j) text(svg, ml + j * s + s / 2, mt + i * s + s / 2 + 3.5, val.toFixed(2).replace(/^0\./, '.').replace(/^-0\./, '-.'), { 'text-anchor': 'middle', fill: Math.abs(val) > 0.55 ? '#fff' : c.text, 'font-size': 9.5 });
    }));
    return svg;
  }

  // ---------------------------------------------------------------- gauge
  function gauge(score, grade) {
    const c = NX.colors();
    const svg = root(300, 190, `Trust score ${score} out of 100`);
    const cx = 150, cy = 150, r = 112;
    const pt = (a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    const arc = (a0, a1) => { const p0 = pt(a0), p1 = pt(a1); return `M${p0[0]},${p0[1]} A${r},${r} 0 0 1 ${p1[0]},${p1[1]}`; };
    const cls = NX.gradeClass(grade, score);
    const color = cls === 'ok' ? c.teal : cls === 'fair' ? c.amber : c.red;
    el('path', { d: arc(Math.PI, 2 * Math.PI - 0.0001), fill: 'none', stroke: c.lineSoft, 'stroke-width': 18, 'stroke-linecap': 'round' }, svg);
    if (score > 0) el('path', { d: arc(Math.PI, Math.PI + Math.PI * Math.min(score, 99.9) / 100), fill: 'none', stroke: color, 'stroke-width': 18, 'stroke-linecap': 'round' }, svg);
    text(svg, cx, cy - 18, String(score), { 'text-anchor': 'middle', fill: c.text, 'font-size': 46, 'font-family': 'Fraunces, Georgia, serif' });
    text(svg, cx, cy + 4, 'out of 100', { 'text-anchor': 'middle', fill: c.muted, 'font-size': 12 });
    text(svg, cx, cy + 28, grade, { 'text-anchor': 'middle', fill: color, 'font-size': 14, 'font-weight': 600 });
    return svg;
  }

  // ---------------------------------------------------------------- copilot / spec adapter
  function fromSpec(s, o = {}) {
    if (s.type === 'hist') return hist(s, o);
    if (s.type === 'scatter') return scatter(s.points, o);
    if (s.type === 'line') return line(s.labels, s.values, o);
    return bars(s.labels, s.values, Object.assign({ signed: !!s.signed, domain: s.signed ? [-1, 1] : undefined }, o));
  }

  // ---------------------------------------------------------------- PNG export
  function exportPNG(svg, filename) {
    const clone = svg.cloneNode(true);
    const vb = svg.viewBox.baseVal;
    const scale = 2;
    clone.setAttribute('xmlns', NS);
    clone.setAttribute('width', vb.width * scale);
    clone.setAttribute('height', vb.height * scale);
    const bg = document.createElementNS(NS, 'rect');
    bg.setAttribute('width', '100%'); bg.setAttribute('height', '100%'); bg.setAttribute('fill', NX.colors().paper);
    clone.insertBefore(bg, clone.firstChild);
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml;charset=utf-8' }));
    const img = new Image();
    img.onload = () => {
      const cv = document.createElement('canvas');
      cv.width = vb.width * scale; cv.height = vb.height * scale;
      cv.getContext('2d').drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      cv.toBlob((blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = filename || 'chart.png';
        document.body.append(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      });
    };
    img.onerror = () => NX.toast('Could not export the chart.', 'error');
    img.src = url;
  }

  NX.charts = { hist, bars, line, scatter, heatmap, gauge, fromSpec, exportPNG, fmt };
})();
