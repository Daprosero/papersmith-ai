import { complete, type UserMessage } from '@earendil-works/pi-ai/compat';
import type { ExtensionContext } from '@earendil-works/pi-coding-agent';
import { Type, type TSchema } from 'typebox';

function parseJson(text: string): unknown {
 const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i)?.[1] ?? text;
 return JSON.parse(fenced.trim());
}

export type ProductionStructuredResponseErrorCode =
 | 'MODEL_PROVIDER_ERROR'
 | 'MODEL_CALL_ABORTED'
 | 'MODEL_EMPTY_RESPONSE'
 | 'MODEL_INVALID_STRUCTURED_RESPONSE';

/** Classifies provider-boundary failures without exposing provider text or exceptions. */
export class ProductionStructuredResponseError extends Error {
 readonly code: ProductionStructuredResponseErrorCode;

 constructor(code: ProductionStructuredResponseErrorCode, options?: { cause?: unknown }) {
  super(code, options);
  this.name = 'ProductionStructuredResponseError';
  this.code = code;
 }
}

export type StructuredOutputContract = Readonly<{
 name: string;
 description: string;
 schema: TSchema;
}>;

export const DEFAULT_MODIFY_INPUT_BUDGET_BYTES = 65536;
export const MODIFY_INPUT_BUDGET_ENV = 'PAPER_PROPOSAL_V2_MODIFY_INPUT_BUDGET_BYTES';

export type ModifyInputBudgetEvidence = Readonly<{
 unit: 'utf8_bytes';
 accountingVersion: '1';
 payloadPath: 'fidelity_modify';
 effectiveBytes: number;
 budgetBytes: number;
}>;

/** A pre-invocation terminal block. No provider call has occurred when this is thrown. */
export class ModifyInputBudgetError extends Error {
 readonly code = 'MODIFY_INPUT_BUDGET_EXCEEDED';
 constructor(readonly evidence: ModifyInputBudgetEvidence) {
  super('MODIFY_INPUT_BUDGET_EXCEEDED');
  this.name = 'ModifyInputBudgetError';
 }
}

function resolveModifyInputBudget(value: number | string | undefined): number {
 if (value === undefined) return DEFAULT_MODIFY_INPUT_BUDGET_BYTES;
 const normalized = typeof value === 'string' && /^[1-9]\d*$/.test(value) ? Number(value) : value;
 if (!Number.isSafeInteger(normalized) || Number(normalized) <= 0) throw new Error('INVALID_MODIFY_INPUT_BUDGET');
 return Number(normalized);
}

/** Counts exactly the UTF-8 bytes sent as system prompt, user JSON, and output tool definition. */
export function measureStructuredInputUtf8Bytes(systemPrompt: string, payload: unknown, output?: StructuredOutputContract): number {
 const tools = output ? [{ name: output.name, description: output.description, parameters: output.schema }] : [];
 return Buffer.byteLength(systemPrompt) + Buffer.byteLength(JSON.stringify(payload)) + Buffer.byteLength(JSON.stringify(tools));
}

/** Serializes model work so the production path never exceeds one parallel call. */
export class ProductionModelRuntime {
 private active?: { ctx: ExtensionContext; signal?: AbortSignal };
 private tail: Promise<void> = Promise.resolve();
 readonly modifyInputBudget: number;

 constructor(options: { modifyInputBudget?: number | string } = {}) {
  this.modifyInputBudget = resolveModifyInputBudget(options.modifyInputBudget ?? process.env[MODIFY_INPUT_BUDGET_ENV]);
 }

 preflightFidelityModify(systemPrompt: string, payload: unknown, output: StructuredOutputContract): ModifyInputBudgetEvidence {
  const evidence: ModifyInputBudgetEvidence = Object.freeze({
   unit: 'utf8_bytes', accountingVersion: '1', payloadPath: 'fidelity_modify',
   effectiveBytes: measureStructuredInputUtf8Bytes(systemPrompt, payload, output), budgetBytes: this.modifyInputBudget,
  });
  if (evidence.effectiveBytes > evidence.budgetBytes) throw new ModifyInputBudgetError(evidence);
  return evidence;
 }

 async withContext<T>(ctx: ExtensionContext, signal: AbortSignal | undefined, work: () => Promise<T>): Promise<T> {
  let release!: () => void;
  const previous = this.tail;
  this.tail = new Promise<void>((resolve) => { release = resolve; });
  await previous;
  this.active = { ctx, signal };
  try { return await work(); } finally { this.active = undefined; release(); }
 }

 async structured(systemPrompt: string, payload: unknown, output?: StructuredOutputContract): Promise<unknown> {
  const active = this.active;
  if (!active?.ctx.model) throw new Error('PRODUCTION_MODEL_REQUIRED');
  const auth = await active.ctx.modelRegistry.getApiKeyAndHeaders(active.ctx.model);
  if (!auth.ok || !auth.apiKey) throw new Error(auth.ok ? `MODEL_AUTH_REQUIRED:${active.ctx.model.provider}` : auth.error);
  const message: UserMessage = {
   role: 'user',
   content: [{ type: 'text', text: JSON.stringify(payload) }],
   timestamp: Date.now(),
  };
  let response: Awaited<ReturnType<typeof complete>>;
  try {
   response = await complete(
    active.ctx.model,
    {
     systemPrompt,
     messages: [message],
     ...(output ? { tools: [{ name: output.name, description: output.description, parameters: output.schema }] } : {}),
    },
    {
     apiKey: auth.apiKey,
     headers: auth.headers,
     env: auth.env,
     signal: active.signal,
     ...(output ? { toolChoice: 'required' } : {}),
    },
   );
  } catch (cause) {
   throw new ProductionStructuredResponseError('MODEL_PROVIDER_ERROR', { cause });
  }
  if (response.stopReason === 'aborted') throw new ProductionStructuredResponseError('MODEL_CALL_ABORTED');
  if (output) {
   const toolCalls = response.content.filter((part): part is { type: 'toolCall'; name: string; arguments: Record<string, unknown> } => part.type === 'toolCall');
   const text = response.content.filter((part): part is { type: 'text'; text: string } => part.type === 'text').map((part) => part.text).join('');
   if (text.trim().length !== 0 || toolCalls.length !== 1 || toolCalls[0].name !== output.name) {
    throw new ProductionStructuredResponseError('MODEL_INVALID_STRUCTURED_RESPONSE');
   }
   return toolCalls[0].arguments;
  }
  const text = response.content
   .filter((part): part is { type: 'text'; text: string } => part.type === 'text')
   .map((part) => part.text)
   .join('\n');
  if (!text) throw new ProductionStructuredResponseError('MODEL_EMPTY_RESPONSE');
  try { return parseJson(text); } catch (cause) {
   throw new ProductionStructuredResponseError('MODEL_INVALID_STRUCTURED_RESPONSE', { cause });
  }
 }
}
