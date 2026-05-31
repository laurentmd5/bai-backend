// API client with CSRF protection and token refresh

const API_BASE = '/api/v1/admin';

async function apiCall(endpoint, options = {}) {
    let token = localStorage.getItem('access_token');
    
    // Ensure we have a CSRF token for write operations
    const method = options.method || 'GET';
    const isWrite = ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method);
    
    const headers = {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        ...options.headers
    };
    
    // Add CSRF token for write requests
    if (isWrite) {
        let csrfToken = getCsrfTokenFromCookie();
        if (!csrfToken) {
            // Try to fetch a new CSRF token
            const csrfRes = await fetch('/api/v1/admin/auth/csrf-token', { credentials: 'include' });
            if (csrfRes.ok) {
                const csrfData = await csrfRes.json();
                csrfToken = csrfData.csrf_token;
                document.cookie = `csrf_token=${csrfToken}; path=/; SameSite=Strict`;
            }
        }
        headers['X-CSRF-Token'] = csrfToken;
    }
    
    let response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
        credentials: 'include'
    });
    
    // If unauthorized, try to refresh token
    if (response.status === 401) {
        const refreshToken = localStorage.getItem('refresh_token');
        if (refreshToken) {
            const refreshRes = await fetch('/api/v1/admin/auth/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken })
            });
            if (refreshRes.ok) {
                const data = await refreshRes.json();
                localStorage.setItem('access_token', data.access_token);
                localStorage.setItem('refresh_token', data.refresh_token);
                document.cookie = `access_token=${data.access_token}; path=/; max-age=900; SameSite=Strict`;
                // Retry original request
                return apiCall(endpoint, options);
            } else {
                window.location.href = '/admin/login';
                throw new Error('Session expired');
            }
        } else {
            window.location.href = '/admin/login';
            throw new Error('No refresh token');
        }
    }
    
    return response;
}

function getCsrfTokenFromCookie() {
    const name = 'csrf_token=';
    const decodedCookie = decodeURIComponent(document.cookie);
    const ca = decodedCookie.split(';');
    for(let i = 0; i < ca.length; i++) {
        let c = ca[i];
        while (c.charAt(0) === ' ') c = c.substring(1);
        if (c.indexOf(name) === 0) return c.substring(name.length, c.length);
    }
    return null;
}
