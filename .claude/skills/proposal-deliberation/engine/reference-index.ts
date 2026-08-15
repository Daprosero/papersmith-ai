import type { ReferenceIndex, StructuralIndex } from './types.js';
/**
 * How a proposal actually cites its own equations. `\eqref`/`\ref` need a
 * `\label`, which these documents do not use: they number with `\tag{N}` and
 * cite in prose as `(Ec. N)`. Left unrecognised, the reference index sees zero
 * references and its `missing` list is vacuously empty — so deleting a tagged
 * equation leaves every citation of it dangling with nothing to object.
 */
export const PROSE_REFERENCE=/\((?:Ec|Eq)\.\s*([0-9]+[a-z]?)\)/g;
export function buildReferenceIndex(source:string, index:StructuralIndex):ReferenceIndex {const labels:Record<string,string>={},tags:Record<string,string>={},duplicates:string[]=[],references:ReferenceIndex['references']=[]; for(const e of index.entries){const text=Buffer.from(source).subarray(e.startByte,e.endByte).toString(); for(const l of e.labels){if(labels[l])duplicates.push(`label:${l}`); else labels[l]=e.entryId} for(const t of e.tags){if(tags[t])duplicates.push(`tag:${t}`); else tags[t]=e.entryId} for(const m of text.matchAll(/\\(eqref|ref)\{([^}]+)\}/g)) references.push({kind:m[1],value:m[2],entryId:e.entryId}); for(const m of text.matchAll(PROSE_REFERENCE)) references.push({kind:'prose',value:m[1],entryId:e.entryId});} return {labels,tags,references,duplicates,missing:references.filter(x=>!labels[x.value]&&!tags[x.value]).map(x=>x.value)};}
