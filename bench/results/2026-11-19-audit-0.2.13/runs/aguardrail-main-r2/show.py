import json, sys
rows = [json.loads(l) for l in open("audit/searches.jsonl")]
for i in map(int, sys.argv[1:]):
    print("#", i)
    print(rows[i]["input"].get("command") or rows[i]["input"])
