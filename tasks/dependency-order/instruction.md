Fix /app/main.py. Read a JSON object mapping string node names to
lists of prerequisite node names. Return a JSON list containing every node
exactly once, with all prerequisites before their dependents. Any valid order
is accepted, including for disconnected graphs. Empty input returns []. If a
prerequisite is not a key in the object, return {"error":"unknown dependency"}.
Otherwise, if no valid order exists (including self-dependencies), return
{"error":"cycle"}. Lists of prerequisites contain no duplicates.

The grader runs Python with -I in a fresh environment. Only /app files are submitted.
