import subprocess, sys, os
env = dict(os.environ, PYTHONWARNINGS="ignore")
for n in ['a(b', 'foo[', '*', 'a|b', '\\', '(', 'x)', '+', '?', '.', '^', '$', 'run_query(', '{', 'a b', '-x', '--help', '', ' ', '-e', 'a\\b', "it's", 'a\nb', '[a-z]', 'self.x', 'a.b', 'a::b', 'x\\|y']:
    p = subprocess.run([".venv/bin/python", "-m", "devkb.cli", "uses", n, "--project", "."], capture_output=True, text=True, env=env)
    print(repr(n), "rc", p.returncode, "|", (p.stdout + p.stderr).strip().splitlines()[:3] and (p.stdout + p.stderr).strip().splitlines()[0][:150])
