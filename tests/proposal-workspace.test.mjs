import { ENGINE_MODULE_ROOT } from "./_engine-module-root.mjs";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { access, link, mkdtemp, mkdir, readFile, realpath, readdir, rename, stat, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const piRoot = ENGINE_MODULE_ROOT;
const { createJiti } = await import(
	pathToFileURL(path.join(piRoot, "node_modules/jiti/lib/jiti.mjs")).href
);
const jiti = createJiti(import.meta.url, {
	alias: {
		"@earendil-works/pi-coding-agent": path.join(piRoot, "dist/index.js"),
		"@earendil-works/pi-ai/compat": path.join(piRoot, "node_modules/@earendil-works/pi-ai/dist/compat.js"),
		"@earendil-works/pi-ai": path.join(piRoot, "node_modules/@earendil-works/pi-ai/dist/index.js"),
		typebox: path.join(piRoot, "node_modules/typebox/build/index.mjs"),
	},
});
const extensionPath = path.resolve(".claude/skills/_core/deliberation/engine/proposal-workspace.ts");
const extension = await jiti.import(extensionPath);
const artifactMarker = "<!-- proposal-workspace:artifact:v1 -->\n";
const fixedCredaBase = String.raw`# CREDA base

Inline source math \(x + 1\) must normalize.

$$
E = mc^2.
\tag{1}
$$

## Unique insertion section

Repeated prose anchor.
Repeated prose anchor.

Second inline fragment \(\alpha = 2\).

$$
\begin{aligned}
a &= b + c\\
d &= e
\end{aligned}
\label{eq:ksc}
\tag{2}
$$
`;
const movableDisplayCredaBase = String.raw`# CREDA display moves

## Section 2.3

Source introduction stays.

Source explanation moves with both selected displays.

$$
q_{23} = 23.
\tag{23}
$$

The adjacency rationale also moves.

$$
q_{24} = 24.
\tag{24}
$$

Source conclusion stays.

## Section 3.1

An intervening inherited display remains in place.

$$
q_{31} = 31.
\tag{31}
$$

## Section 3.3

Target introduction stays.

Target anchor paragraph.

$$
q_{33} = 33.
\tag{33}
$$
`;
const movableSourceBlock = String.raw`Source explanation moves with both selected displays.

$$
q_{23} = 23.
\tag{23}
$$

The adjacency rationale also moves.

$$
q_{24} = 24.
\tag{24}
$$
`;
const tripleDisplayMoveBase = String.raw`# CREDA triple display move

## Source

Source introduction stays.

Source prose moves before the displays.

$$
q_{10} = 10.
\tag{10}
$$

$$
q_{11} = 11.
\tag{11}
$$

$$
q_{12} = 12.
\tag{12}
$$

Source prose moves after the displays.

Source conclusion stays.

## Intervening

$$
q_{20} = 20.
\tag{20}
$$

## Target

Target anchor paragraph.

$$
q_{30} = 30.
\tag{30}
$$
`;
const tripleDisplaySourceBlock = String.raw`Source prose moves before the displays.

$$
q_{10} = 10.
\tag{10}
$$

$$
q_{11} = 11.
\tag{11}
$$

$$
q_{12} = 12.
\tag{12}
$$

Source prose moves after the displays.
`;
const tripleMoveGroupOne = String.raw`Source prose moves before the displays.

$$
q_{10} = 10.
\tag{10}
$$

$$
q_{11} = 11.
\tag{11}
$$
`;
const tripleMoveGroupTwo = String.raw`$$
q_{12} = 12.
\tag{12}
$$

Source prose moves after the displays.
`;
const flatDomainCredaBase = String.raw`# CREDA flat domains

## Flat domain definitions

$$
\mathcal D^s = \{(x_i^s,y_i^s)\}_{i=1}^{n_s}.
\tag{10}
$$

$$
\mathcal D^t = \{x_j^t\}_{j=1}^{n_t}.
\tag{11}
$$

The retained construction maps \mathcal D^s into \mathcal D^t.

## Remaining model

$$
f(x)=x.
\tag{12}
$$
`;
const flatSourceDisplay = "$$\n\\mathcal D^s = \\{(x_i^s,y_i^s)\\}_{i=1}^{n_s}.\n\\tag{10}\n$$\n";
const flatTargetDisplay = "$$\n\\mathcal D^t = \\{x_j^t\\}_{j=1}^{n_t}.\n\\tag{11}\n$$\n";

const sectionedCredaBase = String.raw`# CREDA sections

Introductory bytes stay exact.

~~~markdown
## Not a parsed section
~~~

## Section 3

Section three survives.

$$
s_3 = 3.
\tag{3}
$$

## Section 4

Section four is removed.

$$
s_4 = 4.
\tag{4}
$$

### Section 4.1

Nested section content is removed with Section 4.

## Section 5

Section five is removed.

$$
s_5 = 5.
\tag{5}
$$

## Section 6

Section six is removed.

$$
s_6 = 6.
\tag{6}
$$

## Section 7

Section seven survives.

$$
s_7 = 7.
\tag{7}
$$
`;

async function fixture() {
	const root = await mkdtemp(path.join(os.tmpdir(), "proposal-workspace-"));
	await mkdir(path.join(root, "guidance/paper-guide/guide"), { recursive: true });
	await mkdir(path.join(root, "guidance/reference-papers"), { recursive: true });
	await mkdir(path.join(root, "proposals"), { recursive: true });
	await writeFile(path.join(root, "guidance/paper-guide/guide/guide.md"), "eligible guide\n", "utf8");
	await writeFile(path.join(root, "guidance/reference-papers/secret.md"), "forbidden corpus\n", "utf8");
	await writeFile(path.join(root, "proposals/base.md"), "immutable base\n", "utf8");
	await writeFile(path.join(root, "proposals/matematica_propuesta_CREDA.md"), fixedCredaBase, "utf8");
	return root;
}

async function sectionFixture() {
	const root = await fixture();
	await writeFile(
		path.join(root, "proposals/matematica_propuesta_CREDA.md"),
		sectionedCredaBase,
		"utf8",
	);
	return root;
}

function toolFor(root, options) {
	return extension.createProposalWorkspaceTool(root, options);
}

async function execute(tool, params, ctx) {
	return tool.execute("test-call", params, undefined, undefined, ctx);
}

function uiContext(confirm) {
	return {
		hasUI: true,
		ui: { confirm },
	};
}

async function text(result) {
	return result.content.map((item) => item.text).join("\n");
}

async function createManagedLatest(root, tool, slug, content) {
	await execute(tool, { action: "write", resource: "proposal", slug, content });
	const target = `research-concept-${slug}.md`;
	const bytes = await readFile(path.join(root, "proposals", target));
	return {
		source: {
			target,
			sha256: createHash("sha256").update(bytes).digest("hex"),
		},
	};
}

async function candidateFailure(promise, target, code) {
	let failure;
	try {
		await promise;
		assert.fail("candidate validation must reject invalid composed bytes");
	} catch (error) {
		failure = error;
	}
	assert.equal(failure.candidateValidation?.status, "failed");
	assert.equal(failure.candidateValidation?.phase, "pre-publish");
	assert.equal(failure.candidateValidation?.code, code);
	assert.match(failure.message, /candidate validation failed.*"phase":"pre-publish"/i);
	await assert.rejects(readFile(target), (error) => error?.code === "ENOENT");
	return failure;
}

test("inventories and reads a guide", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const inventory = await execute(tool, { action: "inventory", resource: "guides" });
	assert.match(await text(inventory), /guide\.md/);

	const guide = await execute(tool, { action: "read", resource: "guide", name: "guide.md" });
	assert.equal(await text(guide), "eligible guide\n");
});

test("reads only a marker-owned generated draft with its exact complete-file SHA through the bounded managed target route", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const body = `# Managed draft\n\n${"mathematics\n".repeat(6_000)}`;
	const name = "research-concept-subject-bag-creda-integrated-r03.md";
	await execute(tool, {
		action: "write",
		resource: "proposal",
		slug: "subject-bag-creda-integrated-r03",
		content: body,
	});
	const sourceBytes = await readFile(path.join(root, "proposals", name));

	const result = await execute(tool, {
		action: "read",
		resource: "managed_target",
		name,
	});
	assert.match(await text(result), /^<!-- proposal-workspace:artifact:v1 -->\n# Managed draft/);
	assert.match(await text(result), /output truncated at 65536 bytes/);
	assert.equal(result.details.resource, name);
	assert.equal(
		result.details.sha256,
		createHash("sha256").update(sourceBytes).digest("hex"),
	);
	assert.equal(result.details.bytesReturned, 64 * 1024);
	assert.equal(result.details.truncated, true);
});

test("managed target reads reject an unmarked manual matching-name draft", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-manual-r01.md");
	const manualBytes = Buffer.from("# Manual matching-name draft\n", "utf8");
	await writeFile(target, manualBytes);

	await assert.rejects(
		execute(tool, {
			action: "read",
			resource: "managed_target",
			name: "research-concept-manual-r01.md",
		}),
		/proposal_workspace blocked:.*not marked as a tool-created artifact/i,
	);
	assert.deepEqual(await readFile(target), manualBytes);
});

test("managed target reads reject traversal, bases, arbitrary proposals, and symlinks", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	for (const name of [
		"../research-concept-escape-r01.md",
		"guidance/reference-papers/research-concept-secret-r01.md",
		"base.md",
		"manual-proposal.md",
	]) {
		await assert.rejects(
			execute(tool, { action: "read", resource: "managed_target", name }),
			/proposal_workspace blocked:.*managed target/i,
		);
	}

	const external = await mkdtemp(path.join(os.tmpdir(), "proposal-workspace-managed-read-external-"));
	const externalTarget = path.join(external, "owned-looking.md");
	await writeFile(externalTarget, `${artifactMarker}# External\n`, "utf8");
	await symlink(
		externalTarget,
		path.join(root, "proposals/research-concept-symlinked-r01.md"),
	);
	await assert.rejects(
		execute(tool, {
			action: "read",
			resource: "managed_target",
			name: "research-concept-symlinked-r01.md",
		}),
		/proposal_workspace blocked:.*symbolic link/i,
	);
});

test("blocks traversal and the forbidden reference corpus", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	await assert.rejects(
		execute(tool, { action: "read", resource: "guide", name: "../secret.md" }),
		/proposal_workspace blocked:.*filename/i,
	);
	await assert.rejects(
		execute(tool, {
			action: "read",
			resource: "guide",
			name: "..\/..\/reference-papers\/secret.md",
		}),
		/proposal_workspace blocked:.*guide reads accept only/i,
	);
});

test("blocks file and directory symlink escapes", async () => {
	const root = await fixture();
	const external = await mkdtemp(path.join(os.tmpdir(), "proposal-workspace-external-"));
	await writeFile(path.join(external, "escape.md"), "external\n", "utf8");
	await mkdir(path.join(root, "guidance/paper-guide/escape"), { recursive: true });
	await symlink(
		path.join(external, "escape.md"),
		path.join(root, "guidance/paper-guide/escape/escape.md"),
	);
	const tool = toolFor(root);
	await assert.rejects(
		execute(tool, { action: "read", resource: "guide", name: "escape.md" }),
		/proposal_workspace blocked:.*symbolic link/i,
	);

	const linkedRoot = await mkdtemp(path.join(os.tmpdir(), "proposal-workspace-linked-"));
	await mkdir(path.join(linkedRoot, "guidance"), { recursive: true });
	await mkdir(path.join(linkedRoot, "proposals"), { recursive: true });
	await symlink(path.join(root, "guidance/paper-guide"), path.join(linkedRoot, "guidance/paper-guide"));
	const linkedTool = toolFor(linkedRoot);
	await assert.rejects(
		execute(linkedTool, { action: "inventory", resource: "guides" }),
		/proposal_workspace blocked:.*symbolic-link component/i,
	);
});

test("never overwrites a base through write inputs or a hard-linked target", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "proposal",
			slug: "../base",
			content: "changed\n",
		}),
		/proposal_workspace blocked:.*slug/i,
	);
	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "base",
			name: "base.md",
			content: "changed\n",
		}),
		/proposal_workspace blocked:.*action\/resource/i,
	);
	await link(
		path.join(root, "proposals/base.md"),
		path.join(root, "proposals/research-concept-linked-base.md"),
	);
	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "proposal",
			slug: "linked-base",
			content: "changed\n",
		}),
		/proposal_workspace blocked:.*standalone/i,
	);
	assert.equal(await readFile(path.join(root, "proposals/base.md"), "utf8"), "immutable base\n");
});

test("creates only a valid new research-concept target without authorization", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-safe-topic.md");
	const created = await execute(tool, {
		action: "write",
		resource: "proposal",
		slug: "safe-topic",
		content: "# First\n",
	});
	assert.match(await text(created), /proposals\/research-concept-safe-topic\.md/);
	assert.equal(await readFile(target, "utf8"), `${artifactMarker}# First\n`);
	await access(target);
});

test("atomically derives the fixed CREDA base with base-only inline normalization and an additive insertion", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-creda-exact-r06.md");
	const insertion = String.raw`
### Additive note

Inserted inline syntax \(z\) stays byte-exact.

`;
	const result = await execute(tool, {
		action: "derive",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-exact-r06",
		insertions: [
			{
				id: "additive-note",
				anchor: "## Unique insertion section\n",
				position: "after",
				content: insertion,
			},
		],
	});

	const output = await readFile(target, "utf8");
	assert.ok(output.startsWith(artifactMarker));
	assert.match(output, /Inline source math \$x \+ 1\$ must normalize\./);
	assert.match(output, /Second inline fragment \$\\alpha = 2\$\./);
	assert.ok(output.includes(`## Unique insertion section\n${insertion}`));
	assert.ok(output.includes(String.raw`Inserted inline syntax \(z\) stays byte-exact.`));
	assert.equal(result.details.operation, "derive");
	assert.equal(result.details.base, "proposals/matematica_propuesta_CREDA.md");
	assert.equal(result.details.inlineNormalizationCount, 2);
	assert.equal(result.details.displayBlocksPreserved, 2);
	assert.equal(result.details.numberedEquationsPreserved, 2);
	assert.equal(result.details.insertionCount, 1);
	assert.equal(result.details.candidateValidation.status, "passed");
	assert.equal(result.details.candidateValidation.phase, "pre-publish");
	assert.equal(result.details.candidateValidation.wroteTargetBeforeValidation, false);
	assert.equal(result.details.continuityValidation.status, "not-requested");
	assert.match(result.details.sha256, /^[a-f0-9]{64}$/);
});

