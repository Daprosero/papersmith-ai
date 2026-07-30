import { resolveIntent } from './intent-resolver.js';
import type { ScientificActKind, ScientificActResolution, ScientificThreadId } from './scientific-domain.js';

const actPatterns: Array<[ScientificActKind, RegExp]> = [
	['REQUEST_MATERIALIZATION', /\b(?:request|solicita(?:r)?)\b.*\b(?:materialization|materiali[sz]a(?:r|ción)|publica(?:r|ción))\b|\b(?:materialization|materiali[sz]a(?:r|ción)|publica(?:r|ción))\b/i],
	['ACCEPT_RECONCILIATION', /\b(?:accept|acepta(?:r)?|confirm(?:ar|a))\b.*\b(?:reconciliation|reconciliaci[oó]n)\b/i],
	['PROPOSE_RECONCILIATION', /\b(?:propose|prop(?:oner|ongo))\b.*\b(?:reconciliation|reconciliaci[oó]n)\b/i],
	['BOOTSTRAP_FROM_ACTIVE_PROPOSAL', /\b(?:bootstrap|inicializa(?:r)? desde|comienza desde)\b.*\b(?:active proposal|propuesta activa)\b/i],
	['REQUEST_CONCEPTUAL_REVIEW', /\b(?:conceptual review|revisi[oó]n conceptual|critically review|revisa cr[ií]ticamente)\b/i],
	['REQUEST_TUTOR', /\b(?:ask (?:the )?tutor|solicita(?:r)? tutor|pide (?:al )?tutor)\b/i],
	['MODIFY_SYNTHESIS', /\b(?:modify|revise|modifica(?:r)?|revisa(?:r)?)\b.*\b(?:synthesis|s[ií]ntesis)\b/i],
	['SYNTHESIZE', /\b(?:synthesize|sintetiza(?:r)?)\b/i],
	['ACCEPT_DECISION', /\b(?:accept|acepta(?:r)?)\b.*\b(?:decision|decisi[oó]n)\b/i],
	['REJECT_DECISION', /\b(?:reject|rechaza(?:r)?)\b.*\b(?:decision|decisi[oó]n)\b/i],
	['RETRACT_DECISION', /\b(?:retract|retracta(?:r)?)\b.*\b(?:decision|decisi[oó]n)\b/i],
	['RELATE_THREADS', /\b(?:relate|link|relaciona(?:r)?|vincula(?:r)?)\b.*\b(?:threads?|hilos?)\b/i],
	['CONSTRUCT_HYPOTHESIS', /\b(?:hypothesis|hip[oó]tesis)\b/i],
	['CONSTRUCT_ASSUMPTION', /\b(?:assumption|supuesto)\b/i],
	['CONSTRUCT_ALTERNATIVE', /\b(?:alternative|alternativa)\b/i],
	['RAISE_UNRESOLVED_ISSUE', /\b(?:unresolved issue|open issue|cuesti[oó]n sin resolver|problema sin resolver)\b/i],
	['CONSTRUCT_QUESTION', /\b(?:question|pregunta)\b/i],
	['CONSTRUCT_IDEA', /\b(?:idea|idea seed|semilla)\b/i],
];

function classifyInstruction(instruction: string): ScientificActKind | undefined {
	const matches = actPatterns.filter(([, pattern]) => pattern.test(instruction)).map(([act]) => act);
	return matches.length === 1 ? matches[0] : undefined;
}

export type ScientificActResolverInput = {
	instruction: string;
	scientificAct?: ScientificActKind;
	requestedThreadId?: ScientificThreadId;
	relatedThreadIds?: ScientificThreadId[];
};

export class ScientificActResolver {
	resolve(input: ScientificActResolverInput): ScientificActResolution {
		const directIntent = resolveIntent(input.instruction).intent;
		if (directIntent === 'WITHDRAW_REVISION' || directIntent === 'RESTORE_WITHDRAWN_REVISION') {
			return { status: 'blocked', code: 'LIFECYCLE_ROUTE_PRECEDENCE' };
		}
		const inferred = classifyInstruction(input.instruction);
		if (directIntent === 'DELIBERATE') return { status: 'blocked', code: 'DELIBERATE_ROUTE_PRECEDENCE' };
		if (directIntent !== 'AMBIGUOUS' && inferred !== 'REQUEST_CONCEPTUAL_REVIEW') {
			return { status: 'blocked', code: 'DIRECT_DOCUMENT_ROUTE_PRECEDENCE' };
		}
		if (!inferred) return { status: 'needs_clarification', question: 'State one bounded scientific act for this instruction.' };
		if (input.scientificAct && input.scientificAct !== inferred) {
			return { status: 'needs_clarification', question: 'The supplied scientific act does not match the instruction.' };
		}
		return {
			status: 'resolved',
			act: inferred,
			...(input.requestedThreadId ? { requestedThreadId: input.requestedThreadId } : {}),
			relatedThreadIds: [...new Set(input.relatedThreadIds ?? [])],
		};
	}
}
