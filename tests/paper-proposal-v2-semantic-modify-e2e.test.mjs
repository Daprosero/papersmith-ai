import assert from 'node:assert/strict'; import { createHash } from 'node:crypto'; import { copyFile,mkdtemp,mkdir,readFile } from 'node:fs/promises'; import os from 'node:os'; import path from 'node:path'; import test from 'node:test'; import { pathToFileURL } from 'node:url';
const piRoot='/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent'; const {createJiti}=await import(pathToFileURL(path.join(piRoot,'node_modules/jiti/lib/jiti.mjs')).href); const jiti=createJiti(import.meta.url,{alias:{'@earendil-works/pi-coding-agent':path.join(piRoot,'dist/index.js'),'@earendil-works/pi-ai/compat':path.join(piRoot,'node_modules/@earendil-works/pi-ai/dist/compat.js'),'@earendil-works/pi-ai':path.join(piRoot,'node_modules/@earendil-works/pi-ai/dist/index.js'),typebox:path.join(piRoot,'node_modules/typebox/build/index.mjs')}}); const workspaceModule=await jiti.import(path.resolve('.claude/skills/paper-proposal/engine/proposal-workspace.ts')); const v2=await jiti.import(path.resolve('.claude/skills/paper-proposal/engine/exports.ts'));
const realHashes={base:'525d957c24e05b9eb7acdde5d473657639e132831ad116e83539093adb224560',r01:'bec1edd3cfde073efde4d0053bd8e4375e4af51021ad02b422bf36ea9c1fa55c'};
const oneHot=`# Representative Proposal\n\n## Labels\n\nThe one-hot encoding assigns every class label a dense binary vector.\n\n$$\n\\mathbf y = (y_1, \\ldots, y_C), \\qquad y_c \\in \\{0,1\\}, \\quad \\sum_{c=1}^{C} y_c=1.\n\\label{eq:onehot}\n\\tag{1}\n$$\n\nThe label representation is consumed by the classifier.\n\n$$\n\\mathcal L = -\\sum_{c=1}^{C} y_c \\log g_c.\n\\label{eq:loss}\n\\tag{2}\n$$\n\nStable trailing paragraph.\n`;
async function fixture(source=oneHot){const root=await mkdtemp(path.join(os.tmpdir(),'pp-v2-semantic-'));await mkdir(path.join(root,'proposals'),{recursive:true});const bootstrap=workspaceModule.createProposalWorkspaceTool(root);await bootstrap.execute('seed',{action:'write',resource:'proposal',slug:'r01',content:source});const guard=workspaceModule.createDocumentOperationGuard(root);const workspace=workspaceModule.createProposalWorkspaceTool(root,{operationGuard:guard});return {root,adapter:new v2.ProposalWorkspaceAdapter(root,guard,workspace,()=>`semantic-${Math.random()}`)}}
async function realFixture(){const root=await mkdtemp(path.join(os.tmpdir(),'pp-v2-semantic-real-'));await mkdir(path.join(root,'proposals'),{recursive:true});await copyFile(path.resolve('proposals/research-concept-r01.md'),path.join(root,'proposals/research-concept-r01.md'));const guard=workspaceModule.createDocumentOperationGuard(root);const workspace=workspaceModule.createProposalWorkspaceTool(root,{operationGuard:guard});return {root,adapter:new v2.ProposalWorkspaceAdapter(root,guard,workspace,()=>`semantic-real-${Math.random()}`)}}
function sparsePlanner(calls){return {async plan(input){calls.push(input);assert.equal(input.context.documentSha256,input.documentSha256);assert.equal(input.context.targetEntryId,input.target.entryId);assert.ok(input.context.fragments.length<=6);assert.ok(Buffer.byteLength(JSON.stringify(input.context))<=24000);assert.equal('documentBytes' in input.context,false);return {actions:[{kind:'replace',targetEntryId:input.target.entryId,replacementText:`$$\n\\mathbf y = \\{(c,1)\\}, \\qquad c \\in \\{1,\\ldots,C\\}.\n\\label{eq:onehot}\n\\tag{1}\n$$\n\n`,semanticChange:true,rationale:'Use a sparse coordinate representation.'}],unresolvedQuestions:[]}}}}
const instruction='Cambia la ecuación del one-hot por una representación sparse.';
test('semantic MODIFY publishes only the resolved one-hot equation through the verified adapter',async()=>{const {root,adapter}=await fixture();const before=await readFile(path.join(root,'proposals/research-concept-r01.md'));const calls=[];const result=await new v2.PaperProposalOrchestrator(root,adapter,undefined,sparsePlanner(calls)).execute({instruction});assert.equal(result.status,'published',JSON.stringify({reason:result.reason,validation:result.validation,question:result.question,candidates:result.candidates}));assert.equal(result.plan.intent,'MODIFY');assert.equal(result.plan.semanticChange,true);assert.equal(result.plan.actions.length,1);assert.equal(result.plan.actions[0].kind,'replace');assert.equal(calls.length,1);assert.equal(result.plannerCalls,1);assert.equal(result.modelCalls,1);assert.equal(result.compiled.patches.length,1);assert.equal(result.validation.ok,true);const r02=await readFile(path.join(root,'proposals/research-concept-r02.md'));assert.deepEqual(await readFile(path.join(root,'proposals/research-concept-r01.md')),before);assert.match(r02.toString(),/\\mathbf y = \\{\(c,1\)\\}/);const replacement=result.plan.actions[0].replacementText;const {startByte,endByte}=result.compiled.modifiedRanges[0];assert.deepEqual(before.subarray(0,startByte),r02.subarray(0,startByte));assert.deepEqual(before.subarray(endByte),r02.subarray(startByte+Buffer.byteLength(replacement)));assert.equal(createHash('sha256').update(r02).digest('hex'),result.published.publishedSha256);assert.equal(result.derived.derivedStateManifest.status,'COMMITTED');const receipt=JSON.parse(await readFile(path.join(root,'.paper-proposal/receipts/research-concept-r02.md.json'),'utf8'));assert.equal(receipt.targetRevision,'r02');assert.equal(receipt.modelCalls,1);assert.equal(receipt.roleAuthorizations,0);assert.equal((await new v2.PaperProposalOrchestrator(root,adapter).latest()),'research-concept-r02.md');assert.equal((await readFile('proposals/matematica_propuesta_CREDA.md')).toString('hex')&&v2.sha256(await readFile('proposals/matematica_propuesta_CREDA.md')),realHashes.base);assert.equal(v2.sha256(await readFile('proposals/research-concept-r01.md')),realHashes.r01);});
test('ambiguity blocks two plausible one-hot equations before planner or mutation',async()=>{const source=oneHot.replace('\\mathcal L =','\\text{one-hot alternative}: \\mathcal L =');const {root,adapter}=await fixture(source);const state=await v2.loadDocumentState(root,'research-concept-r01.md');const ranked=v2.resolveTargets(state,'ecuación relacionada con one-hot');let calls=0;const planner={async plan(){calls++;return {}}};const result=await new v2.PaperProposalOrchestrator(root,adapter,undefined,planner).execute({instruction});assert.equal(result.status,'ambiguous',JSON.stringify({reason:result.reason,question:result.question,candidates:result.candidates,ranked}));assert.equal(result.candidates.length,2);assert.equal(calls,0);assert.equal(result.plannerCalls,0);await assert.rejects(readFile(path.join(root,'proposals/research-concept-r02.md')));});
test('unresolved semantic question blocks publication after its single planner call',async()=>{const {root,adapter}=await fixture();let calls=0;const planner={async plan(){calls++;return {unresolvedQuestions:['¿Sparse significa etiqueta entera o vector almacenado dispersamente?']}}};const result=await new v2.PaperProposalOrchestrator(root,adapter,undefined,planner).execute({instruction});assert.equal(result.status,'needs-clarification');assert.equal(result.question,'¿Sparse significa etiqueta entera o vector almacenado dispersamente?');assert.equal(calls,1);assert.equal(result.mutations,0);await assert.rejects(readFile(path.join(root,'proposals/research-concept-r02.md')));});
test('rejects invalid semantic planner output without publication',async()=>{const cases=[{name:'invented target',plan:i=>({actions:[{kind:'replace',targetEntryId:'invented',replacementText:'x'}],unresolvedQuestions:[]})},{name:'two actions',plan:i=>({actions:[{kind:'replace',targetEntryId:i.target.entryId,replacementText:'x'},{kind:'replace',targetEntryId:i.target.entryId,replacementText:'y'}],unresolvedQuestions:[]})},{name:'full document',plan:i=>({actions:[{kind:'replace',targetEntryId:i.target.entryId,replacementText:i.context.fragments.map(f=>f.text).join('\n')}],unresolvedQuestions:[]})}];for(const item of cases){const {root,adapter}=await fixture();const result=await new v2.PaperProposalOrchestrator(root,adapter,undefined,{async plan(input){return item.plan(input)}}).execute({instruction});assert.equal(result.status,'blocked',item.name);await assert.rejects(readFile(path.join(root,'proposals/research-concept-r02.md')));}});
test('explicit-block MODIFY localizes the real adjacent displays and publishes a byte-exact replacement',async()=>{
 const first=`$$
\\sum_{c=1}^C y_{i,c}^s=1,\\qquad i\\in\\{1,\\ldots,N_s\\}.
$$`;
 const second=`$$
y_{i,c}^s\\in\\{0,1\\},\\qquad y_{i,c}^sy_{i,c'}^s=0\\quad\\text{para }c\\ne c',\\qquad c,c'\\in\\{1,\\ldots,C\\}.
$$`;
 const providedTarget=`${first}\n\n${second}`;
 const actualTarget=`${first}\n${second}`;
 const replacement=`$$
\\sum_{c=1}^C y_{i,c}^s=1,
$$

$$
y_{i,c}^s\\neq y_{i,c'}^s,
\\qquad
c,c'\\in C,
\\qquad
y_{i,c}^s,y_{i,c'}^s\\in\\mathbf y_i^s,
$$`;
 const instruction=`En la propuesta administrada research-concept-r01.md, reemplaza exactamente este bloque:\n\n${providedTarget}\n\npor este bloque:\n\n${replacement}\n\nNo modifiques ningún otro byte del documento.`;
 const {root,adapter}=await realFixture();
 const sourcePath=path.join(root,'proposals/research-concept-r01.md');
 const before=await readFile(sourcePath);
 assert.equal(v2.sha256(before),realHashes.r01);
 assert.notEqual(before.indexOf(Buffer.from(actualTarget)),-1);
 const state=await v2.loadDocumentState(root,'research-concept-r01.md');
 const calls=[];
 const planner={async plan(input){
  calls.push(input);
  assert.deepEqual(input.fidelity,{targetBlock:providedTarget,replacementBlock:replacement,preserveExternalBytes:true,noReformat:true,noSemanticReinterpretation:true});
  assert.equal(input.target.composite.entryIds.length,2);
  assert.deepEqual(input.target.composite.entryIds.map(id=>state.structuralIndex.byId[id].type),['display_equation','display_equation']);
  assert.equal(input.target.composite.documentSha256,state.documentSha256);
  assert.equal(input.target.composite.exactProvidedText,actualTarget);
  assert.equal(input.target.composite.textSha256,v2.sha256(actualTarget));
  return {actions:[{kind:'replace',targetEntryId:input.target.entryId,replacementText:replacement}],unresolvedQuestions:[]};
 }};
 const result=await new v2.PaperProposalOrchestrator(root,adapter,undefined,planner).execute({sourceFilename:'research-concept-r01.md',instruction});
 assert.equal(result.status,'published',JSON.stringify({status:result.status,reason:result.reason,question:result.question,candidates:result.candidates}));
 assert.equal(calls.length,1);
 assert.equal(result.plannerCalls,1);
 assert.equal(result.compiled.patches.length,1);
 assert.equal(result.receipt.patchCount,1);
 const patch=result.compiled.patches[0];
 assert.equal(patch.oldText,actualTarget);
 assert.equal(patch.selector.textSha256,v2.sha256(actualTarget));
 const after=await readFile(path.join(root,'proposals/research-concept-r02.md'));
 assert.deepEqual(await readFile(sourcePath),before);
 const {startByte,endByte}=result.compiled.modifiedRanges[0];
 assert.deepEqual(after.subarray(startByte,startByte+Buffer.byteLength(replacement)),Buffer.from(replacement));
 assert.deepEqual(before.subarray(0,startByte),after.subarray(0,startByte));
 assert.deepEqual(before.subarray(endByte),after.subarray(startByte+Buffer.byteLength(replacement)));
});

