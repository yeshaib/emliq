# Contributing to emliq

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Reporting bugs and ideas

Open an [issue](https://github.com/yeshaib/emliq/issues) with what you did, what you expected,
and what happened (plus your OS and emliq version, shown in the bottom-right badge).
**Never paste email contents, tokens, API keys or your `~/.emliq` files into an issue.**

## Making changes

```bash
git clone https://github.com/yeshaib/emliq.git && cd emliq
uv venv && uv pip install -e .
.venv/bin/emliq demo          # try the UI with made-up data (Windows: .venv\Scripts\emliq demo)
python tests/run_tests.py     # must pass before you open a pull request
```

- Keep emliq local-first: no telemetry, no servers, nothing sent anywhere the user didn't choose.
  The one exception is the daily update check (a plain request for the latest GitHub release,
  carrying no user data), which users can turn off.
- Anything that changes mail must go through a confirmation and must never permanently delete.
- Match the style of the surrounding code; keep dependencies to a minimum.
- Every user-visible change gets its own version, following [semantic versioning](https://semver.org):
  `patch` for fixes and small improvements, `minor` for new features, `major` for breaking changes.
  `python scripts/bump.py patch "What changed"` updates the version and the changelog together;
  commit it with the change.
- Test with the demo mailbox, and include tests for new behavior where practical.

By contributing, you agree that your contributions are licensed under the Apache License 2.0.