test("derive rejects omission of an exact block protected by the latest managed target", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const protectedBlock = "Protected accepted current-state block.\n";
	const manifest = await createManagedLatest(
		root,
		tool,
		"continuity-required-r01",
		`${fixedCredaBase}\n${protectedBlock}`,
	);
	manifest.required = [{ id: "retained-current-block", block: protectedBlock }];
	const target = path.join(root, "proposals/research-concept-continuity-required-r02.md");

	const failure = await candidateFailure(
		execute(tool, {
			action: "derive",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "continuity-required-r02",
			insertions: [{ id: "unrelated-note", position: "end", content: "\nUnrelated new note.\n" }],
			continuityManifest: manifest,
		}),
		target,
		"continuity-required-block-count",
	);
	assert.equal(failure.candidateValidation.itemId, "retained-current-block");
	assert.equal(failure.candidateValidation.expectedCount, 1);
	assert.equal(failure.candidateValidation.actualCount, 0);
});

test("derive rejects reintroduction of an exact block removed from the latest managed target", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const removedBlock = "Previously removed current-state block.\n";
	await writeFile(
		path.join(root, "proposals/matematica_propuesta_CREDA.md"),
		`${fixedCredaBase}\n${removedBlock}`,
		"utf8",
	);
	const manifest = await createManagedLatest(root, tool, "continuity-forbidden-r01", fixedCredaBase);
	manifest.forbidden = [{ id: "prior-removal", block: removedBlock }];
	const target = path.join(root, "proposals/research-concept-continuity-forbidden-r02.md");

	const failure = await candidateFailure(
		execute(tool, {
			action: "derive",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "continuity-forbidden-r02",
			insertions: [{ id: "unrelated-note", position: "end", content: "\nUnrelated new note.\n" }],
			continuityManifest: manifest,
		}),
		target,
		"continuity-forbidden-block-count",
	);
	assert.equal(failure.candidateValidation.itemId, "prior-removal");
	assert.equal(failure.candidateValidation.expectedCount, 0);
	assert.equal(failure.candidateValidation.actualCount, 1);
});

test("derive_revision accepts an exact supersession bound to the latest managed bytes", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const priorBlock = "Repeated prose anchor.\nRepeated prose anchor.\n";
	const successorBlock = "Accepted successor prose block.\n";
	const manifest = await createManagedLatest(root, tool, "continuity-supersession-r01", fixedCredaBase);
	manifest.supersessions = [
		{ id: "accepted-supersession", priorBlock, successorBlock },
	];

	const result = await execute(tool, {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "continuity-supersession-r02",
		replacements: [
			{
				id: "replace-prior-block",
				oldText: priorBlock,
				newText: successorBlock,
				authorizedEquations: [],
			},
		],
		continuityManifest: manifest,
	});

	const output = await readFile(
		path.join(root, "proposals/research-concept-continuity-supersession-r02.md"),
		"utf8",
	);
	assert.equal(output.includes(priorBlock), false);
	assert.equal(output.split(successorBlock).length - 1, 1);
	assert.equal(result.details.continuityValidation.status, "passed");
	assert.equal(result.details.continuityValidation.phase, "pre-publish");
	assert.equal(result.details.continuityValidation.supersessionCount, 1);
	assert.equal(result.details.continuityValidation.source.target, manifest.source.target);
	assert.equal(result.details.continuityValidation.source.sha256, manifest.source.sha256);
});

test("continuity manifests reject unsafe, stale, unowned, and duplicate-id sources before publication", async () => {
	{
		const root = await fixture();
		const tool = toolFor(root);
		const target = path.join(root, "proposals/research-concept-continuity-unsafe-r02.md");
		const failure = await candidateFailure(
			execute(tool, {
				action: "derive",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: "continuity-unsafe-r02",
				insertions: [{ id: "note", position: "end", content: "\nNote.\n" }],
				continuityManifest: {
					source: { target: "../research-concept-continuity-unsafe-r01.md", sha256: "0".repeat(64) },
					required: [{ id: "unsafe-source", block: "block\n" }],
				},
			}),
			target,
			"continuity-source-identity",
		);
		assert.equal(failure.candidateValidation.itemId, "source");
	}

	{
		const root = await fixture();
		const tool = toolFor(root);
		const manifest = await createManagedLatest(root, tool, "continuity-stale-r01", fixedCredaBase);
		manifest.source.sha256 = "0".repeat(64);
		manifest.required = [{ id: "base-heading", block: "# CREDA base\n" }];
		const target = path.join(root, "proposals/research-concept-continuity-stale-r02.md");
		const failure = await candidateFailure(
			execute(tool, {
				action: "derive",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: "continuity-stale-r02",
				insertions: [{ id: "note", position: "end", content: "\nNote.\n" }],
				continuityManifest: manifest,
			}),
			target,
			"continuity-source-stale",
		);
		assert.equal(failure.candidateValidation.itemId, "source");
	}

	{
		const root = await fixture();
		const tool = toolFor(root);
		const manifest = await createManagedLatest(root, tool, "continuity-old-r01", fixedCredaBase);
		await createManagedLatest(root, tool, "continuity-old-r02", `${fixedCredaBase}\nNewer accepted state.\n`);
		manifest.required = [{ id: "base-heading", block: "# CREDA base\n" }];
		const target = path.join(root, "proposals/research-concept-continuity-old-r03.md");
		const failure = await candidateFailure(
			execute(tool, {
				action: "derive",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: "continuity-old-r03",
				insertions: [{ id: "note", position: "end", content: "\nNote.\n" }],
				continuityManifest: manifest,
			}),
			target,
			"continuity-source-stale",
		);
		assert.equal(failure.candidateValidation.itemId, "source");
		assert.deepEqual(failure.candidateValidation.newerTargets, ["research-concept-continuity-old-r02.md"]);
	}

	{
		const root = await fixture();
		const tool = toolFor(root);
		const sourceTarget = "research-concept-continuity-unowned-r01.md";
		const sourceBytes = Buffer.from(`${artifactMarker.replace("artifact:v1", "artifact:v0")}# Manual\n`, "utf8");
		await writeFile(path.join(root, "proposals", sourceTarget), sourceBytes);
		const target = path.join(root, "proposals/research-concept-continuity-unowned-r02.md");
		const failure = await candidateFailure(
			execute(tool, {
				action: "derive",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: "continuity-unowned-r02",
				insertions: [{ id: "note", position: "end", content: "\nNote.\n" }],
				continuityManifest: {
					source: { target: sourceTarget, sha256: createHash("sha256").update(sourceBytes).digest("hex") },
					required: [{ id: "manual-heading", block: "# Manual\n" }],
				},
			}),
			target,
			"continuity-source-unowned",
		);
		assert.equal(failure.candidateValidation.itemId, "source");
	}

	{
		const root = await fixture();
		const tool = toolFor(root);
		const manifest = await createManagedLatest(root, tool, "continuity-duplicate-r01", fixedCredaBase);
		manifest.required = [{ id: "duplicate-item", block: "# CREDA base\n" }];
		manifest.forbidden = [{ id: "duplicate-item", block: "Never present.\n" }];
		const target = path.join(root, "proposals/research-concept-continuity-duplicate-r02.md");
		const failure = await candidateFailure(
			execute(tool, {
				action: "derive",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: "continuity-duplicate-r02",
				insertions: [{ id: "note", position: "end", content: "\nNote.\n" }],
				continuityManifest: manifest,
			}),
			target,
			"continuity-manifest-shape",
		);
		assert.equal(failure.candidateValidation.itemId, "duplicate-item");
	}
});

test("derive_successor accepts the marker-owned root r01 only as root r02 using the managed read SHA", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const sourceBody = "# Root proposal\n\nOld root statement.\n";
	const sourcePattern = new RegExp(tool.parameters.properties.source.pattern);
	assert.equal(sourcePattern.test("research-concept-r01.md"), true);
	assert.equal(sourcePattern.test("research-concept-named-r01.md"), true);
	await execute(tool, {
		action: "write",
		resource: "proposal",
		slug: "r01",
		content: sourceBody,
	});
	const sourceRead = await execute(tool, {
		action: "read",
		resource: "managed_target",
		name: "research-concept-r01.md",
	});
	const result = await execute(tool, {
		action: "derive_successor",
		resource: "proposal",
		source: sourceRead.details.resource,
		sourceSha256: sourceRead.details.sha256,
		slug: "r02",
		patches: [
			{
				id: "replace-root-statement",
				kind: "replace",
				oldText: "Old root statement.",
				newText: "New root statement.",
			},
		],
	});

	assert.equal(result.details.source, "proposals/research-concept-r01.md");
	assert.equal(result.details.sourceSha256, sourceRead.details.sha256);
	assert.equal(result.details.target, "proposals/research-concept-r02.md");
	assert.equal(
		await readFile(path.join(root, "proposals/research-concept-r02.md"), "utf8"),
		`${artifactMarker}${sourceBody.replace("Old root statement.", "New root statement.")}`,
	);
});

test("derive_successor rejects root skips and cross-lineage/root transitions", async () => {
	{
		const root = await fixture();
		const tool = toolFor(root);
		const source = await createManagedLatest(root, tool, "r01", "# Root\n\nOld.\n");
		for (const slug of ["r03", "named-r02"]) {
			await candidateFailure(
				execute(tool, {
					action: "derive_successor",
					resource: "proposal",
					source: source.source.target,
					sourceSha256: source.source.sha256,
					slug,
					patches: [{ id: "replace-old", kind: "replace", oldText: "Old.", newText: "New." }],
				}),
				path.join(root, `proposals/research-concept-${slug}.md`),
				"successor-lineage-identity",
			);
		}
	}
	{
		const root = await fixture();
		const tool = toolFor(root);
		const source = await createManagedLatest(root, tool, "named-r01", "# Named\n\nOld.\n");
		await candidateFailure(
			execute(tool, {
				action: "derive_successor",
				resource: "proposal",
				source: source.source.target,
				sourceSha256: source.source.sha256,
				slug: "r02",
				patches: [{ id: "replace-old", kind: "replace", oldText: "Old.", newText: "New." }],
			}),
			path.join(root, "proposals/research-concept-r02.md"),
			"successor-lineage-identity",
		);
	}
});

test("derive_successor replaces one exact block while preserving every surrounding source byte", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const sourceBody = "# Current proposal\n\nBefore bytes stay exact.\n\n## Selected block\n\nOld mathematical statement.\n\nAfter bytes stay exact.\n";
	const manifest = await createManagedLatest(root, tool, "current-state-r01", sourceBody);
	const oldText = "## Selected block\n\nOld mathematical statement.\n";
	const newText = "## Selected block\n\nNew researcher-authorized statement.\n";
	const result = await execute(tool, {
		action: "derive_successor",
		resource: "proposal",
		source: manifest.source.target,
		sourceSha256: manifest.source.sha256,
		slug: "current-state-r02",
		patches: [{ id: "replace-selected-block", kind: "replace", oldText, newText }],
	});

	const output = await readFile(
		path.join(root, "proposals/research-concept-current-state-r02.md"),
		"utf8",
	);
	assert.equal(output, `${artifactMarker}${sourceBody.replace(oldText, newText)}`);
	assert.equal(result.details.operation, "derive_successor");
	assert.equal(result.details.source, `proposals/${manifest.source.target}`);
	assert.equal(result.details.sourceSha256, manifest.source.sha256);
	assert.equal(result.details.target, "proposals/research-concept-current-state-r02.md");
	assert.deepEqual(result.details.patchIds, ["replace-selected-block"]);
	assert.equal(result.details.patchCount, 1);
	assert.equal(result.details.unchangedByteCoverage.verified, true);
	assert.equal(result.details.candidateValidation.status, "passed");
	assert.equal(
		result.details.candidateValidation.untouchedRegionInvariant.unchangedBytes,
		result.details.unchangedByteCoverage.unchangedBytes,
	);
});

test("derive_successor supports one narrowly anchored additive insertion", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const sourceBody = "# Current proposal\n\nStable opening.\n\nStable closing.\n";
	const manifest = await createManagedLatest(root, tool, "current-insert-r01", sourceBody);
	const content = "\n## Added result\n\nResearcher-authorized addition.\n";
	const result = await execute(tool, {
		action: "derive_successor",
		resource: "proposal",
		source: manifest.source.target,
		sourceSha256: manifest.source.sha256,
		slug: "current-insert-r02",
		patches: [
			{
				id: "insert-result",
				kind: "insert",
				anchor: "Stable opening.\n",
				position: "after",
				content,
			},
		],
	});
	const output = await readFile(
		path.join(root, "proposals/research-concept-current-insert-r02.md"),
		"utf8",
	);
	assert.equal(
		output,
		`${artifactMarker}${sourceBody.replace("Stable opening.\n", `Stable opening.\n${content}`)}`,
	);
	assert.equal(result.details.candidateValidation.markdownBlockSafety, true);
});

test("derive_successor rejects block-scoped replacements that fuse Markdown boundaries", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const sourceBody = "# Current proposal\n\n## Selected block\n\nOld statement.\n\nFollowing block.\n";
	const manifest = await createManagedLatest(root, tool, "block-safety-r01", sourceBody);
	await candidateFailure(
		execute(tool, {
			action: "derive_successor",
			resource: "proposal",
			source: manifest.source.target,
			sourceSha256: manifest.source.sha256,
			slug: "block-safety-r02",
			patches: [
				{
					id: "fuse-following-block",
					kind: "replace",
					oldText: "## Selected block\n\nOld statement.\n\n",
					newText: "## Selected block\n\nNew statement.",
				},
			],
		}),
		path.join(root, "proposals/research-concept-block-safety-r02.md"),
		"successor-markdown-block-safety",
	);
});

test("derive_successor accepts a block replacement that preserves an existing one-line boundary", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const oldDisplay = "$$\nA=1.\n$$";
	const newDisplay = "$$\nA=2.\n$$";
	const sourceBody = `# Current proposal\n\n${oldDisplay}\nFollowing block.\n`;
	const manifest = await createManagedLatest(root, tool, "preserved-boundary-r01", sourceBody);
	const result = await execute(tool, {
		action: "derive_successor",
		resource: "proposal",
		source: manifest.source.target,
		sourceSha256: manifest.source.sha256,
		slug: "preserved-boundary-r02",
		patches: [
			{
				id: "replace-display",
				kind: "replace",
				oldText: oldDisplay,
				newText: newDisplay,
			},
		],
	});
	assert.equal(result.details.candidateValidation.markdownBlockSafety, true);
	assert.equal(
		await readFile(path.join(root, "proposals/research-concept-preserved-boundary-r02.md"), "utf8"),
		`${artifactMarker}${sourceBody.replace(oldDisplay, () => newDisplay)}`,
	);
});

