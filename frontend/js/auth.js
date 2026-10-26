/* Sign in / create account page. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  let mode = location.pathname === '/signup' || params.get('mode') === 'signup' ? 'signup' : 'login';

  // Only ever redirect to a path on this site.
  const next = (() => { const n = params.get('next') || ''; return /^\/[A-Za-z0-9_\-/.?=&]*$/.test(n) && !n.startsWith('//') ? n : '/app'; })();

  function setMode(m) {
    mode = m;
    const signup = m === 'signup';
    $('tab-login').classList.toggle('active', !signup); $('tab-signup').classList.toggle('active', signup);
    $('tab-login').setAttribute('aria-selected', String(!signup)); $('tab-signup').setAttribute('aria-selected', String(signup));
    $('auth-title').textContent = signup ? 'Create your free account' : 'Welcome back';
    $('auth-sub').textContent = signup ? 'Save your datasets and pick up where you left off.' : 'Sign in to open your saved datasets.';
    $('auth-submit').textContent = signup ? 'Create account' : 'Sign in';
    $('field-name').hidden = !signup; $('pw-hint').hidden = !signup;
    $('password').autocomplete = signup ? 'new-password' : 'current-password';
    $('auth-error').hidden = true;
    document.title = signup ? 'Create your NexlyticX account' : 'Sign in to NexlyticX';
  }
  function showError(msg) { const e = $('auth-error'); e.textContent = msg; e.hidden = false; }

  $('tab-login').addEventListener('click', () => setMode('login'));
  $('tab-signup').addEventListener('click', () => setMode('signup'));
  $('pw-toggle').addEventListener('click', () => {
    const p = $('password'), show = p.type === 'password';
    p.type = show ? 'text' : 'password';
    $('pw-toggle').textContent = show ? 'Hide' : 'Show';
    $('pw-toggle').setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  });

  $('auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('auth-error').hidden = true;
    const email = $('email').value.trim(), password = $('password').value, name = $('name').value.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email)) return showError('Enter a valid e-mail address.');
    if (mode === 'signup' && !name) return showError('Please enter your name.');
    if (mode === 'signup' && password.length < 8) return showError('Use at least 8 characters for your password.');
    if (!password) return showError('Enter your password.');
    const btn = $('auth-submit'), label = btn.textContent;
    btn.disabled = true; btn.textContent = mode === 'signup' ? 'Creating account…' : 'Signing in…';
    try {
      const res = await NX.api.post(mode === 'signup' ? '/api/auth/register' : '/api/auth/login', mode === 'signup' ? { name, email, password } : { email, password });
      if (res.adopted_datasets) sessionStorage.setItem('nx-adopted', res.adopted_datasets);
      location.href = next;
    } catch (err) {
      showError(err.message);
      btn.disabled = false; btn.textContent = label;
    }
  });

  setMode(mode);
  NX.api.get('/api/config').then((c) => { if (c.require_login) $('guest-alt').hidden = true; }).catch(() => {});
})();