test('only inter-display whitespace may differ during explicit CompositeTarget fallback',async()=>{
 const first='$$\nA=1.\n$$',second='$$\nB=2.\n$$';
 const provided=`${first}\n\n${second}`,actual=`${first}\n${second}`;
 const {root}=await fixture(`# T\n\n${actual}\n`);
 const state=await v2.loadDocumentState(root,'research-concept-r01.md');
 const candidates=v2.resolveTargets(state,provided,{allowInterEntryWhitespaceFallback:true});
 assert.equal(candidates.length,1);
 assert.equal(candidates[0].composite.entryIds.length,2);
 assert.equal(candidates[0].composite.exactProvidedText,actual);
 assert.equal(candidates[0].composite.textSha256,v2.sha256(actual));
});

test('internal equation differences are not structurally equivalent',async()=>{
 const first='$$\nA=1.\n$$',actualSecond='$$\nB=2.\n$$',differentSecond='$$\nB=3.\n$$';
 const {root}=await fixture(`# T\n\n${first}\n${actualSecond}\n`);
 const state=await v2.loadDocumentState(root,'research-concept-r01.md');
 assert.deepEqual(v2.resolveTargets(state,`${first}\n\n${differentSecond}`,{allowInterEntryWhitespaceFallback:true}),[]);
});

