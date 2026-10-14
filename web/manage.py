#!/usr/bin/env python
"""Django command-line utility (runserver, migrate, test, ...)."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
