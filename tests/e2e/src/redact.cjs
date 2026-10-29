'use strict';

const MAX_TEXT = 300;
const PATTERNS = [
  [/Bearer\s+[A-Za-z0-9._~+/-]+=*/gi, 'Bearer ***'],
  [/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, '***'],
  [/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, '<uuid>'],
];

/** Masks every registered secret (credentials, tokens, DEMO names, resource IDs) in output text. */
class Redactor {
  #secrets = new Set();

  add(value) {
    if (typeof value !== 'string' || value.length < 3) return;
    this.#secrets.add(value);
    const encoded = encodeURIComponent(value);
    if (encoded !== value) this.#secrets.add(encoded);
  }

  get size() {
    return this.#secrets.size;
  }

  mask(text) {
    let out = String(text ?? '');
    // Longest first so a secret containing another secret is fully replaced.
    for (const secret of [...this.#secrets].sort((a, b) => b.length - a.length)) {
      out = out.split(secret).join('***');
    }
    for (const [pattern, replacement] of PATTERNS) out = out.replace(pattern, replacement);
    return out.length > MAX_TEXT ? `${out.slice(0, MAX_TEXT)}…` : out;
  }

  maskDeep(value) {
    if (typeof value === 'string') return this.mask(value);
    if (Array.isArray(value)) return value.map((item) => this.maskDeep(item));
    if (value && typeof value === 'object') {
      return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, this.maskDeep(v)]));
    }
    return value;
  }

  toJSON() {
    return '[redactor]';
  }

  [Symbol.for('nodejs.util.inspect.custom')]() {
    return '[redactor]';
  }
}

module.exports = { Redactor };
