// pi-free compatibility shim for `@earendil-works/pi-ai`.
//
// The engine uses a single helper from this package: `StringEnum`, which builds
// a TypeBox schema constraining a field to a fixed set of string literals. The
// implementation below is the canonical union-of-literals form: it validates
// under TypeBox `Value.Check` and serializes to valid JSON Schema for the model
// tool boundary — the two properties the engine and the transport depend on.

import { type SchemaOptions, type Static, type TLiteral, type TUnion, Type } from 'typebox';

export function StringEnum<T extends readonly string[]>(
	values: T,
	options: SchemaOptions = {},
): TUnion<{ [K in keyof T]: TLiteral<T[K] & string> }> {
	const literals = values.map((value) => Type.Literal(value)) as { [K in keyof T]: TLiteral<T[K] & string> };
	return Type.Union(literals, options);
}

export type StaticStringEnum<T extends readonly string[]> = Static<ReturnType<typeof StringEnum<T>>>;
