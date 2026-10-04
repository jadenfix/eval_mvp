import json, sys
sys.path.insert(0, '/app')
from config import merge
print(json.dumps(merge(json.load(sys.stdin))))
