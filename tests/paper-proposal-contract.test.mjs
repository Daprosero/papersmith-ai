import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
const extension=await readFile(path.resolve('.pi/extensions/proposal-workspace.ts'),'utf8');
test('registers exactly one V2 proposal editing orchestrator',()=>{assert.match(extension,/PaperProposalV2Orchestrator/);assert.equal((extension.match(/new PaperProposalV2Orchestrator/g)??[]).length,1);});
test('production extension has no V1 mechanical editing route',()=>{for(const term of ['FAST_PATCH','CHANGE_PLAN','paperProposalInputHandler','parsePaperProposalExactReplacementInput'])assert.equal(extension.includes(term),false,term);});
test('keeps one successor implementation',()=>assert.equal((extension.match(/async function deriveSuccessorProposal/g)??[]).length,1));
