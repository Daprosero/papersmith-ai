import { constants } from 'node:fs';
import { lstat, mkdir, open, realpath, rm } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, join, resolve } from 'node:path';
import { InitialRevisionRenderer, type InitialRevisionGuideFragment } from './initial-revision-renderer.js';
import type { CanonicalProposalMetadata } from './revision-domain.js';
import { commitDerivedState, saveRevisionReceipt } from './derived-state-store.js';
import { rebuildDerivedState } from './derived-state-builder.js';
import { parseManagedRevisionFilename } from './revision-lifecycle-store.js';
import type { ManagedInitialRevisionReceipt } from './revision-receipt.js';
import { artifact, initialRevisionFilename, isInitialRevision } from './artifact-naming.js';
import { violations as canonicalFormViolations } from './preservation.js';
import type { PreservationViolation } from './types.js';

export type { InitialRevisionGuideFragment };

const MANAGED_ARTIFACT_MARKER = artifact.marker;

function sha256(bytes: Buffer): string {
	return createHash('sha256').update(bytes).digest('hex');
}

/** Explicit v1 candidate produced from the caller's idea+guide (spec I1, I2, I5); never the fixed scientific-workflow `CreateR01PayloadV1` contract. */
export type InitialRevisionCandidate = {
	filename: string;
	/** The profile's own first-revision label (`artifact.revisionLabel(1)`), never a literal: the file is named by that label too, and a caller that read a fixed `'r01'` here got a label the document on disk does not carry. A TypeScript literal cannot depend on a runtime profile value, and this project runs no type checker at all, so the guard is a domain's own initial-revision test suite, never this annotation. */
	revision: string;
	markdown: string;
	canonicalMetadata: CanonicalProposalMetadata;
};

/** Injectable seam (HARD test-isolation constraint): lets callers check "does a managed proposal already exist" without any real filesystem access. */
export type InitialRevisionExistingProposalPort = { hasManagedProposal(): Promise<boolean> };

export type InitialRevisionPublicationResult = { filename: string; revision: string; documentSha256: string; bytesWritten: number };

/** Injectable seam (HARD test-isolation constraint): lets tests capture the rendered candidate in memory instead of writing a real proposal `.md`. */
export type InitialRevisionPublicationPort = { publish(candidate: InitialRevisionCandidate): Promise<InitialRevisionPublicationResult> };

export type CreateInitialRevisionInput = { idea: string; guideFragments?: readonly InitialRevisionGuideFragment[] };

export type CreateInitialRevisionResult =
	| { status: 'created'; filename: string; revision: string; documentSha256: string; canonicalMetadata: CanonicalProposalMetadata; markdown: string }
	| { status: 'blocked'; code: 'INITIAL_IDEA_REQUIRED' | 'MANAGED_PROPOSAL_ALREADY_EXISTS' | 'INITIAL_IDEA_SINGLE_SENTENCE' }
	| { status: 'blocked'; code: 'INITIAL_REVISION_CANONICAL_FORM_VIOLATION'; violations: readonly PreservationViolation[] };

/**
 * Explicit, user-triggered creation of the first managed proposal (spec I1). Never auto-bootstraps:
 * it only ever runs when a caller explicitly invokes it, and it always refuses -- rather than
 * overwriting or duplicating -- whenever a managed proposal already exists. Composes
 * `InitialRevisionRenderer.renderFromIdea` (idea + paper-guide, never a fixed generic skeleton) and
 * delegates persistence to an injected publication port so the full creation logic (existence check,
 * rendering, refusal) is unit-testable without touching a real filesystem.
 */
export class InitialRevisionCreationService {
	constructor(
		private readonly existingProposal: InitialRevisionExistingProposalPort,
		private readonly publication: InitialRevisionPublicationPort,
		private readonly renderer: InitialRevisionRenderer = new InitialRevisionRenderer(),
	) {}

