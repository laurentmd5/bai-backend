// ── Formatting ──────────────────────────────────────────────────
function formatDate(isoString) {
  if (!isoString) return '—';
  return new Date(isoString).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

function formatDateShort(isoString) {
  if (!isoString) return '—';
  return new Date(isoString).toLocaleDateString('fr-FR', {
    day: '2-digit', month: 'short', year: 'numeric'
  });
}

function escapeHtml(str) {
  if (str == null) return '—';
  return String(str).replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}

// ── Toasts ───────────────────────────────────────────────────────
function showToast(message, type = 'success', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const icons = { success: 'fa-check-circle', error: 'fa-exclamation-circle', warning: 'fa-exclamation-triangle', info: 'fa-info-circle' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 200);
  }, duration);
}

// legacy alias
function showNotification(message, type = 'success') { showToast(message, type); }

// ── Pagination ───────────────────────────────────────────────────
/**
 * Renders a professional pagination component.
 * @param {HTMLElement} container
 * @param {number} total  - total records
 * @param {number} page   - current page (0-based)
 * @param {number} limit  - records per page
 * @param {Function} onPage - callback(page)
 */
function renderPagination(container, total, page, limit, onPage) {
  if (!container) return;
  const totalPages = Math.ceil(total / limit);
  if (totalPages <= 1) { container.innerHTML = ''; return; }

  const from = page * limit + 1;
  const to   = Math.min((page + 1) * limit, total);

  function pageBtn(label, targetPage, disabled = false, active = false, ellipsis = false) {
    const cls = ['page-btn', active ? 'active' : '', disabled ? '' : '', ellipsis ? 'ellipsis' : ''].filter(Boolean).join(' ');
    const dis  = disabled || ellipsis ? 'disabled' : '';
    return `<button class="${cls}" ${dis} data-page="${targetPage}">${label}</button>`;
  }

  function pageRange(current, total) {
    if (total <= 7) return Array.from({length: total}, (_, i) => i);
    const pages = [];
    if (current <= 3) {
      pages.push(0,1,2,3,4,'…',total-1);
    } else if (current >= total - 4) {
      pages.push(0,'…',total-5,total-4,total-3,total-2,total-1);
    } else {
      pages.push(0,'…',current-1,current,current+1,'…',total-1);
    }
    return pages;
  }

  let html = `<div class="pagination-wrap">
    <div class="pagination-info">Affichage ${from}–${to} sur <strong>${total}</strong></div>
    <div class="pagination-controls">
      ${pageBtn('<i class="fas fa-chevron-left"></i>', page-1, page === 0)}`;

  pageRange(page, totalPages).forEach(p => {
    if (p === '…') {
      html += pageBtn('…', -1, true, false, true);
    } else {
      html += pageBtn(p+1, p, false, p === page);
    }
  });

  html += `${pageBtn('<i class="fas fa-chevron-right"></i>', page+1, page >= totalPages-1)}
    </div>
  </div>`;

  container.innerHTML = html;
  container.querySelectorAll('.page-btn:not([disabled])').forEach(btn => {
    btn.addEventListener('click', () => {
      const p = parseInt(btn.dataset.page);
      if (!isNaN(p) && p >= 0) onPage(p);
    });
  });
}

// ── Skeleton loader ──────────────────────────────────────────────
function skeletonRows(cols, rows = 5) {
  return Array.from({length: rows}, () =>
    `<tr>${Array.from({length: cols}, () =>
      `<td><span class="skeleton" style="width:${60+Math.random()*30}%">&nbsp;</span></td>`
    ).join('')}</tr>`
  ).join('');
}

// ── Debounce ─────────────────────────────────────────────────────
function debounce(fn, delay = 350) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}

// ── Misc helpers ─────────────────────────────────────────────────
function getQueryParam(param) {
  return new URLSearchParams(window.location.search).get(param);
}

function setLoading(button, isLoading, originalText) {
  button.disabled = isLoading;
  button.innerHTML = isLoading
    ? '<i class="fas fa-spinner fa-spin"></i> Chargement…'
    : originalText;
}

function confirmDanger(message) {
  return window.confirm(message);
}
