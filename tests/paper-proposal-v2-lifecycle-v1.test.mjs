import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot='/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const {createJiti}=await import(pathToFileURL(path.join(piRoot,'node_modules/jiti/lib/jiti.mjs')).href);
const jiti=createJiti(import.meta.url,{alias:{'@earendil-works/pi-coding-agent':path.join(piRoot,'dist/index.js'),'@earendil-works/pi-ai/compat':path.join(piRoot,'node_modules/@earendil-works/pi-ai/dist/compat.js'),'@earendil-works/pi-ai':path.join(piRoot,'node_modules/@earendil-works/pi-ai/dist/index.js'),typebox:path.join(piRoot,'node_modules/typebox/build/index.mjs')}});
const v2=await jiti.import(path.resolve('.claude/skills/paper-proposal/engine/exports.ts'));
const workspace=await jiti.import(path.resolve('.claude/skills/paper-proposal/engine/proposal-workspace.ts'));

async function fixture(dependencies={}) {
 const root=await mkdtemp(path.join(os.tmpdir(),'paper-proposal-lifecycle-v1-'));
 await mkdir(path.join(root,'.paper-proposal'),{recursive:true});
 let id=0;
 const service=new v2.LifecycleService(root,{newId:(kind)=>`${kind}-${++id}`,now:()=>new Date('2026-01-01T00:00:00.000Z'),...dependencies});
 return {root,service};
}

async function registeredWorkspace() {
 const run=await fixture();
 const base=await run.service.registerBaseDocument({workspaceId:'workspace-1',requestId:'register-1',baseDocumentId:'base-1',content:'Title\nUnchanged paragraph\n'});
 assert.equal(base.outcome,'COMMITTED');
 return {...run,base};
}

test('registers one immutable base with stable identity and durable content',async()=>{
 const {root,service}=await fixture();
 const base=await service.registerBaseDocument({workspaceId:'workspace-1',requestId:'register-1',baseDocumentId:'base-1',content:'Complete base content'});
 assert.equal(base.outcome,'COMMITTED');
 assert.equal(base.inventory.lifecycleState,'BASE_REGISTERED');
 assert.equal(base.base.baseDocumentId,'base-1');
 assert.equal(base.base.content,'Complete base content');
 assert.equal((await service.rebuildLifecycleInventory('workspace-1')).base.baseDocumentId,'base-1');
 assert.match(base.storageRoot,new RegExp(`${path.sep.replace(/\\/g,'\\\\')}\.paper-proposal${path.sep.replace(/\\/g,'\\\\')}lifecycle${path.sep.replace(/\\/g,'\\\\')}v1`));
});

test('enforces one base, verifies hashes, and replays an equivalent registration without mutation',async()=>{
 const {service}=await registeredWorkspace();
 const replay=await service.registerBaseDocument({workspaceId:'workspace-1',requestId:'register-1',baseDocumentId:'base-1',content:'Title\nUnchanged paragraph\n'});
 assert.equal(replay.outcome,'ALREADY_COMMITTED');
 assert.equal(replay.baseDocumentId,'base-1');
 const mismatch=await service.registerBaseDocument({workspaceId:'workspace-1',requestId:'register-2',baseDocumentId:'base-2',content:'Other',contentHash:'0'.repeat(64)});
 assert.deepEqual({outcome:mismatch.outcome,code:mismatch.code},{outcome:'REJECTED',code:'SOURCE_CONTENT_HASH_MISMATCH'});
 const conflict=await service.registerBaseDocument({workspaceId:'workspace-1',requestId:'register-3',baseDocumentId:'base-2',content:'Other'});
 assert.deepEqual({outcome:conflict.outcome,code:conflict.code},{outcome:'REJECTED',code:'BASE_DOCUMENT_ALREADY_REGISTERED'});
});

