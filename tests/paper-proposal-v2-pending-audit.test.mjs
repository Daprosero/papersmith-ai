import assert from 'node:assert/strict';
import { copyFile, mkdir, mkdtemp, readFile, readdir, rename, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot='/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const {createJiti}=await import(pathToFileURL(path.join(piRoot,'node_modules/jiti/lib/jiti.mjs')).href);
const jiti=createJiti(import.meta.url,{alias:{'@earendil-works/pi-coding-agent':path.join(piRoot,'dist/index.js'),'@earendil-works/pi-ai/compat':path.join(piRoot,'node_modules/@earendil-works/pi-ai/dist/compat.js'),'@earendil-works/pi-ai':path.join(piRoot,'node_modules/@earendil-works/pi-ai/dist/index.js'),typebox:path.join(piRoot,'node_modules/typebox/build/index.mjs')}});
const v2=await jiti.import(path.resolve('.claude/skills/paper-proposal/engine/exports.ts'));

const operationId='11111111-1111-4111-8111-111111111111';
const r01='research-concept-r01.md';
const r02='research-concept-r02.md';
const publicPaths=[`proposals/${r02}`,`.paper-proposal/state/${r02}.json`,`.paper-proposal/receipts/${r02}.json`];

function immutablePath(publicRelativePath) {
  return publicRelativePath.startsWith('proposals/')?`artifacts/${publicRelativePath}`:`artifacts/${publicRelativePath.replace(/^\.paper-proposal\//,'')}`;
}

async function writeJson(filename,value) {
  await mkdir(path.dirname(filename),{recursive:true});
  await writeFile(filename,JSON.stringify(value));
}

async function fixture() {
  const root=await mkdtemp(path.join(os.tmpdir(),'pp-v2-pending-audit-'));
  await mkdir(path.join(root,'proposals'),{recursive:true});
  await writeFile(path.join(root,'proposals',r01),'# Base\n\nBase text.\n');
  await v2.loadDocumentState(root,r01);
  await writeFile(path.join(root,'proposals',r02),'# Revision\n\nRevised text.\n');
  const state=await v2.loadDocumentState(root,r02);
  const stored=JSON.parse(await readFile(v2.derivedStatePath(root,r02),'utf8'));
  stored.manifest.status='COMMITTED';
  await writeJson(v2.derivedStatePath(root,r02),stored);
  await writeJson(v2.receiptPath(root,r02),{
    sourceRevision:'r01',targetRevision:'r02',sourceFilename:r01,targetFilename:r02,
    documentShaBefore:v2.sha256(await readFile(path.join(root,'proposals',r01))),
    documentShaAfter:state.documentSha256,derivedStateStatus:'COMMITTED',
  });

  const operationDirectory=path.join(root,'.paper-proposal','withdrawn',operationId);
  const artifacts=[];
  for (const publicRelativePath of publicPaths) {
    const source=path.join(root,publicRelativePath);
    const bytes=await readFile(source);
    const immutable=path.join(operationDirectory,immutablePath(publicRelativePath));
    const backup=path.join(operationDirectory,'public-backup',publicRelativePath);
    await mkdir(path.dirname(immutable),{recursive:true});
    await mkdir(path.dirname(backup),{recursive:true});
    await copyFile(source,immutable);
    await rename(source,backup);
    artifacts.push({publicRelativePath,sha256:v2.sha256(bytes),expectedLocation:'quarantine-public-backup'});
  }
  const now=Date.now();
  const expiresAt=new Date(now+v2.PENDING_AUDIT_LEASE_MS).toISOString();
  const inventoryDigest=v2.pendingAuditInventoryDigest(artifacts);
  await writeJson(path.join(operationDirectory,'metadata.json'),{
    schemaVersion:'1',operationId,operationTimestamp:new Date(now).toISOString(),requestedFilename:r02,revision:'r02',
    documentSha256:artifacts[0].sha256,sourceRevision:'r01',sourceFilename:r01,reason:'Pending audit fixture.',
    artifacts:artifacts.map(({publicRelativePath,sha256})=>({publicRelativePath,quarantineRelativePath:immutablePath(publicRelativePath),sha256})),
    inventoryDigest,preWithdrawalLatestFilename:r02,
  });
  const context={
    operationType:'WITHDRAW_REVISION',operationId,pendingAudit:true,
    phase:'WITHDRAW_PUBLIC_ARTIFACTS_MOVED',temporarilyMovedArtifacts:artifacts,
    expectedMarker:{relativePath:`.paper-proposal/withdrawn/${operationId}/audit-marker.json`,state:'PENDING_AUDIT',inventoryDigest,expiresAt},
  };
  const marker={
    operationType:context.operationType,operationId,state:'PENDING_AUDIT',phase:context.phase,
    temporarilyMovedArtifacts:artifacts,inventoryDigest,createdAt:new Date(now).toISOString(),expiresAt,
  };
  await writeJson(path.join(operationDirectory,'audit-marker.json'),marker);
  return {root,operationDirectory,context,marker};
}

async function runActiveSelfAudit(value,run=()=>v2.runPaperProposalSelfAudit({projectRoot:value.root,auditContext:value.context})) {
  v2.resetMutationLockMetrics();
  return v2.withRevisionLifecycleMutationLock(
    {projectRoot:value.root,operationId:value.context.operationId,filename:r02},
    lifecycleLockOwner=>v2.withActivePendingAuditOperation({projectRoot:value.root,auditContext:value.context,lifecycleLockOwner},run),
  );
}

async function rollback(value) {
  for (const publicRelativePath of publicPaths) {
    const source=path.join(value.operationDirectory,'public-backup',publicRelativePath);
    const destination=path.join(value.root,publicRelativePath);
    await mkdir(path.dirname(destination),{recursive:true});
    await rename(source,destination);
  }
  await rm(value.operationDirectory,{recursive:true});
}

test('active bounded PENDING_AUDIT context passes through SelfAudit unchanged',async()=>{
  const value=await fixture();
  const audit=await runActiveSelfAudit(value);
  assert.equal(audit.status,'PASS',JSON.stringify(audit));
  assert.equal(audit.checks.find(check=>check.id==='consistency').evidence.status,'PASS');
  assert.equal(audit.checks.find(check=>check.id==='locks-released').status,'PASS');
});

test('PENDING_AUDIT context fails closed without an active lifecycle operation',async()=>{
  const value=await fixture();
  const audit=await v2.runConsistencyAudit({projectRoot:value.root,auditContext:value.context});
  assert.equal(audit.status,'FAIL');
  assert.ok(audit.failures.some(failure=>failure.startsWith('PENDING_AUDIT_INACTIVE_OPERATION')));
});

test('an arbitrary active mutation lock cannot authorize a PENDING_AUDIT context',async()=>{
  const value=await fixture();
  v2.resetMutationLockMetrics();
  await v2.withMutationLock(`pending-audit-test:${value.root}`,()=>assert.rejects(
    v2.withActivePendingAuditOperation({
      projectRoot:value.root,
      auditContext:value.context,
      lifecycleLockOwner:{operationId:value.context.operationId,filename:r02},
    },()=>v2.runConsistencyAudit({projectRoot:value.root,auditContext:value.context})),
    /PENDING_AUDIT_REQUIRES_MATCHING_LIFECYCLE_LOCK_OWNER/,
  ));
});

test('active PENDING_AUDIT rejects an undeclared quarantine artifact',async()=>{
  const value=await fixture();
  await writeFile(path.join(value.operationDirectory,'public-backup','proposals','undeclared.md'),'not declared');
  const audit=await runActiveSelfAudit(value);
  assert.equal(audit.status,'FAIL');
  assert.ok(audit.checks.find(check=>check.id==='consistency').evidence.failures.some(failure=>failure.includes('UNDECLARED_ARTIFACT')));
});

test('active PENDING_AUDIT rejects a declared SHA mismatch',async()=>{
  const value=await fixture();
  const artifacts=value.context.temporarilyMovedArtifacts.map((artifact,index)=>index===0?{...artifact,sha256:'0'.repeat(64)}:artifact);
  const inventoryDigest=v2.pendingAuditInventoryDigest(artifacts);
  value.context={...value.context,temporarilyMovedArtifacts:artifacts,expectedMarker:{...value.context.expectedMarker,inventoryDigest}};
  value.marker={...value.marker,temporarilyMovedArtifacts:artifacts,inventoryDigest};
  await writeJson(path.join(value.operationDirectory,'audit-marker.json'),value.marker);
  const audit=await runActiveSelfAudit(value);
  assert.equal(audit.status,'FAIL');
  assert.ok(audit.checks.find(check=>check.id==='consistency').evidence.failures.some(failure=>failure.includes('SHA_MISMATCH')));
});

test('lifecycle-v1 legacy diagnostics leave an active PENDING_AUDIT fixture byte-identical and do not create authority',async()=>{
  const value=await fixture();
  const tracked=['metadata.json','audit-marker.json',...publicPaths.map(publicRelativePath=>`public-backup/${publicRelativePath}`)];
  const before=await Promise.all(tracked.map(relativePath=>readFile(path.join(value.operationDirectory,relativePath),'utf8')));
  const inventory=await v2.readLifecycleV1Inventory({projectRoot:value.root,workspaceId:'legacy-pending-audit'});
  assert.deepEqual(inventory,{status:'unregistered',code:'LIFECYCLE_V1_UNREGISTERED',auditEvidence:['lifecycle-v1:authority-unregistered']});
  await assert.rejects(readdir(path.join(value.root,'.paper-proposal','lifecycle','v1')),{code:'ENOENT'});
  assert.deepEqual(await Promise.all(tracked.map(relativePath=>readFile(path.join(value.operationDirectory,relativePath),'utf8'))),before);
  const audit=await runActiveSelfAudit(value);
  assert.equal(audit.status,'PASS',JSON.stringify(audit));
});

test('a finalized committed marker passes fresh context-free audits',async()=>{
  const value=await fixture();
  await runActiveSelfAudit(value);
  await writeJson(path.join(value.operationDirectory,'audit-marker.json'),{...value.marker,state:'COMMITTED',auditStatus:'PASS',selfAuditStatus:'PASS'});
  v2.resetMutationLockMetrics();
  const consistency=await v2.runConsistencyAudit({projectRoot:value.root});
  const selfAudit=await v2.runPaperProposalSelfAudit({projectRoot:value.root});
  assert.equal(consistency.status,'PASS',JSON.stringify(consistency));
  assert.equal(selfAudit.status,'PASS',JSON.stringify(selfAudit));
});

test('injected pending-audit failure followed by rollback passes normal audits',async()=>{
  const value=await fixture();
  await assert.rejects(runActiveSelfAudit(value,async()=>{throw new Error('INJECTED_AUDIT_FAILURE');}),/INJECTED_AUDIT_FAILURE/);
  await rollback(value);
  v2.resetMutationLockMetrics();
  const consistency=await v2.runConsistencyAudit({projectRoot:value.root});
  const selfAudit=await v2.runPaperProposalSelfAudit({projectRoot:value.root});
  assert.equal(consistency.status,'PASS',JSON.stringify(consistency));
  assert.equal(selfAudit.status,'PASS',JSON.stringify(selfAudit));
});
