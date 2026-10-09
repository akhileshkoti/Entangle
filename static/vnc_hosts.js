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