test("derive_successor rejects a stale source SHA and leaves no target", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const manifest = await createManagedLatest(root, tool, "stale-successor-r01", "# State\n\nOld.\n");
	const target = path.join(root, "proposals/research-concept-stale-successor-r02.md");
	await candidateFailure(
		execute(tool, {
			action: "derive_successor",
			resource: "proposal",
			source: manifest.source.target,
			sourceSha256: "0".repeat(64),
			slug: "stale-successor-r02",
			patches: [{ id: "replace-old", kind: "replace", oldText: "Old.", newText: "New." }],
		}),
		target,
		"successor-source-stale",
	);
});

test("derive_successor rejects non-latest and unowned sources", async () => {
	{
		const root = await fixture();
		const tool = toolFor(root);
		const old = await createManagedLatest(root, tool, "latest-check-r01", "# State\n\nOld.\n");
		await createManagedLatest(root, tool, "latest-check-r02", "# State\n\nCurrent.\n");
		const target = path.join(root, "proposals/research-concept-latest-check-r03.md");
		await candidateFailure(
			execute(tool, {
				action: "derive_successor",
				resource: "proposal",
				source: old.source.target,
				sourceSha256: old.source.sha256,
				slug: "latest-check-r03",
				patches: [{ id: "replace-old", kind: "replace", oldText: "Old.", newText: "New." }],
			}),
			target,
			"continuity-source-stale",
		);
	}
	{
		const root = await fixture();
		const tool = toolFor(root);
		const source = "research-concept-unowned-successor-r01.md";
		const bytes = Buffer.from("# Manual source\n\nOld.\n", "utf8");
		await writeFile(path.join(root, "proposals", source), bytes);
		const target = path.join(root, "proposals/research-concept-unowned-successor-r02.md");
		await candidateFailure(
			execute(tool, {
				action: "derive_successor",
				resource: "proposal",
				source,
				sourceSha256: createHash("sha256").update(bytes).digest("hex"),
				slug: "unowned-successor-r02",
				patches: [{ id: "replace-old", kind: "replace", oldText: "Old.", newText: "New." }],
			}),
			target,
			"continuity-source-unowned",
		);
	}
});

test("derive_successor rejects ambiguous and overlapping patch manifests", async () => {
	{
		const root = await fixture();
		const tool = toolFor(root);
		const manifest = await createManagedLatest(
			root,
			tool,
			"ambiguous-successor-r01",
			"# State\n\nRepeated block.\n\nRepeated block.\n",
		);
		await candidateFailure(
			execute(tool, {
				action: "derive_successor",
				resource: "proposal",
				source: manifest.source.target,
				sourceSha256: manifest.source.sha256,
				slug: "ambiguous-successor-r02",
				patches: [{ id: "ambiguous", kind: "replace", oldText: "Repeated block.", newText: "Changed." }],
			}),
			path.join(root, "proposals/research-concept-ambiguous-successor-r02.md"),
			"successor-patch-ambiguous",
		);
	}
	{
		const root = await fixture();
		const tool = toolFor(root);
		const manifest = await createManagedLatest(
			root,
			tool,
			"overlap-successor-r01",
			"# State\n\nAlpha beta gamma.\n",
		);
		await candidateFailure(
			execute(tool, {
				action: "derive_successor",
				resource: "proposal",
				source: manifest.source.target,
				sourceSha256: manifest.source.sha256,
				slug: "overlap-successor-r02",
				patches: [
					{ id: "wide", kind: "replace", oldText: "Alpha beta", newText: "Delta" },
					{ id: "nested", kind: "replace", oldText: "beta gamma", newText: "epsilon" },
				],
			}),
			path.join(root, "proposals/research-concept-overlap-successor-r02.md"),
			"successor-patch-overlap",
		);
	}
});

test("derive_successor rejects no-op patches and target collisions without changing files", async () => {
	{
		const root = await fixture();
		const tool = toolFor(root);
		const manifest = await createManagedLatest(root, tool, "noop-successor-r01", "# State\n\nSame.\n");
		await candidateFailure(
			execute(tool, {
				action: "derive_successor",
				resource: "proposal",
				source: manifest.source.target,
				sourceSha256: manifest.source.sha256,
				slug: "noop-successor-r02",
				patches: [{ id: "same", kind: "replace", oldText: "Same.", newText: "Same." }],
			}),
			path.join(root, "proposals/research-concept-noop-successor-r02.md"),
			"successor-no-op",
		);
	}
	{
		const root = await fixture();
		const tool = toolFor(root);
		const source = await createManagedLatest(root, tool, "collision-successor-r01", "# State\n\nOld.\n");
		await createManagedLatest(root, tool, "collision-successor-r02", "# Existing target\n");
		const target = path.join(root, "proposals/research-concept-collision-successor-r02.md");
		const before = await readFile(target);
		let failure;
		try {
			await execute(tool, {
				action: "derive_successor",
				resource: "proposal",
				source: source.source.target,
				sourceSha256: source.source.sha256,
				slug: "collision-successor-r02",
				patches: [{ id: "replace-old", kind: "replace", oldText: "Old.", newText: "New." }],
			});
			assert.fail("target collision must fail closed");
		} catch (error) {
			failure = error;
		}
		assert.equal(failure.candidateValidation?.code, "successor-target-collision");
		assert.equal(failure.candidateValidation?.wroteTarget, false);
		assert.deepEqual(await readFile(target), before);
	}
});

test("derive accepts sanctioned inline delimiter normalization in a surviving inherited ATX heading", async () => {
	const root = await fixture();
	const basePath = path.join(root, "proposals/matematica_propuesta_CREDA.md");
	const inheritedHeading = `${String.raw`## Objective for \(x + 1\)`}\n`;
	await writeFile(
		basePath,
		(await readFile(basePath, "utf8")).replace(
			"## Unique insertion section\n",
			inheritedHeading,
		),
		"utf8",
	);

	const result = await execute(toolFor(root), {
		action: "derive",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-inline-heading-r94",
		insertions: [
			{
				id: "heading-note",
				anchor: inheritedHeading,
				position: "after",
				content: "\nAdded after the normalized inherited heading.\n",
			},
		],
	});

	const output = await readFile(
		path.join(root, "proposals/research-concept-creda-inline-heading-r94.md"),
		"utf8",
	);
	assert.match(output, /^## Objective for \$x \+ 1\$$/m);
	assert.equal(result.details.candidateValidation.status, "passed");
	assert.equal(result.details.candidateValidation.inheritedHeadingsPreserved, 2);
});

test("derive_revision still rejects arbitrary text edits in inherited headings with normalized inline math", async () => {
	const root = await fixture();
	const basePath = path.join(root, "proposals/matematica_propuesta_CREDA.md");
	const inheritedHeading = `${String.raw`## Objective for \(x + 1\)`}\n`;
	await writeFile(
		basePath,
		(await readFile(basePath, "utf8")).replace(
			"## Unique insertion section\n",
			inheritedHeading,
		),
		"utf8",
	);
	const slug = "creda-edited-inline-heading-r95";

	await candidateFailure(
		execute(toolFor(root), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug,
			replacements: [
				{
					id: "edit-inherited-heading",
					oldText: inheritedHeading,
					newText: `${String.raw`## Objective for \(y + 1\)`}\n`,
				},
			],
		}),
		path.join(root, `proposals/research-concept-${slug}.md`),
		"inherited-heading-integrity",
	);
});

test("derive rejects a duplicate inherited heading that uses the pre-normalized inline delimiters", async () => {
	const root = await fixture();
	const basePath = path.join(root, "proposals/matematica_propuesta_CREDA.md");
	const inheritedHeading = `${String.raw`## Objective for \(x + 1\)`}\n`;
	await writeFile(
		basePath,
		(await readFile(basePath, "utf8")).replace(
			"## Unique insertion section\n",
			inheritedHeading,
		),
		"utf8",
	);
	const slug = "creda-duplicate-inline-heading-r96";

	await candidateFailure(
		execute(toolFor(root), {
			action: "derive",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug,
			insertions: [
				{
					id: "duplicate-inherited-heading",
					anchor: inheritedHeading,
					position: "after",
					content: `\n${inheritedHeading}\n`,
				},
			],
		}),
		path.join(root, `proposals/research-concept-${slug}.md`),
		"inherited-heading-integrity",
	);
});

test("derive rejects a fully composed candidate that fuses an inherited ATX heading at an insertion boundary", async () => {
	const root = await fixture();
	const slug = "creda-fused-insertion-heading-r84";
	const target = path.join(root, `proposals/research-concept-${slug}.md`);
	const failure = await candidateFailure(
		execute(toolFor(root), {
			action: "derive",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug,
			insertions: [
				{
					id: "fuse-next-heading",
					anchor: "## Unique insertion section\n",
					position: "before",
					content: "Inserted paragraph without a terminating boundary",
				},
			],
		}),
		target,
		"markdown-block-boundary",
	);
	assert.equal(failure.candidateValidation.operation, "derive");
	assert.equal(failure.candidateValidation.wroteTarget, false);
});

test("derive rejects a newly authored ATX-like heading fused inside an otherwise separated insertion block", async () => {
	const root = await fixture();
	const slug = "creda-fused-new-heading-r92";
	await candidateFailure(
		execute(toolFor(root), {
			action: "derive",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug,
			insertions: [
				{
					id: "fused-new-heading",
					anchor: "## Unique insertion section\n",
					position: "after",
					content: "\nInserted paragraph ## Fused heading\n\n",
				},
			],
		}),
		path.join(root, `proposals/research-concept-${slug}.md`),
		"atx-heading-standalone",
	);
});

test("derive_revision rejects a fully composed replacement that fuses an inherited ATX heading", async () => {
	const root = await fixture();
	await writeFile(
		path.join(root, "proposals/matematica_propuesta_CREDA.md"),
		movableDisplayCredaBase,
		"utf8",
	);
	const slug = "creda-fused-replacement-heading-r85";
	await candidateFailure(
		execute(toolFor(root), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug,
			replacements: [
				{
					id: "fuse-section-heading",
					oldText: "Source conclusion stays.\n\n## Section 3.1\n",
					newText: "Source conclusion updated.## Section 3.1\n",
				},
			],
		}),
		path.join(root, `proposals/research-concept-${slug}.md`),
		"inherited-heading-integrity",
	);
});

test("derive_revision rejects replacement bytes that lack trailing Markdown block separation", async () => {
	const root = await fixture();
	await writeFile(
		path.join(root, "proposals/matematica_propuesta_CREDA.md"),
		movableDisplayCredaBase,
		"utf8",
	);
	const slug = "creda-unseparated-replacement-r93";
	await candidateFailure(
		execute(toolFor(root), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug,
			replacements: [
				{
					id: "unseparated-source-conclusion",
					oldText: "Source conclusion stays.\n",
					newText: "Source conclusion updated without a trailing boundary.",
				},
			],
		}),
		path.join(root, `proposals/research-concept-${slug}.md`),
		"markdown-block-boundary",
	);
});

test("derive_revision rejects removed flat-domain definitions while retained output references their exact symbols", async () => {
	const root = await fixture();
	await writeFile(
		path.join(root, "proposals/matematica_propuesta_CREDA.md"),
		flatDomainCredaBase,
		"utf8",
	);
	const slug = "creda-removed-flat-domains-r86";
	const failure = await candidateFailure(
		execute(toolFor(root), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug,
			replacements: [
				{
					id: "remove-source-flat-domain",
					oldText: flatSourceDisplay,
					newText: "",
					authorizedEquations: [{ numberedTag: 10 }],
				},
				{
					id: "remove-target-flat-domain",
					oldText: flatTargetDisplay,
					newText: "",
					authorizedEquations: [{ numberedTag: 11 }],
				},
			],
		}),
		path.join(root, `proposals/research-concept-${slug}.md`),
		"flat-domain-definition",
	);
	assert.deepEqual(failure.candidateValidation.symbols.sort(), ["\\mathcal D^s", "\\mathcal D^t"]);
});

test("derive_revision accepts narrow replacement definitions for retained flat-domain references", async () => {
	const root = await fixture();
	await writeFile(
		path.join(root, "proposals/matematica_propuesta_CREDA.md"),
		flatDomainCredaBase,
		"utf8",
	);
	const replacementSource = "$$\n\\mathcal{D}^s \\coloneqq \\{(z_i^s,y_i^s)\\}_{i=1}^{m_s}.\n\\tag{10}\n$$\n";
	const replacementTarget = "$$\n\\mathcal{D}^t := \\{z_j^t\\}_{j=1}^{m_t}.\n\\tag{11}\n$$\n";
	const result = await execute(toolFor(root), {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-redefined-flat-domains-r87",
		replacements: [
			{
				id: "replace-source-flat-domain",
				oldText: flatSourceDisplay,
				newText: replacementSource,
				authorizedEquations: [{ numberedTag: 10 }],
			},
			{
				id: "replace-target-flat-domain",
				oldText: flatTargetDisplay,
				newText: replacementTarget,
				authorizedEquations: [{ numberedTag: 11 }],
			},
		],
	});
	assert.equal(result.details.candidateValidation.status, "passed");
	assert.equal(result.details.candidateValidation.phase, "pre-publish");
	assert.equal(result.details.candidateValidation.flatDomainDefinitionsChecked, 2);
});

test("derive_revision applies an explicitly authorized equation replacement to a new immutable derivative", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const basePath = path.join(root, "proposals/matematica_propuesta_CREDA.md");
	const baseBefore = await readFile(basePath);
	const target = path.join(root, "proposals/research-concept-creda-correction-r32.md");
	const inheritedEquation = "$$\nE = mc^2.\n\\tag{1}\n$$\n";
	const correctedEquation = "$$\nE = mc^2 + \\varepsilon.\n\\tag{1}\n$$\n";

	const result = await execute(tool, {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-correction-r32",
		replacements: [
			{
				id: "correct-energy-equation",
				oldText: inheritedEquation,
				newText: correctedEquation,
				authorizedEquations: [{ numberedTag: 1 }],
			},
		],
	});

	const output = await readFile(target, "utf8");
	assert.ok(output.startsWith(artifactMarker));
	assert.ok(output.includes(correctedEquation));
	assert.ok(!output.includes(inheritedEquation));
	assert.match(output, /Inline source math \$x \+ 1\$ must normalize\./);
	assert.ok(output.includes("$$\n\\begin{aligned}\n"));
	assert.deepEqual(await readFile(basePath), baseBefore);
	assert.equal(result.details.operation, "derive_revision");
	assert.equal(result.details.replacementCount, 1);
	assert.equal(result.details.authorizedEquationCount, 1);
	assert.equal(result.details.displayBlocksPreserved, 1);
	assert.equal(result.details.resultingDisplayBlockCount, 2);
	assert.match(result.details.sha256, /^[a-f0-9]{64}$/);
});

