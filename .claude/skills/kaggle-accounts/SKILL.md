---
name: kaggle-accounts
description: "Trigger: add, list, or remove the Kaggle credentials this project uses. Validates every credential against the live API before storing it; keys are never printed. Stdlib-only, no venv."
---

# Kaggle Accounts

Manage the Kaggle credentials the project runs with. Adding proves each
credential against the live API and stores only what authenticates; removing is
an interactive pick from what is there. Keys go in and are never shown again.

## Activation Contract

Invoked with no clear intent, this is a two-step conversation, not a command:

1. Run `list` and report what is stored.
2. Ask **add or remove** as an interactive selection — the `AskUserQuestion`
   tool, never a question typed into the reply. Offer *Add an account* and
   *Remove an account*; offer removal only when something is stored.

Never infer the intent from context: a session that mentions Kaggle is not a
request to change credentials.

**Every question this skill asks is a selection, not prose.** The opening
add-or-remove, and the pick of which accounts to remove, are both interactive
prompts. A question written into the reply asks the user to retype an alias that
the tool could have let them click, and a retyped alias is a typo waiting to
delete the wrong credential.

Then follow the matching flow below.

## Environment

**None.** The script is stdlib-only — no `.venv`, no `setup.sh`, no
`requirements.txt`, no `pip install kaggle`. Validation is one HTTPS request
with Basic auth, which `urllib` already does. Creating a virtualenv to hold zero
packages is ceremony, so there is none. Requires Python 3.10+ and a network
connection when adding.

## How to execute

```
python3 .claude/skills/kaggle-accounts/scripts/accounts_cli.py <command>
```

- `list [--json]` — stored accounts. Reads nothing remote, touches nothing.
- `add <kaggle.json>… [--alias NAME]` — validate and store.
- `remove <alias>…` — delete stored accounts.

## Adding

**Ask for the path to a `kaggle.json`, never for the token.** A Kaggle
credential is two fields, `username` and `key`, and Kaggle hands both over in a
single downloaded file (kaggle.com → Settings → API → *Create New Token*). Ask
for that file's path.

Never ask the user to paste the key into the conversation, and never echo one
you happen to see. A token pasted in chat is in the transcript permanently and
cannot be taken back; a file path costs nothing and leaks nothing.

Several paths can go in one call. Each is handled independently:

- Every credential is validated against Kaggle before anything is written.
- **Only the ones that authenticate are stored.** A rejected file is reported
  with its reason and dropped; it never costs the good credentials beside it.
- An account whose username is already stored has its key replaced, which is
  what makes rotating an expired token the same command as adding.
- Each account is named after its Kaggle username unless `--alias` is given.
  `--alias` applies to a single file — with several files there is no
  unambiguous way to pair names to paths, so it is refused rather than guessed.

Report which were stored and which were rejected. Then tell the user the
downloaded `kaggle.json` files still contain those tokens and are theirs to
delete — say it, do not delete them.

## Removing

Removal is a **selection**, never an inference:

1. Run `list --json` to get the aliases and usernames.
2. Present them as an **interactive multi-select** (`AskUserQuestion`), one
   option per stored account showing its alias and username, and let the user
   mark what goes. Never ask them to type the aliases back.
3. Run `remove` with exactly the chosen aliases.

If an alias does not exist the whole batch is refused. A typo that silently
removes only the aliases it happened to match is worse than removing nothing,
because the report would read as success.

There is no confirmation beyond the selection — the multi-select *is* the
confirmation. Deleting a credential destroys no account and loses no work; the
token can be regenerated on Kaggle.

## Keys never cross into the agent

`list` prints aliases and usernames, never keys, and `--json` omits them too. So
an agent can offer a choice of accounts, and remove one, without a secret ever
entering its context. Whatever launches runs reads the store file directly.

Never `cat`, `bat`, `rg`, or otherwise read `store/accounts.json` to answer a
question about which accounts exist. `list` answers that without the keys.

## Where credentials live

`store/accounts.json`, inside the skill, `0600`, ignored by
`store/.gitignore`.

The store is inside the repository, so that ignore rule is the whole protection
— and it is enforced as a **precondition**: before writing, the script asks
`git check-ignore` whether the path is genuinely ignored and refuses to write if
it is not. It asks git for the effective answer rather than checking that a
file exists, because an ignore rule can be present and still not match. Outside
a git checkout it falls back to requiring the `.gitignore`.

The ignore file itself is committed so the protection exists *before* the first
credential is written rather than after.

Writes are atomic: a truncated write would cost every credential in the file,
not just the one being added.

## Decision Gates

| Situation | Action |
| --- | --- |
| Invoked with no stated intent | `list`, then an interactive add-or-remove selection |
| User wants to add | Ask for `kaggle.json` path(s); never for the token itself |
| User pastes a raw token in chat | Do not store it; ask for the file, and say the pasted one should be rotated |
| Some credentials in a batch fail | Store the rest; report each rejection with its reason |
| Kaggle unreachable while validating | Report it as unreachable, not as invalid; store nothing |
| User wants to remove | `list --json`, multi-select, then `remove` |
| An alias to remove does not exist | Refuse the whole batch; change nothing |
| `store/.gitignore` missing or not matching | Refuse to write; say to restore it |
| Store file unreadable or malformed | Report it; write nothing |
| Asked which accounts exist | Run `list`; never read the store file directly |

## Output Reporting

Report only what changed: which accounts were stored, updated, rejected, or
removed. Never a key, never a store dump, never a path listing.

**Speak the user's language.** The questions, the account listing, and the
report go in the language the user is writing in, not the language of this
document. The script's stdout stays English: it is data to read, not a message
to relay verbatim. Aliases, usernames, paths, and flags are never translated.
