Fix /app/main.py. argv[1] names an existing SQLite database with
accounts(id TEXT PRIMARY KEY, balance INTEGER). Read {"updates":[[id,delta],...]}
from stdin, where deltas are integers. Apply all changes atomically, including
multiple changes to the same account. If any account is absent, roll back ALL
updates and output {"error":"unknown account"}. Otherwise commit and output a
JSON object of ALL account balances, including untouched accounts. An empty
update list leaves the database unchanged and returns all balances. Exit successfully.

The grader runs Python with -I in a fresh environment. Only /app files are submitted.
