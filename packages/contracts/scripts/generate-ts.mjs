// Generates src/generated.ts from schema/contracts.schema.json (exported from Pydantic).
// Usage: node scripts/generate-ts.mjs [--check]
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { compile } from 'json-schema-to-typescript';

const root = fileURLToPath(new URL('..', import.meta.url));
const schemaPath = `${root}schema/contracts.schema.json`;
const outPath = `${root}src/generated.ts`;

const schema = JSON.parse(await readFile(schemaPath, 'utf8'));
const ts = await compile(schema, 'NazarContracts', {
  bannerComment:
    '/* eslint-disable */\n// GENERATED FILE - do not edit. Source: packages/contracts/python (Pydantic).\n// Regenerate with `pnpm contracts:generate`.',
  additionalProperties: false,
  unreachableDefinitions: true,
  style: { singleQuote: true, printWidth: 100 },
});

if (process.argv.includes('--check')) {
  const current = await readFile(outPath, 'utf8').catch(() => '');
  if (current !== ts) {
    console.error('src/generated.ts is out of date. Run `pnpm contracts:generate`.');
    process.exit(1);
  }
} else {
  await writeFile(outPath, ts);
}
