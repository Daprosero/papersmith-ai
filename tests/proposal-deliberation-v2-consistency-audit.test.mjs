import assert from 'node:assert/strict'; import path from 'node:path'; import test from 'node:test'; import { pathToFileURL } from 'node:url';
const {createJiti}=await import('jiti'); const jiti=createJiti(import.meta.url);
test('Jiti loads consistency audit module',async()=>{const audit=await jiti.import(path.resolve('skills/_core/deliberation/engine/consistency-audit.ts'));assert.equal(typeof audit.runConsistencyAudit,'function');});
