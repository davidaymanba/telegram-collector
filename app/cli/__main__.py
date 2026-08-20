"""Allow `python -m app.cli` execution."""

from app.cli.commands import main

if __name__ == "__main__":
    raise SystemExit(main())
