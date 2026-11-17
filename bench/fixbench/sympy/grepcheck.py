"""For each bug: words (>=3 chars) of the ticket that occur as whole words in the faulty (removed) lines."""
import json, re, pathlib
B = pathlib.Path(__file__).parent / 'bugs'
for d in sorted(B.iterdir()):
    t = json.loads((d / 'ticket.json').read_text())
    words = set(w.lower() for w in re.findall(r'[A-Za-z_][A-Za-z0-9_]{2,}', t['title'] + ' ' + t['body']))
    fault = [l[1:] for l in (d / 'mutation.patch').read_text().splitlines() if l[:1] in '-+' and not l.startswith(('---', '+++'))]
    ftoks = set(w.lower() for l in fault for w in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', l))
    print(d.name, sorted(words & ftoks), '| fault:', ' / '.join(x.strip() for x in fault))
