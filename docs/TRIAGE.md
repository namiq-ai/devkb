# Triage and handling of outside issues and pull requests

Two user-level systemd timers run the Claude Code CLI (the signed-in session, no API key) against `namiq-ai/devkb`:

| Timer | Every | Does |
|---|---|---|
| `devkb-triage` | 4 hours | Judges each new item from an outsider (not the owner, a member or a collaborator; bots are skipped): is it **valid**, does it **need information**, is it a **duplicate** of an open item, is it **invalid**, how **urgent**. Labels it and posts one comment. |
| `devkb-handle` | 4 hours, 30 minutes later | Picks up items labelled `handle:*` and works them (below). |

`ops/triage/triage.py` is both. Without `--apply` (or `TRIAGE_APPLY=1`) it writes nothing to GitHub: it prints what it would post.

## What triage decides

| Verdict | Label added | Comment |
|---|---|---|
| valid | type (`bug`, `enhancement`, `documentation`), `priority: high\|medium\|low`, `handle:KIND` | what it understood, and for a pull request the main review points |
| needs more information | `needs-info` | up to five specific questions. When the author replies, the next run triages it again and removes `needs-info` |
| duplicate | `duplicate` | links the open item. **Nothing is closed.** |
| invalid | `invalid` | why, politely. A security report is told to use private reporting |
| usage question | `question` | the answer from the docs and code |

Every triaged item also gets `triaged`. The handling kind is chosen by triage and can be set or changed by a maintainer on any item (add one `handle:` label):

| `handle:` | Item | The handler |
|---|---|---|
| `review` | pull request | reads the diff and the checked-out code, posts a review as a **comment** (it cannot approve) |
| `plan` | large or unclear request, or a bug with an unknown cause | posts an implementation plan: files and functions, steps, tests, open questions |
| `draft-pr` | bug with a clear cause, or a small feature | works in its own worktree on `auto/N-slug` from `origin/main`, adds a test, runs the full suite and `scripts/check_dist.py` itself, and only then pushes and opens a **draft** pull request that closes the issue |

When it finishes, the item gets `handled`; when it cannot (the suite fails, no change, wrong kind for the item), `handler-failed` and a line in the local log, and nothing is posted. At most 2 items are handled and 10 triaged per run (`TRIAGE_MAX_HANDLE`, `TRIAGE_MAX_ITEMS`).

## The feedback thread

Issues labelled `user-result` (today #25, "Tell us what you tried devkb on") collect what users did with devkb. Every `triage` run
also reads the **new comments by outsiders** on those threads (a comment is answered once; the ids are kept in
`~/devkb-triage/feedback-seen.json`) and, per comment, chooses:

| Action | What happens |
|---|---|
| ticket | the comment reports a defect or asks for a capability that fits the scope, and the model checked it against the code: a new issue is filed (labels `from-feedback`, type, priority; at most `handle:plan`, never an automatic fix) with the comment's link and the reporter's words quoted; the thread gets a reply that links it |
| needs information | a reply with up to five specific questions |
| reply | thanks and an answer from the docs and code, or a link to the open item it duplicates |
| ignore | spam; nothing is posted |

The reply addresses the commenter by the login GitHub returned (the one place an `@mention` is allowed). `triage.py feedback` runs only this
step. Settings: `TRIAGE_FEEDBACK_LABEL` (`user-result`), `TRIAGE_MAX_FEEDBACK` (10 comments per run).

## What it can never do

- close, merge, approve, or push to `main` (it pushes `auto/*` branches only, and opens drafts);
- act on text it reads. The report is **untrusted input**: it is fenced in the prompt as data, the model has no GitHub credential, no network tool and (for triage, plan and review) no shell and no edit tool. The model answers with one JSON object; the script validates it (labels from a fixed list, `duplicate_of` must be another known item, free text is sanitized: no `@mentions`, no hidden HTML comments) and is the only thing that talks to GitHub. Every agent run starts with user settings only and every hook disabled (`--setting-sources user`, `disableAllHooks`), so a checkout's `.claude/settings.json`, which a pull request controls, never runs. The fixing agent may read and edit files in its worktree and run nothing. The script then refuses a change to `conftest.py`, `pyproject.toml`, `scripts/`, `ops/`, `.claude/`, `.github/` or `plugins/`, and runs the tests and `scripts/check_dist.py` inside bubblewrap: no network, no credentials, no home directory, only the worktree writable. Without `bwrap` installed it refuses to run them. Only comments posted by the daemon's own login count as its own;
- hide that it is an AI: every comment says so, and every draft pull request says it was written by an agent and needs review.

A prompt-injection attempt in an issue can at worst make the daemon post a wrong but sanitized comment or label, or draft a wrong change that a maintainer reviews. Outsider text is fenced, and the fence's tag is broken wherever it appears inside that text, so it cannot be closed early. Read a draft pull request from an outsider's issue as you would one from an outsider.

## Install

```
python3 ops/triage/triage.py install      # makes ~/devkb-triage/devkb (a worktree at origin/main), installs and starts the timers
python3 ops/triage/triage.py status       # what waits, what the last runs did and cost, next timer times
python3 ops/triage/triage.py uninstall
```

It starts in **dry-run**. After you have read a few dry-run results in `~/devkb-triage/runs/DATE/*.jsonl` (or from `python3 ops/triage/triage.py triage`), turn posting on:

```
echo TRIAGE_APPLY=1 >> ~/.config/devkb-triage.env
```

Other settings in the same file: `TRIAGE_REPO` (default `namiq-ai/devkb`), `TRIAGE_MODEL` (`sonnet`), `TRIAGE_HOME` (`~/devkb-triage`), `TRIAGE_MAX_ITEMS`, `TRIAGE_MAX_HANDLE`, `TRIAGE_MAX_TURNS`. The GitHub CLI (`gh`) must be signed in with rights to label, comment, push branches and open pull requests.

Run one item by hand: `python3 ops/triage/triage.py triage --only 152` (dry run), `handle --only 152 --apply`.

The runs write `~/devkb-triage/runs/DATE/{triage,handle}.jsonl` (verdict, labels, cost). A measured dry-run triage of a pull request cost $0.10.
