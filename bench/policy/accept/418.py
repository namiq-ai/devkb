"""#418: a TypeScript or TSX symbol has its real start and end line: `outline` says `range=exact` and `symbol NAME --source` prints exactly the lines of the
declaration to its closing token, whatever braces strings, nested template literals, regular-expression literals, comments and JSX text hold.
Black box: the checkout's own CLI on a fixture repository; prints one JSON line."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/devkb/.venv/bin/python")
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else (str(SHARED) if SHARED.exists() else sys.executable)
SPANS = '''export function plain(a: number): number {
  return a + 1;
}

export function braceInString(): string {
  const open = "{";
  const close = '}';
  return open + close;
}

export function nestedTemplate(user: { name: string }): string {
  return `hello ${user.name} ${`inner ${ { a: 1 }.a } }`} done`;
}

export function regexAndComments(s: string): boolean {
  // a comment with a brace }
  /* and a block comment { */
  return /[{}]+/.test(s);
}

export const arrowBlock = (x: number) => {
  const text = "}}";
  return text + x;
};

export const arrowExpr = (x: number) =>
  x * 2;

export class Counter {
  count = 0;
  inc(): number {
    return ++this.count;
  }
}

export const api = {
  one: () => get<number>("/one"),
  two: (id: string) => {
    return get<string>(`/two/${id}`);
  },
};

function get<T>(url: string): T {
  return url as unknown as T;
}
'''
VIEW = '''export function View({ count }: { count: number }) {
  return (
    <div>
      <p>Don't panic: {count} items</p>
      <span>{"}"}</span>
    </div>
  );
}

export function After() {
  return 1;
}
'''
EXPECT = {"plain": (1, 3), "braceInString": (5, 9), "nestedTemplate": (11, 13), "regexAndComments": (15, 19), "arrowBlock": (21, 24),
          "Counter": (29, 34), "one": (37, 37), "two": (38, 40), "View": (1, 8), "After": (10, 12)}
res, detail = {}, {}
with tempfile.TemporaryDirectory() as td:
    repo = Path(td) / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "spans.ts").write_text(SPANS)
    (repo / "src" / "View.tsx").write_text(VIEW)
    for c in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@e.x", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=repo, check=True, capture_output=True)
    env = dict(os.environ, HOME=td, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
    for k in ("DEVKB_GUARDRAIL", "DEVKB_TELEMETRY", "DEVKB_MISSLOG", "DEVKB_DIR"):
        env.pop(k, None)
    run = lambda *a: subprocess.run([py, "-P", "-m", "devkb.cli", *a, "--project", str(repo)], cwd=repo, env=env, capture_output=True, text=True, timeout=300)
    res["builds"] = run("build").returncode == 0
    for name, (a, b) in EXPECT.items():
        out = run("symbol", name, "--source").stdout
        head = next((ln for ln in out.splitlines() if re.match(r"\s*1\.\s", ln)), "")
        m = re.search(r"\bL(\d+)(?:-(\d+))?\b", head)
        got = (int(m.group(1)), int(m.group(2) or m.group(1))) if m and "end unknown" not in head else None
        shown = [int(x) for x in re.findall(r"^\s{2,}(\d+)  ", out, re.M)]
        res[name] = got == (a, b) and bool(shown) and shown[0] == a and shown[-1] == b
        detail[name] = {"got": got, "shown": [shown[0], shown[-1]] if shown else None}
    for f in ("src/spans.ts", "src/View.tsx"):
        res[f"outline {f} is exact"] = "range=exact" in run("outline", f).stdout
print(json.dumps({"results": res, "pass": all(res.values()), "detail": detail}))
