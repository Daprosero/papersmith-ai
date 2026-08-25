import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
const engineDir=path.resolve('.claude/skills/proposal-deliberation/engine');
const PROFILE='domain-profile.ts';
const profile=await readFile(path.join(engineDir,PROFILE),'utf8');
// Whatever this domain calls itself, it says so once. The lock reads those values
// back out of the profile rather than naming a project here, so a later domain is
// held to the same rule without this file being edited to know about it.
const declared=[...profile.matchAll(/^\t(?:deriveBase|baseLabel|baseLabelLong|exampleSlug): "([^"]+)",$/gm)].map(m=>m[1]);
const names=[...(profile.match(/^\tnames: \[([^\]]*)\],$/m)?.[1]??'').matchAll(/"([^"]+)"/g)].map(m=>m[1]);
const engineFiles=(await readdir(engineDir,{recursive:true,withFileTypes:true}))
	.filter(e=>e.isFile()&&e.name.endsWith('.ts')&&e.name!==PROFILE)
	.map(e=>path.join(e.parentPath??e.path,e.name));
const sources=await Promise.all(engineFiles.map(async file=>[path.relative(engineDir,file),await readFile(file,'utf8')]));
test('the profile declares its values and the names behind them',()=>{assert.equal(declared.length,4,`expected 4 declared values, found ${declared.length}`);assert.ok(names.length>0,'the profile declares no domain name, so the lock below would pass vacuously');for(const value of[...declared,...names])assert.notEqual(value.trim(),'');});
test('every declared name really is this domain speaking',()=>{const unused=names.filter(n=>!declared.some(v=>v.toLowerCase().includes(n.toLowerCase()))&&!profile.toLowerCase().includes(n.toLowerCase()));assert.deepEqual(unused,[],'a name no profile value contains is not this domain naming itself');});
test('no engine file outside the profile names the domain',()=>{
	assert.ok(sources.length>40,`expected the whole engine, scanned ${sources.length}`);
	const leaks=[];
	for(const[rel,source]of sources){const lower=source.toLowerCase();
		// Composed values catch the exact strings; `names` catches the same proper
		// noun re-spelled -- lowercased inside a slug, say, which is how the first
		// sweep of this engine left a residue behind.
		for(const value of declared)if(source.includes(value))leaks.push(`${rel} spells ${JSON.stringify(value)}`);
		for(const name of names)if(lower.includes(name.toLowerCase()))leaks.push(`${rel} names ${JSON.stringify(name)}`);}
	assert.deepEqual([...new Set(leaks)],[],'the engine must read these off the profile, never spell them');
});