test('non-contiguous equivalent equations are ambiguous before planner',async()=>{
 const first='$$\nA=1.\n$$',second='$$\nB=2.\n$$',target=`${first}\n\n${second}`;
 const source=`# T\n\n${first}\n\nIntervening prose.\n\n${second}\n`;
 const {root,adapter}=await fixture(source);let calls=0;
 const result=await new v2.PaperProposalOrchestrator(root,adapter,undefined,{async plan(){calls++;return {}}}).execute({instruction:`Reemplaza exactamente este bloque:\n${target}\npor este bloque:\n$$\nC=3.\n$$`});
 assert.equal(result.status,'ambiguous');
 assert.equal(calls,0);
});

test('duplicate whitespace-equivalent composite ranges remain ambiguous',async()=>{
 const first='$$\nA=1.\n$$',second='$$\nB=2.\n$$',provided=`${first}\n\n${second}`,actual=`${first}\n${second}`;
 const source=`# T\n\n${actual}\n\nBetween ranges.\n\n${actual}\n`;
 const {root,adapter}=await fixture(source);let calls=0;
 const result=await new v2.PaperProposalOrchestrator(root,adapter,undefined,{async plan(){calls++;return {}}}).execute({instruction:`Reemplaza exactamente este bloque:\n${provided}\npor este bloque:\n$$\nC=3.\n$$`});
 assert.equal(result.status,'ambiguous');
 assert.equal(result.candidates.length,2);
 assert.equal(calls,0);
});

test('one explicit entry still resolves as a CompositeTarget of one',async()=>{const target='$$\nA=1.\n$$',source=`# T\n\n${target}\n`;const {root}=await fixture(source);const state=await v2.loadDocumentState(root,'research-concept-r01.md');const candidates=v2.resolveTargets(state,target);assert.equal(candidates.length,1);assert.equal(candidates[0].composite.entryIds.length,1);});
