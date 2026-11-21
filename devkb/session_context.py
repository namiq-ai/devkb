"""What the task is about, recorded when the prompt arrives, so a tie between equally good names can be broken by the task
and not by popularity. `devkb hook prompt` records the prompt's words here; `symbol` reads them when several definitions
match a name equally well (`resolve` is defined in six files; the ticket is about C++ macros, so `cpp_resolve.py` first).

The record is a hint, never a filter: it only orders matches that already tie, it ages out after `MAX_AGE`, and a missing
or unreadable file means the old order. It holds words, not the prompt."""
import json
import re
import time
from pathlib import Path

NAME = "session-context.json"
MAX_AGE = 12 * 3600
MAX_WORDS = 200
STOP = frozenset("""this that with from have will when then than they them there their what which where while would could should
about into over under also each only does done make made must need needs more most some such these those been being both
file files code line lines test tests tested testing function functions class method methods name names call calls called
fix fixes fixed bug issue ticket expected actual reproduce scope start done when check using used uses use user users
should shall not nor and the for are was were has had its""".split())
WORD = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")


def words(text: str) -> list[str]:
    """Distinct lowercase words of at least 3 letters, identifiers split at `_` and case changes, stop words dropped."""
    seen: dict[str, None] = {}
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text or ""):
        parts = [p for t in tok.split("_") for p in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", t)]
        for p in parts + [tok.replace("_", "")]:
            p = p.lower()
            if len(p) >= 3 and p not in STOP and WORD.fullmatch(p):
                seen.setdefault(p)
    return list(seen)[:MAX_WORDS]


def record(project: Path | str, prompt: str) -> None:
    """Never raises: a hint that cannot be written is simply absent."""
    try:
        d = Path(project) / ".devkb"
        if d.is_dir():
            (d / NAME).write_text(json.dumps({"at": time.time(), "words": words(prompt)}))
    except OSError:
        pass


def load(project: Path | str) -> frozenset[str]:
    try:
        r = json.loads((Path(project) / ".devkb" / NAME).read_text())
        if time.time() - float(r.get("at", 0)) <= MAX_AGE:
            return frozenset(w for w in r.get("words", []) if isinstance(w, str))
    except (OSError, ValueError, TypeError):
        pass
    return frozenset()
