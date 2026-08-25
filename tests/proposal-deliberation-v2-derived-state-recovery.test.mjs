import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, {
  alias: {
    '@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
    '@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
    '@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
    typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
  },
});
const v2 = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/exports.ts'));

const document = '# Título α\n\nTexto Unicode y referencia \\eqref{eq:uno}.\n\n$$\nx = 1\n\\label{eq:uno}\n\\tag{1}\n$$\n\n## Resultados\n\nSímbolo z ∈ R.\n';

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-state-'));
  await mkdir(path.join(root, 'proposals'), { recursive: true });
  const filename = 'research-concept-r01.md';
  await writeFile(path.join(root, 'proposals', filename), document);
  return { root, filename };
}

function rangesValid(state) {
  return state.structuralIndex.entries.every((entry) =>
    entry.startByte >= 0
    && entry.endByte >= entry.startByte
    && entry.endByte <= state.documentBytes.length
    && entry.textSha256 === v2.sha256(state.documentBytes.subarray(entry.startByte, entry.endByte)));
}

async function persistedState(root, filename) {
  return JSON.parse(await readFile(v2.derivedStatePath(root, filename), 'utf8'));
}

async function assertValidWithoutReceipt(root, filename, state) {
  assert.equal(state.derivedStateStatus, 'VALID');
  assert.equal(state.derivedStateManifest.status, 'VALID');
  assert.equal(rangesValid(state), true);
  assert.equal((await persistedState(root, filename)).manifest.status, 'VALID');
  await assert.rejects(readFile(v2.receiptPath(root, filename), 'utf8'), { code: 'ENOENT' });
}

function applyAdapterPatches(sourceBytes, patches) {
  let candidate = sourceBytes.toString('utf8');
  for (const patch of patches) {
    if (patch.kind === 'insert') {
      const first = candidate.indexOf(patch.anchor);
      assert.notEqual(first, -1);
      assert.equal(candidate.indexOf(patch.anchor, first + patch.anchor.length), -1);
      const point = patch.position === 'before' ? first : first + patch.anchor.length;
      candidate = `${candidate.slice(0, point)}${patch.content}${candidate.slice(point)}`;
      continue;
    }
    assert.fail(`Unexpected patch kind: ${patch.kind}`);
  }
  return Buffer.from(candidate);
}

test('MISSING rebuild persists VALID indexes without a receipt', async () => {
  const { root, filename } = await fixture();
  const before = await readFile(path.join(root, 'proposals', filename));
  const state = await v2.loadDocumentState(root, filename);

  await assertValidWithoutReceipt(root, filename, state);
  assert.equal(state.documentSha256, v2.sha256(before));
  assert.equal(state.derivedStateManifest.structuralIndexSha256, v2.sha256(JSON.stringify(state.structuralIndex)));
  assert.equal(state.derivedStateManifest.referenceIndexSha256, v2.sha256(JSON.stringify(state.referenceIndex)));
  assert.equal(state.derivedStateManifest.symbolIndexSha256, v2.sha256(JSON.stringify(state.symbolIndex)));
  assert.equal(state.derivedStateManifest.conceptIndexSha256, v2.sha256(JSON.stringify(state.conceptIndex)));
  assert.deepEqual(await readFile(path.join(root, 'proposals', filename)), before);
});

test('STALE state rebuild persists VALID indexes without a receipt', async () => {
  const { root, filename } = await fixture();
  const first = await v2.loadDocumentState(root, filename);
  const stale = await persistedState(root, filename);
  stale.manifest.documentSha256 = '0'.repeat(64);
  await writeFile(v2.derivedStatePath(root, filename), JSON.stringify(stale));
  await writeFile(path.join(root, 'proposals', filename), `${document}\nNueva línea.`);

  const rebuilt = await v2.loadDocumentState(root, filename);

  await assertValidWithoutReceipt(root, filename, rebuilt);
  assert.notEqual(rebuilt.documentSha256, first.documentSha256);
  assert.equal(rebuilt.derivedStateManifest.documentSha256, rebuilt.documentSha256);
});

test('CORRUPT state rebuild persists VALID indexes without a receipt', async () => {
  const { root, filename } = await fixture();
  await v2.loadDocumentState(root, filename);
  const corrupt = await persistedState(root, filename);
  const entry = corrupt.structuralIndex.entries[0];
  entry.endByte = 999999;
  corrupt.structuralIndex.byId[entry.entryId].endByte = 999999;
  corrupt.manifest.structuralIndexSha256 = v2.sha256(JSON.stringify(corrupt.structuralIndex));
  await writeFile(v2.derivedStatePath(root, filename), JSON.stringify(corrupt));

  const rebuilt = await v2.loadDocumentState(root, filename);

  await assertValidWithoutReceipt(root, filename, rebuilt);
  assert.notEqual(rebuilt.structuralIndex.entries[0].endByte, 999999);
});

