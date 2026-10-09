// Must come first: fills in crypto.subtle (AES only) on plain-http pages,
// before noVNC needs it for the macOS login.
import '/static/subtle_aes_fallback.js';
import RFB from '/static/vendor/novnc/core/rfb.js';

const statusEl = document.getElementById('status');
const screenEl = document.getElementById('vnc-screen');
const cadBtn = document.getElementById('cad-btn');
const reconnectBtn = document.getElementById('reconnect-btn');
const loginForm = document.getElementById('vnc-login');
const loginTitle = document.getElementById('vnc-login-title');
const usernameInput = document.getElementById('vnc-username');
const passwordInput = document.getElementById('vnc-password');

// URL is /vnc/<name>/ -- the relay sits right next to it at /vnc/<name>/ws.
const name = decodeURIComponent(location.pathname.split('/')[2]);
const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/vnc/${encodeURIComponent(name)}/ws`;

let rfb = null;

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.style.color = isError ? '#e88' : '';
}

function connect() {
  reconnectBtn.hidden = true;
  setStatus(`Connecting to ${name}...`);

  rfb = new RFB(screenEl, wsUrl, { shared: true });
  rfb.scaleViewport = true;
  rfb.background = '#111';

  rfb.addEventListener('connect', () => {
    loginForm.hidden = true;
    cadBtn.disabled = false;
    setStatus(name);
    rfb.focus();
  });

  rfb.addEventListener('desktopname', (e) => {
    document.title = `Entangle - ${e.detail.name}`;
    setStatus(e.detail.name);
  });

  rfb.addEventListener('credentialsrequired', (e) => {
    const types = e.detail.types;
    usernameInput.hidden = !types.includes('username');
    loginTitle.textContent = `Sign in to ${name}`;
    loginForm.hidden = false;
    setStatus('Waiting for credentials...');
    (usernameInput.hidden ? passwordInput : usernameInput).focus();
  });

  rfb.addEventListener('securityfailure', (e) => {
    const reason = e.detail.reason ? `: ${e.detail.reason}` : '';
    setStatus(`Authentication failed${reason}`, true);
  });

  rfb.addEventListener('disconnect', (e) => {
    cadBtn.disabled = true;
    loginForm.hidden = true;
    reconnectBtn.hidden = false;
    // A securityfailure or showFatal() already set a more specific message.
    if (!/^(Authentication failed|Error:)/.test(statusEl.textContent)) {
      setStatus(e.detail.clean ? 'Disconnected' : `Can't reach VNC server on ${name}`, true);
    }
    rfb = null;
  });
}

loginForm.addEventListener('submit', (e) => {
  e.preventDefault();
  if (!rfb) return;
  const creds = { password: passwordInput.value };
  if (!usernameInput.hidden) creds.username = usernameInput.value;
  passwordInput.value = '';
  loginForm.hidden = true;
  setStatus('Authenticating...');
  rfb.sendCredentials(creds);
});

cadBtn.addEventListener('click', () => {
  if (rfb) {
    rfb.sendCtrlAltDel();
    rfb.focus();
  }
});

reconnectBtn.addEventListener('click', connect);

// noVNC's async auth steps don't route failures to a 'disconnect' event,
// so without this a crash there just leaves the page on "Authenticating...".
function showFatal(err) {
  const message = (err && err.message) || String(err);
  setStatus(`Error: ${message}`, true);
  reconnectBtn.hidden = false;
  if (rfb) {
    try { rfb.disconnect(); } catch { /* already torn down */ }
  }
}
window.addEventListener('unhandledrejection', (e) => showFatal(e.reason));
window.addEventListener('error', (e) => showFatal(e.error || e.message));

connect();
