"""
Compile translation files (.po -> .mo) without GNU gettext.

Django's own `compilemessages` needs GNU gettext, which is not installed on
Windows by default. This script does the same job with the polib package.

Usage (from the project root):
    pip install -r requirements-dev.txt
    python scripts/compile_translations.py

Workflow for a new text:
    1. Wrap it in the code:  {% translate "Text" %}  or  _("Text")
    2. Add the msgid / msgstr pair to web/locale/fa/LC_MESSAGES/django.po
    3. Run this script and restart the server.
"""

from pathlib import Path

import polib

LOCALE_DIR = Path(__file__).resolve().parent.parent / "web" / "locale"


def main() -> None:
    po_files = sorted(LOCALE_DIR.glob("*/LC_MESSAGES/*.po"))
    if not po_files:
        print(f"No .po files found under {LOCALE_DIR}")
        return
    for po_path in po_files:
        catalog = polib.pofile(str(po_path))
        missing = [
            entry.msgid
            for entry in catalog
            if not (entry.msgstr or (entry.msgstr_plural and all(entry.msgstr_plural.values())))
        ]
        catalog.save_as_mofile(str(po_path.with_suffix(".mo")))
        print(
            f"compiled {po_path.relative_to(LOCALE_DIR.parent)}  ({len(catalog)} entries, {len(missing)} untranslated)"
        )
        for msgid in missing:
            print(f"   untranslated: {msgid}")


if __name__ == "__main__":
    main()