test('rebuilt VALID state reloads and remains usable', async () => {
  const { root, filename } = await fixture();
  const rebuilt = await v2.loadDocumentState(root, filename);
  const reloaded = await v2.loadDocumentState(root, filename);

  await assertValidWithoutReceipt(root, filename, reloaded);
  assert.equal(reloaded.derivedStateManifest.createdAt, rebuilt.derivedStateManifest.createdAt);
  assert.deepEqual(
    reloaded.structuralIndex.entries.map((entry) => entry.entryId),
    rebuilt.structuralIndex.entries.map((entry) => entry.entryId),
  );
  assert.equal(
    reloaded.derivedStateManifest.structuralIndexSha256,
    rebuilt.derivedStateManifest.structuralIndexSha256,
  );
  assert.ok(v2.resolveTargets(reloaded, 'eq:uno').length > 0);
});

test('later publication from VALID source persists COMMITTED state and receipt', async () => {
  const { root, filename } = await fixture();
  const source = await v2.loadDocumentState(root, filename);
  const selectedEntryId = source.structuralIndex.entries.find((entry) => entry.type === 'paragraph').entryId;
  const adapter = {
    async publishSuccessor(input) {
      const publishedBytes = applyAdapterPatches(
        await readFile(path.join(root, 'proposals', input.sourceFilename)),
        input.patches,
      );
      const targetFilename = 'research-concept-r02.md';
      await writeFile(path.join(root, 'proposals', targetFilename), publishedBytes);
      return {
        operationId: 'recovery-publication-test',
        sourceFilename: input.sourceFilename,
        sourceSha256: input.sourceSha256,
        targetFilename,
        targetRevision: 'r02',
        publishedSha256: v2.sha256(publishedBytes),
        publishedBytes,
        patchCount: input.patches.length,
        workspaceEvidence: { published: true },
        guardEvidence: { complete: { decision: 'allowed' } },
      };
    },
  };

  const result = await new v2.ProposalDeliberationOrchestrator(root, adapter).execute({
    instruction: 'inserta una nota literal después del párrafo seleccionado',
    selectedEntryId,
    literalContent: '\n\nRecovery publication note.\n',
  });

  assert.equal(result.status, 'published', JSON.stringify(result));
  const committed = await persistedState(root, 'research-concept-r02.md');
  const receipt = JSON.parse(await readFile(v2.receiptPath(root, 'research-concept-r02.md'), 'utf8'));
  assert.equal(committed.manifest.status, 'COMMITTED');
  assert.equal(receipt.targetFilename, 'research-concept-r02.md');
  assert.equal(receipt.documentShaAfter, committed.manifest.documentSha256);
  assert.equal((await v2.loadDocumentState(root, 'research-concept-r02.md')).derivedStateStatus, 'COMMITTED');
});

test('COMMITTED state without a publication receipt remains rejected', async () => {
  const { root, filename } = await fixture();
  const state = await v2.loadDocumentState(root, filename);
  const invalid = await persistedState(root, filename);
  invalid.manifest.status = 'COMMITTED';
  await writeFile(v2.derivedStatePath(root, filename), JSON.stringify(invalid));

  const bytes = await readFile(path.join(root, 'proposals', filename));
  assert.equal(await v2.loadDerivedState(root, filename, state.documentSha256, state.parserVersion, bytes), undefined);
  const audit = await v2.runConsistencyAudit({ projectRoot: root });
  assert.equal(audit.status, 'FAIL');
  assert.ok(audit.failures.includes(`COMMITTED_WITHOUT_RECEIPT:${filename}`));
});

test('rebuild invents no publication or operation evidence', async () => {
  const { root, filename } = await fixture();
  const state = await v2.loadDocumentState(root, filename);
  const stored = await persistedState(root, filename);

  await assertValidWithoutReceipt(root, filename, state);
  for (const key of ['receipt', 'operationId', 'sourceRevision', 'patchIds']) {
    assert.equal(Object.hasOwn(state, key), false);
    assert.equal(Object.hasOwn(stored, key), false);
    assert.equal(Object.hasOwn(stored.manifest, key), false);
  }
});
