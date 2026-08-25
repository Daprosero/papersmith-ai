import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot='/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const {createJiti}=await import(pathToFileURL(path.join(piRoot,'node_modules/jiti/lib/jiti.mjs')).href);
const jiti=createJiti(import.meta.url,{alias:{'@earendil-works/pi-coding-agent':path.join(piRoot,'dist/index.js'),'@earendil-works/pi-ai/compat':path.join(piRoot,'node_modules/@earendil-works/pi-ai/dist/compat.js'),'@earendil-works/pi-ai':path.join(piRoot,'node_modules/@earendil-works/pi-ai/dist/index.js'),typebox:path.join(piRoot,'node_modules/typebox/build/index.mjs')}});
const v2=await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/exports.ts'));

const marker='<!-- proposal-workspace:artifact:v1 -->\n';
const document=Buffer.from(`${marker}# Proposal\n\nIntro.\n\n$$\nα = 1\n\\label{eq:alpha}\n$$\n\n## Results\n\nStable.\n`);

async function compilation(){
 const state=await v2.rebuildDerivedState('research-concept-r01.md','r01','ROOT',document);
 const entry=state.structuralIndex.entries.find(candidate=>candidate.type==='display_equation');
 const replacement='$$\nα = 2\n\\label{eq:alpha}\n$$';
 const plan={planVersion:'2',documentSha256:state.documentSha256,intent:'MODIFY',instructionHash:'representation-test',resolvedTargets:[entry.entryId],semanticChange:true,destructiveIntent:false,cleanupLevel:'NONE',constraints:[],actions:[{kind:'replace',targetEntryId:entry.entryId,replacementText:replacement,semanticChange:true}],expectedEffects:[],unresolvedQuestions:[]};
 return {state,entry,compiled:v2.compilePatches(state,plan)};
}

test('V2 selectors, offsets, oldText, and hashes share the marker-inclusive document bytes',async()=>{
 const {state,compiled}=await compilation();
 const patch=compiled.patches[0];
 assert.equal(state.documentBytes.subarray(0,Buffer.byteLength(marker)).toString(),marker);
 assert.equal(state.documentSha256,v2.sha256(state.documentBytes));
 assert.equal(patch.selector.documentSha256,state.documentSha256);
 assert.deepEqual(state.documentBytes.subarray(patch.selector.startByte,patch.selector.endByte),Buffer.from(patch.oldText));
 assert.equal(patch.selector.textSha256,v2.sha256(Buffer.from(patch.oldText)));
 assert.equal(patch.selector.startByte,state.documentBytes.indexOf(Buffer.from('$$\nα = 1')));
 assert.equal(compiled.candidateSha256,v2.sha256(Buffer.from(compiled.candidate)));
 assert.equal(patch.id,'patch-1');
});

test('ProposalWorkspaceAdapter transports CompiledPatch objects without transforming any field',async()=>{
 const {state,compiled}=await compilation();
 const insertion={id:'patch-2',kind:'insert',anchor:'## Results\n\nStable.\n',position:'after',content:'\n\nAdded.\n'};
 const patches=[compiled.patches[0],insertion];
 let transported;
 const guard={execute:async input=>input.action==='authorize_mutation'?{decision:'allowed',authorization:'test-authorization'}:{decision:'allowed'}};
 const workspace={execute:async(_id,input)=>{if(input.action==='derive_successor'){transported=input.patches;throw new Error('CAPTURE_COMPLETE')}throw new Error('UNEXPECTED_WORKSPACE_CALL')}};
 const adapter=new v2.ProposalWorkspaceAdapter('/tmp',guard,workspace,()=> 'representation-adapter');
 const profile=v2.resolveEffectiveOperationProfile({intent:'MOVE',cleanupLevel:'NONE'});
 await assert.rejects(adapter.publishSuccessor({intent:'MOVE',cleanupLevel:'NONE',effectiveOperationProfile:profile,sourceFilename:'research-concept-r01.md',sourceSha256:state.documentSha256,patches,modelCalls:0,plannerCalls:0,roleAuthorizations:0,validationResults:{}}),/CAPTURE_COMPLETE/);
 assert.strictEqual(transported,patches);
 assert.strictEqual(transported[0],compiled.patches[0]);
 assert.strictEqual(transported[1],insertion);
 assert.deepEqual(transported,patches);
});