test("derive_revision atomically moves exact prose-plus-display blocks when every moved display is selected", async () => {
	const root = await fixture();
	const basePath = path.join(root, "proposals/matematica_propuesta_CREDA.md");
	await writeFile(basePath, movableDisplayCredaBase, "utf8");
	const targetAnchor = "Target anchor paragraph.\n";

	const result = await execute(toolFor(root), {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-adjacent-display-move-r66",
		replacements: [
			{
				id: "remove-selected-source-block",
				oldText: movableSourceBlock,
				newText: "",
				authorizedEquations: [{ numberedTag: 23 }, { numberedTag: 24 }],
			},
			{
				id: "insert-selected-target-block",
				oldText: targetAnchor,
				newText: `${targetAnchor}\n${movableSourceBlock}`,
			},
		],
		authorizedDisplayRelocations: [
			{
				sourceReplacementId: "remove-selected-source-block",
				destinationReplacementId: "insert-selected-target-block",
			},
		],
	});

	const output = await readFile(
		path.join(root, "proposals/research-concept-creda-adjacent-display-move-r66.md"),
		"utf8",
	);
	assert.ok(!output.includes(`## Section 2.3\n\n${movableSourceBlock}`));
	assert.ok(output.includes(`## Section 3.3\n\nTarget introduction stays.\n\n${targetAnchor}\n${movableSourceBlock}`));
	assert.equal(output.match(/\\tag\{23\}/g)?.length, 1);
	assert.equal(output.match(/\\tag\{24\}/g)?.length, 1);
	assert.ok(output.indexOf("\\tag{31}") < output.indexOf("\\tag{23}"));
	assert.ok(output.indexOf("\\tag{24}") < output.indexOf("\\tag{33}"));
	assert.equal(result.details.authorizedEquationCount, 2);
	assert.equal(result.details.displayBlocksPreserved, 2);
	assert.equal(result.details.resultingDisplayBlockCount, 4);
});

test("derive_revision admits explicit empty authorization only for wholly display-free replacements", async () => {
	const successRoot = await fixture();
	const successBase = path.join(successRoot, "proposals/matematica_propuesta_CREDA.md");
	await writeFile(successBase, movableDisplayCredaBase, "utf8");
	const successTool = toolFor(successRoot);
	const authorizedEquationsSchema =
		successTool.parameters.properties.replacements.items.properties.authorizedEquations;
	assert.equal(authorizedEquationsSchema.minItems, 0);

	const successResult = await execute(successTool, {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-display-free-empty-auth-r81",
		replacements: [
			{
				id: "update-display-free-target",
				oldText: "Target anchor paragraph.\n",
				newText: "Updated target anchor paragraph.\n",
				authorizedEquations: [],
			},
		],
	});
	assert.equal(successResult.details.authorizedEquationCount, 0);
	assert.match(
		await readFile(
			path.join(successRoot, "proposals/research-concept-creda-display-free-empty-auth-r81.md"),
			"utf8",
		),
		/Updated target anchor paragraph\./,
	);

	const displayTargetRoot = await fixture();
	await writeFile(
		path.join(displayTargetRoot, "proposals/matematica_propuesta_CREDA.md"),
		movableDisplayCredaBase,
		"utf8",
	);
	await assert.rejects(
		execute(toolFor(displayTargetRoot), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-display-target-empty-auth-r82",
			replacements: [
				{
					id: "remove-selected-source-for-empty-target",
					oldText: movableSourceBlock,
					newText: "",
					authorizedEquations: [{ numberedTag: 23 }, { numberedTag: 24 }],
				},
				{
					id: "insert-display-target-with-empty-auth",
					oldText: "Target anchor paragraph.\n",
					newText: `Target anchor paragraph.\n\n${movableSourceBlock}`,
					authorizedEquations: [],
				},
			],
		}),
		/empty authorizedEquations.*both oldText and newText.*display-free/i,
	);

	const displaySourceRoot = await fixture();
	await writeFile(
		path.join(displaySourceRoot, "proposals/matematica_propuesta_CREDA.md"),
		movableDisplayCredaBase,
		"utf8",
	);
	await assert.rejects(
		execute(toolFor(displaySourceRoot), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-display-source-empty-auth-r83",
			replacements: [
				{
					id: "remove-display-source-with-empty-auth",
					oldText: movableSourceBlock,
					newText: "",
					authorizedEquations: [],
				},
				{
					id: "insert-selected-target-after-empty-source",
					oldText: "Target anchor paragraph.\n",
					newText: `Target anchor paragraph.\n\n${movableSourceBlock}`,
				},
			],
		}),
		/empty authorizedEquations.*both oldText and newText.*display-free/i,
	);
});

test("derive_revision moves one exact mixed source block containing three individually authorized displays", async () => {
	const root = await fixture();
	await writeFile(
		path.join(root, "proposals/matematica_propuesta_CREDA.md"),
		tripleDisplayMoveBase,
		"utf8",
	);
	const targetAnchor = "Target anchor paragraph.\n";

	const result = await execute(toolFor(root), {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-triple-display-move-r73",
		replacements: [
			{
				id: "remove-triple-display-source-block",
				oldText: tripleDisplaySourceBlock,
				newText: "",
				authorizedEquations: [
					{ numberedTag: 10 },
					{ numberedTag: 11 },
					{ numberedTag: 12 },
				],
			},
			{
				id: "insert-triple-display-target-block",
				oldText: targetAnchor,
				newText: `${targetAnchor}\n${tripleDisplaySourceBlock}`,
			},
		],
		authorizedDisplayRelocations: [
			{
				sourceReplacementId: "remove-triple-display-source-block",
				destinationReplacementId: "insert-triple-display-target-block",
			},
		],
	});

	const output = await readFile(
		path.join(root, "proposals/research-concept-creda-triple-display-move-r73.md"),
		"utf8",
	);
	assert.ok(!output.includes(`## Source\n\nSource introduction stays.\n\n${tripleDisplaySourceBlock}`));
	assert.ok(output.includes(`## Target\n\n${targetAnchor}\n${tripleDisplaySourceBlock}`));
	assert.equal(output.match(/\\tag\{10\}/g)?.length, 1);
	assert.equal(output.match(/\\tag\{11\}/g)?.length, 1);
	assert.equal(output.match(/\\tag\{12\}/g)?.length, 1);
	assert.ok(output.indexOf("\\tag{10}") < output.indexOf("\\tag{11}"));
	assert.ok(output.indexOf("\\tag{11}") < output.indexOf("\\tag{12}"));
	assert.equal(result.details.authorizedEquationCount, 3);
	assert.equal(result.details.displayBlocksPreserved, 2);
	assert.equal(result.details.resultingDisplayBlockCount, 5);
	assert.equal(result.details.authorizedDisplayRelocationCount, 1);
	assert.equal(result.details.candidateValidation.status, "passed");
	assert.equal(result.details.candidateValidation.authorizedRelocatedDisplayCount, 3);
	assert.deepEqual(result.details.candidateValidation.relocationGroups[0].baseIndexes, [1, 2, 3]);
});

test("derive_revision rejects cross-group reorder even when each moved group preserves its own relative order", async () => {
	const root = await fixture();
	await writeFile(
		path.join(root, "proposals/matematica_propuesta_CREDA.md"),
		tripleDisplayMoveBase,
		"utf8",
	);
	const slug = "creda-cross-group-display-reorder-r89";
	await candidateFailure(
		execute(toolFor(root), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug,
			replacements: [
				{
					id: "remove-first-move-group",
					oldText: tripleMoveGroupOne,
					newText: "",
					authorizedEquations: [{ numberedTag: 10 }, { numberedTag: 11 }],
				},
				{
					id: "remove-second-move-group",
					oldText: tripleMoveGroupTwo,
					newText: "",
					authorizedEquations: [{ numberedTag: 12 }],
				},
				{
					id: "insert-reordered-move-groups",
					oldText: "Target anchor paragraph.\n",
					newText: `Target anchor paragraph.\n\n${tripleMoveGroupTwo}\n${tripleMoveGroupOne}`,
				},
			],
			authorizedDisplayRelocations: [
				{
					sourceReplacementId: "remove-first-move-group",
					destinationReplacementId: "insert-reordered-move-groups",
				},
				{
					sourceReplacementId: "remove-second-move-group",
					destinationReplacementId: "insert-reordered-move-groups",
				},
			],
		}),
		path.join(root, `proposals/research-concept-${slug}.md`),
		"cross-group-display-reorder",
	);
});

test("derive_revision fails closed when inherited display copies lack explicit relocation authorization", async () => {
	const root = await fixture();
	await writeFile(
		path.join(root, "proposals/matematica_propuesta_CREDA.md"),
		tripleDisplayMoveBase,
		"utf8",
	);
	const slug = "creda-implicit-triple-display-move-r88";
	await candidateFailure(
		execute(toolFor(root), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug,
			replacements: [
				{
					id: "remove-implicit-source-group",
					oldText: tripleDisplaySourceBlock,
					newText: "",
					authorizedEquations: [
						{ numberedTag: 10 },
						{ numberedTag: 11 },
						{ numberedTag: 12 },
					],
				},
				{
					id: "insert-implicit-destination-group",
					oldText: "Target anchor paragraph.\n",
					newText: `Target anchor paragraph.\n\n${tripleDisplaySourceBlock}`,
				},
			],
		}),
		path.join(root, `proposals/research-concept-${slug}.md`),
		"unauthorized-display-relocation",
	);
});

test("derive_revision accepts multiple stable display IDs for one exact mixed source block", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	await writeFile(
		path.join(root, "proposals/matematica_propuesta_CREDA.md"),
		tripleDisplayMoveBase,
		"utf8",
	);
	const inventory = JSON.parse(
		await text(await execute(tool, { action: "inventory", resource: "displays", limit: 5 })),
	);
	const sourceDisplayIds = inventory.displays
		.filter((display) => [10, 11, 12].includes(display.numberedTags[0]))
		.map((display) => ({ displayId: display.displayId }));
	assert.equal(sourceDisplayIds.length, 3);

	await execute(tool, {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-triple-display-id-move-r74",
		replacements: [
			{
				id: "remove-id-selected-source-block",
				oldText: tripleDisplaySourceBlock,
				newText: "",
				authorizedEquations: sourceDisplayIds,
			},
			{
				id: "insert-id-selected-target-block",
				oldText: "Target anchor paragraph.\n",
				newText: `Target anchor paragraph.\n\n${tripleDisplaySourceBlock}`,
			},
		],
		authorizedDisplayRelocations: [
			{
				sourceReplacementId: "remove-id-selected-source-block",
				destinationReplacementId: "insert-id-selected-target-block",
			},
		],
	});
});

test("derive_revision triple-display mixed blocks fail closed for missing auth, preserved-display auth, partial selection, and overlap", async () => {
	const cases = [
		{
			slug: "creda-triple-missing-auth-r75",
			replacements: [
				{
					id: "remove-under-authorized-triple-block",
					oldText: tripleDisplaySourceBlock,
					newText: "",
					authorizedEquations: [{ numberedTag: 10 }, { numberedTag: 11 }],
				},
			],
			error: /omits or alters an inherited display block without matching authorization/i,
		},
		{
			slug: "creda-triple-preserved-auth-r76",
			replacements: [
				{
					id: "authorize-preserved-triple-display",
					oldText: tripleDisplaySourceBlock,
					newText: tripleDisplaySourceBlock.replace("Source prose moves before", "Updated prose stays before"),
					authorizedEquations: [{ numberedTag: 10 }],
				},
			],
			error: /authorization for a byte-preserved display block/i,
		},
		{
			slug: "creda-triple-partial-block-r77",
			replacements: [
				{
					id: "select-partial-triple-block",
					oldText: tripleDisplaySourceBlock.slice(0, tripleDisplaySourceBlock.indexOf("q_{12}")),
					newText: "",
					authorizedEquations: [
						{ numberedTag: 10 },
						{ numberedTag: 11 },
						{ numberedTag: 12 },
					],
				},
			],
			error: /does not select complete Markdown blocks|intersects only part of an inherited display block/i,
		},
		{
			slug: "creda-triple-overlap-r78",
			replacements: [
				{
					id: "remove-overlapping-triple-block",
					oldText: tripleDisplaySourceBlock,
					newText: "",
					authorizedEquations: [
						{ numberedTag: 10 },
						{ numberedTag: 11 },
						{ numberedTag: 12 },
					],
				},
				{
					id: "remove-overlapping-middle-display",
					oldText: "$$\nq_{11} = 11.\n\\tag{11}\n$$\n",
					newText: "",
					authorizedEquations: [{ numberedTag: 11 }],
				},
			],
			error: /overlap/i,
		},
	];

	for (const candidate of cases) {
		const root = await fixture();
		await writeFile(
			path.join(root, "proposals/matematica_propuesta_CREDA.md"),
			tripleDisplayMoveBase,
			"utf8",
		);
		await assert.rejects(
			execute(toolFor(root), {
				action: "derive_revision",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: candidate.slug,
				replacements: candidate.replacements,
			}),
			candidate.error,
		);
	}
});

