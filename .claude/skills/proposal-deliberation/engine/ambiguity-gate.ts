import type { TargetCandidate } from './types.js';
export function ambiguityGate(candidates:TargetCandidate[]){
 if(!candidates.length)return {blocked:true,status:'ambiguous' as const,question:'No encontré un objetivo. Indicá la sección, etiqueta o un fragmento distintivo.',candidates:[]};
 const [first,second]=candidates;
 if(second&&first.score-second.score<=4)return {blocked:true,status:'ambiguous' as const,question:`Seleccioná un objetivo:\n${candidates.map((c,i)=>`${i+1}. ${(c.headingPath??[]).join(' › ') || c.type}: ${c.shortPreview??''}`).join('\n')}`,candidates};
 return {blocked:false,status:'resolved' as const,candidate:first,candidates:[first]};
}
