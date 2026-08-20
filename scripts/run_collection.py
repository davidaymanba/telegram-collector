"""Compatibility wrapper for collection.

The collection implementation is introduced in later phases. Prefer:

    python -m app.cli collect
"""

from app.cli.commands import main

if __name__ == "__main__":
    raise SystemExit(main(["collect"]))
