import type { TargetCandidate } from './types.js';
export function ambiguityGate(candidates:TargetCandidate[]){
 if(!candidates.length)return {blocked:true,status:'ambiguous' as const,question:'No encontré un objetivo. Indicá la sección, etiqueta o un fragmento distintivo.',candidates:[]};
 const [first,second]=candidates;
 if(second&&first.score-second.score<=4){
  // Terms every candidate matched carry no discriminating power; naming them
  // turns an opaque menu into an error the caller can act on, because the fix
  // is to drop them, never to add more words.
  const shared=(first.matchedTerms??[]).filter(term=>candidates.every(c=>(c.matchedTerms??[]).includes(term)));
  const hint=shared.length?`\n\nLos términos ${shared.map(t=>`"${t}"`).join(', ')} coinciden con todos los candidatos y no discriminan: repetí la consulta sin ellos, dejando solo palabras distintivas — sin palabras vacías, sin puntuación, sin número de sección y con las tildes tal como aparecen en el encabezado.`:'';
  return {blocked:true,status:'ambiguous' as const,question:`Seleccioná un objetivo:\n${candidates.map((c,i)=>`${i+1}. ${(c.headingPath??[]).join(' › ') || c.type}: ${c.shortPreview??''}`).join('\n')}${hint}`,candidates};
 }
 return {blocked:false,status:'resolved' as const,candidate:first,candidates:[first]};
}
