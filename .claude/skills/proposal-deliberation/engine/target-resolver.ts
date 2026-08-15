import { buildStructuralIndex } from './document-index.js';
import { sha256,type CompositeTarget,type DocumentState,type SectionReplacementContract,type StructuralEntry,type TargetCandidate } from './types.js';

export type TargetResolutionOptions={allowInterEntryWhitespaceFallback?:boolean};
export type SectionRangeResolution={candidate?:TargetCandidate;entryIds?:string[];reason?:'SECTION_RANGE_INVALID'|'SECTION_RANGE_NOT_FOUND'|'SECTION_RANGE_AMBIGUOUS'|'SECTION_RANGE_REVERSED'|'SECTION_RANGE_INCOMPLETE_BODY'};
export type SuccessorTargetResolution={candidates:TargetCandidate[];reason?:'SUCCESSOR_TARGET_NOT_FOUND'};

type StructuralCore={entry:StructuralEntry;startByte:number;endByte:number;text:Buffer};

const words=(value:string)=>(value.toLowerCase().match(/[\p{L}\p{N}_-]{2,}/gu)??[]);
/**
 * Function words that carry no discriminating power in a heading. Term matching
 * is a plain substring test against the heading line, so a single `de` matches
 * nearly every Spanish heading, lifts them all into contention, and collapses
 * the ambiguity gate's score margin — turning an otherwise exact locus
 * description into a blocked one.
 */
const STOPWORDS=new Set(['de','del','la','el','los','las','un','una','unos','unas','en','con','por','para','sin','sobre','entre','al','lo','su','sus','que','se','es','son','como','mas','más','of','the','an','in','on','for','to','with','and','or','by','from','is','are','as','at','be']);
/** Drops stopword tokens, keeping the original when nothing discriminating survives. */
const dropStopwords=(value:string)=>{
 const kept=value.split(/\s+/u).filter(token=>!STOPWORDS.has(token.toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu,''))).join(' ').trim();
 return words(kept).length?kept:value;
};
const escapeRegExp=(value:string)=>value.replace(/[.*+?^${}()|[\]\\]/gu,'\\$&');
/**
 * True when `value` occurs in `query` as a standalone token.
 *
 * Label and tag matching used to ask `query.includes(label)` — the containment
 * test the wrong way round. A one-character tag like `3` is a substring of any
 * query mentioning `30`, `13` or `3-3`, and each match is worth 8 points against
 * 3 for a content word, so a spurious hit outranks nearly three real ones.
 * Boundaries fix that without breaking punctuated labels like `eq:uno`, whose
 * `:` is not a word character on either side.
 */
const isolatedInQuery=(query:string,value:string)=>new RegExp(`(?<![\\p{L}\\p{N}_-])${escapeRegExp(value)}(?![\\p{L}\\p{N}_-])`,'u').test(query);
/**
 * Maps each label/tag to the smallest entry carrying it — the one that actually
 * declares it.
 *
 * `document-index` reads an entry's tags straight out of its own text, and a
 * section's text contains every equation inside it, so the section ends up
 * carrying `\tag{3}` without ever writing it. Since the section also matches all
 * the prose the equation lacks, asking for equation 3 resolved to the whole
 * section that owns it. Crediting only the declaring entry keeps the ancestor
 * from outscoring its own descendant.
 */
function declaringEntries(entries:readonly StructuralEntry[],key:'labels'|'tags'){const owner=new Map<string,{id:string;size:number}>();for(const entry of entries){const size=entry.endByte-entry.startByte;for(const value of entry[key]){const current=owner.get(value);if(!current||size<current.size)owner.set(value,{id:entry.entryId,size});}}return owner;}
const equationSymbols=(value:string)=>[...new Set(value.match(/\\[A-Za-z]+|\b[A-Za-z]\b/g)??[])];
const entryText=(state:DocumentState,id:string)=>{const e=state.structuralIndex.byId[id];return e?state.documentBytes.subarray(e.startByte,e.endByte).toString('utf8'):''};
const leaf=(entry:StructuralEntry)=>['display_equation','paragraph','inline_math_region','list','code_block','definition','theorem','algorithm'].includes(entry.type);
const sameHeadingPath=(left:string[],right:string[])=>JSON.stringify(left)===JSON.stringify(right);
const whitespaceOnly=(bytes:Buffer,start:number,end:number)=>/^\s*$/u.test(bytes.subarray(start,end).toString('utf8'));

