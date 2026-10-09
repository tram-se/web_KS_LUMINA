#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    if (
        len(sys.argv) >= 2
        and sys.argv[1] == "runserver"
        and not any(arg and not arg.startswith("-") for arg in sys.argv[2:])
    ):
        sys.argv.append("0.0.0.0:8000")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Run: pip install -r requirements.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
