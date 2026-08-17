---
name: kaggle-accounts
description: "Trigger: check that this project's Kaggle accounts actually authenticate, take in new credentials left in kaggle-inbox/, or remove accounts. Two interactive options — validate or remove. Stdlib-only, no venv."
---

# Kaggle Accounts

Prove the project's Kaggle accounts work, and keep only the ones that do.

The user supplies credentials by hand — a `kaggle.json`, or a `.txt`/`.md` list
with one `username key` per line, left in `kaggle-inbox/`. That being manual is what this
is *for*. The work worth automating is not moving a file; it is answering **does
this account actually authenticate**, which is a question only Kaggle can answer
and one that stops being true over time.

## Activation Contract

Invoking this skill asks **one** interactive question, with exactly two options:

1. Run `list` first, so the question is asked against what is actually there.
2. Ask with `AskUserQuestion` — never a question typed into the reply:
   - **Validate accounts** — re-check everything stored, and take in whatever is
     in the inbox.
   - **Remove accounts** — delete accounts. Offer this only when something is
     stored; there is nothing to remove from an empty store.

Never infer the intent from context: a session that mentions Kaggle is not a
request to touch credentials.

**Every question is a selection, not prose.** The opening choice, and the pick
of which accounts to remove, are both interactive prompts built from what the
CLI reports. A question written into the reply asks the user to retype something
they could have clicked, and a retyped username is a typo waiting to delete the
wrong account.

A prompt can only offer what something enumerated first, so each question has a
command behind it: `list` for the accounts, `discover` for the credential files.
If a question has no command behind it, it is the wrong question.

## Environment

**None.** The script is stdlib-only — no `.venv`, no `setup.sh`, no
`requirements.txt`, no `pip install kaggle`. Validation is one HTTPS request
with Basic auth, which `urllib` already does. Creating a virtualenv to hold zero
packages is ceremony, so there is none. Requires Python 3.10+ and a network
connection.

## How to execute

```
python3 .claude/skills/kaggle-accounts/scripts/accounts_cli.py <command>
```

- `validate` — re-check every stored account, take in the inbox, keep what passes.
- `remove <username>…` — delete stored accounts.
- `list [--json]` — stored accounts, never their keys.
- `discover [--json]` — credential files lying around and the accounts in each.

## Validating

One command does the whole thing: `validate`.

- **Every stored account is re-checked.** This is the half that has to keep
  happening. Tokens get expired and rotated, and an account that quietly stopped
  working does not fail when it was added — it fails hours later in the middle
  of a run.
- **Everything in `kaggle-inbox/` is taken in**, and only what authenticates is
  stored. A list is judged line by line: the rows that pass are stored, the
  rows that fail are reported by line number, and one bad row never costs the
  rows around it.
- A username already stored has its key replaced, which makes rotating an
  expired token the same command as adding one.

Only the inbox is taken in automatically. That folder means "these are for you";
a `kaggle.json` sitting in `~/Downloads` shows up in `discover` and is taken only
when named, because finding a file in somebody's home directory is not the same
as being handed it.

**A dead credential is reported, never quietly dropped.** Removing an account is
the user's other option, not a side effect of asking whether it still works.

Report which accounts passed, which stopped working, and which new ones were
stored or rejected. Then let the user decide what to do about the failures.

## Removing

Removal is a **selection**, never an inference:

1. Run `list --json` to get the usernames.
2. Present them as an **interactive multi-select** (`AskUserQuestion`), one
   option per stored account, and let the user mark what goes. Never ask them to
   type the usernames back.
3. Run `remove` with exactly the chosen usernames.

If a username does not exist the whole batch is refused. A typo that silently
removes only the names it happened to match is worse than removing nothing,
because the report would read as success.

The multi-select *is* the confirmation. Deleting a credential destroys no
account and loses no work; the token can be regenerated on Kaggle.

## Where credentials come from

Never ask for a token, and never ask for a path in prose. There are two ways in,
and neither goes through the conversation:

- **The inbox.** `kaggle-inbox/` at the repository root exists for exactly this
  and ships already ignored by git. Drop in a `kaggle.json` (kaggle.com →
  Settings → API → *Create New Token*) or a `.txt`/`.md` with one
  `username key` per line — comma, colon, tab or space between them, `#`
  headings and blank lines skipped, markdown bullets and table pipes stripped,
  and a table's header row skipped by the `|---|` under it. Then validate.

  **Both fields on the same line.** Username on one line and token on the next
  is not read as a pair: for a list of several accounts that shape is ambiguous,
  and guessing at it would pair the wrong token to the wrong account in silence.

  A `.txt` or `.md` list is looked for **in the inbox only.** Reading every text file in
  somebody's Downloads to see whether it happens to hold credentials is not a
  thing to do quietly; putting one in the inbox is what opts it in.

