const listEl = document.getElementById('device-list');

async function loadDevices() {
  let devices;
  try {
    const res = await fetch('/api/devices');
    devices = await res.json();
  } catch {
    listEl.innerHTML = '<li class="empty">Could not reach server</li>';
    return;
  }

  if (devices.length === 0) {
    listEl.innerHTML = '<li class="empty">No devices seen yet -- plug one in over USB</li>';
    return;
  }

  listEl.innerHTML = '';
  for (const d of devices) {
    const li = document.createElement('li');
    li.className = d.connected ? 'connected' : 'disconnected';

    const a = document.createElement('a');
    a.href = `/d/${encodeURIComponent(d.serial)}/`;
    a.textContent = d.model;
    li.appendChild(a);

    const meta = document.createElement('span');
    meta.className = 'meta';
    const bits = [d.serial];
    if (!d.connected) bits.push('disconnected');
    if (d.viewers > 0) bits.push(`${d.viewers} viewer${d.viewers === 1 ? '' : 's'}`);
    meta.textContent = bits.join(' · ');
    li.appendChild(meta);

    listEl.appendChild(li);
  }
}

loadDevices();
setInterval(loadDevices, 3000);