test("derive_revision rejects reordered moved displays and target-side unapproved displays", async () => {
	const display10 = "$$\nq_{10} = 10.\n\\tag{10}\n$$\n";
	const display11 = "$$\nq_{11} = 11.\n\\tag{11}\n$$\n";
	const display12 = "$$\nq_{12} = 12.\n\\tag{12}\n$$\n";
	const cases = [
		{
			slug: "creda-triple-reordered-target-r79",
			targetBlock: tripleDisplaySourceBlock.replace(
				`${display10}\n${display11}`,
				() => `${display11}\n${display10}`,
			),
			error: /preserve.*display.*order|reorders individually authorized moved displays/i,
		},
		{
			slug: "creda-triple-unapproved-target-r80",
			targetBlock: `${tripleDisplaySourceBlock}\n$$\nq_{99} = 99.\n\\tag{99}\n$$\n`,
			error: /target-side unapproved display/i,
		},
		{
			slug: "creda-triple-omitted-target-r90",
			targetBlock: tripleDisplaySourceBlock.replace(`${display12}\n`, ""),
			error: /duplicates, omits, or reorders selected displays/i,
		},
		{
			slug: "creda-triple-duplicated-target-r91",
			targetBlock: `${tripleDisplaySourceBlock}\n${display12}`,
			error: /duplicates, omits, or reorders selected displays|duplicates an authorized|duplicate numbered tag/i,
		},
	];

	for (const candidate of cases) {
		const root = await fixture();
		await writeFile(
			path.join(root, "proposals/matematica_propuesta_CREDA.md"),
			tripleDisplayMoveBase,
			"utf8",
		);
		await assert.rejects(
			execute(toolFor(root), {
				action: "derive_revision",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: candidate.slug,
				replacements: [
					{
						id: "remove-triple-source-for-target-check",
						oldText: tripleDisplaySourceBlock,
						newText: "",
						authorizedEquations: [
							{ numberedTag: 10 },
							{ numberedTag: 11 },
							{ numberedTag: 12 },
						],
					},
					{
						id: "insert-checked-triple-target",
						oldText: "Target anchor paragraph.\n",
						newText: `Target anchor paragraph.\n\n${candidate.targetBlock}`,
					},
				],
				authorizedDisplayRelocations: [
					{
						sourceReplacementId: "remove-triple-source-for-target-check",
						destinationReplacementId: "insert-checked-triple-target",
					},
				],
			}),
			candidate.error,
		);
	}
});

test("derive_revision safely removes selected adjacent prose and displays while prose-only removal needs no equation authorization", async () => {
	const selectedRoot = await fixture();
	const selectedBase = path.join(selectedRoot, "proposals/matematica_propuesta_CREDA.md");
	await writeFile(selectedBase, movableDisplayCredaBase, "utf8");
	const selectedResult = await execute(toolFor(selectedRoot), {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-adjacent-display-removal-r67",
		replacements: [
			{
				id: "remove-selected-source-block",
				oldText: movableSourceBlock,
				newText: "",
				authorizedEquations: [{ numberedTag: 23 }, { numberedTag: 24 }],
			},
		],
	});
	const selectedOutput = await readFile(
		path.join(selectedRoot, "proposals/research-concept-creda-adjacent-display-removal-r67.md"),
		"utf8",
	);
	assert.ok(!selectedOutput.includes(movableSourceBlock));
	assert.equal(selectedResult.details.authorizedEquationCount, 2);

	const proseRoot = await fixture();
	const proseBase = path.join(proseRoot, "proposals/matematica_propuesta_CREDA.md");
	await writeFile(proseBase, movableDisplayCredaBase, "utf8");
	const proseResult = await execute(toolFor(proseRoot), {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-prose-only-removal-r68",
		replacements: [
			{
				id: "remove-source-introduction",
				oldText: "Source introduction stays.\n",
				newText: "",
			},
		],
	});
	const proseOutput = await readFile(
		path.join(proseRoot, "proposals/research-concept-creda-prose-only-removal-r68.md"),
		"utf8",
	);
	assert.ok(!proseOutput.includes("Source introduction stays."));
	assert.equal(proseResult.details.authorizedEquationCount, 0);
	assert.equal(proseResult.details.displayBlocksPreserved, 4);
});

test("derive_revision block moves reject partial, mismatched, unselected, and byte-preserved display authorization", async () => {
	const cases = [
		{
			slug: "creda-partial-adjacent-display-r69",
			replacements: [
				{
					id: "partial-selected-source-block",
					oldText: movableSourceBlock.slice(0, movableSourceBlock.lastIndexOf("$$\n")),
					newText: "",
					authorizedEquations: [{ numberedTag: 23 }, { numberedTag: 24 }],
				},
			],
			error: /does not select complete Markdown blocks|intersects only part of an inherited display block/i,
		},
		{
			slug: "creda-mismatched-adjacent-display-r70",
			replacements: [
				{
					id: "mismatched-selected-source-block",
					oldText: movableSourceBlock,
					newText: "",
					authorizedEquations: [{ numberedTag: 23 }, { numberedTag: 31 }],
				},
			],
			error: /does not match a display block completely selected/i,
		},
		{
			slug: "creda-unselected-adjacent-display-r71",
			replacements: [
				{
					id: "under-authorized-source-block",
					oldText: movableSourceBlock,
					newText: "",
					authorizedEquations: [{ numberedTag: 23 }],
				},
			],
			error: /omits or alters an inherited display block without matching authorization/i,
		},
		{
			slug: "creda-byte-preserved-adjacent-display-r72",
			replacements: [
				{
					id: "authorize-unchanged-source-block",
					oldText: movableSourceBlock,
					newText: movableSourceBlock.replace("Source explanation moves", "Source explanation remains"),
					authorizedEquations: [{ numberedTag: 23 }, { numberedTag: 24 }],
				},
			],
			error: /authorization for a byte-preserved display block/i,
		},
	];

	for (const candidate of cases) {
		const root = await fixture();
		await writeFile(
			path.join(root, "proposals/matematica_propuesta_CREDA.md"),
			movableDisplayCredaBase,
			"utf8",
		);
		await assert.rejects(
			execute(toolFor(root), {
				action: "derive_revision",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: candidate.slug,
				replacements: candidate.replacements,
			}),
			candidate.error,
		);
	}
});

test("derive_revision authorizes exact unnumbered display-block replacement and removal", async () => {
	const inheritedDisplay = "$$\nH(X) = -\\sum_x p(x) \\log p(x).\n$$\n";
	const correctedDisplay = "$$\nH(X) = -\\sum_x p(x) \\log_2 p(x).\n$$\n";

	const replacementRoot = await fixture();
	const replacementBase = path.join(replacementRoot, "proposals/matematica_propuesta_CREDA.md");
	await writeFile(
		replacementBase,
		(await readFile(replacementBase, "utf8")).replace(
			"## Unique insertion section\n",
			() => `## Entropy\n\n${inheritedDisplay}\n## Unique insertion section\n`,
		),
		"utf8",
	);
	const replacementResult = await execute(toolFor(replacementRoot), {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-unnumbered-replacement-r41",
		replacements: [
			{
				id: "correct-entropy-display",
				oldText: inheritedDisplay,
				newText: correctedDisplay,
				authorizedEquations: [{ displayBlock: inheritedDisplay }],
			},
		],
	});
	const replacementOutput = await readFile(
		path.join(replacementRoot, "proposals/research-concept-creda-unnumbered-replacement-r41.md"),
		"utf8",
	);
	assert.ok(replacementOutput.includes(correctedDisplay));
	assert.ok(!replacementOutput.includes(inheritedDisplay));
	assert.equal(replacementResult.details.authorizedEquationCount, 1);
	assert.equal(replacementResult.details.displayBlocksPreserved, 2);
	assert.equal(replacementResult.details.resultingDisplayBlockCount, 3);

	const removalRoot = await fixture();
	const removalBase = path.join(removalRoot, "proposals/matematica_propuesta_CREDA.md");
	await writeFile(
		removalBase,
		(await readFile(removalBase, "utf8")).replace(
			"## Unique insertion section\n",
			() => `## Domain display\n\n${inheritedDisplay}\n## Unique insertion section\n`,
		),
		"utf8",
	);
	const removalResult = await execute(toolFor(removalRoot), {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-unnumbered-removal-r42",
		replacements: [
			{
				id: "remove-domain-display",
				oldText: inheritedDisplay,
				newText: "",
				authorizedEquations: [{ displayBlock: inheritedDisplay }],
			},
		],
	});
	const removalOutput = await readFile(
		path.join(removalRoot, "proposals/research-concept-creda-unnumbered-removal-r42.md"),
		"utf8",
	);
	assert.ok(!removalOutput.includes(inheritedDisplay));
	assert.equal(removalResult.details.authorizedEquationCount, 1);
	assert.equal(removalResult.details.displayBlocksPreserved, 2);
	assert.equal(removalResult.details.resultingDisplayBlockCount, 2);
});

test("inventories and reads parser-exact fixed-base displays, then replaces an unnumbered display by stable ID", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const basePath = path.join(root, "proposals/matematica_propuesta_CREDA.md");
	const inheritedDisplay = "$$\nH(X) = -\\sum_x p(x) \\log p(x).\n$$\n";
	const correctedDisplay = "$$\nH(X) = -\\sum_x p(x) \\log_2 p(x).\n$$\n";
	await writeFile(
		basePath,
		(await readFile(basePath, "utf8")).replace(
			"## Unique insertion section\n",
			() => `## Section 2.2\n\n${inheritedDisplay}\n## Unique insertion section\n`,
		),
		"utf8",
	);

	const inventory = await execute(tool, {
		action: "inventory",
		resource: "displays",
		offset: 1,
		limit: 1,
	});
	const page = JSON.parse(await text(inventory));
	assert.equal(page.total, 3);
	assert.equal(page.offset, 1);
	assert.equal(page.displays.length, 1);
	assert.match(page.displays[0].displayId, /^display-sha256-[a-f0-9]{64}-occurrence-1$/);
	assert.deepEqual(page.displays[0].equationLabels, []);
	assert.deepEqual(page.displays[0].numberedTags, []);
	assert.equal(page.nextOffset, 2);
	assert.equal(inventory.details.truncated, true);

	const fullInventory = JSON.parse(
		await text(await execute(tool, { action: "inventory", resource: "displays", offset: 0, limit: 3 })),
	);
	assert.deepEqual(fullInventory.displays[0].numberedTags, [1]);
	assert.deepEqual(fullInventory.displays[2].equationLabels, ["eq:ksc"]);
	assert.deepEqual(fullInventory.displays[2].numberedTags, [2]);

	const displayId = page.displays[0].displayId;
	const display = await execute(tool, { action: "read", resource: "display", displayId });
	assert.equal(await text(display), inheritedDisplay);
	assert.equal(display.details.displayId, displayId);
	assert.equal(display.details.canonicalCompleteBlock, true);
	assert.equal(display.details.bytes, Buffer.byteLength(inheritedDisplay, "utf8"));

	const result = await execute(tool, {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-display-id-r50",
		replacements: [
			{
				id: "correct-section-two-display",
				newText: correctedDisplay,
				authorizedEquations: [{ displayId }],
			},
		],
	});
	const output = await readFile(
		path.join(root, "proposals/research-concept-creda-display-id-r50.md"),
		"utf8",
	);
	assert.ok(output.includes(correctedDisplay));
	assert.ok(!output.includes(inheritedDisplay));
	assert.equal(result.details.authorizedEquationCount, 1);
	assert.equal(result.details.displayBlocksPreserved, 2);
	assert.equal(result.details.resultingDisplayBlockCount, 3);
});

