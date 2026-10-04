import json, sys
value = json.load(sys.stdin)
if any(dep not in value for deps in value.values() for dep in deps):
    answer = {'error': 'unknown dependency'}
else:
    answer = []
    remaining = set(value)
    while remaining:
        ready = sorted(node for node in remaining if all(dep in answer for dep in value[node]))
        if not ready:
            answer = {'error': 'cycle'}
            break
        answer.extend(ready)
        remaining.difference_update(ready)
print(json.dumps(answer))