- **A terminal prompt**, for a token that lives in a password manager or a
  download that is long gone:

  ```
  python3 .claude/skills/kaggle-accounts/scripts/accounts_cli.py validate --interactive
  ```

  It asks for the username, then the key with the echo off. The key is in no
  message, no argv, and no shell history.

**Tell the user to run that one themselves, in their own shell. Never run it for
them.** It refuses when stdin is not a terminal precisely so that an agent
running it hits an error instead of finding a way — but the refusal is the
backstop, not the rule. There is deliberately no `--key` flag either: a secret on
a command line is in the process list and in the shell history, which is the same
leak wearing a different hat.

If a user pastes a token anyway: do not store it, and say plainly that it is in
the transcript for good and should be expired at kaggle.com → Settings → API →
*Expire API Token*. Say it once. Then point at the two ways in — the point is to
get them a working credential, not to make them feel caught.

## The inbox is transit, not storage

A file that came from `kaggle-inbox/` and gave up **everything it held** is
deleted, and the report says so: the same token sitting in two places in
plaintext is exposure with nothing bought.

Everything it held, not most of it. Deleting a list because four of its five
rows worked would take the fifth — the one that still needs a retry — with it.
A list with any row left is kept, and the report says how many did not go in.

Only the inbox, too. A file the user keeps in `~/Downloads` or anywhere else is
theirs: report that it still holds tokens and leave the deleting to them.

## Keys never cross into the agent

`list` prints usernames, never keys, and `--json` omits them too. So an agent can
offer a choice of accounts, and remove one, without a secret ever entering its
context. Whatever launches runs reads the store file directly.

Never `cat`, `bat`, `rg`, or otherwise read `store/accounts.json` to answer a
question about which accounts exist. `list` answers that without the keys.

## Where credentials live

`store/accounts.json`, inside the skill, `0600`, ignored by `store/.gitignore`.
An account is its Kaggle username; there is no alias, because a second name for
the same thing gives you two ways to refer to one account and one of them is
always the wrong one.

The store is inside the repository, so that ignore rule is the whole protection
— and it is enforced as a **precondition**: before writing, the script asks
`git check-ignore` whether the path is genuinely ignored and refuses to write if
it is not. It asks git for the effective answer rather than checking that a file
exists, because an ignore rule can be present and still not match. Outside a git
checkout it falls back to requiring the `.gitignore`.

Both ignore files are committed so the protection exists *before* the first
credential is written rather than after.

Writes are atomic: a truncated write would cost every credential in the file,
not just the one being added.

## Decision Gates

| Situation | Action |
| --- | --- |
| Invoked | `list`, then the interactive validate-or-remove selection |
| Nothing stored | Offer validate only; there is nothing to remove |
| User picks validate | Run `validate`; report passed, failed, stored, rejected |
| A stored account stops authenticating | Report it; do not remove it — that is the user's other option |
| Some lines of a list fail | Store the rest; report each by line number, never the line |
| Kaggle unreachable while validating | Report it as unreachable, not as invalid; store nothing |
| Nothing to validate | Say to drop a file in `kaggle-inbox/` and run again |
| User picks remove | `list --json`, multi-select, then `remove` |
| A username to remove does not exist | Refuse the whole batch; change nothing |
| User pastes a raw token | Do not store it; say to expire it, once; then point at the two ways in |
| Asked to run `validate --interactive` for them | Refuse: it is theirs to run in a terminal, and the command refuses anyway |
| An inbox file gave up everything it held | It is deleted; report that it was consumed |
| An inbox file has rows left | It is kept; report how many did not go in |
| `discover` warns the inbox is not ignored | Relay it; say to restore `kaggle-inbox/.gitignore` before dropping a token |
| A `.gitignore` missing or not matching | Refuse to write; say to restore it |
| Store file unreadable or malformed | Report it; write nothing |
| Asked which accounts exist | Run `list`; never read the store file directly |

## Output Reporting

Report only what changed or what was learned: which accounts authenticate, which
stopped working, which were stored, rejected or removed. Never a key, never a
store dump, never a path listing.

**Speak the user's language.** The questions, the account listing, and the
report go in the language the user is writing in, not the language of this
document. The script's stdout stays English: it is data to read, not a message
to relay verbatim. Usernames, paths, and flags are never translated.