test('materializes exact base and successor lineage while resolving stable active identity independently of locators',async()=>{
 const {service,base}=await registeredWorkspace();
 const first=await service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',locator:'research-concept-r99.md',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[{from:'Unchanged',to:'Approved'}]});
 assert.equal(first.outcome,'COMMITTED');
 assert.equal(first.revision.content,'Title\nApproved paragraph\n');
 assert.deepEqual(first.revision.lineage,{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'});
 const successor=await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-2',operation:'CREATE_SUCCESSOR',revisionId:'revision-2',locator:'research-concept-r01.md',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[{from:'Approved',to:'Approved twice'}]});
 assert.equal(successor.outcome,'COMMITTED');
 const active=await service.resolveActiveRevision('workspace-1');
 assert.deepEqual({outcome:active.outcome,revisionId:active.revision?.revisionId},{outcome:'COMMITTED',revisionId:'revision-2'});
 assert.deepEqual(successor.inventory.revisions.map(item=>[item.revisionId,item.state]),[['revision-1','SUPERSEDED'],['revision-2','ACTIVE']]);
 const replay=await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-2',operation:'CREATE_SUCCESSOR',revisionId:'revision-2',locator:'research-concept-r01.md',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[{from:'Approved',to:'Approved twice'}]});
 assert.deepEqual({outcome:replay.outcome,revisionId:replay.revisionId},{outcome:'ALREADY_COMMITTED',revisionId:'revision-2'});
});

test('withdraws and restores only durable withdrawal identity, preserving withdrawn-only history across restart',async()=>{
 const {root,service,base}=await registeredWorkspace();
 const first=await service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const second=await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-2',operation:'CREATE_SUCCESSOR',revisionId:'revision-2',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const withdrawn=await service.withdrawRevision({workspaceId:'workspace-1',requestId:'withdraw-1',revisionId:'revision-2'});
 assert.deepEqual({outcome:withdrawn.outcome,state:withdrawn.inventory.lifecycleState,active:withdrawn.inventory.activeRevisionId},{outcome:'COMMITTED',state:'WITHDRAWN_ONLY',active:undefined});
 assert.deepEqual(withdrawn.inventory.revisions.map(item=>[item.revisionId,item.state]),[['revision-1','SUPERSEDED'],['revision-2','WITHDRAWN']]);
 const fresh=new v2.LifecycleService(root);
 const rebuilt=await fresh.rebuildLifecycleInventory('workspace-1');
 assert.deepEqual({state:rebuilt.lifecycleState,withdrawals:rebuilt.withdrawals.map(item=>item.withdrawalId),active:rebuilt.activeRevisionId},{state:'WITHDRAWN_ONLY',withdrawals:[withdrawn.withdrawal.withdrawalId],active:undefined});
 const filenameAttempt=await fresh.restoreWithdrawnRevision({workspaceId:'workspace-1',requestId:'restore-file',reference:'research-concept-r02.md'});
 assert.deepEqual({outcome:filenameAttempt.outcome,code:filenameAttempt.code},{outcome:'REJECTED',code:'WITHDRAWAL_IDENTITY_NOT_FOUND'});
 const restored=await fresh.restoreWithdrawnRevision({workspaceId:'workspace-1',requestId:'restore-1',withdrawalId:withdrawn.withdrawal.withdrawalId});
 assert.deepEqual({outcome:restored.outcome,revisionId:restored.revision?.revisionId,state:restored.inventory.lifecycleState},{outcome:'COMMITTED',revisionId:second.revision.revisionId,state:'ACTIVE'});
});

test('public lifecycle-v1 routing withdraws only active revisions and restores only persistent withdrawal IDs',async()=>{
 const {root,service,base}=await registeredWorkspace();
 const first=await service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-2',operation:'CREATE_SUCCESSOR',revisionId:'revision-2',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const router=new v2.LifecycleV1PublicRouter({projectRoot:root,workspaceId:'workspace-1',service});
 const withdrawn=await router.execute({operation:'WITHDRAW_REVISION',requestId:'withdraw-1',revisionId:'revision-2'});
 assert.deepEqual({outcome:withdrawn.outcome,state:withdrawn.inventory?.lifecycleState,active:withdrawn.inventory?.activeRevisionId},{outcome:'COMMITTED',state:'WITHDRAWN_ONLY',active:undefined});
 assert.deepEqual(await router.execute({operation:'RESTORE_WITHDRAWN_REVISION',requestId:'restore-base',reference:'base-1'}),{outcome:'REJECTED',code:'BASE_DOCUMENT_NOT_RESTORABLE'});
 assert.deepEqual(await router.execute({operation:'RESTORE_WITHDRAWN_REVISION',requestId:'restore-revision',reference:'revision-1'}),{outcome:'REJECTED',code:'REVISION_NOT_WITHDRAWN'});
 assert.deepEqual(await router.execute({operation:'RESTORE_WITHDRAWN_REVISION',requestId:'restore-file',reference:'research-concept-r02.md'}),{outcome:'REJECTED',code:'WITHDRAWAL_IDENTITY_NOT_FOUND'});
 const restored=await router.execute({operation:'RESTORE_WITHDRAWN_REVISION',requestId:'restore-1',withdrawalId:withdrawn.withdrawalId});
 assert.deepEqual({outcome:restored.outcome,active:restored.inventory?.activeRevisionId,withdrawal:restored.withdrawal?.state},{outcome:'COMMITTED',active:'revision-2',withdrawal:'RESTORED'});
});

test('public lifecycle routing uses configured v1 authority without legacy proposal files',async()=>{
 const {root,service,base}=await registeredWorkspace();
 const first=await service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',locator:'research-concept-r01.md',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-2',operation:'CREATE_SUCCESSOR',revisionId:'revision-2',locator:'research-concept-r02.md',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const tools=[];
 v2.resetRuntimeMetrics();
 workspace.createPaperProposalExtension({projectRoot:root,scientificWorkflow:{lifecycleV1WorkspaceId:'workspace-1'}})({registerTool:(tool)=>tools.push(tool),on:()=>{}});
 const execute=tools.find((tool)=>tool.name==='paper_proposal_execute');
 const withdrawn=(await execute.execute('withdraw-v1',{operation:'WITHDRAW_REVISION',instruction:'withdraw research-concept-r02.md',sourceFilename:'research-concept-r02.md',idempotencyKey:'withdraw-v1'})).details;
 assert.deepEqual({status:withdrawn.status,operation:withdrawn.operation,revisionId:withdrawn.revisionId,lifecycleState:withdrawn.lifecycleState,activeRevisionId:withdrawn.activeRevisionId},{status:'withdrawn',operation:'WITHDRAW_REVISION',revisionId:'revision-2',lifecycleState:'WITHDRAWN_ONLY',activeRevisionId:null});
 assert.match(withdrawn.withdrawalId,/^[0-9a-f-]{36}$/);
 assert.deepEqual(withdrawn.transitionEvidence,{operation:'WITHDRAW_REVISION',requestId:'withdraw-v1',outcome:'committed',lifecycleState:'WITHDRAWN_ONLY',activeRevisionId:null,revisionId:'revision-2',withdrawalId:withdrawn.withdrawalId});
 assert.doesNotMatch(JSON.stringify(withdrawn.transitionEvidence),/Title|Unchanged paragraph|withdraw research-concept|paper-proposal-lifecycle-v1-|absolute|contents\//i);
 const rejected=(await execute.execute('restore-v1-rejected',{operation:'RESTORE_WITHDRAWN_REVISION',instruction:'restore the withdrawn revision',sourceFilename:'research-concept-r01.md',idempotencyKey:'restore-v1-rejected'})).details;
 assert.deepEqual({status:rejected.status,semanticCode:rejected.semanticCode,lifecycleState:rejected.lifecycleState},{status:'blocked',semanticCode:'WITHDRAWAL_IDENTITY_NOT_FOUND',lifecycleState:null});
 assert.deepEqual(rejected.transitionEvidence,{operation:'RESTORE_WITHDRAWN_REVISION',requestId:'restore-v1-rejected',outcome:'rejected',semanticCode:'WITHDRAWAL_IDENTITY_NOT_FOUND'});
 const restored=(await execute.execute('restore-v1',{operation:'RESTORE_WITHDRAWN_REVISION',instruction:'restore the withdrawn revision',withdrawalOperationId:withdrawn.withdrawalId,idempotencyKey:'restore-v1'})).details;
 assert.deepEqual({status:restored.status,operation:restored.operation,revisionId:restored.revisionId,lifecycleState:restored.lifecycleState,activeRevisionId:restored.activeRevisionId},{status:'restored',operation:'RESTORE_WITHDRAWN_REVISION',revisionId:'revision-2',lifecycleState:'ACTIVE',activeRevisionId:'revision-2'});
 assert.deepEqual(restored.transitionEvidence,{operation:'RESTORE_WITHDRAWN_REVISION',requestId:'restore-v1',outcome:'committed',lifecycleState:'ACTIVE',activeRevisionId:'revision-2',revisionId:'revision-2',withdrawalId:withdrawn.withdrawalId});
 assert.deepEqual(v2.getRuntimeMetrics().lifecycleMetrics,{withdrawal_committed:1,withdrawal_rejected:0,restore_committed:1,restore_rejected:1});
 const transitions=await Promise.all((await readdir(path.join(root,'.paper-proposal','lifecycle','v1','transitions'))).map((name)=>readFile(path.join(root,'.paper-proposal','lifecycle','v1','transitions',name),'utf8')));
 assert.doesNotMatch(transitions.join('\n'),/Title|Unchanged paragraph|withdraw research-concept|paper-proposal-lifecycle-v1-/);
 await assert.rejects(readFile(path.join(root,'proposals','research-concept-r02.md')),{code:'ENOENT'});
});

test('ignores pre-marker staging, reconstructs committed marker state, and fails closed for contradictory durable records',async()=>{
 const interrupted=await fixture({beforeCommitMarker:()=>{throw new Error('injected-before-marker');}});
 const pending=await interrupted.service.registerBaseDocument({workspaceId:'workspace-1',requestId:'register-1',baseDocumentId:'base-1',content:'base'});
 assert.equal(pending.outcome,'INCONSISTENT');
 assert.equal((await new v2.LifecycleService(interrupted.root).rebuildLifecycleInventory('workspace-1')).lifecycleState,'EMPTY');
 const markerCommitted=await fixture({afterCommitMarker:()=>{throw new Error('injected-after-marker');}});
 const afterMarker=await markerCommitted.service.registerBaseDocument({workspaceId:'workspace-1',requestId:'register-1',baseDocumentId:'base-1',content:'base'});
 assert.equal(afterMarker.outcome,'INCONSISTENT');
 assert.equal((await new v2.LifecycleService(markerCommitted.root).rebuildLifecycleInventory('workspace-1')).base.baseDocumentId,'base-1');
 const {root,service,base}=await registeredWorkspace();
 const first=await service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-2',operation:'CREATE_SUCCESSOR',revisionId:'revision-2',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const transitions=path.join(root,'.paper-proposal','lifecycle','v1','transitions');
 const transitionRows=await Promise.all((await readdir(transitions)).map(async name=>({name,marker:JSON.parse(await readFile(path.join(transitions,name),'utf8'))})));
 const selected=transitionRows.find(row=>row.marker.operation==='CREATE_SUCCESSOR');
 selected.marker.stateChanges=[];
 await writeFile(path.join(transitions,selected.name),JSON.stringify(selected.marker));
 await assert.rejects(new v2.LifecycleService(root).rebuildLifecycleInventory('workspace-1'),/LIFECYCLE_INVENTORY_INCONSISTENT/);
});

test('fails closed for an orphan withdrawal record instead of treating it as history',async()=>{
 const {root,service,base}=await registeredWorkspace();
 const first=await service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const second=await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-2',operation:'CREATE_SUCCESSOR',revisionId:'revision-2',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const transitions=path.join(root,'.paper-proposal','lifecycle','v1','transitions');
 const rows=await Promise.all((await readdir(transitions)).map(async name=>JSON.parse(await readFile(path.join(transitions,name),'utf8'))));
 const transition=rows.find(item=>item.operation==='CREATE_SUCCESSOR');
 const orphan={schemaVersion:'lifecycle-v1',workspaceId:'workspace-1',withdrawalId:'withdrawal-orphan',revisionId:second.revision.revisionId,contentHash:second.revision.contentHash,recoveryContent:second.revision.content,transitionId:transition.transitionId,state:'COMMITTED'};
 await writeFile(path.join(root,'.paper-proposal','lifecycle','v1','withdrawals','withdrawal-orphan.json'),JSON.stringify(orphan));
 await assert.rejects(new v2.LifecycleService(root).rebuildLifecycleInventory('workspace-1'),/LIFECYCLE_INVENTORY_INCONSISTENT/);
});

test('persists request and result records before exposing a committed lifecycle result',async()=>{
 const {root,service}=await fixture();
 const result=await service.registerBaseDocument({workspaceId:'workspace-1',requestId:'register-1',baseDocumentId:'base-1',content:'base'});
 assert.equal(result.outcome,'COMMITTED');
 const request=JSON.parse(await readFile(path.join(root,'.paper-proposal','lifecycle','v1','requests','register-1.json'),'utf8'));
 const storedResult=JSON.parse(await readFile(path.join(root,'.paper-proposal','lifecycle','v1','results','register-1.json'),'utf8'));
 assert.deepEqual({requestId:request.requestId,workspaceId:request.workspaceId,transitionId:request.transitionId},{requestId:'register-1',workspaceId:'workspace-1',transitionId:storedResult.transitionId});
 assert.equal(storedResult.value.baseDocumentId,'base-1');
});

test('fails closed for missing content, broken lineage, and cross-workspace durable evidence',async()=>{
 const missing=await registeredWorkspace();
 await rm(path.join(missing.root,'.paper-proposal','lifecycle','v1','contents',missing.base.base.contentHash));
 await assert.rejects(new v2.LifecycleService(missing.root).rebuildLifecycleInventory('workspace-1'),/SOURCE_CONTENT_HASH_MISMATCH/);
 const broken=await registeredWorkspace();
 const first=await broken.service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:broken.base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const revisionPath=path.join(broken.root,'.paper-proposal','lifecycle','v1','revisions','revision-1.json');
 const revision=JSON.parse(await readFile(revisionPath,'utf8'));
 revision.lineage.sourceId='base-other';
 await writeFile(revisionPath,JSON.stringify(revision));
 await assert.rejects(new v2.LifecycleService(broken.root).rebuildLifecycleInventory('workspace-1'),/INVALID_LINEAGE_REFERENCE/);
 const cross=await registeredWorkspace();
 const crossRevision=await cross.service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:cross.base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const crossPath=path.join(cross.root,'.paper-proposal','lifecycle','v1','revisions','revision-1.json');
 const crossRecord=JSON.parse(await readFile(crossPath,'utf8'));
 crossRecord.workspaceId='workspace-2';
 await writeFile(crossPath,JSON.stringify(crossRecord));
 await assert.rejects(new v2.LifecycleService(cross.root).rebuildLifecycleInventory('workspace-2'),/LIFECYCLE_INVENTORY_INCONSISTENT/);
 assert.equal(crossRevision.outcome,'COMMITTED');
});

test('rejects duplicate revision identities, locator conflicts, and mismatched resulting hashes without changing active state',async()=>{
 const {service,base}=await registeredWorkspace();
 const first=await service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',locator:'same-locator.md',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const duplicate=await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-duplicate',operation:'CREATE_SUCCESSOR',revisionId:'revision-1',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 assert.deepEqual({outcome:duplicate.outcome,code:duplicate.code},{outcome:'REJECTED',code:'ACTIVE_REVISION_ALREADY_EXISTS'});
 const locator=await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-locator',operation:'CREATE_SUCCESSOR',revisionId:'revision-2',locator:'same-locator.md',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 assert.deepEqual({outcome:locator.outcome,code:locator.code},{outcome:'REJECTED',code:'OUTPUT_FILENAME_CONFLICT'});
 const mismatch=await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-hash',operation:'CREATE_SUCCESSOR',revisionId:'revision-2',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[],contentHash:'0'.repeat(64)});
 assert.deepEqual({outcome:mismatch.outcome,code:mismatch.code},{outcome:'REJECTED',code:'SOURCE_CONTENT_HASH_MISMATCH'});
 const active=await service.resolveActiveRevision('workspace-1');
 assert.deepEqual({outcome:active.outcome,revisionId:active.revision?.revisionId},{outcome:'COMMITTED',revisionId:'revision-1'});
});

test('reports recovery/inconsistency if inventory projection publication is interrupted after the commit marker',async()=>{
 const run=await fixture({afterInventoryProjection:()=>{throw new Error('injected-after-projection');}});
 const result=await run.service.registerBaseDocument({workspaceId:'workspace-1',requestId:'register-1',baseDocumentId:'base-1',content:'base'});
 assert.equal(result.outcome,'INCONSISTENT');
 const rebuilt=await new v2.LifecycleService(run.root).rebuildLifecycleInventory('workspace-1');
 assert.deepEqual({state:rebuilt.lifecycleState,base:rebuilt.base.baseDocumentId},{state:'BASE_REGISTERED',base:'base-1'});
});

test('exposes explicitly registered lifecycle-v1 inventory read-only without consulting legacy filenames',async()=>{
 const {root,service,base}=await registeredWorkspace();
 const first=await service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',locator:'research-concept-r99.md',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const before=await (await import('node:fs/promises')).readdir(path.join(root,'.paper-proposal','lifecycle','v1'),{recursive:true});
 const inventory=await v2.readLifecycleV1Inventory({projectRoot:root,workspaceId:'workspace-1'});
 assert.deepEqual({status:inventory.status,lifecycleState:inventory.lifecycleState,baseDocumentId:inventory.baseDocument?.baseDocumentId,activeRevisionId:inventory.activeRevision?.revisionId},{status:'valid',lifecycleState:'ACTIVE',baseDocumentId:'base-1',activeRevisionId:first.revision.revisionId});
 assert.deepEqual(await (await import('node:fs/promises')).readdir(path.join(root,'.paper-proposal','lifecycle','v1'),{recursive:true}),before);
});

test('legacy workspaces are diagnostic-only and lifecycle-v1 reads never create authority records',async()=>{
 const {root}=await fixture();
 const proposals=path.join(root,'proposals');
 const withdrawn=path.join(root,'.paper-proposal','withdrawn');
 await mkdir(proposals,{recursive:true});
 await mkdir(withdrawn,{recursive:true});
 const legacyProposal=path.join(proposals,'research-concept-r99.md');
 const legacyWithdrawal=path.join(withdrawn,'legacy-withdrawal.json');
 await writeFile(legacyProposal,'legacy proposal bytes');
 await writeFile(legacyWithdrawal,'legacy withdrawal bytes');
 const before=await Promise.all([readFile(legacyProposal,'utf8'),readFile(legacyWithdrawal,'utf8')]);
 const inventory=await v2.readLifecycleV1Inventory({projectRoot:root,workspaceId:'legacy-workspace'});
 assert.deepEqual(inventory,{status:'unregistered',code:'LIFECYCLE_V1_UNREGISTERED',auditEvidence:['lifecycle-v1:authority-unregistered']});
 await assert.rejects(readdir(path.join(root,'.paper-proposal','lifecycle','v1')),{code:'ENOENT'});
 assert.deepEqual(await Promise.all([readFile(legacyProposal,'utf8'),readFile(legacyWithdrawal,'utf8')]),before);
 const router=new v2.LifecycleV1PublicRouter({projectRoot:root,workspaceId:'legacy-workspace'});
 assert.deepEqual(await router.execute({operation:'WITHDRAW_REVISION',requestId:'legacy-withdraw',locator:'research-concept-r99.md'}),{outcome:'REJECTED',code:'LIFECYCLE_V1_UNREGISTERED'});
 assert.deepEqual(await Promise.all([readFile(legacyProposal,'utf8'),readFile(legacyWithdrawal,'utf8')]),before);
});

test('workspace-scoped v1 authority does not let another workspace suppress legacy diagnostics',async()=>{
 const {root,service}=await registeredWorkspace();
 const before=await service.rebuildLifecycleInventory('workspace-1');
 const missing=await v2.readLifecycleV1Inventory({projectRoot:root,workspaceId:'workspace-2'});
 assert.deepEqual(missing,{status:'unregistered',code:'LIFECYCLE_V1_UNREGISTERED',auditEvidence:['lifecycle-v1:authority-unregistered']});
 const router=new v2.LifecycleV1PublicRouter({projectRoot:root,workspaceId:'workspace-2'});
 assert.deepEqual(await router.execute({operation:'WITHDRAW_REVISION',requestId:'withdraw-missing',locator:'research-concept-r99.md'}),{outcome:'REJECTED',code:'LIFECYCLE_V1_UNREGISTERED'});
 const after=await new v2.LifecycleService(root).rebuildLifecycleInventory('workspace-1');
 assert.deepEqual(after,before);
});

test('public lifecycle composition blocks an explicitly configured legacy workspace without mutating it',async()=>{
 const {root}=await fixture();
 const proposals=path.join(root,'proposals');
 await mkdir(proposals,{recursive:true});
 const legacyProposal=path.join(proposals,'research-concept-r99.md');
 await writeFile(legacyProposal,'legacy proposal bytes');
 const before=await readFile(legacyProposal,'utf8');
 const tools=[];
 v2.resetRuntimeMetrics();
 workspace.createPaperProposalExtension({projectRoot:root,scientificWorkflow:{lifecycleV1WorkspaceId:'legacy-workspace'}})({registerTool:(tool)=>tools.push(tool),on:()=>{}});
 const execute=tools.find((tool)=>tool.name==='paper_proposal_execute');
 const result=(await execute.execute('legacy-public-withdraw',{operation:'WITHDRAW_REVISION',instruction:'withdraw research-concept-r99.md',sourceFilename:'research-concept-r99.md',idempotencyKey:'legacy-public-withdraw'})).details;
 assert.deepEqual({status:result.status,semanticCode:result.semanticCode,lifecycleState:result.lifecycleState},{status:'blocked',semanticCode:'LIFECYCLE_V1_UNREGISTERED',lifecycleState:null});
 assert.equal(await readFile(legacyProposal,'utf8'),before);
 await assert.rejects(readdir(path.join(root,'.paper-proposal','lifecycle','v1')),{code:'ENOENT'});
 assert.deepEqual(v2.getRuntimeMetrics().lifecycleMetrics,{withdrawal_committed:0,withdrawal_rejected:1,restore_committed:0,restore_rejected:0});
});

test('lifecycle materialization planner uses only explicit base bytes and the resolved active revision',async()=>{
 const {root,service}=await fixture();
 const planner=new v2.LifecycleMaterializationPlanner({projectRoot:root,workspaceId:'workspace-1',service});
 const legacy=await planner.materialize({requestId:'legacy-request',revisionId:'revision-legacy',approvedChanges:[]});
 assert.deepEqual({status:legacy.status,code:legacy.code},{status:'blocked',code:'BASE_DOCUMENT_NOT_REGISTERED'});
 const base=await service.registerBaseDocument({workspaceId:'workspace-1',requestId:'register-1',baseDocumentId:'base-1',content:'Title\nStable text\n'});
 const first=await planner.materialize({requestId:'materialize-1',revisionId:'revision-1',approvedChanges:[{from:'Stable',to:'Approved'}]});
 assert.deepEqual({status:first.status,operation:first.result?.operation,content:first.revision?.content,lineage:first.revision?.lineage},{status:'ready',operation:'CREATE_FROM_BASE',content:'Title\nApproved text\n',lineage:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'}});
 const successor=await planner.materialize({requestId:'materialize-2',revisionId:'revision-2',approvedChanges:[{from:'Approved',to:'Approved twice'}]});
 assert.deepEqual({status:successor.status,operation:successor.result?.operation,active:successor.inventory?.activeRevisionId,states:successor.inventory?.revisions.map(item=>[item.revisionId,item.state])},{status:'ready',operation:'CREATE_SUCCESSOR',active:'revision-2',states:[['revision-1','SUPERSEDED'],['revision-2','ACTIVE']]});
});

test('lifecycle materialization planner rejects a withdrawn lifecycle rather than reinterpreting it as a first materialization',async()=>{
 const {root,service,base}=await registeredWorkspace();
 const first=await service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const successor=await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-2',operation:'CREATE_SUCCESSOR',revisionId:'revision-2',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 assert.equal((await service.withdrawRevision({workspaceId:'workspace-1',requestId:'withdraw-2',revisionId:successor.revision.revisionId})).outcome,'COMMITTED');
 const blocked=await new v2.LifecycleMaterializationPlanner({projectRoot:root,workspaceId:'workspace-1'}).materialize({requestId:'create-after-withdrawal',revisionId:'revision-3',approvedChanges:[]});
 assert.deepEqual({status:blocked.status,code:blocked.code},{status:'blocked',code:'ACTIVE_REVISION_NOT_FOUND'});
 assert.deepEqual((await new v2.LifecycleService(root).rebuildLifecycleInventory('workspace-1')).revisions.map(item=>[item.revisionId,item.state]),[['revision-1','SUPERSEDED'],['revision-2','WITHDRAWN']]);
});

test('successor creation rejects stale, superseded, withdrawn, and non-revision source evidence without changing the inventory',async()=>{
 const {service,base}=await registeredWorkspace();
 const first=await service.createFromBase({workspaceId:'workspace-1',requestId:'create-1',operation:'CREATE_FROM_BASE',revisionId:'revision-1',source:{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const second=await service.createSuccessor({workspaceId:'workspace-1',requestId:'create-2',operation:'CREATE_SUCCESSOR',revisionId:'revision-2',source:{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 const before=await service.rebuildLifecycleInventory('workspace-1');
 for(const [requestId,source] of [
  ['base-source',{sourceKind:'BASE_DOCUMENT',sourceId:'base-1',sourceContentHash:base.base.contentHash,baseDocumentId:'base-1'}],
  ['superseded-source',{sourceKind:'REVISION',sourceId:'revision-1',sourceContentHash:first.revision.contentHash,baseDocumentId:'base-1'}],
  ['stale-hash',{sourceKind:'REVISION',sourceId:'revision-2',sourceContentHash:'0'.repeat(64),baseDocumentId:'base-1'}],
  ['filename-only',{sourceKind:'REVISION',sourceId:'research-concept-r02.md',sourceContentHash:second.revision.contentHash,baseDocumentId:'base-1'}],
 ]) {
  const rejected=await service.createSuccessor({workspaceId:'workspace-1',requestId,operation:'CREATE_SUCCESSOR',revisionId:`revision-${requestId}`,source,approvedChanges:[]});
  assert.deepEqual({outcome:rejected.outcome,code:rejected.code},{outcome:'REJECTED',code:'INVALID_LINEAGE_REFERENCE'});
 }
 assert.equal((await service.withdrawRevision({workspaceId:'workspace-1',requestId:'withdraw-2',revisionId:'revision-2'})).outcome,'COMMITTED');
 const withdrawn=await service.createSuccessor({workspaceId:'workspace-1',requestId:'withdrawn-source',operation:'CREATE_SUCCESSOR',revisionId:'revision-3',source:{sourceKind:'REVISION',sourceId:'revision-2',sourceContentHash:second.revision.contentHash,baseDocumentId:'base-1'},approvedChanges:[]});
 assert.deepEqual({outcome:withdrawn.outcome,code:withdrawn.code},{outcome:'REJECTED',code:'ACTIVE_REVISION_NOT_FOUND'});
 assert.deepEqual((await service.rebuildLifecycleInventory('workspace-1')).revisions.map(item=>[item.revisionId,item.state]),[['revision-1','SUPERSEDED'],['revision-2','WITHDRAWN']]);
 assert.deepEqual(before.revisions.map(item=>item.revisionId),['revision-1','revision-2']);
});