test("inventories fixed-base Markdown sections with stable IDs and bounded extents", async () => {
	const root = await sectionFixture();
	const tool = toolFor(root);
	const inventory = await execute(tool, {
		action: "inventory",
		resource: "sections",
		offset: 0,
		limit: 16,
	});
	const payload = JSON.parse(await text(inventory));

	assert.equal(payload.total, 7);
	assert.equal(payload.sections.length, 7);
	assert.ok(!payload.sections.some((section) => section.headingText === "Not a parsed section"));
	assert.deepEqual(
		payload.sections.map(({ headingText, headingLevel }) => [headingText, headingLevel]),
		[
			["CREDA sections", 1],
			["Section 3", 2],
			["Section 4", 2],
			["Section 4.1", 3],
			["Section 5", 2],
			["Section 6", 2],
			["Section 7", 2],
		],
	);
	for (const section of payload.sections) {
		assert.match(section.sectionId, /^section-sha256-[a-f0-9]{64}-occurrence-1$/);
		assert.ok(Number.isSafeInteger(section.startByte));
		assert.ok(Number.isSafeInteger(section.endByte));
		assert.equal(section.endByte - section.startByte, section.bytes);
		assert.ok(section.headingBytes > 0);
	}
	const section4 = payload.sections.find((section) => section.headingText === "Section 4");
	const section5 = payload.sections.find((section) => section.headingText === "Section 5");
	const baseBytes = Buffer.from(sectionedCredaBase, "utf8");
	assert.equal(section4.endByte, section5.startByte);
	assert.match(baseBytes.subarray(section4.startByte, section4.endByte).toString("utf8"), /^## Section 4\n/);
	assert.match(baseBytes.subarray(section4.startByte, section4.endByte).toString("utf8"), /### Section 4\.1/);
	assert.equal(section4.displayCount, 1);

	const repeated = JSON.parse(
		await text(await execute(tool, { action: "inventory", resource: "sections", limit: 16 })),
	);
	assert.deepEqual(
		repeated.sections.map((section) => section.sectionId),
		payload.sections.map((section) => section.sectionId),
	);
	assert.equal(inventory.details.resource, "sections");
	assert.equal(inventory.details.truncated, false);
});

test("derive_revision removes multiple authorized sibling sections and preserves surviving displays in order", async () => {
	const root = await sectionFixture();
	const tool = toolFor(root);
	const basePath = path.join(root, "proposals/matematica_propuesta_CREDA.md");
	const baseBefore = await readFile(basePath);
	const inventory = JSON.parse(
		await text(await execute(tool, { action: "inventory", resource: "sections", limit: 16 })),
	);
	const removed = ["Section 4", "Section 5", "Section 6"].map((headingText) =>
		inventory.sections.find((section) => section.headingText === headingText),
	);
	const result = await execute(tool, {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-remove-sections-r08",
		authorizedSectionRemovals: removed.map(({ sectionId }) => ({ sectionId })),
	});

	const output = await readFile(
		path.join(root, "proposals/research-concept-creda-remove-sections-r08.md"),
	);
	const orderedExtents = [...removed].sort((left, right) => left.startByte - right.startByte);
	const expectedChunks = [];
	let cursor = 0;
	for (const extent of orderedExtents) {
		expectedChunks.push(baseBefore.subarray(cursor, extent.startByte));
		cursor = extent.endByte;
	}
	expectedChunks.push(baseBefore.subarray(cursor));
	assert.deepEqual(output, Buffer.concat([Buffer.from(artifactMarker), ...expectedChunks]));
	const rendered = output.toString("utf8");
	for (const heading of ["## Section 4", "### Section 4.1", "## Section 5", "## Section 6"]) {
		assert.ok(!rendered.includes(heading));
	}
	const survivingThird = "$$\ns_3 = 3.\n\\tag{3}\n$$\n";
	const survivingSeventh = "$$\ns_7 = 7.\n\\tag{7}\n$$\n";
	const thirdIndex = rendered.indexOf(survivingThird);
	const seventhIndex = rendered.indexOf(survivingSeventh);
	assert.ok(thirdIndex > artifactMarker.length);
	assert.ok(seventhIndex > thirdIndex + survivingThird.length);
	assert.equal(rendered.slice(thirdIndex, thirdIndex + survivingThird.length), survivingThird);
	assert.equal(rendered.slice(seventhIndex, seventhIndex + survivingSeventh.length), survivingSeventh);
	assert.deepEqual(await readFile(basePath), baseBefore);
	assert.equal(result.details.authorizedSectionRemovalCount, 3);
	assert.equal(result.details.authorizedSectionDisplayCount, 3);
	assert.equal(result.details.authorizedEquationCount, 3);
	assert.equal(result.details.displayBlocksPreserved, 2);
	assert.equal(result.details.resultingDisplayBlockCount, 2);
	assert.equal(result.details.replacementCount, 0);
});

test("derive_revision section selectors fail closed for unknown, ambiguous, duplicate, nested, and cross-overlapping selections", async () => {
	const cases = [
		{
			slug: "creda-unknown-section-r61",
			build: () => [{ sectionId: `section-sha256-${"0".repeat(64)}-occurrence-1` }],
			error: /sectionId.*unknown.*current fixed CREDA base/i,
		},
		{
			slug: "creda-ambiguous-section-r62",
			build: (sections) => [
				{
					sectionId: sections.find((section) => section.headingText === "Section 4").sectionId,
					approved: true,
				},
			],
			error: /authorized section removal.*ambiguous or contains unknown fields/i,
		},
		{
			slug: "creda-duplicate-section-r63",
			build: (sections) => {
				const sectionId = sections.find((section) => section.headingText === "Section 5").sectionId;
				return [{ sectionId }, { sectionId }];
			},
			error: /repeats sectionId/i,
		},
		{
			slug: "creda-nested-section-r64",
			build: (sections) => [
				{ sectionId: sections.find((section) => section.headingText === "Section 4").sectionId },
				{ sectionId: sections.find((section) => section.headingText === "Section 4.1").sectionId },
			],
			error: /overlap or are nested/i,
		},
	];

	for (const candidate of cases) {
		const root = await sectionFixture();
		const tool = toolFor(root);
		const inventory = JSON.parse(
			await text(await execute(tool, { action: "inventory", resource: "sections", limit: 16 })),
		);
		await assert.rejects(
			execute(tool, {
				action: "derive_revision",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: candidate.slug,
				authorizedSectionRemovals: candidate.build(inventory.sections),
			}),
			candidate.error,
		);
		await assert.rejects(
			readFile(path.join(root, `proposals/research-concept-${candidate.slug}.md`)),
			(error) => error?.code === "ENOENT",
		);
	}

	const overlapRoot = await sectionFixture();
	const overlapTool = toolFor(overlapRoot);
	const overlapInventory = JSON.parse(
		await text(await execute(overlapTool, { action: "inventory", resource: "sections", limit: 16 })),
	);
	const section4Id = overlapInventory.sections.find(
		(section) => section.headingText === "Section 4",
	).sectionId;
	const inheritedDisplay = "$$\ns_4 = 4.\n\\tag{4}\n$$\n";
	await assert.rejects(
		execute(overlapTool, {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-overlap-section-replacement-r65",
			authorizedSectionRemovals: [{ sectionId: section4Id }],
			replacements: [
				{
					id: "correct-section-four-display",
					oldText: inheritedDisplay,
					newText: "$$\ns_4 = 4 + \\varepsilon.\n\\tag{4}\n$$\n",
					authorizedEquations: [{ numberedTag: 4 }],
				},
			],
		}),
		/mutations.*overlap or are nested/i,
	);
	await assert.rejects(
		readFile(path.join(overlapRoot, "proposals/research-concept-creda-overlap-section-replacement-r65.md")),
		(error) => error?.code === "ENOENT",
	);
});

test("derive_revision display IDs fail closed for unknown, ambiguous, and partial selectors", async () => {
	const inheritedDisplay = "$$\nH(X) = -\\sum_x p(x) \\log p(x).\n$$\n";
	const correctedDisplay = "$$\nH(X) = -\\sum_x p(x) \\log_2 p(x).\n$$\n";
	const cases = [
		{
			slug: "creda-unknown-display-id-r51",
			replacement: {
				id: "unknown-display",
				newText: correctedDisplay,
				authorizedEquations: [
					{ displayId: `display-sha256-${"0".repeat(64)}-occurrence-1` },
				],
			},
			error: /displayId.*unknown.*current fixed CREDA base/i,
		},
		{
			slug: "creda-ambiguous-display-id-r52",
			buildReplacement: (displayId) => ({
				id: "ambiguous-display",
				newText: correctedDisplay,
				authorizedEquations: [{ displayId, displayBlock: inheritedDisplay }],
			}),
			error: /display authorization.*ambiguous/i,
		},
		{
			slug: "creda-partial-display-id-r53",
			buildReplacement: (displayId) => ({
				id: "partial-display",
				oldText: inheritedDisplay.slice(3, -3),
				newText: correctedDisplay,
				authorizedEquations: [{ displayId }],
			}),
			error: /oldText.*does not exactly match.*resolved by displayId/i,
		},
	];

	for (const candidate of cases) {
		const root = await fixture();
		const basePath = path.join(root, "proposals/matematica_propuesta_CREDA.md");
		await writeFile(
			basePath,
			(await readFile(basePath, "utf8")).replace(
				"## Unique insertion section\n",
				() => `## Section 2.2\n\n${inheritedDisplay}\n## Unique insertion section\n`,
			),
			"utf8",
		);
		const tool = toolFor(root);
		const inventory = JSON.parse(
			await text(await execute(tool, { action: "inventory", resource: "displays", offset: 1, limit: 1 })),
		);
		const displayId = inventory.displays[0].displayId;
		const replacement = candidate.buildReplacement
			? candidate.buildReplacement(displayId)
			: candidate.replacement;
		await assert.rejects(
			execute(tool, {
				action: "derive_revision",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: candidate.slug,
				replacements: [replacement],
			}),
			candidate.error,
		);
		await assert.rejects(
			readFile(path.join(root, `proposals/research-concept-${candidate.slug}.md`)),
			(error) => error?.code === "ENOENT",
		);
	}
});

test("derive_revision rejects unsafe exact display-block authorization selectors", async () => {
	const inheritedDisplay = "$$\nH(X) = -\\sum_x p(x) \\log p(x).\n$$\n";
	const correctedDisplay = "$$\nH(X) = -\\sum_x p(x) \\log_2 p(x).\n$$\n";
	const numberedDisplay = "$$\nE = mc^2.\n\\tag{1}\n$$\n";
	const cases = [
		{
			slug: "creda-partial-display-selector-r43",
			authorizations: [{ displayBlock: "H(X) = -\\sum_x p(x) \\log p(x)." }],
			error: /overlaps.*not its exact complete parsed block/i,
		},
		{
			slug: "creda-overlap-display-selector-r44",
			authorizations: [{ displayBlock: `## Entropy\n\n${inheritedDisplay}` }],
			error: /overlaps.*not its exact complete parsed block/i,
		},
		{
			slug: "creda-missing-display-selector-r45",
			authorizations: [{ displayBlock: "$$\nI(X;Y) = 0.\n$$\n" }],
			error: /displayBlock authorization.*missing.*fixed CREDA base/i,
		},
		{
			slug: "creda-nondisplay-selector-r46",
			authorizations: [{ displayBlock: "Repeated prose anchor." }],
			error: /selects non-display text/i,
		},
		{
			slug: "creda-oldtext-selector-mismatch-r47",
			authorizations: [{ displayBlock: numberedDisplay }],
			error: /does not match.*exact oldText/i,
		},
		{
			slug: "creda-overlapping-display-authorizations-r48",
			authorizations: [
				{ displayBlock: inheritedDisplay },
				{ displayBlock: inheritedDisplay },
			],
			error: /overlapping authorization selectors/i,
		},
	];

	for (const candidate of cases) {
		const root = await fixture();
		const basePath = path.join(root, "proposals/matematica_propuesta_CREDA.md");
		await writeFile(
			basePath,
			(await readFile(basePath, "utf8")).replace(
				"## Unique insertion section\n",
				() => `## Entropy\n\n${inheritedDisplay}\n## Unique insertion section\n`,
			),
			"utf8",
		);
		await assert.rejects(
			execute(toolFor(root), {
				action: "derive_revision",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: candidate.slug,
				replacements: [
					{
						id: "correct-unnumbered-display",
						oldText: inheritedDisplay,
						newText: correctedDisplay,
						authorizedEquations: candidate.authorizations,
					},
				],
			}),
			candidate.error,
		);
		await assert.rejects(
			readFile(path.join(root, `proposals/research-concept-${candidate.slug}.md`)),
			(error) => error?.code === "ENOENT",
		);
	}

	const ambiguousRoot = await fixture();
	const ambiguousBasePath = path.join(ambiguousRoot, "proposals/matematica_propuesta_CREDA.md");
	await writeFile(
		ambiguousBasePath,
		`${await readFile(ambiguousBasePath, "utf8")}\n## Entropy\n\n${inheritedDisplay}\n## Duplicate display\n\n${inheritedDisplay}`,
		"utf8",
	);
	await assert.rejects(
		execute(toolFor(ambiguousRoot), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-ambiguous-display-selector-r49",
			replacements: [
				{
					id: "correct-first-duplicate-display",
					oldText: `## Entropy\n\n${inheritedDisplay}`,
					newText: `## Entropy\n\n${correctedDisplay}`,
					authorizedEquations: [{ displayBlock: inheritedDisplay }],
				},
			],
		}),
		/displayBlock authorization.*duplicate or ambiguous/i,
	);
});

test("derive_revision fails closed when an inherited display is omitted without its matching authorization", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const basePath = path.join(root, "proposals/matematica_propuesta_CREDA.md");
	const baseBefore = await readFile(basePath);
	const secondEquation =
		"$$\n\\begin{aligned}\na &= b + c\\\\\nd &= e\n\\end{aligned}\n\\label{eq:ksc}\n\\tag{2}\n$$\n";

	await assert.rejects(
		execute(tool, {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-unauthorized-removal-r33",
			replacements: [{ id: "remove-ksc", oldText: secondEquation, newText: "" }],
		}),
		/omits or alters an inherited display block without matching authorization/i,
	);
	await assert.rejects(
		readFile(path.join(root, "proposals/research-concept-creda-unauthorized-removal-r33.md")),
		(error) => error?.code === "ENOENT",
	);
	assert.deepEqual(await readFile(basePath), baseBefore);
});

test("derive_revision rejects overlapping and ambiguous exact replacements", async () => {
	const overlapRoot = await fixture();
	await assert.rejects(
		execute(toolFor(overlapRoot), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-overlap-r34",
			replacements: [
			{
				id: "heading-and-inline",
				oldText: String.raw`# CREDA base

Inline source math \(x + 1\) must normalize.
`,
				newText: "# Corrected CREDA base\n",
			},
			{
				id: "inline-only",
				oldText: String.raw`Inline source math \(x + 1\) must normalize.
`,
				newText: "Inline source math is corrected.\n",
			},
		],
		}),
		/overlap/i,
	);

	const ambiguousRoot = await fixture();
	await assert.rejects(
		execute(toolFor(ambiguousRoot), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-ambiguous-replacement-r35",
			replacements: [
				{
					id: "ambiguous-prose",
					oldText: "Repeated prose anchor.",
					newText: "Corrected prose anchor.",
				},
			],
		}),
		/oldText.*not unique/i,
	);

	const reorderRoot = await fixture();
	const firstBlock = "$$\nE = mc^2.\n\\tag{1}\n$$\n";
	const secondBlock =
		"$$\n\\begin{aligned}\na &= b + c\\\\\nd &= e\n\\end{aligned}\n\\label{eq:ksc}\n\\tag{2}\n$$\n";
	await assert.rejects(
		execute(toolFor(reorderRoot), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-reordered-r39",
			replacements: [
				{
					id: "move-second-first",
					oldText: firstBlock,
					newText: secondBlock,
					authorizedEquations: [{ numberedTag: 1 }],
				},
				{
					id: "move-first-second",
					oldText: secondBlock,
					newText: firstBlock,
					authorizedEquations: [{ equationLabel: "eq:ksc" }],
				},
			],
		}),
		/copying or reordering inherited display blocks is denied/i,
	);

	const malformedRoot = await fixture();
	await assert.rejects(
		execute(toolFor(malformedRoot), {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-malformed-r40",
			replacements: [
				{
					id: "malformed-equation",
					oldText: firstBlock,
					newText: "$$\nE = mc^2 + 1.\n\\tag{1}\n",
					authorizedEquations: [{ numberedTag: 1 }],
				},
			],
		}),
		/unclosed display-math block/i,
	);
});

test("derive_revision preserves non-authorized equation bytes and order around a label-authorized correction", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const equationInsertion = "\nResearcher note after equation one.\n";
	const inheritedSecondBlock =
		"$$\n\\begin{aligned}\na &= b + c\\\\\nd &= e\n\\end{aligned}\n\\label{eq:ksc}\n\\tag{2}\n$$\n";
	const correctedSecondBlock =
		"$$\n\\begin{aligned}\na &= b + c\\\\\nd &= e + 1\n\\end{aligned}\n\\label{eq:ksc}\n\\tag{2}\n$$\n";
	await execute(tool, {
		action: "derive_revision",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-order-r36",
		replacements: [
			{
				id: "correct-ksc-equation",
				oldText: inheritedSecondBlock,
				newText: correctedSecondBlock,
				authorizedEquations: [{ equationLabel: "eq:ksc" }],
			},
		],
		insertions: [
			{
				id: "equation-one-note",
				anchor: { numberedTag: 1 },
				position: "after",
				content: equationInsertion,
			},
		],
	});

	const output = await readFile(
		path.join(root, "proposals/research-concept-creda-order-r36.md"),
		"utf8",
	);
	const firstBlock = "$$\nE = mc^2.\n\\tag{1}\n$$\n";
	const firstIndex = output.indexOf(firstBlock);
	const secondIndex = output.indexOf(correctedSecondBlock);
	assert.ok(firstIndex > artifactMarker.length);
	assert.equal(output.slice(firstIndex, firstIndex + firstBlock.length), firstBlock);
	assert.ok(output.includes(`${firstBlock}${equationInsertion}`));
	assert.ok(secondIndex > firstIndex + firstBlock.length + equationInsertion.length);
	assert.equal(output.slice(secondIndex, secondIndex + correctedSecondBlock.length), correctedSecondBlock);
	assert.ok(!output.includes(inheritedSecondBlock));
});

