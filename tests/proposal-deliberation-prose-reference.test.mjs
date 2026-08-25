import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { createJiti } from 'jiti';
const jiti=createJiti(import.meta.url);
const engine=path.resolve('.claude/skills/_core/deliberation/engine');
const {PROSE_REFERENCE,buildReferenceIndex}=await jiti.import(path.join(engine,'reference-index.ts'));
const {mathAtoms,mathDelta}=await jiti.import(path.join(engine,'math-integrity.ts'));
const {buildStructuralIndex}=await jiti.import(path.join(engine,'document-index.ts'));
// These documents number with \tag{N} and cite as `(Ec. N)`; they never use
// \label/\eqref. Nothing exercised that convention before this file, so moving it
// behind the domain profile could not be told apart from deleting it.
const cited=(value)=>`## S\n\nSee (Ec. ${value}) above.\n\n$$\nx = 1 \\tag{${value}}\n$$\n`;
test('the prose citation form is what these documents actually use',()=>{
	assert.deepEqual([...'(Ec. 12) (Eq. 3a) (Ec.7)'.matchAll(PROSE_REFERENCE)].map(m=>m[1]),['12','3a','7']);
	assert.deepEqual([...'(Ecuacion 4) (Ec 5) [Ec. 6]'.matchAll(PROSE_REFERENCE)].map(m=>m[1]),[],'only the parenthesised abbreviated form counts');
});
test('a prose citation is a reference, and an uncited tag is not missing',()=>{
	const source=cited('12');
	const index=buildReferenceIndex(source,buildStructuralIndex(source));
	// Structural entries nest -- document contains subsection contains paragraph --
	// and each containing entry sees the same citation, so references carry one
	// row per container rather than one per citation. Asserting a count here would
	// pin the nesting depth of this fixture, not the convention under test.
	assert.ok(index.references.length>0,'the citation is seen at all');
	assert.deepEqual([...new Set(index.references.map(r=>`${r.kind}:${r.value}`))],['prose:12']);
	assert.deepEqual(index.missing,[],'the tag it cites is present');
});
test('deleting the tagged display leaves the citation dangling, and the index says so',()=>{
	const orphan='## S\n\nSee (Ec. 12) above.\n';
	const index=buildReferenceIndex(orphan,buildStructuralIndex(orphan));
	assert.ok(index.missing.length>0,'a citation with no surviving tag must be reported');
	assert.deepEqual([...new Set(index.missing)],['12']);
});
test('a prose citation is a mathematical atom that can be lost',()=>{
	assert.ok(mathAtoms(cited('12')).has('ref:12'),'the citation is an atom');
	const delta=mathDelta(cited('12'),'## S\n\nSee it above.\n');
	assert.ok(delta.lost.some(a=>a.id==='ref:12'),'dropping the citation is a loss');
	assert.equal(delta.lost.find(a=>a.id==='ref:12').text,'(Ec. 12)','the atom carries the citation as written');
});