function structuralCore(bytes:Buffer,entry:StructuralEntry):StructuralCore{
 let endByte=entry.endByte;
 if(entry.type==='display_equation'){
  const text=bytes.subarray(entry.startByte,entry.endByte).toString('utf8');
  const closing=[...text.matchAll(/^\$\$(?=[ \t]*(?:\r?$))/gm)].at(-1);
  if(closing?.index!==undefined)endByte=entry.startByte+Buffer.byteLength(text.slice(0,closing.index+2));
 }
 return {entry,startByte:entry.startByte,endByte,text:bytes.subarray(entry.startByte,endByte)};
}

function compositeCandidate(state:DocumentState,members:StructuralEntry[],startByte:number,endByte:number,evidence:string):TargetCandidate{
 const actualText=state.documentBytes.subarray(startByte,endByte);
 const textSha256=sha256(actualText);
 const composite:CompositeTarget={entryIds:members.map(entry=>entry.entryId),startByte,endByte,documentSha256:state.documentSha256,textSha256,exactProvidedText:actualText.toString('utf8')};
 return {entryId:`composite:${startByte}:${textSha256.slice(0,16)}`,type:'composite',headingPath:members[0].headingPath,matchedTerms:[],matchedLabels:[],matchedTags:[],matchedSymbols:[],score:100,confidence:1,shortPreview:actualText.toString('utf8').slice(0,180),evidence:[evidence],composite};
}

function exactCompositeTargets(state:DocumentState,providedText:string):TargetCandidate[]{
 const needle=Buffer.from(providedText);if(!needle.length)return [];
 const candidates:TargetCandidate[]=[];
 for(let start=state.documentBytes.indexOf(needle);start>=0;start=state.documentBytes.indexOf(needle,start+1)){
  const end=start+needle.length;
  const members=state.structuralIndex.entries.filter(e=>leaf(e)&&e.startByte>=start&&e.startByte<end&&e.endByte<=end+1).sort((a,b)=>a.startByte-b.startByte);
  if(!members.length||members[0].startByte!==start||members.at(-1)!.endByte<end||members.at(-1)!.endByte>end+1)continue;
  if(!members.every(e=>sameHeadingPath(e.headingPath,members[0].headingPath)))continue;
  if(members.some((e,i)=>i>0&&!whitespaceOnly(state.documentBytes,members[i-1].endByte,e.startByte)))continue;
  candidates.push(compositeCandidate(state,members,start,end,'explicit composite selection'));
 }
 return candidates;
}

function interEntryWhitespaceCompositeTargets(state:DocumentState,providedText:string):TargetCandidate[]{
 const providedBytes=Buffer.from(providedText);
 const providedEntries=buildStructuralIndex(providedText).entries.filter(leaf).sort((a,b)=>a.startByte-b.startByte);
 if(providedEntries.length<2)return [];
 const providedCores=providedEntries.map(entry=>structuralCore(providedBytes,entry));
 if(providedCores[0].startByte!==0||providedCores.at(-1)!.endByte!==providedBytes.length)return [];
 if(providedCores.some((core,index)=>index>0&&!whitespaceOnly(providedBytes,providedCores[index-1].endByte,core.startByte)))return [];

 const documentEntries=state.structuralIndex.entries.filter(leaf).sort((a,b)=>a.startByte-b.startByte||a.endByte-b.endByte);
 const candidates:TargetCandidate[]=[];
 for(let startIndex=0;startIndex<=documentEntries.length-providedEntries.length;startIndex++){
  const members=documentEntries.slice(startIndex,startIndex+providedEntries.length);
  if(!members.every(entry=>sameHeadingPath(entry.headingPath,members[0].headingPath)))continue;
  const cores=members.map(entry=>structuralCore(state.documentBytes,entry));
  if(cores.some((core,index)=>core.entry.type!==providedCores[index].entry.type||!core.text.equals(providedCores[index].text)))continue;
  if(cores.some((core,index)=>index>0&&!whitespaceOnly(state.documentBytes,cores[index-1].endByte,core.startByte)))continue;
  candidates.push(compositeCandidate(state,members,cores[0].startByte,cores.at(-1)!.endByte,'explicit composite selection with document inter-entry whitespace'));
 }
 return candidates;
}

