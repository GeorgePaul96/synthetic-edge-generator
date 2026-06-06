# Changelog

## [0.1.0] - 2026-06-06

### Added
- `@fuzz_contract` decorator for declaring function contracts
- Coverage-guided fuzzing engine with sys.monitoring path tracking
- Signature-aware input generation driven by type hints
- Crash deduplication and input minimization
- Pytest export: each unique crash becomes a committable test
- `synthedge <module.py>` CLI entry point
- Real-world validation: found bugs in humanize 4.15, boltons 25.0, validators 0.35