test("derive_revision accepts only the fixed base and never replaces an existing revision target", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const replacement = {
		id: "rename-section",
		oldText: "## Unique insertion section\n",
		newText: "## Corrected insertion section\n",
	};
	await assert.rejects(
		execute(tool, {
			action: "derive_revision",
			resource: "proposal",
			base: "../matematica_propuesta_CREDA.md",
			slug: "creda-wrong-base-r37",
			replacements: [replacement],
		}),
		/accepts only the fixed base/i,
	);

	const target = path.join(root, "proposals/research-concept-creda-existing-revision-r38.md");
	const existing = Buffer.from(`${artifactMarker}# Existing revision\n`, "utf8");
	await writeFile(target, existing);
	await assert.rejects(
		execute(tool, {
			action: "derive_revision",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-existing-revision-r38",
			replacements: [replacement],
		}),
		/requires a new proposal target.*never replaces/i,
	);
	assert.deepEqual(await readFile(target), existing);
});

test("derive appends the single final pending-obligations section through an unanchored end insertion", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-creda-pending-r13.md");
	const anchoredInsertion = "\nAnchored addition.\n";
	const endInsertion =
		"\n## Supuestos y obligaciones matemáticas pendientes\n\n- Confirmar la condición de frontera final.\n";

	const result = await execute(tool, {
		action: "derive",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-pending-r13",
		insertions: [
			{ id: "pending-obligations", position: "end", content: endInsertion },
			{
				id: "anchored-addition",
				anchor: "# CREDA base\n",
				position: "after",
				content: anchoredInsertion,
			},
		],
	});

	const normalizedBase = fixedCredaBase
		.replace(String.raw`\(x + 1\)`, "$x + 1$")
		.replace(String.raw`\(\alpha = 2\)`, "$\\alpha = 2$");
	const expectedCopiedResult = normalizedBase.replace(
		"# CREDA base\n",
		`# CREDA base\n${anchoredInsertion}`,
	);
	const output = await readFile(target, "utf8");
	assert.equal(output, `${artifactMarker}${expectedCopiedResult}${endInsertion}`);
	assert.equal(
		(output.match(/^## Supuestos y obligaciones matemáticas pendientes$/gm) ?? []).length,
		1,
	);
	assert.equal(result.details.insertionCount, 2);
	assert.equal(result.details.displayBlocksPreserved, 2);
	assert.equal(result.details.numberedEquationsPreserved, 2);
});

test("derive rejects multiple, anchored, duplicate, oversized, marker-bearing, and path-unsafe end insertions", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const cases = [
		{
			slug: "creda-two-ends-r14",
			insertions: [
				{ id: "first-end", position: "end", content: "First pending section.\n" },
				{ id: "second-end", position: "end", content: "Second pending section.\n" },
			],
			error: /at most one end insertion/i,
		},
		{
			slug: "creda-anchored-end-r15",
			insertions: [
				{
					id: "anchored-end",
					anchor: "# CREDA base\n",
					position: "end",
					content: "Pending section.\n",
				},
			],
			error: /end insertion.*must not include an anchor/i,
		},
		{
			slug: "creda-duplicate-end-r16",
			insertions: [
				{ id: "same", position: "end", content: "Pending section.\n" },
				{ id: "same", anchor: "# CREDA base\n", position: "after", content: "Addition.\n" },
			],
			error: /duplicate insertion id/i,
		},
		{
			slug: "creda-marker-end-r17",
			insertions: [
				{
					id: "unsafe-marker",
					position: "end",
					content: "<!-- proposal-workspace:artifact:v1 -->\n",
				},
			],
			error: /invalid content/i,
		},
		{
			slug: "creda-oversized-end-r18",
			insertions: [{ id: "oversized", position: "end", content: "x".repeat(64 * 1024 + 1) }],
			error: /invalid content/i,
		},
	];

	for (const candidate of cases) {
		await assert.rejects(
			execute(tool, {
				action: "derive",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: candidate.slug,
				insertions: candidate.insertions,
			}),
			candidate.error,
		);
		await assert.rejects(
			readFile(path.join(root, `proposals/research-concept-${candidate.slug}.md`)),
			(error) => error?.code === "ENOENT",
		);
	}

	await assert.rejects(
		execute(tool, {
			action: "derive",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "../escape-r19",
			insertions: [{ id: "safe-end", position: "end", content: "Pending section.\n" }],
		}),
		/proposal_workspace blocked:.*slug/i,
	);
});

test("derive preserves every base display block and numbered equation byte-for-byte in source order", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	await execute(tool, {
		action: "derive",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-equations-r07",
		insertions: [
			{
				id: "preface",
				anchor: "# CREDA base\n",
				position: "after",
				content: "\nDerived preface.\n",
			},
		],
	});
	const output = await readFile(
		path.join(root, "proposals/research-concept-creda-equations-r07.md"),
		"utf8",
	);
	const firstBlock = "$$\nE = mc^2.\n\\tag{1}\n$$\n";
	const secondBlock =
		"$$\n\\begin{aligned}\na &= b + c\\\\\nd &= e\n\\end{aligned}\n\\label{eq:ksc}\n\\tag{2}\n$$\n";
	const firstIndex = output.indexOf(firstBlock);
	const secondIndex = output.indexOf(secondBlock);
	assert.ok(firstIndex > artifactMarker.length);
	assert.ok(secondIndex > firstIndex + firstBlock.length);
	assert.equal(output.slice(firstIndex, firstIndex + firstBlock.length), firstBlock);
	assert.equal(output.slice(secondIndex, secondIndex + secondBlock.length), secondBlock);
});

test("derive inserts equation anchors only after their complete parsed base display blocks", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const firstInsertion = "\nNumbered-tag adaptation.\n";
	const alignInsertion = "\nLabel-anchored align adaptation.\n";
	await execute(tool, {
		action: "derive",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-equation-anchors-r24",
		insertions: [
			{
				id: "tag-adaptation",
				anchor: { numberedTag: 1 },
				position: "after",
				content: firstInsertion,
			},
			{
				id: "align-adaptation",
				anchor: { equationLabel: "eq:ksc" },
				position: "after",
				content: alignInsertion,
			},
		],
	});

	const output = await readFile(
		path.join(root, "proposals/research-concept-creda-equation-anchors-r24.md"),
		"utf8",
	);
	const firstBlock = "$$\nE = mc^2.\n\\tag{1}\n$$\n";
	const alignBlock =
		"$$\n\\begin{aligned}\na &= b + c\\\\\nd &= e\n\\end{aligned}\n\\label{eq:ksc}\n\\tag{2}\n$$\n";
	assert.ok(output.includes(`${firstBlock}${firstInsertion}`));
	assert.ok(output.includes(`${alignBlock}${alignInsertion}`));
	assert.equal(output.slice(output.indexOf(alignBlock), output.indexOf(alignBlock) + alignBlock.length), alignBlock);
});

test("derive rejects unsafe, unknown, duplicate, ambiguous, non-display, and non-after equation anchors", async () => {
	const cases = [
		{
			slug: "creda-unknown-label-r25",
			anchor: { equationLabel: "eq:not-in-fixed-base" },
			error: /equation label.*unknown.*fixed CREDA base/i,
		},
		{
			slug: "creda-duplicate-label-r26",
			anchor: { equationLabel: "eq:ksc" },
			mutate: (base) => base.replace("\\tag{1}", "\\label{eq:ksc}\n\\tag{1}"),
			error: /equation label.*duplicate or ambiguous/i,
		},
		{
			slug: "creda-outside-label-r27",
			anchor: { equationLabel: "eq:outside" },
			mutate: (base) => `${base}\nOutside display \\label{eq:outside}.\n`,
			error: /equation label.*not within display math/i,
		},
		{
			slug: "creda-ambiguous-equation-r28",
			anchor: { equationLabel: "eq:ksc", numberedTag: 2 },
			error: /equation anchor.*ambiguous/i,
		},
		{
			slug: "creda-invalid-tag-r29",
			anchor: { numberedTag: 0 },
			error: /invalid numbered tag selector/i,
		},
		{
			slug: "creda-duplicate-tag-r30",
			anchor: { numberedTag: 2 },
			mutate: (base) => base.replace("\\tag{1}", "\\tag{2}"),
			error: /numbered tag.*duplicate or ambiguous/i,
		},
		{
			slug: "creda-before-equation-r31",
			anchor: { equationLabel: "eq:ksc" },
			position: "before",
			error: /equation anchor.*only supports position after/i,
		},
	];

	for (const candidate of cases) {
		const root = await fixture();
		if (candidate.mutate) {
			const basePath = path.join(root, "proposals/matematica_propuesta_CREDA.md");
			await writeFile(basePath, candidate.mutate(await readFile(basePath, "utf8")), "utf8");
		}
		await assert.rejects(
			execute(toolFor(root), {
				action: "derive",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: candidate.slug,
				insertions: [
					{
						id: "equation-adaptation",
						anchor: candidate.anchor,
						position: candidate.position ?? "after",
						content: "\nAddition.\n",
					},
				],
			}),
			candidate.error,
		);
		await assert.rejects(
			readFile(path.join(root, `proposals/research-concept-${candidate.slug}.md`)),
			(error) => error?.code === "ENOENT",
		);
	}
});

test("derive fails closed on missing, non-unique, and display-block-splitting anchors", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const cases = [
		{ slug: "creda-missing-r08", id: "missing", anchor: "## Not in the base\n", error: /anchor.*missing/i },
		{ slug: "creda-duplicate-r09", id: "duplicate", anchor: "Repeated prose anchor.", error: /anchor.*not unique/i },
		{ slug: "creda-split-r10", id: "split", anchor: "E = mc^2.", error: /split a base display-math block/i },
	];
	for (const candidate of cases) {
		await assert.rejects(
			execute(tool, {
				action: "derive",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: candidate.slug,
				insertions: [
					{ id: candidate.id, anchor: candidate.anchor, position: "after", content: "\nAddition.\n" },
				],
			}),
			candidate.error,
		);
		await assert.rejects(
			readFile(path.join(root, `proposals/research-concept-${candidate.slug}.md`)),
			(error) => error?.code === "ENOENT",
		);
	}
});

test("derive rejects a base with missing display blocks and never replaces an existing revision target", async () => {
	const damagedRoot = await fixture();
	await writeFile(
		path.join(damagedRoot, "proposals/matematica_propuesta_CREDA.md"),
		"# Damaged CREDA base\n\nInline only \\(x\\).\n",
		"utf8",
	);
	await assert.rejects(
		execute(toolFor(damagedRoot), {
			action: "derive",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-damaged-r11",
			insertions: [{ id: "note", anchor: "# Damaged CREDA base\n", position: "after", content: "note\n" }],
		}),
		/missing its display-math blocks/i,
	);

	const existingRoot = await fixture();
	const existingTarget = path.join(existingRoot, "proposals/research-concept-creda-existing-r12.md");
	const existingBytes = Buffer.from(`${artifactMarker}# Existing revision\n`, "utf8");
	await writeFile(existingTarget, existingBytes);
	await assert.rejects(
		execute(toolFor(existingRoot), {
			action: "derive",
			resource: "proposal",
			base: "matematica_propuesta_CREDA.md",
			slug: "creda-existing-r12",
			insertions: [{ id: "note", anchor: "# CREDA base\n", position: "after", content: "note\n" }],
		}),
		/requires a new proposal target.*never replaces/i,
	);
	assert.deepEqual(await readFile(existingTarget), existingBytes);
});

test("derive rejects duplicate insertion ids, reserved content, arbitrary bases, and path attacks", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const common = {
		action: "derive",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "creda-validation-r11",
	};
	await assert.rejects(
		execute(tool, {
			...common,
			insertions: [
				{ id: "same", anchor: "# CREDA base\n", position: "after", content: "one\n" },
				{ id: "same", anchor: "## Unique insertion section\n", position: "after", content: "two\n" },
			],
		}),
		/duplicate insertion id/i,
	);
	await assert.rejects(
		execute(tool, {
			...common,
			insertions: [
				{
					id: "reserved",
					anchor: "# CREDA base\n",
					position: "after",
					content: "<!-- proposal-workspace:artifact:v1 -->\n",
				},
			],
		}),
		/invalid content/i,
	);
	for (const base of ["../matematica_propuesta_CREDA.md", "/tmp/matematica_propuesta_CREDA.md", "base.md"]) {
		await assert.rejects(
			execute(tool, {
				...common,
				base,
				insertions: [{ id: "safe", anchor: "# CREDA base\n", position: "after", content: "safe\n" }],
			}),
			/accepts only the fixed base/i,
		);
	}
	for (const slug of ["../escape-r01", "creda-r1"]) {
		await assert.rejects(
			execute(tool, {
				...common,
				slug,
				insertions: [{ id: "safe", anchor: "# CREDA base\n", position: "after", content: "safe\n" }],
			}),
			/proposal_workspace blocked:.*slug/i,
		);
	}
});

test("appends a bounded immutable revision without UI and preserves all prior bytes", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-safe-topic.md");
	await execute(tool, {
		action: "write",
		resource: "proposal",
		slug: "safe-topic",
		content: "# Existing\r\n\r\nPrior bytes stay exact.\n",
	});
	const prior = await readFile(target);
	const ctx = {
		hasUI: false,
		ui: { confirm: async () => assert.fail("append must not request UI confirmation") },
	};

	const appended = await execute(
		tool,
		{
			action: "append",
			resource: "proposal",
			slug: "safe-topic",
			content: "## Gate 2 revision\n\nApproved mathematical refinement.",
		},
		ctx,
	);
	const artifact = await readFile(target);
	assert.deepEqual(artifact.subarray(0, prior.length), prior);
	assert.match(artifact.subarray(prior.length).toString("utf8"), /proposal-workspace:revision:start/);
	assert.match(artifact.subarray(prior.length).toString("utf8"), /## Gate 2 revision/);
	assert.match(artifact.subarray(prior.length).toString("utf8"), /proposal-workspace:revision:end/);
	assert.equal(appended.details.operation, "append");
	assert.equal(appended.details.path, "proposals/research-concept-safe-topic.md");
	assert.equal(appended.details.revision.offset, prior.length);
	assert.equal(appended.details.revision.resultingBytes, artifact.length);
	assert.match(appended.details.revision.id, /^sha256:[a-f0-9]{64}$/);
	assert.match(appended.details.revision.blockSha256, /^[a-f0-9]{64}$/);
	assert.match(await text(appended), /byte offset/);
});