function headingLevel(state:DocumentState,entry:StructuralEntry){return /^#{1,6}(?=\s)/u.exec(entryText(state,entry.entryId))?.[0].length;}
function sectionBodyEnd(state:DocumentState,entry:StructuralEntry){const level=headingLevel(state,entry);if(!level)return entry.endByte;const next=state.structuralIndex.entries.filter(candidate=>candidate.startByte>entry.startByte&&['section','subsection','heading'].includes(candidate.type)).sort((a,b)=>a.startByte-b.startByte).find(candidate=>(headingLevel(state,candidate)??7)<=level);return next?.startByte??state.documentBytes.length;}
function hasSectionBody(state:DocumentState,startByte:number,endByte:number){const selected=state.documentBytes.subarray(startByte,endByte).toString('utf8');return selected.replace(/^ {0,3}#{1,6}\s+.*(?:\r?\n|$)/gmu,'').trim().length>0;}
function sectionReplacementCandidate(state:DocumentState,start:StructuralEntry,requestedSectionIds:string[],evidence:string){
 const startByte=start.startByte,endByte=sectionBodyEnd(state,start),last=state.structuralIndex.entries.filter(entry=>entry.startByte>=startByte&&entry.endByte===endByte).sort((left,right)=>right.startByte-left.startByte)[0];
 const startsAtLineStart=startByte===0||state.documentBytes[startByte-1]===0x0a,endsAfterCompleteLine=endByte===state.documentBytes.length||state.documentBytes[endByte-1]===0x0a;
 if(!last||!startsAtLineStart||!endsAfterCompleteLine||!hasSectionBody(state,startByte,endByte))return;
 const candidate=compositeCandidate(state,[start,last],startByte,endByte,evidence);
 candidate.composite!.sectionReplacement={kind:'numbered-section-range',startByte,endByte,newline:state.documentBytes.includes(0x0d)?'\r\n':'\n',startAtLineStart:true,endAfterCompleteLine:true,requestedSectionIds};
 return candidate;
}

/** Resolves only `sections <number>–<number>` against complete numbered Markdown section bodies. */
export function resolveSectionRange(state:DocumentState,raw:string):SectionRangeResolution {
 const match=/^(?:sections?\s+)?(\d+(?:\.\d+)*)\s*[–-]\s*(\d+(?:\.\d+)*)$/iu.exec(raw.trim());
 if(!match)return {reason:'SECTION_RANGE_INVALID'};
 const sectionNumber=(entry:StructuralEntry)=>{
  if(!['section','subsection','heading'].includes(entry.type))return;
  return /^#{1,6}\s+(\d+(?:\.\d+)*)(?=[\s.:]|$)/u.exec(entryText(state,entry.entryId))?.[1];
 };
 const numbered=state.structuralIndex.entries.filter(entry=>sectionNumber(entry) !== undefined);
 const starts=numbered.filter(entry=>sectionNumber(entry)===match[1]);
 const ends=numbered.filter(entry=>sectionNumber(entry)===match[2]);
 if(starts.length>1||ends.length>1)return {reason:'SECTION_RANGE_AMBIGUOUS'};
 if(starts.length!==1||ends.length!==1)return {reason:'SECTION_RANGE_NOT_FOUND'};
 const [start]=starts,[end]=ends;
 if(start.startByte>end.startByte)return {reason:'SECTION_RANGE_REVERSED'};
 const startByte=start.startByte,endByte=sectionBodyEnd(state,end);
 const startsAtLineStart=startByte===0||state.documentBytes[startByte-1]===0x0a;
 const endsAfterCompleteLine=endByte===state.documentBytes.length||state.documentBytes[endByte-1]===0x0a;
 if(!startsAtLineStart||!endsAfterCompleteLine||!hasSectionBody(state,startByte,endByte))return {reason:'SECTION_RANGE_INCOMPLETE_BODY'};
 const entryIds=state.structuralIndex.entries.filter(entry=>entry.type!=='document'&&entry.startByte>=startByte&&entry.endByte<=endByte).map(entry=>entry.entryId);
 const candidate=compositeCandidate(state,[start,end],startByte,endByte,`explicit numbered section range ${match[1]}–${match[2]}`);
 const sectionReplacement:SectionReplacementContract={kind:'numbered-section-range',startByte,endByte,newline:state.documentBytes.includes(0x0d)?'\r\n':'\n',startAtLineStart:true,endAfterCompleteLine:true,requestedSectionIds:[start.entryId,end.entryId]};
 candidate.composite!.sectionReplacement=sectionReplacement;
 return {candidate,entryIds};
}

function successorSelectionQuery(query:string){const selected=/(?:\bsecci[oó]n|\bsubsecci[oó]n|\bsection|\bsubsection|\bapartado)\s+(?:de(?:l|\s+la)?\s+)?(.+?)(?=[,;:.]|\b(?:para|pero|donde|que|conserva|preserva|mant(?:é|e)n|keep)\b|$)/iu.exec(query)?.[1];return dropStopwords((selected??query).replace(/\becuaci[oó]n(?:es)?\b/giu,' ').trim());}
function collapseNestedSuccessorCandidates(candidates:TargetCandidate[]){return candidates.filter(candidate=>!candidates.some(other=>other.entryId!==candidate.entryId&&other.composite!.startByte>=candidate.composite!.startByte&&other.composite!.endByte<=candidate.composite!.endByte&&(other.composite!.startByte!==candidate.composite!.startByte||other.composite!.endByte!==candidate.composite!.endByte)));}

/**
 * Builds a successor locus candidate directly from a matched heading's natural
 * span (heading start through the next same-or-higher-level heading, or the
 * document end). Unlike `sectionReplacementCandidate` (used only by the
 * explicit numbered-range path), this does NOT require a "complete section
 * body" or line-start/line-end alignment, and never attaches a
 * `sectionReplacement` contract: the byte-preserving composite engine splices
 * at these exact offsets directly, with no boundary reformatting, so those
 * numbered-range-only requirements would only add friction here.
 */
function successorLocusCandidate(state:DocumentState,entry:StructuralEntry,evidence:string){
 const startByte=entry.startByte,endByte=sectionBodyEnd(state,entry);
 if(endByte<startByte)return;
 // The heading's own structural entry may end before the natural section
 // boundary (e.g. when it has child subsections it does not itself span);
 // find whichever entry actually ends exactly at that boundary so
 // `materializeCompositeTarget` can validate the composite's full span.
 const last=state.structuralIndex.entries.filter(candidate=>candidate.startByte>=startByte&&candidate.endByte===endByte).sort((left,right)=>right.startByte-left.startByte)[0];
 if(!last)return;
 return compositeCandidate(state,[entry,last],startByte,endByte,evidence);
}

/** Resolves a semantic successor target into one Markdown heading's natural span, inferred from the request/deliberation without requiring a numbered range. */
export function resolveSuccessorTarget(state:DocumentState,query:string):SuccessorTargetResolution {
 const semanticQuery=successorSelectionQuery(query);
 const headingCandidates=resolveTargets(state,semanticQuery).filter(candidate=>['section','subsection','heading'].includes(candidate.type));
 const direct=state.structuralIndex.entries.filter(entry=>['section','subsection','heading'].includes(entry.type)).flatMap(entry=>{
  const heading=entryText(state,entry.entryId).split(/\r?\n/u,1)[0].toLowerCase(),matchedTerms=words(semanticQuery).filter(term=>heading.includes(term));
  if(!matchedTerms.length)return [];
  const resolved=headingCandidates.find(candidate=>candidate.entryId===entry.entryId);
  return [resolved??{entryId:entry.entryId,type:entry.type,headingPath:entry.headingPath,matchedTerms,matchedLabels:[],matchedTags:[],matchedSymbols:[],score:matchedTerms.length*3,confidence:Math.min(1,matchedTerms.length/3),shortPreview:entryText(state,entry.entryId).slice(0,180),evidence:matchedTerms}];
 });
 // A successor locus must be matched by its own heading line. Falling back to
 // `headingCandidates` would accept a section scored on its BODY — including a
 // descendant equation's `\tag`, whose label the section entry also carries —
 // so a query like "3-3" silently resolved to whichever section owns equation 3.
 // A wrong target is worse than none: report NOT_FOUND and let the caller name
 // the section.
 const semantic=direct;
 if(!semantic.length)return {candidates:[],reason:'SUCCESSOR_TARGET_NOT_FOUND'};
 const candidates=semantic.flatMap(candidate=>{
  const entry=state.structuralIndex.byId[candidate.entryId],structural=entry&&successorLocusCandidate(state,entry,`semantic successor target: ${candidate.evidence.join(', ')}`);
  return structural?[{...structural,matchedTerms:candidate.matchedTerms,matchedLabels:candidate.matchedLabels,matchedTags:candidate.matchedTags,matchedSymbols:candidate.matchedSymbols,score:candidate.score,confidence:candidate.confidence,evidence:[...structural.evidence,...candidate.evidence]}]:[];
 });
 const canonical=collapseNestedSuccessorCandidates(candidates);
 return canonical.length?{candidates:canonical}:{candidates:[],reason:'SUCCESSOR_TARGET_NOT_FOUND'};
}

export function materializeCompositeTarget(state:DocumentState,candidate:TargetCandidate){
 const composite=candidate.composite;if(!composite)return;
 const existing=state.structuralIndex.byId[candidate.entryId];if(existing)return existing;
 const first=state.structuralIndex.byId[composite.entryIds[0]],last=state.structuralIndex.byId[composite.entryIds.at(-1)!];
 if(composite.documentSha256!==state.documentSha256||!first||!last||first.startByte!==composite.startByte||last.endByte<composite.endByte||sha256(state.documentBytes.subarray(composite.startByte,composite.endByte))!==composite.textSha256)throw new Error('INVALID_COMPOSITE_TARGET');
 const entry:StructuralEntry={entryId:candidate.entryId,type:'composite',startByte:composite.startByte,endByte:composite.endByte,textSha256:composite.textSha256,parentId:first.parentId,childIds:[],ordinal:first.ordinal,headingPath:first.headingPath,labels:[],tags:[],lexicalTerms:[],deterministicAliases:[],neighboringEntryIds:[],...(composite.sectionReplacement?{sectionReplacement:composite.sectionReplacement}:{})};
 state.structuralIndex.entries.push(entry);state.structuralIndex.byId[entry.entryId]=entry;return entry;
}

export function resolveTargets(state:DocumentState,query:string,options:TargetResolutionOptions={}):TargetCandidate[]{
 const exact=exactCompositeTargets(state,query);
 const composite=exact.length?exact:(options.allowInterEntryWhitespaceFallback?interEntryWhitespaceCompositeTargets(state,query):[]);
 if(composite.length||query.includes('$$'))return composite;
 const direct=state.structuralIndex.byId[query]??state.structuralIndex.entries.find(e=>e.labels.includes(query)||e.tags.includes(query));
 if(direct&&direct.type!=='document')return [{entryId:direct.entryId,type:direct.type,headingPath:direct.headingPath,matchedTerms:[],matchedLabels:direct.labels,matchedTags:direct.tags,matchedSymbols:[],score:100,confidence:1,shortPreview:entryText(state,direct.entryId).slice(0,180),evidence:['explicit selection']}];
 const terms=words(query); const equationRequested=/ecuaci[oó]n/i.test(query); const oneHot=/one[- ]?hot|codificaci[oó]n|etiqueta|clase/i.test(query);
 const entries=(equationRequested?state.structuralIndex.entries.filter(e=>e.type==='display_equation'):state.structuralIndex.entries).filter(e=>e.type!=='document');
 // Ownership is resolved over EVERY entry, not the filtered set: an equation
 // still declares its tag even when the filter above has excluded its ancestors.
 const labelOwner=declaringEntries(state.structuralIndex.entries,'labels'),tagOwner=declaringEntries(state.structuralIndex.entries,'tags');
 return entries.map(e=>{
  const own=entryText(state,e.entryId); const neighbors=e.neighboringEntryIds.map(id=>entryText(state,id)).join('\n'); const nearby=`${own}\n${neighbors}\n${e.headingPath.join(' ')}`.toLowerCase();
  const matchedTerms=terms.filter(t=>nearby.includes(t)||e.lexicalTerms.includes(t)||e.deterministicAliases.some(a=>a.includes(t)));
  const matchedLabels=e.labels.filter(x=>isolatedInQuery(query,x)&&labelOwner.get(x)?.id===e.entryId); const matchedTags=e.tags.filter(x=>isolatedInQuery(query,x)&&tagOwner.get(x)?.id===e.entryId);
  const symbols=equationSymbols(own); const matchedSymbols=symbols.filter(symbol=>Object.values(state.symbolIndex.symbols).some(x=>x.normalized===symbol.replace(/^\\/,'').toLowerCase()||x.uses.includes(e.entryId)));
  const semanticEvidence=oneHot&&/one[- ]?hot|codificaci[oó]n|etiqueta|clase/i.test(neighbors)?4:0;
  const oneHotMatch=/one[- ]?hot|codificaci[oó]n|etiqueta|clase/i.test(own)||semanticEvidence>0;const score=matchedTerms.length*3+matchedLabels.length*8+matchedTags.length*8+semanticEvidence+(equationRequested&&e.type==='display_equation'&&(!oneHot||oneHotMatch)?3:0);
  return {entryId:e.entryId,type:e.type,headingPath:e.headingPath,matchedTerms,matchedLabels,matchedTags,matchedSymbols,score,confidence:Math.min(1,score/12),shortPreview:own.slice(0,180),evidence:[...matchedTerms,...matchedLabels,...matchedTags,...(semanticEvidence?['nearby one-hot/coding definition']:[])]};
 }).filter(c=>c.score>0).sort((a,b)=>b.score-a.score||a.entryId.localeCompare(b.entryId)).slice(0,8);
}

export function resolveSourceAndDestination(state:DocumentState,sourceQuery:string,destinationQuery:string){return {sourceCandidates:resolveTargets(state,sourceQuery),destinationCandidates:resolveTargets(state,destinationQuery)}}
