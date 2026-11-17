---
id: 3
type: story
title: "A C function resolves through linkage, and a function-pointer table is unresolved"
parent: epic-language-profiles
covers: [R3, R4]
after: [1]
hitl: false
risk: medium
---

# A C function resolves through linkage, and a function-pointer table is unresolved

## Description

The C profile of D7: a C call resolves through linkage, not through classes. Today a C function is resolved by the C++ order (same class, same file, qualified, typed receiver, unique free function); this story gives C files their own order and the reasons a pack can show.

## Requirements

1. **A `static` function resolves only inside its own file** (R3)
   **Given** tests/fixtures/profiles/c_linkage has `a.c` and `b.c` each defining `static int helper(void)` and each calling it, and `c.c` calling `helper()` with no definition in `c.c`
   **When** the fixture is built
   **Then** `a.c`'s call links to `a.c::helper`, `b.c`'s to `b.c::helper`, and `c.c`'s call has no edge and is unresolved

2. **An `extern` function resolves repository-wide only when its name is unique** (R3)
   **Given** `init()` defined once in `a.c`, and `dup()` non-static in both `a.c` and `b.c`; `main.c` calls both
   **When** the fixture is built
   **Then** `main.c::main` has an edge to `init` and none to `dup`; `dup` is unresolved in `main.c`; the pack of `dup` is Incomplete

3. **A function-pointer table or ops struct is an unresolved indirect reference with a reason** (R3)
   **Given** `static const struct ops o = { .read = my_read };` and `handlers[] = { on_a, on_b };`
   **When** `devkb pack --project tests/fixtures/profiles/c_linkage file ops.c` runs
   **Then** `my_read`, `on_a` and `on_b` are Incomplete with reason `indirect-reference` and the file holding the reference in `search_files`

4. **C has no receivers** (R3)
   **Given** `p->read(p)` in a C file where `read` is a field and also the short name of a repository function
   **When** the fixture is built
   **Then** no `cpp-typed-receiver` edge is made and the call is counted unresolved

5. **A C++ file's output does not change** (R4)
   **Given** the C++ fixtures of ADR-DKB-001 stories 2 and 3
   **When** their tests run
   **Then** they pass unchanged (`pytest tests -k "cpp"` exits 0)

## Boundaries

- Must not change: the denylist of C library names; the C++ resolution order of ADR-DKB-001 §3.
- Out: macro expansion (stays a stated limit); calls through a pointer to a function the table names (resolved by no one, counted unresolved).

## References

- parent — _bmad-output/initiative-language-profiles-and-boundaries/tickets/epic-language-profiles/epic-language-profiles.md
- spec — docs/specs/SPEC-DKB-002_language-profiles-and-cross-language-boundaries.md
- decision — docs/adr/ADR-DEVKB-009_language-profiles-and-boundaries.md
