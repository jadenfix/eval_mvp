Fix /app/main.py. Read a JSON object with a "csv" string from stdin.
The CSV header must be exactly name,amount. Return a JSON object mapping each
name to the sum of its integer amounts. Preserve names, including commas within
quoted fields. Ignore completely blank lines. Empty data returns {}. Negative
amounts are valid. A wrong header, missing/extra field, or non-integer amount
returns {"error":"invalid"}; do not emit partial totals. Exit successfully.

The grader runs Python with -I in a fresh environment. Only /app files are submitted.
