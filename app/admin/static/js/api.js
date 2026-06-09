// ── API client : CSRF + token refresh + error handling ───────────

const API_BASE = '/api/v1/admin';

async function apiCall(endpoint, options = {}) {
  let token = localStorage.getItem('access_token');
  const method = (options.method || 'GET').toUpperCase();
  const isWrite = ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method);

  const headers = {
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...options.headers,
  };

  // Attach CSRF token for state-changing requests
  if (isWrite) {
    let csrf = getCsrfToken();
    if (!csrf) {
      try {
        const r = await fetch(`${API_BASE}/auth/csrf-token`, { credentials: 'include' });
        if (r.ok) {
          const d = await r.json();
          csrf = d.csrf_token;
          document.cookie = `csrf_token=${csrf}; path=/; SameSite=Strict`;
        }
      } catch (_) { /* non-fatal */ }
    }
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }

  let response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
    credentials: 'include',
  });

  // Token refresh on 401
  if (response.status === 401) {
    const refresh = localStorage.getItem('refresh_token');
    if (refresh) {
      try {
        const rr = await fetch(`${API_BASE}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refresh }),
          credentials: 'include',
        });
        if (rr.ok) {
          const d = await rr.json();
          localStorage.setItem('access_token', d.access_token);
          localStorage.setItem('refresh_token', d.refresh_token);
          document.cookie = `access_token=${d.access_token}; path=/; max-age=900; SameSite=Strict`;
          return apiCall(endpoint, options);
        }
      } catch (_) { /* fall through to redirect */ }
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/admin/login';
    throw new Error('Session expirée');
  }

  // Rate limit feedback
  if (response.status === 429) {
    const retryAfter = response.headers.get('Retry-After') || '60';
    showToast(`Trop de requêtes — réessayez dans ${retryAfter}s`, 'warning');
  }

  return response;
}

// Safe JSON parse that shows a toast on API errors
async function apiJSON(endpoint, options = {}) {
  try {
    const res = await apiCall(endpoint, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.detail || data.message || `Erreur ${res.status}`;
      showToast(typeof msg === 'string' ? msg : JSON.stringify(msg), 'error');
      return null;
    }
    return data;
  } catch (err) {
    if (err.message !== 'Session expirée') showToast('Erreur réseau', 'error');
    return null;
  }
}

function getCsrfToken() {
  const local = localStorage.getItem('csrf_token');
  if (local) return local;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}
