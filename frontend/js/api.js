/**
 * SnapEvent — Shared API helpers
 * All fetch calls go through these wrappers.
 */

const API = {
  async request(method, path, body = null, isFormData = false) {
    const opts = {
      method,
      credentials: 'include',
      headers: {},
    };
    if (body) {
      if (isFormData) {
        opts.body = body; // FormData — browser sets Content-Type
      } else {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
    }
    const res = await fetch(path, opts);
    if (res.status === 401) {
      window.location.href = '/login.html';
      return;
    }
    if (!res.ok) {
      const text = await res.text();
      let msg;
      try { msg = JSON.parse(text).detail || text; } catch { msg = text; }
      throw new Error(msg);
    }
    if (res.status === 204) return null;
    const ct = res.headers.get('content-type') || '';
    return ct.includes('application/json') ? res.json() : res.text();
  },

  get:    (path)          => API.request('GET', path),
  post:   (path, body)    => API.request('POST', path, body),
  del:    (path)          => API.request('DELETE', path),
  upload: (path, formData)=> API.request('POST', path, formData, true),
};

/* ── Participant API (uses X-Participant-Code header) ──────────────────── */
const ParticipantAPI = {
  _code: null,

  setCode(code) { this._code = code; },

  async request(method, path, body = null, isFormData = false) {
    const opts = {
      method,
      credentials: 'include',
      headers: {},
    };
    if (this._code) opts.headers['X-Participant-Code'] = this._code;
    if (body) {
      if (isFormData) {
        opts.body = body;
      } else {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
    }
    const res = await fetch(path, opts);
    if (!res.ok) {
      const text = await res.text();
      let msg;
      try { msg = JSON.parse(text).detail || text; } catch { msg = text; }
      throw new Error(msg);
    }
    if (res.status === 204) return null;
    return res.json();
  },

  get:    (path)           => ParticipantAPI.request('GET', path),
  post:   (path, body)     => ParticipantAPI.request('POST', path, body),
  del:    (path)           => ParticipantAPI.request('DELETE', path),
  upload: (path, formData) => ParticipantAPI.request('POST', path, formData, true),
};

/* ── UI helpers ──────────────────────────────────────────────────────────── */

function showAlert(el, message, type = 'error') {
  el.className = `alert alert--${type} show`;
  el.textContent = message;
}

function hideAlert(el) {
  el.className = 'alert';
}

function permissionBadge(permission) {
  const map = {
    VIEW_ONLY:          ['view', 'View Only'],
    VIEW_UPLOAD:        ['upload', 'View & Upload'],
    VIEW_UPLOAD_DELETE: ['full', 'Full Access'],
  };
  const [cls, label] = map[permission] || ['view', permission];
  return `<span class="badge badge--${cls}">${label}</span>`;
}

function statusBadge(status) {
  const cls = status.toLowerCase();
  return `<span class="badge badge--${cls}">${status}</span>`;
}

function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  });
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (typeof child === 'string') node.appendChild(document.createTextNode(child));
    else if (child) node.appendChild(child);
  }
  return node;
}
