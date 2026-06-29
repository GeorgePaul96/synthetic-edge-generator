"""Legacy convenience entry point.

Superseded by the `synthedge` CLI (synthedge/cli.py). Kept so `python main.py`
still fuzzes the bundled operations.py demo targets; it now delegates to the
CLI's run_fuzzer rather than duplicating the fuzz loop.
"""
import os

from synthedge.cli import run_fuzzer, print_summary


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    summary = run_fuzzer(os.path.join(here, "operations.py"))
    if summary:
        print_summary(summary)


if __name__ == "__main__":
    main()
