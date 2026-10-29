import fs from 'node:fs/promises';
import openapiTS, { astToString } from 'openapi-typescript';

const input = new URL('../../services/api/openapi.json', import.meta.url);
const output = new URL('../src/shared/api/schema.d.ts', import.meta.url);
// Read a local JSON object only; do not resolve a remote API or use authentication secrets.
const schema = JSON.parse(await fs.readFile(input, 'utf8'));
const generated = '// Generated from services/api/openapi.json. Do not edit.\n'
  + astToString(await openapiTS(schema));
if (process.argv.includes('--check')) {
  const committed = await fs.readFile(output, 'utf8').catch(() => '');
  if (committed.replaceAll('\r\n', '\n') !== generated.replaceAll('\r\n', '\n')) {
    throw new Error('API types are stale. Run npm run api:types.');
  }
  console.log('API types match the OpenAPI snapshot.');
} else {
  await fs.mkdir(new URL('.', output), { recursive: true });
  await fs.writeFile(output, generated);
}
