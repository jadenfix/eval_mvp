Fix the configuration merger in /app. main.py reads a JSON object
containing optional defaults, file, and cli objects, and outputs the merged
JSON object. Later layers override earlier ones: defaults < file < cli.
Keys absent from a layer retain their previous value. Omitted layers are empty.
Values are JSON primitives; retain their types and values. Preserve the CLI
entry point and expose the same behavior through config.merge(value).

The grader runs Python with -I in a fresh environment. Only /app files are submitted.
