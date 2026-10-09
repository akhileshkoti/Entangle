// Must come first: fills in crypto.subtle (AES only) on plain-http pages,
// before noVNC needs it for the macOS login.
import '/static/subtle_aes_fallback.js';
import RFB from '/static/vendor/novnc/core/rfb.js';
import { PENDING_CREDENTIALS_KEY } from '/static/vnc_shared.js';

const statusEl = document.getElementById('status');
const screenEl = document.getElementById('vnc-screen');
const cadBtn = document.getElementById('cad-btn');
const reconnectBtn = document.getElementById('reconnect-btn');
const loginForm = document.getElementById('vnc-login');
const loginTitle = document.getElementById('vnc-login-title');
const usernameInput = document.getElementById('vnc-username');
const passwordInput = document.getElementById('vnc-password');

// Two URL shapes:
//   /vnc/<name>/          a host from vnc_hosts.json; relay at /vnc/<name>/ws
//   /vnc/?host=<ip>&port= any VNC server (devices page's "Open remote
//                         device"); relay at /vnc/ws?host=...&port=...
// Either can add ?devicename=... to label the page (else the configured name
// or the host), and ?username=...&password=... to sign in automatically.
const params = new URLSearchParams(location.search);
const pathName = decodeURIComponent(location.pathname.split('/')[2] || '');
const wsBase = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`;
let wsUrl;
if (pathName) {
  wsUrl = `${wsBase}/vnc/${encodeURIComponent(pathName)}/ws`;
} else {
  const target = new URLSearchParams({ host: params.get('host') || '' });
  if (params.get('port')) target.set('port', params.get('port'));
  wsUrl = `${wsBase}/vnc/ws?${target}`;
}
const deviceName = params.get('devicename');
const name = deviceName || pathName || params.get('host');
document.title = `Entangle - ${name}`;

let rfb = null;

// Credentials, if given, come from the URL (username only matters for
// macOS) or, from the devices page's form, via sessionStorage -- which keeps
// them out of browser history. URL ones are taken out of the address bar
// right away so they aren't left on screen or in a bookmark; the browser's
// history still records the URL as it was opened, though.
let urlCredentials = null;
try {
  const handedOver = sessionStorage.getItem(PENDING_CREDENTIALS_KEY);
  if (handedOver) {
    sessionStorage.removeItem(PENDING_CREDENTIALS_KEY);
    urlCredentials = JSON.parse(handedOver);
  }
} catch { /* storage blocked: fall back to the form */ }
if (params.has('username') || params.has('password')) {
  urlCredentials = urlCredentials || {};
  if (params.has('username')) urlCredentials.username = params.get('username');
  if (params.has('password')) urlCredentials.password = params.get('password');
  params.delete('username');
  params.delete('password');
  const query = params.toString();
  history.replaceState(null, '', location.pathname + (query ? `?${query}` : '') + location.hash);
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.style.color = isError ? '#e88' : '';
}

function connect() {
  reconnectBtn.hidden = true;
  setStatus(`Connecting to ${name}...`);

  rfb = new RFB(screenEl, wsUrl, { shared: true, credentials: urlCredentials || {} });
  rfb.scaleViewport = true;
  rfb.background = '#111';

  rfb.addEventListener('connect', () => {
    loginForm.hidden = true;
    cadBtn.disabled = false;
    setStatus(name);
    rfb.focus();
  });

  rfb.addEventListener('desktopname', (e) => {
    if (deviceName) return;  // explicitly named: keep that
    document.title = `Entangle - ${e.detail.name}`;
    setStatus(e.detail.name);
  });

  rfb.addEventListener('credentialsrequired', (e) => {
    const types = e.detail.types;
    usernameInput.hidden = !types.includes('username');
    // URL gave only some of what's needed (e.g. password without username).
    if (urlCredentials && urlCredentials.username && !usernameInput.value) {
      usernameInput.value = urlCredentials.username;
    }
    loginTitle.textContent = `Sign in to ${name}`;
    loginForm.hidden = false;
    setStatus('Waiting for credentials...');
    (usernameInput.hidden ? passwordInput : usernameInput).focus();
  });

  rfb.addEventListener('securityfailure', (e) => {
    // Wrong URL credentials: don't retry them on Reconnect, ask instead.
    urlCredentials = null;
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
