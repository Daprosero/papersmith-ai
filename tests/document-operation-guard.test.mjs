import assert from 'node:assert/strict'; import test from 'node:test'; import { readFile } from 'node:fs/promises';
const source=await readFile('.pi/extensions/proposal-workspace.ts','utf8');
test('V2 guard exposes only semantic document operations',()=>{for(const operation of ['MODIFY','INSERT','DELETE','MOVE','CONCEPTUAL_REVISION','REVIEW','DELIBERATE','AMBIGUOUS'])assert.match(source,new RegExp(`['\"]${operation}['\"]`));assert.doesNotMatch(source,/FAST_PATCH/);});
