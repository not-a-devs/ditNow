import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const expectedSkills = [
  'campus-ux-audit',
  'fullstack-implementation',
  'implementation-planner',
  'nav-doc-maintenance',
  'official-service-audit',
  'quality-release-gate',
  'rbac-privacy-review',
  'spec-gap-review',
];
const required = [
  'NAV.md', 'AGENTS.md', 'CLAUDE.md', 'README.md',
  'docs/00_START_HERE.md', 'docs/10_AI_RUNBOOK.md', 'docs/11_DECISION_LOG.md',
  'mvp/package.json', 'scripts/check-agent-config.mjs',
];
const errors = [];
const check = (condition, message) => { if (!condition) errors.push(message); };
const exists = (rel) => existsSync(join(root, rel));

for (const rel of required) check(exists(rel), `MISSING: ${rel}`);

for (const tool of ['.agents', '.claude']) {
  const dir = join(root, tool, 'skills');
  const names = existsSync(dir)
    ? readdirSync(dir, { withFileTypes: true }).filter((item) => item.isDirectory()).map((item) => item.name).sort()
    : [];
  check(names.join(',') === expectedSkills.join(','),
    `${tool} skill set differs: expected ${expectedSkills.join(', ')}, found ${names.join(', ')}`);
  for (const name of expectedSkills) {
    const rel = `${tool}/skills/${name}/SKILL.md`;
    check(exists(rel), `SKILL MISSING: ${rel}`);
    if (!exists(rel)) continue;
    const content = readFileSync(join(root, rel), 'utf8');
    const frontmatter = content.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
    check(Boolean(frontmatter), `SKILL FRONTMATTER MISSING: ${rel}`);
    if (frontmatter) {
      check(new RegExp(`^name:\\s*${name}\\s*$`, 'm').test(frontmatter[1]), `SKILL NAME INVALID: ${rel}`);
      check(/^description:\s*\S.+$/m.test(frontmatter[1]), `SKILL DESCRIPTION MISSING: ${rel}`);
    }
  }
}

for (const name of expectedSkills) {
  const codex = `.agents/skills/${name}/SKILL.md`;
  const claude = `.claude/skills/${name}/SKILL.md`;
  if (exists(codex) && exists(claude)) {
    check(readFileSync(join(root, codex)).equals(readFileSync(join(root, claude))), `SKILL DRIFT: ${name}`);
  }
}

if (exists('NAV.md')) {
  const nav = readFileSync(join(root, 'NAV.md'), 'utf8');
  // Section 3 mixes present and proposed paths; only its "current" lines describe files.
  const section3 = (nav.split(/^## 3\./m)[1] ?? '').split(/^## 4\./m)[0];
  const currentSection3 = section3.split('\n').filter((line) => /^- 현재 /.test(line)).join('\n');
  const currentSections = nav.split(/^## 3\./m)[0]
    + currentSection3
    + (nav.split(/^## 4\./m)[1] ?? '').split(/^## 6\./m)[0];
  const candidates = [...currentSections.matchAll(/`([^`\r\n]+)`/g)]
    .map((match) => match[1])
    .filter((value) => /^(?:README\.md|(?:docs|mvp|scripts|\.agents|\.claude)\/[^\s`]*)$/.test(value));
  for (const rel of new Set(candidates)) {
    check(exists(rel), `NAV PATH MISSING: ${rel}`);
    if (exists(rel) && rel.endsWith('/')) check(statSync(join(root, rel)).isDirectory(), `NAV PATH IS NOT DIRECTORY: ${rel}`);
  }
  console.log(`NAV current paths checked: ${new Set(candidates).size}`);
}

for (const error of errors) console.error(error);
console.log(`Agent config validation: ${errors.length ? 'FAIL' : 'PASS'} (${expectedSkills.length} mirrored skills)`);
if (errors.length) process.exitCode = 1;