test("append requires an existing target and enforces immutable block boundaries", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-safe-topic.md");
	await assert.rejects(
		execute(tool, {
			action: "append",
			resource: "proposal",
			slug: "safe-topic",
			content: "## Revision\n",
		}),
		/proposal_workspace blocked:.*requires an existing generated proposal target/i,
	);

	await execute(tool, {
		action: "write",
		resource: "proposal",
		slug: "safe-topic",
		content: "# Existing\n",
	});
	await assert.rejects(
		execute(tool, {
			action: "append",
			resource: "proposal",
			slug: "safe-topic",
			content: "x".repeat(64 * 1024),
		}),
		/proposal_workspace blocked:.*revision block exceeds/i,
	);
	await assert.rejects(
		execute(tool, {
			action: "append",
			resource: "proposal",
			slug: "safe-topic",
			content: "<!-- proposal-workspace:revision:end -->",
		}),
		/proposal_workspace blocked:.*reserved revision marker/i,
	);
	assert.equal(await readFile(target, "utf8"), `${artifactMarker}# Existing\n`);
});

test("append denies a manually-created matching-name file without changing any bytes", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-manual-topic.md");
	const manualBytes = Buffer.from("# Manually created base-like file\r\nExact bytes must survive.\n", "utf8");
	await writeFile(target, manualBytes);

	await assert.rejects(
		execute(tool, {
			action: "append",
			resource: "proposal",
			slug: "manual-topic",
			content: "## Unauthorized append\n",
		}),
		/proposal_workspace blocked:.*not marked as a tool-created artifact/i,
	);
	assert.deepEqual(await readFile(target), manualBytes);
});

test("append rejects bases, traversal, reference paths, symlinks, and hard links", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	await assert.rejects(
		execute(tool, {
			action: "append",
			resource: "base",
			name: "base.md",
			content: "forbidden\n",
		}),
		/proposal_workspace blocked:.*action\/resource/i,
	);
	await assert.rejects(
		execute(tool, {
			action: "append",
			resource: "proposal",
			slug: "../base",
			content: "forbidden\n",
		}),
		/proposal_workspace blocked:.*slug/i,
	);
	await assert.rejects(
		execute(tool, {
			action: "append",
			resource: "proposal",
			name: "guidance/reference-papers/secret.md",
			slug: "safe-topic",
			content: "forbidden\n",
		}),
		/proposal_workspace blocked:.*action\/resource/i,
	);

	const external = await mkdtemp(path.join(os.tmpdir(), "proposal-workspace-append-external-"));
	const externalTarget = path.join(external, "outside.md");
	await writeFile(externalTarget, "external bytes\n", "utf8");
	await symlink(externalTarget, path.join(root, "proposals/research-concept-symlinked.md"));
	await assert.rejects(
		execute(tool, {
			action: "append",
			resource: "proposal",
			slug: "symlinked",
			content: "forbidden\n",
		}),
		/proposal_workspace blocked:.*standalone/i,
	);
	assert.equal(await readFile(externalTarget, "utf8"), "external bytes\n");

	await link(
		path.join(root, "proposals/base.md"),
		path.join(root, "proposals/research-concept-hard-linked.md"),
	);
	await assert.rejects(
		execute(tool, {
			action: "append",
			resource: "proposal",
			slug: "hard-linked",
			content: "forbidden\n",
		}),
		/proposal_workspace blocked:.*standalone/i,
	);
	assert.equal(await readFile(path.join(root, "proposals/base.md"), "utf8"), "immutable base\n");
});

test("append does not bypass replacement authorization", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-safe-topic.md");
	await execute(tool, {
		action: "write",
		resource: "proposal",
		slug: "safe-topic",
		content: "# Existing\n",
	});
	await execute(tool, {
		action: "append",
		resource: "proposal",
		slug: "safe-topic",
		content: "## Approved revision\n",
	});
	const afterAppend = await readFile(target);

	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "proposal",
			slug: "safe-topic",
			content: "# Unauthorized replacement\n",
		}),
		/proposal_workspace blocked:.*already exists.*capability/i,
	);
	await assert.rejects(
		execute(tool, {
			action: "append",
			resource: "proposal",
			slug: "safe-topic",
			content: "## Another revision\n",
			capability: "A".repeat(43),
		}),
		/proposal_workspace blocked:.*action\/resource/i,
	);
	assert.deepEqual(await readFile(target), afterAppend);
});

test("denies existing-target writes and rejects boolean approval claims", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-safe-topic.md");
	await writeFile(target, "# Existing\n", "utf8");

	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "proposal",
			slug: "safe-topic",
			content: "# Replaced\n",
		}),
		/proposal_workspace blocked:.*already exists.*capability/i,
	);
	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "proposal",
			slug: "safe-topic",
			content: "# Replaced\n",
			overwrite: true,
		}),
		/proposal_workspace blocked:.*unknown authorization.*overwrite/i,
	);
	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "proposal",
			slug: "safe-topic",
			content: "# Replaced\n",
			capability: "the researcher explicitly approved replacement",
		}),
		/proposal_workspace blocked:.*capability is malformed/i,
	);
	assert.equal(await readFile(target, "utf8"), "# Existing\n");
});

test("UI confirmation denial issues no overwrite capability and leaves the target unchanged", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-safe-topic.md");
	await writeFile(target, "# Existing\n", "utf8");

	await assert.rejects(
		execute(
			tool,
			{ action: "authorize_overwrite", resource: "proposal", slug: "safe-topic" },
			uiContext(async () => false),
		),
		/proposal_workspace blocked:.*human did not approve/i,
	);
	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "proposal",
			slug: "safe-topic",
			content: "# Replaced\n",
		}),
		/proposal_workspace blocked:.*already exists.*capability/i,
	);
	assert.equal(await readFile(target, "utf8"), "# Existing\n");
});

test("preserves the tool-owned marker through a human-approved destructive replacement", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-safe-topic.md");
	await execute(tool, {
		action: "write",
		resource: "proposal",
		slug: "safe-topic",
		content: "# Existing\n",
	});
	let confirmation;
	const authorization = await execute(
		tool,
		{ action: "authorize_overwrite", resource: "proposal", slug: "safe-topic" },
		uiContext(async (title, message) => {
			confirmation = { title, message };
			return true;
		}),
	);
	assert.match(confirmation.title, /authorize proposal replacement/i);
	assert.match(confirmation.message, /proposals\/research-concept-safe-topic\.md/);
	assert.equal(typeof authorization.details.capability, "string");

	await execute(tool, {
		action: "write",
		resource: "proposal",
		slug: "safe-topic",
		content: "# Replaced\n",
		capability: authorization.details.capability,
	});
	assert.equal(await readFile(target, "utf8"), `${artifactMarker}# Replaced\n`);
	await execute(tool, {
		action: "append",
		resource: "proposal",
		slug: "safe-topic",
		content: "## Still tool-owned\n",
	});
	assert.match(await readFile(target, "utf8"), /## Still tool-owned/);
});

test("rejects a capability when its target is replaced before write", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-safe-topic.md");
	const replacement = path.join(root, "proposals/replacement.md");
	await writeFile(target, "# Existing\n", "utf8");
	const initialIdentity = await stat(target);
	const authorization = await execute(
		tool,
		{ action: "authorize_overwrite", resource: "proposal", slug: "safe-topic" },
		uiContext(async () => true),
	);
	await writeFile(replacement, "# Replaced outside tool\n", "utf8");
	await rename(replacement, target);
	const replacementIdentity = await stat(target);
	assert.notDeepEqual(
		[replacementIdentity.dev, replacementIdentity.ino],
		[initialIdentity.dev, initialIdentity.ino],
	);

	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "proposal",
			slug: "safe-topic",
			content: "# Unauthorized overwrite\n",
			capability: authorization.details.capability,
		}),
		/proposal_workspace blocked:.*does not match the current proposal target/i,
	);
	assert.equal(await readFile(target, "utf8"), "# Replaced outside tool\n");
});

test("binds overwrite capabilities to the exact existing target", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const firstTarget = path.join(root, "proposals/research-concept-first-topic.md");
	const secondTarget = path.join(root, "proposals/research-concept-second-topic.md");
	await writeFile(firstTarget, "# First\n", "utf8");
	await writeFile(secondTarget, "# Second\n", "utf8");
	const authorization = await execute(
		tool,
		{ action: "authorize_overwrite", resource: "proposal", slug: "first-topic" },
		uiContext(async () => true),
	);

	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "proposal",
			slug: "second-topic",
			content: "# Wrong target\n",
			capability: authorization.details.capability,
		}),
		/proposal_workspace blocked:.*does not match the current proposal target/i,
	);
	assert.equal(await readFile(firstTarget, "utf8"), "# First\n");
	assert.equal(await readFile(secondTarget, "utf8"), "# Second\n");
});

test("rejects replayed and expired overwrite capabilities", async () => {
	const root = await fixture();
	let now = 1_000;
	const tool = toolFor(root, { now: () => now });
	const target = path.join(root, "proposals/research-concept-safe-topic.md");
	await writeFile(target, "# Existing\n", "utf8");
	const approve = uiContext(async () => true);

	const firstAuthorization = await execute(
		tool,
		{ action: "authorize_overwrite", resource: "proposal", slug: "safe-topic" },
		approve,
	);
	const firstCapability = firstAuthorization.details.capability;
	await execute(tool, {
		action: "write",
		resource: "proposal",
		slug: "safe-topic",
		content: "# First replacement\n",
		capability: firstCapability,
	});
	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "proposal",
			slug: "safe-topic",
			content: "# Replay\n",
			capability: firstCapability,
		}),
		/proposal_workspace blocked:.*invalid or has already been consumed/i,
	);

	const expiringAuthorization = await execute(
		tool,
		{ action: "authorize_overwrite", resource: "proposal", slug: "safe-topic" },
		approve,
	);
	now += extension.OVERWRITE_CAPABILITY_TTL_MS + 1;
	await assert.rejects(
		execute(tool, {
			action: "write",
			resource: "proposal",
			slug: "safe-topic",
			content: "# Expired\n",
			capability: expiringAuthorization.details.capability,
		}),
		/proposal_workspace blocked:.*capability has expired/i,
	);
	assert.equal(await readFile(target, "utf8"), "# First replacement\n");
});

test("fails closed when overwrite authorization has no UI", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const target = path.join(root, "proposals/research-concept-safe-topic.md");
	await writeFile(target, "# Existing\n", "utf8");

	await assert.rejects(
		execute(
			tool,
			{ action: "authorize_overwrite", resource: "proposal", slug: "safe-topic" },
			{ hasUI: false, ui: { confirm: async () => assert.fail("headless mode must not prompt") } },
		),
		/proposal_workspace blocked:.*requires an interactive UI confirmation/i,
	);
	assert.equal(await readFile(target, "utf8"), "# Existing\n");
});

test("accepts lowercase-suffixed numbered tags and rejects malformed tag values", async () => {
	const validTags = ["1", "15", "14a", "14b", "20c", "23a"];
	const validRoot = await fixture();
	const validBase = [
		"# Tag validation",
		"",
		...validTags.flatMap((tag, index) => ["$$", `q_${index + 1} = ${index + 1}.`, `\\tag{${tag}}`, "$$", ""]),
	].join("\n");
	await writeFile(path.join(validRoot, "proposals/matematica_propuesta_CREDA.md"), validBase, "utf8");
	const validResult = await execute(toolFor(validRoot), {
		action: "derive",
		resource: "proposal",
		base: "matematica_propuesta_CREDA.md",
		slug: "tag-values-valid-r01",
		insertions: [{ id: "tag-note", position: "end", content: "\nAccepted tags remain valid.\n" }],
	});
	assert.equal(validResult.details.candidateValidation.status, "passed");

	const invalidTags = ["0", "00", "01", "14A", "a14", "14_a", "14-1", "1000000"];
	for (const [index, tag] of invalidTags.entries()) {
		const root = await fixture();
		const base = `# Invalid tag\n\n$$\nq = 1.\n\\tag{${tag}}\n$$\n`;
		await writeFile(path.join(root, "proposals/matematica_propuesta_CREDA.md"), base, "utf8");
		await assert.rejects(
			execute(toolFor(root), {
				action: "derive",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: `tag-value-invalid-${index}-r01`,
				insertions: [{ id: "tag-note", position: "end", content: "\nRejected tag.\n" }],
			}),
			/malformed equation label or numbered tag/i,
		);
	}

	for (const [index, malformed] of [String.raw`\tag{15`, String.raw`\tag 15}`, String.raw`\tag15`].entries()) {
		const root = await fixture();
		const base = `# Incomplete tag\n\n$$\nq = 1.\n${malformed}\n$$\n`;
		await writeFile(path.join(root, "proposals/matematica_propuesta_CREDA.md"), base, "utf8");
		await assert.rejects(
			execute(toolFor(root), {
				action: "derive",
				resource: "proposal",
				base: "matematica_propuesta_CREDA.md",
				slug: `tag-braces-invalid-${index}-r01`,
				insertions: [{ id: "tag-note", position: "end", content: "\nRejected tag.\n" }],
			}),
			/malformed equation label or numbered tag/i,
		);
	}
});

test("derive_successor preserves inherited lowercase-suffixed tags during an unrelated exact display replacement", async () => {
	const root = await fixture();
	const tool = toolFor(root);
	const sourceBody = String.raw`# Tagged source

$$
a = 14.
\tag{14a}
$$

$$
b = 20.
\tag{20c}
$$

$$
c = 23.
\tag{23a}
$$

$$
d = 1.
$$
`;
	const manifest = await createManagedLatest(root, tool, "tagged-successor-r01", sourceBody);
	const result = await execute(tool, {
		action: "derive_successor",
		resource: "proposal",
		source: manifest.source.target,
		sourceSha256: manifest.source.sha256,
		slug: "tagged-successor-r02",
		patches: [{ id: "replace-untagged-display", kind: "replace", oldText: "d = 1.", newText: "d = 2." }],
	});

	assert.equal(result.details.patchCount, 1);
	assert.equal(result.details.unchangedByteCoverage.verified, true);
	assert.match(
		await readFile(path.join(root, "proposals/research-concept-tagged-successor-r02.md"), "utf8"),
		/\\tag\{14a\}[\s\S]*\\tag\{20c\}[\s\S]*\\tag\{23a\}/,
	);
});
