/* Account: profile, password, sign out and account deletion (members); sign-up prompt (guests). */
(function () {
  const { h } = NX;

  async function logout() {
    try { await NX.api.post('/api/auth/logout'); } catch (e) { /* ignore */ }
    sessionStorage.removeItem('nx-ds');
    location.href = '/';
  }
  NX.logout = logout;

  function passwordCard() {
    const cur = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', 'aria-label': 'Current password' });
    const nw = h('input', { class: 'input', type: 'password', autocomplete: 'new-password', 'aria-label': 'New password' });
    const msg = h('div', { hidden: true });
    const btn = h('button', { class: 'btn btn-primary btn-sm', type: 'button', onclick: async () => {
      msg.hidden = true; btn.disabled = true;
      try { await NX.api.post('/api/auth/password', { current_password: cur.value, new_password: nw.value }); cur.value = nw.value = ''; NX.toast('Password updated. Other devices were signed out.'); }
      catch (e) { msg.hidden = false; msg.className = 'form-error'; msg.textContent = e.message; }
      btn.disabled = false;
    } }, 'Update password');
    return NX.card('Change password', 'Other devices will be signed out.', msg,
      h('div', { class: 'field' }, h('label', null, 'Current password'), cur), h('div', { class: 'field' }, h('label', null, 'New password (8+ characters)'), nw), btn);
  }

  function dangerCard() {
    const pw = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', 'aria-label': 'Password to confirm' });
    const msg = h('div', { hidden: true });
    return h('div', { class: 'card', style: { borderColor: 'var(--red)' } },
      h('div', { class: 'card-title' }, 'Delete account'),
      h('div', { class: 'card-caption', style: { marginBottom: '12px' } }, 'Permanently deletes your account and every dataset saved to it. This cannot be undone.'), msg,
      h('div', { class: 'field' }, h('label', null, 'Enter your password to confirm'), pw),
      h('button', { class: 'btn btn-danger btn-sm', type: 'button', onclick: async () => {
        if (!window.confirm('Delete your account and all saved datasets forever?')) return;
        try { await NX.api.post('/api/auth/delete-account', { password: pw.value }); sessionStorage.removeItem('nx-ds'); location.href = '/'; }
        catch (e) { msg.hidden = false; msg.className = 'form-error'; msg.textContent = e.message; }
      } }, 'Delete my account'));
  }

  NX.views.account = {
    async render(root) {
      const u = NX.state.user;
      if (!u) {
        root.replaceChildren(NX.viewHead('Account', null), h('div', { class: 'empty-state' }, h('h2', null, "You're browsing as a guest"),
          h('p', null, `Guest datasets live in memory and are deleted after ${NX.state.config.session_ttl_minutes} minutes of inactivity. Create a free account to keep your datasets, return to them later and from any device.`),
          h('div', { class: 'row', style: { justifyContent: 'center' } },
            h('a', { class: 'btn btn-primary', href: '/signup' }, 'Create free account'), h('a', { class: 'btn btn-secondary', href: '/login?next=/app' }, 'Sign in'))));
        return;
      }
      const saved = NX.state.datasets.length;
      root.replaceChildren(NX.viewHead('Account', 'Your profile and security settings.'),
        h('div', { class: 'grid-2' }, h('div', { class: 'stack' },
          NX.card('Profile', null, h('div', { class: 'row', style: { marginBottom: '14px' } }, h('div', { class: 'avatar', style: { width: '44px', height: '44px', fontSize: '15px' } }, NX.fmt.initials(u.name)),
            h('div', null, h('b', null, u.name), h('div', { class: 'muted' }, u.email))),
            h('div', { class: 'stat-grid' }, h('div', { class: 'stat' }, h('small', null, 'Saved datasets'), h('b', null, `${saved} of ${NX.state.config.max_saved_datasets}`)),
              h('div', { class: 'stat' }, h('small', null, 'Member since'), h('b', null, new Date(u.created_at * 1000).toLocaleDateString()))),
            h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: logout }, 'Sign out')),
          dangerCard()), passwordCard()));
    },
  };
})();