	async execute(input: CreateInitialRevisionInput): Promise<CreateInitialRevisionResult> {
		const idea = input.idea?.trim();
		if (!idea) return { status: 'blocked', code: 'INITIAL_IDEA_REQUIRED' };
		if (await this.existingProposal.hasManagedProposal()) return { status: 'blocked', code: 'MANAGED_PROPOSAL_ALREADY_EXISTS' };
		const composed = this.renderer.renderFromIdea({ idea, guideFragments: input.guideFragments });
		// An idea with no second sentence collapses `title` and `sectionHeading` to the same
		// bytes, by construction: `sectionHeading`'s fallback chain ends in `sentences[0] ?? idea`,
		// which is character for character what `title` computes on the line above it
		// (`initial-revision-renderer.ts`). The document then goes out with `# X` and `## X`
		// identical, and what that costs was measured on both hosts:
		//
		//   a domain with no canonical-form rules of its own  v1 IS created, and can never be
		//       edited: every locus query against it is ambiguous and blocked, and a second
		//       CREATE is refused MANAGED_PROPOSAL_ALREADY_EXISTS. The only exit is moving
		//       files by hand, outside this engine entirely.
		//   a domain that declares them  the renderer's triplication trips that domain's OWN
		//       canonical form, so an idea obeying every rule its skill states cannot become
		//       v1 at all -- and the refusal blames the author for a repetition THIS ENGINE
		//       introduced.
		//
		// Refused here rather than repaired in the renderer: this engine cannot write a section
		// heading the author did not write. `sentences` splits on `(?<=[.!?])\s+`, so "one
		// sentence" means "no sentence-ending punctuation" -- newlines and blank lines do not
		// supply one, which is why an idea laid out over several lines still collapses.
		if (composed.canonicalMetadata.title === composed.canonicalMetadata.sectionHeading) {
			return { status: 'blocked', code: 'INITIAL_IDEA_SINGLE_SENTENCE' };
		}
		// Canonical form, over the COMPOSED v1 rather than over the idea alone.
		//
		// Every other publication path in this engine runs `validateCandidate`, whose
		// `canonicalForm` term is exactly this rule set, before a byte is written. This one ran
		// nothing: `renderFromIdea` injects each declared source's fragment VERBATIM, so
		// whatever a source document happens to contain -- a report table already carrying
		// numbers, a URL nobody verified -- became v1 unexamined, and only a later successor
		// whose locus happened to cover that region would ever notice. For a domain whose whole
		// canonical form is "this document plans work that has not happened", that is the exact
		// failure the gate exists to prevent, and it is silent.
		//
		// `violations` and not `delta`: a violation is never an intentional change, so it
		// blocks outright rather than asking for an acknowledgement (`preservation.ts`). There
		// is nothing to acknowledge at v1 anyway -- no predecessor exists, so no atom can be
		// lost. A profile whose rule set recognizes nothing here returns `[]` and this is a
		// no-op, which is why the mathematical domain is unaffected.
		const violations = canonicalFormViolations(composed.markdown);
		if (violations.length) return { status: 'blocked', code: 'INITIAL_REVISION_CANONICAL_FORM_VIOLATION', violations };
		const filename = initialRevisionFilename(composed.slug);
		if (!isInitialRevision(filename)) throw new Error('INITIAL_REVISION_FILENAME_INVALID');
		const candidate: InitialRevisionCandidate = { filename, revision: artifact.revisionLabel(1), markdown: composed.markdown, canonicalMetadata: composed.canonicalMetadata };
		let published: InitialRevisionPublicationResult;
		try {
			published = await this.publication.publish(candidate);
		} catch (error) {
			// Re-audit cleanup (issue #7): a concurrent winner (same OR a differently-slugged idea) may have
			// committed the project's single managed proposal between our pre-check above and this call's own
			// atomic publish attempt. Surface the same clean blocked result the pre-check itself would have
			// returned, instead of letting the raw error propagate uncaught.
			if (error instanceof Error && error.message === 'MANAGED_PROPOSAL_ALREADY_EXISTS') return { status: 'blocked', code: 'MANAGED_PROPOSAL_ALREADY_EXISTS' };
			throw error;
		}
		return { status: 'created', filename: published.filename, revision: published.revision, documentSha256: published.documentSha256, canonicalMetadata: candidate.canonicalMetadata, markdown: candidate.markdown };
	}
}

async function canonicalProposalsDirectory(projectRoot: string): Promise<string> {
	const root = await realpath(resolve(projectRoot));
	const directory = resolve(root, artifact.directory);
	let existing: string | undefined;
	try {
		existing = await realpath(directory);
	} catch {
		existing = undefined;
	}
	if (existing === undefined) {
		await mkdir(directory, { recursive: true, mode: 0o700 });
		existing = await realpath(directory);
	}
	if (existing !== directory) throw new Error('PROPOSALS_DIRECTORY_UNSAFE');
	const info = await lstat(directory);
	if (!info.isDirectory() || info.isSymbolicLink()) throw new Error('PROPOSALS_DIRECTORY_UNSAFE');
	return directory;
}

function initialRevisionLockPath(root: string): string {
	return join(root, artifact.sidecarRoot, 'locks', 'initial-revision.lock');
}

