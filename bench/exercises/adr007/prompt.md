Implement ADR-DEVKB-007 in this repository (devkb). Read docs/adr/ADR-DEVKB-007_pull-requests-and-issues.md and implement its Decision section completely:

- the `PullRequest` node type and the `MERGES` and `CLOSES` verbs, with the natural keys, properties and confidences the ADR gives;
- hosted issues as `Ticket` nodes (`GH-<n>`), including `ticket_type` and sub-issue `CHILD_OF`;
- the offline layer from git (always on) and the opt-in online GitHub layer (`devkb build --github`, or `{"github": {"enabled": true}}` in devkb.json), with its local cache in `.devkb/github/` and the behaviour when GitHub cannot be reached;
- the privacy rules (no descriptions, review text or author logins unless `"github": {"authors": true}`);
- the tool and pack changes, including `devkb pack pr N`;
- `devkb/ontology.md` updated to match.

For the ADR's two open questions use the draft's defaults: author logins opt-in, and the online layer only on explicit request.

Write tests using fixture git repositories; mock the GitHub API in tests, which must not use the network. Run the full suite with `.venv/bin/python -m pytest tests -q`; it must pass.

For manual checks you may read the pinned public checkouts in bench-work/<id>/checkout (lattice-scan, mealie, dispatch); never write inside them (build with DEVKB_DIR pointing to a directory of your own outside them). You may use `gh api` for read-only GitHub calls. Do not modify study/. Do not push.

When you are finished, commit everything on the current branch with a descriptive message, and end with a short summary of what you implemented and anything you did not.
