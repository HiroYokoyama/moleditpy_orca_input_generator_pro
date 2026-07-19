"""
tests/conftest.py

Prefer the real PyQt6 over the per-module stubs when it is installed.

Several test modules call a local `_install_stubs()` that injects fake PyQt6
modules into sys.modules so pure-logic paths can be tested without a GUI
toolkit.  Each of those helpers begins with:

    if "PyQt6" in sys.modules:
        return

so importing the genuine PyQt6 *here* -- conftest is loaded before any test
module -- makes them all no-ops, and the suite exercises real Qt widgets
instead of stubs.  That is what lets the GUI construction paths in
main_dialog.py, highlighter.py and mixins.py be covered at all.

When PyQt6 is not installed this module does nothing and the stubs behave
exactly as before, so the suite still runs on a bare `pip install pytest`.
"""

import os

# Must be set before QApplication is constructed; makes Qt run headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - PyQt6-less environments
    QApplication = None


if QApplication is not None:
    # A single QApplication must outlive every test in the session; Qt aborts
    # if widgets are created without one.
    _app = QApplication.instance() or QApplication([])
