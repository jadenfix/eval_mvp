Extend /app/main.py with --unique. Input is one JSON array of integers;
output is one JSON array. Without options, preserve input order and duplicates.
--sort retains its existing ascending sort behavior. --unique removes duplicate
values while preserving first-occurrence order. With both options, return sorted
unique values, regardless of option order. Handle empty arrays and negative integers.

The grader runs Python with -I in a fresh environment. Only /app files are submitted.