/**
 * Re-audit cleanup (issue #7): a project-wide, slug-INDEPENDENT atomic single-winner guard.
 *
 * `hasManagedProposal`'s pre-check (in `proposal-workspace.ts`) and the target `.md`'s own O_EXCL
 * open (below) are each individually correct but not jointly sufficient: the pre-check is broad
 * (any managed file) but non-atomic with the write, while the O_EXCL write is atomic but keyed by
 * the exact SLUGGED filename. Two concurrent `CREATE_INITIAL_REVISION` calls with two DIFFERENT
 * ideas produce two different target filenames, so both could pass the pre-check and both O_EXCL
 * opens could succeed -- violating the single-managed-proposal invariant.
 *
 * This lock closes that gap: it is keyed by one FIXED path, independent of any slug, so only ONE
 * `open(..., O_EXCL)` on this exact path can ever succeed among any number of concurrent callers,
 * regardless of which idea (and therefore which target filename) each one carries. It is left in
 * place permanently on success -- mirroring the durable "a managed proposal now exists" invariant,
 * which is correctly permanent -- and released only when THIS attempt itself later fails, so a
 * legitimate retry after a failed write is never permanently locked out by our own failure.
 */
async function acquireInitialRevisionCreationLock(root: string): Promise<string> {
	const lockPath = initialRevisionLockPath(root);
	await mkdir(dirname(lockPath), { recursive: true, mode: 0o700 });
	let handle;
	try {
		handle = await open(lockPath, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW ?? 0), 0o600);
	} catch (error) {
		if ((error as NodeJS.ErrnoException).code === 'EEXIST') throw new Error('MANAGED_PROPOSAL_ALREADY_EXISTS');
		throw error;
	}
	try {
		await handle.writeFile(Buffer.from(JSON.stringify({ createdAt: new Date().toISOString() })));
		await handle.sync();
	} finally {
		await handle.close();
	}
	return lockPath;
}

async function releaseInitialRevisionCreationLock(lockPath: string): Promise<void> {
	try {
		await rm(lockPath, { force: true });
	} catch {
		// Best-effort release only: a leftover lock after a failed attempt merely blocks the next retry,
		// it never corrupts or duplicates any managed proposal.
	}
}

/**
 * Real filesystem publication port used by production wiring; writes the marker-prefixed managed
 * `.md` atomically and only when the target does not already exist (guarded further by the
 * project-wide single-winner lock above), then writes the derived-state and receipt sidecars in
 * the SAME layout ordinary edit/materialization publication produces (`derived-state-store.ts`'s
 * profile-derived state/<filename>.json COMMITTED manifest and receipts/<filename>.json
 * receipt) -- re-audit cleanup (issue #2). Without these sidecars, `readCanonicalManagedRevisionInventory`
 * (`revision-lifecycle-store.ts`) hard-requires a COMMITTED state json and reports the whole inventory as
 * `inconsistent`, degrading scientific-workflow admission for an otherwise perfectly valid, freshly
 * created first revision.
 */
export function createFilesystemInitialRevisionPublicationPort(projectRoot: string): InitialRevisionPublicationPort {
	return {
		async publish(candidate) {
			const directory = await canonicalProposalsDirectory(projectRoot);
			const lockPath = await acquireInitialRevisionCreationLock(projectRoot);
			try {
				const target = resolve(directory, candidate.filename);
				if (dirname(target) !== directory) throw new Error('INITIAL_REVISION_TARGET_ESCAPES_PROPOSALS_DIRECTORY');
				const output = Buffer.concat([MANAGED_ARTIFACT_MARKER, Buffer.from(candidate.markdown, 'utf8')]);
				let handle;
				try {
					handle = await open(target, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW ?? 0), 0o600);
				} catch (error) {
					if ((error as NodeJS.ErrnoException).code === 'EEXIST') throw new Error('MANAGED_PROPOSAL_ALREADY_EXISTS');
					throw error;
				}
				try {
					await handle.writeFile(output);
					await handle.sync();
					const written = await handle.stat();
					if (!written.isFile() || written.nlink !== 1 || written.size !== output.length) throw new Error('INITIAL_REVISION_WRITE_VERIFICATION_FAILED');
				} finally {
					await handle.close();
				}
				const documentSha256 = sha256(output);
				const lineage = parseManagedRevisionFilename(candidate.filename).lineage;
				const derived = await rebuildDerivedState(candidate.filename, candidate.revision, lineage, output);
				await commitDerivedState(projectRoot, derived);
				const receipt: ManagedInitialRevisionReceipt = {
					operation: 'CREATE_INITIAL_REVISION',
					targetRevision: candidate.revision,
					targetFilename: candidate.filename,
					documentShaAfter: documentSha256,
					derivedStateStatus: 'COMMITTED',
					createdAt: new Date().toISOString(),
				};
				await saveRevisionReceipt(projectRoot, candidate.filename, receipt);
				return { filename: candidate.filename, revision: candidate.revision, documentSha256, bytesWritten: output.length };
			} catch (error) {
				await releaseInitialRevisionCreationLock(lockPath);
				throw error;
			}
		},
	};
}
