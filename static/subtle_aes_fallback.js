// Browsers only expose crypto.subtle in secure contexts (HTTPS or
// localhost), but Entangle is normally opened as http://<lan-ip>:<port>/.
// noVNC needs AES for macOS Screen Sharing's login (Apple's ARD auth,
// security type 30), so without this it crashes right after the
// credentials are submitted. When crypto.subtle is missing, this installs
// a minimal stand-in covering exactly what that path uses: importKey +
// encrypt for raw AES-CBC keys (noVNC builds AES-ECB out of AES-CBC with a
// zero IV). Everything else stays missing, as before.
//
// Must be imported before noVNC (see vnc.js).

const SBOX = new Uint8Array(256);
(function buildSbox() {
  // Walk the multiplicative group of GF(2^8) with generator 3, keeping
  // p = 3^i and q = 3^-i in step, then apply the AES affine transform.
  let p = 1, q = 1;
  do {
    p = p ^ ((p << 1) & 0xff) ^ (p & 0x80 ? 0x1b : 0);
    q ^= q << 1;
    q ^= q << 2;
    q ^= q << 4;
    q &= 0xff;
    if (q & 0x80) q ^= 0x09;
    const rotl = (x, s) => ((x << s) | (x >> (8 - s))) & 0xff;
    SBOX[p] = q ^ rotl(q, 1) ^ rotl(q, 2) ^ rotl(q, 3) ^ rotl(q, 4) ^ 0x63;
  } while (p !== 1);
  SBOX[0] = 0x63;
})();

const xtime = (b) => ((b << 1) ^ (b & 0x80 ? 0x1b : 0)) & 0xff;

function expandKey(key) {
  const nk = key.length / 4;
  const rounds = nk + 6;
  const w = new Uint8Array(16 * (rounds + 1));
  w.set(key);
  let rcon = 1;
  for (let i = nk; i < 4 * (rounds + 1); i++) {
    let t = w.slice(4 * (i - 1), 4 * i);
    if (i % nk === 0) {
      t = new Uint8Array([SBOX[t[1]] ^ rcon, SBOX[t[2]], SBOX[t[3]], SBOX[t[0]]]);
      rcon = xtime(rcon);
    } else if (nk > 6 && i % nk === 4) {
      t = t.map((b) => SBOX[b]);
    }
    for (let j = 0; j < 4; j++) w[4 * i + j] = w[4 * (i - nk) + j] ^ t[j];
  }
  return { w, rounds };
}

function encryptBlock({ w, rounds }, input) {
  const s = new Uint8Array(16);
  for (let i = 0; i < 16; i++) s[i] = input[i] ^ w[i];
  for (let r = 1; r <= rounds; r++) {
    // SubBytes + ShiftRows (state is column-major: s[col * 4 + row]).
    const t = new Uint8Array(16);
    for (let c = 0; c < 4; c++) {
      for (let row = 0; row < 4; row++) t[c * 4 + row] = SBOX[s[((c + row) % 4) * 4 + row]];
    }
    if (r !== rounds) {
      // MixColumns
      for (let c = 0; c < 4; c++) {
        const [a0, a1, a2, a3] = t.subarray(c * 4, c * 4 + 4);
        const all = a0 ^ a1 ^ a2 ^ a3;
        t[c * 4] = a0 ^ all ^ xtime(a0 ^ a1);
        t[c * 4 + 1] = a1 ^ all ^ xtime(a1 ^ a2);
        t[c * 4 + 2] = a2 ^ all ^ xtime(a2 ^ a3);
        t[c * 4 + 3] = a3 ^ all ^ xtime(a3 ^ a0);
      }
    }
    for (let i = 0; i < 16; i++) s[i] = t[i] ^ w[16 * r + i];
  }
  return s;
}

const toBytes = (data) =>
  data instanceof ArrayBuffer ? new Uint8Array(data) : new Uint8Array(data.buffer, data.byteOffset, data.byteLength);

const fallbackSubtle = {
  async importKey(format, keyData, algorithm, extractable, usages) {
    const name = typeof algorithm === 'string' ? algorithm : algorithm.name;
    const key = toBytes(keyData).slice();
    if (format !== 'raw' || name !== 'AES-CBC' || ![16, 24, 32].includes(key.length)) {
      throw new DOMException(`crypto.subtle fallback only supports raw AES-CBC keys`, 'NotSupportedError');
    }
    return { type: 'secret', extractable, usages, algorithm: { name, length: key.length * 8 }, _schedule: expandKey(key) };
  },

  // AES-CBC with PKCS#7 padding, matching WebCrypto's output.
  async encrypt(algorithm, key, data) {
    if (algorithm.name !== 'AES-CBC' || !key || !key._schedule) {
      throw new DOMException(`crypto.subtle fallback only supports AES-CBC`, 'NotSupportedError');
    }
    const plain = toBytes(data);
    const pad = 16 - (plain.length % 16);
    const padded = new Uint8Array(plain.length + pad);
    padded.set(plain);
    padded.fill(pad, plain.length);

    let prev = toBytes(algorithm.iv);
    if (prev.length !== 16) throw new DOMException('AES-CBC iv must be 16 bytes', 'OperationError');
    const out = new Uint8Array(padded.length);
    for (let off = 0; off < padded.length; off += 16) {
      const block = padded.slice(off, off + 16);
      for (let i = 0; i < 16; i++) block[i] ^= prev[i];
      prev = encryptBlock(key._schedule, block);
      out.set(prev, off);
    }
    return out.buffer;
  },
};

if (globalThis.crypto && !globalThis.crypto.subtle) {
  Object.defineProperty(globalThis.crypto, 'subtle', { value: fallbackSubtle, configurable: true });
}

export { fallbackSubtle };
