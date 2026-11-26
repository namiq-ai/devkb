"""What keeps a benchmark agent inside its own run (#451).

An agent gets `Bash`, so without this one empty variable (`rm -rf $B $B.*`) or one wildcard in a shared temp folder reaches whatever the user can
reach. Each run gets its own scratch folder; the agent's shell runs in Claude Code's sandbox (bubblewrap on Linux), which lets it write only to its
checkout and that folder, with no way for a command to opt out; the file tools are held to the working directories; the launching session's
variables are not passed on.

The sandbox's own filter against local (unix) sockets needs a nested user namespace, which Ubuntu's AppArmor policy refuses, so no command could
start. It is switched off (`allowAllUnixSockets`) and the folders that hold the sockets are hidden instead (`SOCKET_DIRS`): through one of them
(Docker, the user's systemd bus, a tmux server) a command would act outside the sandbox. Abstract sockets are cut off with the network. Pure functions here; the proof that it holds on a host is `zbench.py isolation`, which judges from outside the agent.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

SOCKET_DIRS = ("/run", "/tmp")      # /var/run is a link to /run; the agent's own temp folder is in its scratch, not here
KEEP = ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN")      # how the user signs in; every other CLAUDE* variable belongs to the launching session


def scratch_root() -> Path:
    return Path(os.environ.get("ZBENCH_SCRATCH") or Path.home() / ".cache" / "devkb" / "zbench-scratch")


def scratch(run_dir: Path) -> Path:
    """The run's own folder for temporary and cache files: the same for the same run folder, different for any other."""
    return scratch_root() / f"{run_dir.name}-{hashlib.sha1(str(run_dir).encode()).hexdigest()[:10]}"


def agent_env(env: dict, box: Path) -> dict:
    """`env` as the agent gets it: no variables of the launching session, temp and cache folders inside `box`."""
    out = {k: v for k, v in env.items() if k in KEEP or not k.startswith("CLAUDE")}
    tmp, cache = str(box / "tmp"), str(box / "cache")
    return dict(out, TMPDIR=tmp, CLAUDE_CODE_TMPDIR=tmp, XDG_CACHE_HOME=cache)


def settings(box: Path, deny_write: list[Path], deny_read: list[Path]) -> dict:
    """Passed with `--settings`. `failIfUnavailable`: a host without the sandbox refuses to start rather than run unprotected."""
    return {"sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False, "autoAllowBashIfSandboxed": True,
                        "network": {"allowAllUnixSockets": True},
                        "filesystem": {"allowWrite": [str(box)], "denyWrite": [str(p) for p in deny_write],
                                       "denyRead": [*SOCKET_DIRS, *(str(p) for p in deny_read)]}},
            "permissions": {"blockWritesOutsideWorkingDirectories": True,
                            "deny": [f"Read(/{p}/**)" for p in deny_read]}}
