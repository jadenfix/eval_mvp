import json, sys
print(json.dumps(sum(json.load(sys.stdin))))
