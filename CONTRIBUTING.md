# Contributing to PKflow

Thanks for your interest in improving PKflow! This document explains how to set
up a development environment and the conventions the project follows.

## Development setup

Requires Python ≥ 3.10.

```bash
git clone https://github.com/kinginsun/pkflow.git
cd pkflow
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest        # confirm the suite is green
```

NONMEM and `pandoc` are only needed for the end-to-end paths (running models and
HTML/DOCX reports). The bulk of the test suite runs without them.

## Workflow

1. **Open an issue first** for bugs or non-trivial features so we can agree on
   the approach before code is written.
2. **Branch** from `main` for your change.
3. **Test-driven development.** Add a failing test that captures the desired
   behavior, watch it fail, then write the minimal code to pass it. This is how
   every feature and bug fix in PKflow has been built.
4. **Keep the suite green.** Run `python -m pytest` before opening a PR.
5. **Open a pull request** describing what changed and why, and link the issue.

## Code conventions

- **Statistics are pure functions.** VPC binning, bootstrap CIs, shrinkage, and
  comparison tables take data in and return data out, with no I/O — so they can
  be unit-tested without NONMEM. Keep new analytics this way; put side effects
  (file writes, subprocess calls) in thin CLI/orchestrator wrappers.
- **The backend boundary is small.** Engine-specific code lives behind the
  `Backend` protocol (`parse / run / collect / simulate`). A new backend or
  executor should be a single focused module.
- **Match the surrounding style** — comment density, naming, and idioms.
- Prefer small, focused files; if a module grows large, it is probably doing too
  much.

## Reporting bugs

Please include: the command or code you ran, the full error/traceback, your
Python and pharmpy versions, and (if relevant) a minimal control stream that
reproduces the problem.

## License

By contributing, you agree that your contributions will be licensed under the
project's [MIT License](LICENSE).
