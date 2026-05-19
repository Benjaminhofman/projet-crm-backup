// ── Constantes inactivité ─────────────────────────────────────────────────────

const _INACTIVITY_LOGOUT_MS  = 60 * 60 * 1000; // 60 min
const _INACTIVITY_WARNING_MS = 55 * 60 * 1000; // 55 min

let _logoutTimer   = null;
let _warningTimer  = null;
let _countdownInvl = null;
let _warningBanner = null;

// ── Déconnexion ───────────────────────────────────────────────────────────────

function logout() {
    localStorage.removeItem('crm_token');
    window.location.replace('/login.html');
}

// ── Bannière d'avertissement inactivité ───────────────────────────────────────

function _showWarningBanner() {
    if (_warningBanner) return;

    _warningBanner = document.createElement('div');
    _warningBanner.id = 'inactivity-banner';
    _warningBanner.style.cssText = [
        'position:fixed',
        'bottom:0',
        'left:0',
        'right:0',
        'z-index:99999',
        'background:#e67e22',
        'color:white',
        'display:flex',
        'align-items:center',
        'justify-content:space-between',
        'padding:14px 24px',
        'font-family:Segoe UI,sans-serif',
        'font-size:14px',
        'font-weight:500',
        'box-shadow:0 -4px 16px rgba(0,0,0,0.25)',
        'animation:slideUp 0.3s ease',
    ].join(';');

    // Injection du keyframe slideUp si absent
    if (!document.getElementById('_inactivity-style')) {
        const style = document.createElement('style');
        style.id = '_inactivity-style';
        style.textContent = `
            @keyframes slideUp {
                from { transform: translateY(100%); opacity: 0; }
                to   { transform: translateY(0);    opacity: 1; }
            }
        `;
        document.head.appendChild(style);
    }

    const msg = document.createElement('span');
    msg.id = 'inactivity-msg';
    msg.textContent = '⚠️ Session expire dans 5:00 — Inactivité détectée';

    const btn = document.createElement('button');
    btn.textContent = 'Rester connecté';
    btn.style.cssText = [
        'background:white',
        'color:#e67e22',
        'border:none',
        'padding:8px 18px',
        'border-radius:6px',
        'cursor:pointer',
        'font-size:14px',
        'font-weight:700',
        'flex-shrink:0',
        'margin-left:20px',
        'transition:background 0.15s',
    ].join(';');
    btn.onmouseover = () => btn.style.background = '#fdebd0';
    btn.onmouseout  = () => btn.style.background = 'white';
    btn.onclick     = _resetInactivityTimers;

    _warningBanner.appendChild(msg);
    _warningBanner.appendChild(btn);
    document.body.appendChild(_warningBanner);

    // Décompte affiché dans le message (5:00 → 0:00)
    let secondsLeft = 5 * 60;
    _countdownInvl = setInterval(() => {
        secondsLeft--;
        if (secondsLeft <= 0) {
            clearInterval(_countdownInvl);
            return;
        }
        const m = Math.floor(secondsLeft / 60);
        const s = String(secondsLeft % 60).padStart(2, '0');
        msg.textContent = `⚠️ Session expire dans ${m}:${s} — Inactivité détectée`;
        if (secondsLeft <= 60 && _warningBanner) {
            _warningBanner.style.background = '#e74c3c';
            btn.style.color = '#e74c3c';
        }
    }, 1000);
}

function _hideWarningBanner() {
    clearInterval(_countdownInvl);
    _countdownInvl = null;
    if (_warningBanner) {
        _warningBanner.remove();
        _warningBanner = null;
    }
}

// ── Gestion du timer d'inactivité ─────────────────────────────────────────────

function _resetInactivityTimers() {
    clearTimeout(_logoutTimer);
    clearTimeout(_warningTimer);
    _hideWarningBanner();

    _warningTimer = setTimeout(_showWarningBanner, _INACTIVITY_WARNING_MS);
    _logoutTimer  = setTimeout(logout,             _INACTIVITY_LOGOUT_MS);
}

function _startInactivityWatch() {
    ['mousemove', 'keydown', 'click', 'scroll'].forEach(evt => {
        document.addEventListener(evt, _resetInactivityTimers, { passive: true });
    });
    _resetInactivityTimers();
}

// ── Injection bouton Déconnexion ───────────────────────────────────────────────

function injectLogoutButton() {
    if (document.getElementById('logout-btn')) return;

    const container =
        document.querySelector('.header > div') ||
        document.querySelector('.header')       ||
        document.querySelector('.top-bar');

    if (!container) return;

    const btn = document.createElement('button');
    btn.id          = 'logout-btn';
    btn.textContent = '🚪 Déconnexion';
    btn.onclick     = logout;
    btn.style.cssText = [
        'background:#e74c3c',
        'color:white',
        'border:none',
        'padding:8px 14px',
        'border-radius:6px',
        'cursor:pointer',
        'font-size:14px',
        'font-weight:600',
        'white-space:nowrap',
        'transition:background 0.2s',
        'flex-shrink:0',
    ].join(';');
    btn.onmouseover = () => btn.style.background = '#c0392b';
    btn.onmouseout  = () => btn.style.background = '#e74c3c';

    container.appendChild(btn);
}

// ── Vérification auth ─────────────────────────────────────────────────────────

async function checkAuth() {
    const token = localStorage.getItem('crm_token');
    if (!token) {
        window.location.replace('/login.html');
        return;
    }

    // Vérification locale : décode le payload JWT sans appel réseau
    try {
        const parts = token.split('.');
        if (parts.length === 3) {
            const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
            if (payload.exp && payload.exp > Date.now() / 1000 + 60) {
                injectLogoutButton();
                _startInactivityWatch();
                return;
            }
        }
    } catch {
        // Payload illisible ou expiré → on tombe sur le fetch /api/auth/verify
    }

    try {
        const res  = await fetch('/api/auth/verify', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        const data = await res.json();
        if (!data.valid) {
            localStorage.removeItem('crm_token');
            window.location.replace('/login.html');
        } else {
            injectLogoutButton();
            _startInactivityWatch();
        }
    } catch {
        // Erreur réseau transitoire — on ne redirige pas pour ne pas bloquer l'accès
    }
}
