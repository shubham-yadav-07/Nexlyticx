/* Landing page: 3D hero that tilts with the cursor, and sign-in aware navigation. */
window.addEventListener('DOMContentLoaded', () => {
  const scene = document.getElementById('scene'), stage = document.getElementById('stage');
  if (scene && stage && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const bx = 10, by = -20;
    scene.addEventListener('mousemove', (e) => {
      const r = scene.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5, py = (e.clientY - r.top) / r.height - 0.5;
      stage.style.transform = `rotateX(${bx - py * 14}deg) rotateY(${by + px * 22}deg)`;
    });
    scene.addEventListener('mouseleave', () => { stage.style.transform = `rotateX(${bx}deg) rotateY(${by}deg)`; });
  }

  // Show "Open app" instead of Log in / Get started when already signed in.
  if (window.NX) {
    NX.api.get('/api/auth/me').then((me) => {
      if (!me.user) return;
      const box = document.getElementById('nav-auth');
      box.replaceChildren(NX.h('span', { class: 'muted hide-sm', style: { fontSize: '13px' } }, me.user.name),
        NX.h('a', { class: 'btn btn-primary btn-sm', href: '/app' }, 'Open app'));
    }).catch(() => {});
  }
});
