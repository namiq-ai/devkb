import json, random, sys
repo, graph, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
nodes = {}
for l in open(f"{graph}/nodes.jsonl"):
    x = json.loads(l); nodes[x["uid"]] = x
edges = [json.loads(l) for l in open(f"{graph}/edges.jsonl")]
edges = [e for e in edges if e["verb"] == "CALLS"]
random.seed(2032)
sample = sorted(random.sample(edges, n), key=lambda e: e["properties"]["evidence_ref"])
def src(rel, ln):
    try: return open(f"{repo}/{rel}").read().splitlines()[ln - 1].strip()[:125]
    except Exception: return "?"
for i, e in enumerate(sample, 1):
    ev = e["properties"]["evidence_ref"]; rel, ln = ev.split(":")[0], int(ev.split(":")[1])
    t = nodes[e["to_uid"]]; tk = t["natural_key"]; trel = tk.split("::")[0]; tl = t["properties"].get("line_start", 0)
    print(f"{i:2d}. {nodes[e['from_uid']]['natural_key'].split('::')[1]} -> {tk}")
    print(f"    call {rel}:{ln}: {src(rel, ln)}")
    print(f"    def  {tl}: {src(trel, tl)}")
