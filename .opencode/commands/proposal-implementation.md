---
description: Convertir la propuesta vigente en Python verificado contra el documento
agent: build
---

Load the `proposal-implementation` skill via the skill tool and follow `.claude/skills/proposal-implementation/SKILL.md` exactly.

Steps: resolve the base with `proposal-deliberation` STATUS (never guess `latest`), run the structure phase first (layout without executing), then the materialization phase. Delegate the build stretch to `@implementation-build` and the walk stretch to `@implementation-walk`. Never submit remote work from here; that belongs to `remote-execution`.
