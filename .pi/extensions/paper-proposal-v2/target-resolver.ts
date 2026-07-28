import { buildStructuralIndex } from './document-index.js';
import { sha256,type CompositeTarget,type DocumentState,type StructuralEntry,type TargetCandidate } from './types.js';

export type TargetResolutionOptions={allowInterEntryWhitespaceFallback?:boolean};

type StructuralCore={entry:StructuralEntry;startByte:number;endByte:number;text:Buffer};

const words=(value:string)=>(value.toLowerCase().match(/[\p{L}\p{N}_-]{2,}/gu)??[]);
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

export function materializeCompositeTarget(state:DocumentState,candidate:TargetCandidate){
 const composite=candidate.composite;if(!composite)return;
 const existing=state.structuralIndex.byId[candidate.entryId];if(existing)return existing;
 const first=state.structuralIndex.byId[composite.entryIds[0]],last=state.structuralIndex.byId[composite.entryIds.at(-1)!];
 if(composite.documentSha256!==state.documentSha256||!first||!last||first.startByte!==composite.startByte||last.endByte<composite.endByte||sha256(state.documentBytes.subarray(composite.startByte,composite.endByte))!==composite.textSha256)throw new Error('INVALID_COMPOSITE_TARGET');
 const entry:StructuralEntry={entryId:candidate.entryId,type:'composite',startByte:composite.startByte,endByte:composite.endByte,textSha256:composite.textSha256,parentId:first.parentId,childIds:[],ordinal:first.ordinal,headingPath:first.headingPath,labels:[],tags:[],lexicalTerms:[],deterministicAliases:[],neighboringEntryIds:[]};
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
 return entries.map(e=>{
  const own=entryText(state,e.entryId); const neighbors=e.neighboringEntryIds.map(id=>entryText(state,id)).join('\n'); const nearby=`${own}\n${neighbors}\n${e.headingPath.join(' ')}`.toLowerCase();
  const matchedTerms=terms.filter(t=>nearby.includes(t)||e.lexicalTerms.includes(t)||e.deterministicAliases.some(a=>a.includes(t)));
  const matchedLabels=e.labels.filter(x=>query.includes(x)); const matchedTags=e.tags.filter(x=>query.includes(x));
  const symbols=equationSymbols(own); const matchedSymbols=symbols.filter(symbol=>Object.values(state.symbolIndex.symbols).some(x=>x.normalized===symbol.replace(/^\\/,'').toLowerCase()||x.uses.includes(e.entryId)));
  const semanticEvidence=oneHot&&/one[- ]?hot|codificaci[oó]n|etiqueta|clase/i.test(neighbors)?4:0;
  const oneHotMatch=/one[- ]?hot|codificaci[oó]n|etiqueta|clase/i.test(own)||semanticEvidence>0;const score=matchedTerms.length*3+matchedLabels.length*8+matchedTags.length*8+semanticEvidence+(equationRequested&&e.type==='display_equation'&&(!oneHot||oneHotMatch)?3:0);
  return {entryId:e.entryId,type:e.type,headingPath:e.headingPath,matchedTerms,matchedLabels,matchedTags,matchedSymbols,score,confidence:Math.min(1,score/12),shortPreview:own.slice(0,180),evidence:[...matchedTerms,...matchedLabels,...matchedTags,...(semanticEvidence?['nearby one-hot/coding definition']:[])]};
 }).filter(c=>c.score>0).sort((a,b)=>b.score-a.score||a.entryId.localeCompare(b.entryId)).slice(0,8);
}

export function resolveSourceAndDestination(state:DocumentState,sourceQuery:string,destinationQuery:string){return {sourceCandidates:resolveTargets(state,sourceQuery),destinationCandidates:resolveTargets(state,destinationQuery)}}
