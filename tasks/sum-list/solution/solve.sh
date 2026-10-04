#!/bin/sh
cat > /app/main.py <<'PY'
import json
import sys
print(json.dumps(sum(json.load(sys.stdin))))
PY
