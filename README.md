# eval_mvp

Minimal coding benchmark using Python's standard library, Harbor, and Docker.

Requires Python 3, Docker running, and Harbor 0.23.0 (`uv tool install harbor==0.23.0`).
The runner and grader use only Python's standard library.

From this directory, check the bundled task:

```sh
python3 benchmark.py --agent oracle
python3 benchmark.py --agent nop
```

Expected: oracle scores 1.0; nop scores 0.0. Nop exercises the bundled incorrect
implementation, so it also checks that plausible wrong work is rejected.

Run a coding agent, with your provider credentials set in the environment:

```sh
python3 benchmark.py --model provider/model
```

Replace `provider/model` with your actual Harbor/LiteLLM model identifier.
The default agent is Terminus-2; select another with `--agent`.

One attempt per task, sequential execution, no automatic retries. The bundled
task has a 120-second agent limit and a 30-second verifier limit. The agent
environment permits network access; the verifier disables it using Docker
Compose. Only /app is transferred. Submitted programs run without privileges;
grading code and rewards are protected from that user.

Each job saves its configuration, task checksums, trajectories, test output,
and summary.json under runs/. Score is passes / tasks; infrastructure errors
produce an incomplete report with score null. Agent timeouts are unsuccessful
attempts. Logs contain execution metadata and must be treated as private.

Add task directories under tasks/ and keep task contents fixed between compared
runs. This one-task example demonstrates the machinery, not broad coding ability.

Verified locally with Docker and Harbor: reference solution 1/1; unchanged wrong
solution 0/1; separate verifier mode in both trials. No model-backed run performed.
