---
name: devkb-roles
description: Use at the start of any working session in a repository that has the devkb-sdlc tools, for any role: tester, developer, DevOps, data engineer, architect, tech lead, analyst. It loads the role's territory, waiting work, code, tests and documents in one step.
---

# Start a session as a role

1. If `.devkb/startup/<ROLE>.md` exists, read it first. It is generated from the graph by `make devkb-startup ROLE=<ROLE>` and holds your territory, waiting tickets, most-depended-on code, test command, documents to read and role-specific facts. If it is missing or stale, call `role_brief` with your role code.
2. Stay inside your territory. A change that needs a path in "never touch" is another role's ticket.
3. Pick the skill for the work in front of you: the brief's "Ask the graph" line names the ones your role uses most.
4. At the end of the session, say what you changed and which tickets moved.

Limits: the brief is a snapshot from the last graph build. Check `_meta.stale`, and re-generate after large merges.
