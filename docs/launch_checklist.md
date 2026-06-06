# synthedge Pre-Launch Checklist

## Code Quality

- [x] 73 tests passing (`pytest tests/`)
- [x] No known crashes in the fuzzer engine itself
- [x] Deduplication and minimization working correctly
- [x] Pytest exporter produces valid, importable test files
- [ ] No `sys.monitoring` fallback path tested on Python 3.9–3.11
- [ ] Async function support
- [ ] `@fuzz_contract` can be applied directly to third-party functions without a wrapper shim

## Documentation

- [x] README with install instructions, quick start, and options table
- [x] `examples/findings_report.md` with detailed real-world findings
- [x] `examples/real_world_targets.py` showing how to write fuzz targets
- [ ] `CONTRIBUTING.md` for external contributors
- [ ] Docstrings on public API (`fuzz_contract`, `EdgeCaseEngine`, `CorpusManager`)
- [ ] `docs/` or wiki page explaining how to write good fuzz targets

## Packaging

- [x] `pyproject.toml` with correct metadata, entry point, and package discovery
- [x] `synthedge` CLI entry point registered (`synthedge.cli:main`)
- [x] `pip install -e .` works locally
- [ ] Published to PyPI (`pip install synthedge` from public registry)
- [ ] Version pinned in `pyproject.toml` with optional dependencies listed
- [ ] Package tested in a clean virtual environment (no hidden local dependencies)

## Credibility

- [x] Real bugs found in `humanize 4.15.0`, `boltons 25.0.0`, `validators 0.35.0`
- [x] Findings documented with exact reproducers
- [x] 0 false positives in reported findings
- [x] Deduplicated crash count shown in output (1,193 → 4)
- [ ] Issues filed upstream in humanize, boltons, validators repos
- [ ] Demo GIF or screenshot in README (TODO placeholder exists)

## Distribution

- [x] Show HN post draft (`docs/show_hn.md`)
- [x] Reddit r/Python post draft (`docs/reddit_post.md`)
- [ ] GitHub repository is public
- [ ] GitHub repo URL filled in in Show HN and Reddit drafts
- [ ] GitHub Actions CI running tests on push
- [ ] Release tagged `v0.1.0` on GitHub

## Missing Features That Could Block Adoption

- [ ] No way to fuzz a function directly without the `@fuzz_contract` decorator — requires writing wrapper functions around third-party code
- [ ] No `str` enum / literal support: functions expecting specific string values (e.g., `mode="read"`) won't get meaningful inputs
- [ ] No dict or list type hint support: only scalar types (`float`, `int`, `str`, `bool`, `None`) are handled
- [ ] No seed corpus from user: cannot provide known-interesting inputs to guide fuzzing
- [ ] No timeout per iteration: a function that hangs will stall the entire run
