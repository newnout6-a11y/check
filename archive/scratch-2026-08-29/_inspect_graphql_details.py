import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

with open("scratch/serialized_graphql.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for k, v in data.items():
    print(f"\n=================== Query: {k} ===================")
    for subk, subv in v.items():
        print(f"--- Key: {subk} ---")
        if isinstance(subv, (dict, list)):
            dump = json.dumps(subv, indent=2, ensure_ascii=False)
            print(dump[:600] if len(dump) > 600 else dump)
        else:
            print(subv)
