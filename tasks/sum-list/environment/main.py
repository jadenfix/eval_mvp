import json
import sys

numbers = json.load(sys.stdin)
print(json.dumps(len(numbers)))  # Bug: count instead of sum.
