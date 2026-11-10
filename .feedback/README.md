# Feedback task starting environment

Upstream: https://github.com/tiran/defusedxml
Upstream commit: `c7445887f5e1bcea470a16f61369d29870cfcfe1`
Prepared on macOS with CPython 3.12.11. No external database, queue, or cloud account is required.
The dependency file pins the installed runtime and test packages for the selected baseline. It is not a claim that all optional upstream test suites are installed.

From the repository root:

```sh
export NO_INTERNET=1 TZ=UTC
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r .feedback/requirements.txt -e .
.venv/bin/python tests.py
```

Scope note: Use upstream tests.py suite entry point. pytest incorrectly collected abstract BaseTests with no parse adapter; no source changes.

Observed baseline (2026-11-10): `OK (skipped=15)`
Whole-command wall time: 0.128 seconds, exit code 0. This is one local measurement, not a runtime guarantee. The first install is excluded.

This seed adds preparation metadata only. Application sources and upstream tests are unchanged; there is no task solution in this commit.
