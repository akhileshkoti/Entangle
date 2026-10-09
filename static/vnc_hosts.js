import { PENDING_CREDENTIALS_KEY } from '/static/vnc_shared.js';

const vncListEl = document.getElementById('vnc-list');

async function loadVncHosts() {
  let hosts;
  try {
    const res = await fetch('/api/vnc');
    hosts = await res.json();
  } catch {
    vncListEl.innerHTML = '<li class="empty">Could not reach server</li>';
    return;
  }

  if (hosts.length === 0) {
    vncListEl.innerHTML = '<li class="empty">None configured -- add them to vnc_hosts.json (see vnc_hosts.example.json)</li>';
    return;
  }

  vncListEl.innerHTML = '';
  for (const h of hosts) {
    const li = document.createElement('li');
    li.className = h.reachable ? 'connected' : 'disconnected';

    const a = document.createElement('a');
    a.href = `/vnc/${encodeURIComponent(h.name)}/`;
    a.textContent = h.name;
    li.appendChild(a);

    const meta = document.createElement('span');
    meta.className = 'meta';
    const bits = [`${h.host}:${h.port}`];
    if (!h.reachable) bits.push('unreachable');
    if (h.viewers > 0) bits.push(`${h.viewers} viewer${h.viewers === 1 ? '' : 's'}`);
    meta.textContent = bits.join(' · ');
    li.appendChild(meta);

    vncListEl.appendChild(li);
  }
}

loadVncHosts();
setInterval(loadVncHosts, 3000);

// "Open remote device": any VNC server by IP, not just vnc_hosts.json.
// Host/port/name go in the viewer URL (so a reload or bookmark still
// works); credentials go through sessionStorage, to stay out of the URL
// and browser history.
const dialog = document.getElementById('open-remote-dialog');
const form = document.getElementById('open-remote-form');

document.getElementById('open-remote-btn').addEventListener('click', () => {
  dialog.showModal();
  form.elements.host.focus();
});
document.getElementById('open-remote-cancel').addEventListener('click', () => dialog.close());

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const f = form.elements;
  const query = new URLSearchParams({ host: f.host.value.trim() });
  if (f.port.value && f.port.value !== '5900') query.set('port', f.port.value);
  if (f.devicename.value.trim()) query.set('devicename', f.devicename.value.trim());

  const credentials = {};
  if (f.username.value) credentials.username = f.username.value;
  if (f.password.value) credentials.password = f.password.value;
  if (Object.keys(credentials).length) {
    try {
      sessionStorage.setItem(PENDING_CREDENTIALS_KEY, JSON.stringify(credentials));
    } catch { /* storage blocked: the viewer will ask instead */ }
  }
  f.password.value = '';
  location.href = `/vnc/?${query}`;
});
