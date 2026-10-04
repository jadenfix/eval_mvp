import json, sys
print(json.dumps(sorted(json.load(sys.stdin))))
