"""Compatibility wrapper for Telegram login.

The real login implementation is introduced in Phase 2. Prefer:

    python -m app.cli telegram-login
"""

from app.cli.commands import main

if __name__ == "__main__":
    raise SystemExit(main(["telegram-login"]))
