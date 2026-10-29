import { readFile, writeFile, mkdir } from 'node:fs/promises';
import openapiTS, { astToString } from 'openapi-typescript';

const snapshot = new URL('../../../services/api/openapi.json', import.meta.url);
const destination = new URL('../src/lib/generated/api.d.ts', import.meta.url);
const document = JSON.parse(await readFile(snapshot, 'utf8'));
const result = '// Generated from services/api/openapi.json. Do not edit.\n' + astToString(await openapiTS(document));
if (process.argv.includes('--check')) {
  const existing = await readFile(destination, 'utf8').catch(() => '');
  if (existing.replaceAll('\r\n', '\n') !== result.replaceAll('\r\n', '\n')) throw new Error('OpenAPI types are stale. Run npm run api:types.');
  console.log('New web API types match the public server snapshot.');
} else {
  await mkdir(new URL('.', destination), { recursive: true });
  await writeFile(destination, result);
}
