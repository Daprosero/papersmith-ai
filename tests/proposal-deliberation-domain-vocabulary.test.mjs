import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
import { createJiti } from 'jiti';
const jiti=createJiti(import.meta.url);
const engineDir=path.resolve('.claude/skills/proposal-deliberation/engine');
const {DOMAIN}=await jiti.import(path.join(engineDir,'domain-profile.ts'));
const {resolveIntent}=await jiti.import(path.join(engineDir,'intent-resolver.ts'));
const read=(name)=>readFile(path.join(engineDir,name),'utf8');
const v=DOMAIN.vocabulary;

// The engine's intent matching is Spanish and shared -- every domain says "mueve",
// "copia", "agrega". What is NOT shared is what the instruction is ABOUT, and that
// subject used to be spelled directly into intent resolution, locus scoring and the
// tutor gate. These tests pin the subject to the profile so a sibling domain can
// replace it without editing the engine.

// Fixtures below are written out, never built from `v`. Deriving the instruction
// from the profile makes the assertion true for ANY value the profile holds --
// it would pass just as happily on a profile that had been emptied.
test('a subject-matter instruction resolves to conceptual revision',()=>{
	for(const instruction of['revisá la regularización del documento','ajustá la motivación matemática','esto aplica a múltiples dominios','el enfoque semi-supervisado del método'])
		assert.equal(resolveIntent(instruction).intent,'CONCEPTUAL_REVISION',instruction);
	assert.notEqual(resolveIntent('revisá el párrafo tercero').intent,'CONCEPTUAL_REVISION','a neutral instruction must not be captured');
});
test('naming the subject picks the subject locus description',()=>{
	for(const instruction of['cambia la parte de one-hot','cambia la parte de one hot'])
		assert.equal(resolveIntent(instruction).targetDescription,v.subjectLocusDescription,instruction);
	assert.notEqual(resolveIntent('cambia el tercer párrafo').targetDescription,v.subjectLocusDescription);
});
test('the expert pattern classifies this domain’s own work',()=>{
	const expert=new RegExp(v.expertPattern,'i');
	for(const yes of['motivación matemática','la ecuación 3','regularización L2','enfoque semi-supervisado','el marco teórico'])
		assert.ok(expert.test(yes),yes);
	for(const no of['mové el párrafo','arreglá la tabla de resultados'])
		assert.equal(expert.test(no),false,no);
	// Limitation, stated rather than implied: this pins the pattern, not the
	// orchestrator gate it feeds. The structural test below is what ties the two
	// together; an end-to-end CONCEPTUAL_REVISION gate test needs a full
	// orchestrator fixture and does not exist yet.
});
test('the display noun and its stripping form agree',()=>{
	const noun=new RegExp(v.displayNounPattern,'i'),strip=new RegExp(v.displayNounStripPattern,'giu');
	assert.ok(noun.test('mostrame la ecuación'));
	assert.ok(noun.test('mostrame la ecuacion'),'the unaccented spelling is the same word');
	// Assert the noun is gone, not how many spaces replaced it: the stripping form
	// substitutes a space per match and the caller collapses whitespace later, so
	// pinning a spacing here would test the fixture rather than the convention.
	const stripped='la ecuación y las ecuaciones'.replace(strip,' ').replace(/\s+/g,' ').trim();
	assert.equal(stripped,'la y las','both inflections are stripped');
});
test('the engine reads the subject off the profile and never spells it',async()=>{
	for(const [file,needle] of [['intent-resolver.ts','DOMAIN.vocabulary'],['orchestrator.ts','DOMAIN.vocabulary.expertPattern'],['target-resolver.ts','DOMAIN.vocabulary']]){
		const source=await read(file);
		assert.ok(source.includes(needle),`${file} must read ${needle}`);
		for(const term of [...v.subjectTerms,...v.conceptualTerms])
			assert.equal(source.toLowerCase().includes(term.toLowerCase()),false,`${file} still spells ${JSON.stringify(term)}`);
	}
});
