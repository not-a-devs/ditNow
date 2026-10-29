import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
function csv(path) {
  const input = readFileSync(resolve(root, path), 'utf8').replace(/^\uFEFF/, '');
  const rows = []; let row = []; let cell = ''; let quoted = false;
  for (let i = 0; i < input.length; i++) {
    const c = input[i];
    if (c === '"') {
      if (quoted && input[i + 1] === '"') { cell += '"'; i++; }
      else quoted = !quoted;
    } else if (!quoted && (c === ',' || c === '\n')) {
      row.push(cell.replace(/\r$/, '')); cell = '';
      if (c === '\n') { if (row.some(Boolean)) rows.push(row); row = []; }
    } else cell += c;
  }
  if (quoted) throw new Error(`Unclosed CSV quote: ${path}`);
  if (cell || row.length) { row.push(cell.replace(/\r$/, '')); rows.push(row); }
  const [header, ...body] = rows;
  return body.map((values, index) => {
    if (values.length !== header.length) throw new Error(`CSV columns ${path}:${index + 2}`);
    return Object.fromEntries(header.map((name, i) => [name, values[i]]));
  });
}
const trace = csv('docs/v1-draft/09_FEATURE_TRACEABILITY.csv');
const progress = csv('docs/dev-prep/06_FEATURE_IMPLEMENTATION_STATUS.csv');
const errors = []; const require = (ok, why) => { if (!ok) errors.push(why); };
const ids = new Set(trace.map((r) => r.feature_id));
require(trace.length === 92 && ids.size === 92, 'Baseline must contain 92 unique FR IDs');
require(progress.length === 92 && new Set(progress.map((r) => r.feature_id)).size === 92,
  'Progress must contain 92 unique FR IDs');
const states = new Set(['NOT_IMPLEMENTED', 'PARTIAL', 'BLOCKED', 'IMPLEMENTED']);
const layers = new Set(['NOT_RUN', 'PARTIAL', 'IMPLEMENTED', 'TESTED', 'VERIFIED', 'N_A']);
for (const r of progress) {
  const id = r.feature_id;
  require(ids.has(id), `Unknown ID ${id}`);
  require(states.has(r.status), `Invalid status ${id}`);
  require(['P0', 'P1', 'P2'].includes(r.priority), `Priority missing ${id}`);
  require(['A', 'B', 'C', 'D', 'E', 'F'].includes(r.owner_area), `Owner missing ${id}`);
  for (const key of ['frontend', 'fastapi', 'mariadb', 'tests'])
    require(layers.has(r[key]), `Invalid ${key} ${id}`);
  for (const key of ['documentation', 'evidence', 'blocker', 'next_task', 'checked_date'])
    require(Boolean(r[key]), `Missing ${key} ${id}`);
  require(r.documentation === 'DOCUMENTED', `Documentation state ${id}`);
  require(!r.evidence.split(';').some((v) => /^mvp[\\/]/.test(v)), `Legacy code cannot prove ${id}`);
  if (r.status === 'IMPLEMENTED') {
    require(['IMPLEMENTED', 'TESTED', 'VERIFIED', 'N_A'].includes(r.frontend), `No frontend ${id}`);
    require(['IMPLEMENTED', 'TESTED', 'VERIFIED'].includes(r.fastapi), `No backend ${id}`);
    require(['IMPLEMENTED', 'TESTED', 'VERIFIED', 'N_A'].includes(r.mariadb), `No persistence ${id}`);
  }
  for (const layer of ['frontend', 'fastapi', 'mariadb', 'tests']) {
    if (r[layer] === 'VERIFIED') require(/(?:https:\/\/github\.com\/[^; ]+\/actions\/runs\/\d+|[0-9a-f]{40})/.test(r.evidence), `No run/HEAD evidence ${id}:${layer}`);
    if (r[layer] === 'N_A') require(r.evidence.includes(`N_A:${layer}=`), `No N_A reason ${id}:${layer}`);
  }
  const source = trace.find((t) => t.feature_id === id);
  require(Boolean(source?.test_id && source?.test_scenario_acceptance && source?.db_tables && source?.rbac_rule),
    `Trace missing TC/AC/DB/RBAC ${id}`);
}
for (const id of ids) require(progress.some((r) => r.feature_id === id), `Missing ${id}`);
for (const path of ['docs/dev-prep/05_PARALLEL_IMPLEMENTATION_BOARD.md', 'docs/11_DECISION_LOG.md'])
  require(existsSync(resolve(root, path)), `Missing ${path}`);
const counts = Object.fromEntries([...states].map((s) => [s, progress.filter((r) => r.status === s).length]));
console.log(JSON.stringify({ baseline: trace.length, progress: progress.length, counts, errors }, null, 2));
if (errors.length) process.exitCode = 1;
