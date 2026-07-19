"""
tests/test_highlighter.py

Behavioural tests for OrcaSyntaxHighlighter (highlighter.py).

Unlike the other test modules, which install lightweight PyQt6 stubs so the
pure-logic paths can run without a GUI toolkit, these tests need the *real*
PyQt6: QSyntaxHighlighter/QRegularExpression behaviour is what is under test,
and a stub cannot tell us whether a pattern flag actually exists.

The whole module is skipped when PyQt6 is unavailable.  It runs headless via
QT_QPA_PLATFORM=offscreen, so no display server is required.

ORCA's highlightBlock() is not a plain "apply every rule" loop -- it inspects
each rule's pattern text and decides whether the rule applies to this line:

  1. the comment rule (#) applies everywhere;
  2. ^%, ^*, ^$ and the `end` rule apply on any line;
  3. the keyword-token rule applies only on `!` route lines;
  4. the ^! rule applies only on `!` route lines.

Each of those branches is covered below.

Regression note: these tests cover the PyQt6 scoped-enum spelling
QRegularExpression.PatternOption.CaseInsensitiveOption.  The unscoped
QRegularExpression.CaseInsensitiveOption does not exist in PyQt6 and raised
AttributeError out of the highlighter constructor -- which, because setup_ui()
builds a highlighter, stopped the plugin dialog from opening at all.
"""

import os
import sys
import importlib.util
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

try:
    from PyQt6.QtGui import QTextDocument
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - exercised only on PyQt6-less runs
    QApplication = None


def _load_highlighter():
    """Import the real highlighter module under its package name."""
    full_name = "orca_input_generator_pro.highlighter"
    if full_name in sys.modules:
        return sys.modules[full_name]
    path = os.path.join(_REPO_ROOT, "orca_input_generator_pro", "highlighter.py")
    spec = importlib.util.spec_from_file_location(full_name, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "orca_input_generator_pro"
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load at import time, not in setUpClass: sibling test modules install a
# MagicMock under this name while pytest is still collecting, and whichever
# module gets there first wins.  Registering the real one here means the rest
# of the suite exercises the genuine highlighter too.
_HL_MOD = _load_highlighter() if QApplication is not None else None


@unittest.skipIf(QApplication is None, "PyQt6 not installed")
class HighlighterTestBase(unittest.TestCase):
    """Shared QApplication + helpers for driving the highlighter."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.mod = _HL_MOD
        cls.Highlighter = cls.mod.OrcaSyntaxHighlighter

    def formats_for(self, text):
        """Run the highlighter over `text`; return the first line's formats.

        Returns a list of (start, length, QTextCharFormat) for the ranges the
        highlighter applied, which is the observable output of highlightBlock.
        """
        doc = QTextDocument()
        hl = self.Highlighter(doc)
        doc.setPlainText(text)
        # With no view attached the first highlight pass is deferred, so ask
        # for it explicitly before reading the formats back.
        hl.rehighlight()
        # Keep a reference so the highlighter outlives the call.
        self._hl = hl
        block = doc.firstBlock()
        return [(r.start, r.length, r.format) for r in block.layout().formats()]

    def assert_highlighted(self, text, msg=None):
        self.assertTrue(
            self.formats_for(text),
            msg or f"expected {text!r} to be highlighted, got nothing",
        )

    def assert_not_highlighted(self, text, msg=None):
        self.assertEqual(
            [], self.formats_for(text), msg or f"expected {text!r} to be left plain"
        )


class TestHighlighterConstruction(HighlighterTestBase):
    def test_constructs_without_error(self):
        """The constructor must not raise -- see the regression note above."""
        doc = QTextDocument()
        hl = self.Highlighter(doc)
        self.assertIsNotNone(hl)

    def test_accepts_none_parent(self):
        self.assertIsNotNone(self.Highlighter(None))

    def test_builds_rule_table(self):
        hl = self.Highlighter(QTextDocument())
        self.assertTrue(hl.rules, "expected a non-empty rule table")
        for pattern, fmt in hl.rules:
            self.assertTrue(
                pattern.isValid(), f"invalid regex: {pattern.pattern()!r}"
            )
            self.assertIsNotNone(fmt)


class TestKeywordLines(HighlighterTestBase):
    """Branch 3/4: keyword rules apply only on `!` route lines."""

    def test_bang_line_highlighted(self):
        self.assert_highlighted("! B3LYP def2-SVP Opt")

    def test_keyword_highlighted_on_route_line(self):
        """The whole `!` line is highlighted.

        The ^!.* rule and the keyword-token rule share one keyword_format
        object, so Qt coalesces their ranges -- assert on the covered span
        rather than on the number of ranges.
        """
        line = "! B3LYP Opt Freq"
        formats = self.formats_for(line)
        self.assertTrue(formats)
        covered = max(start + length for start, length, _ in formats)
        self.assertEqual(len(line), covered)

    def test_keyword_not_highlighted_off_route_line(self):
        """A bare keyword outside a `!` line must be left alone."""
        self.assert_not_highlighted("B3LYP Opt Freq")

    def test_keyword_case_insensitive_on_route_line(self):
        upper = self.formats_for("! B3LYP OPT")
        lower = self.formats_for("! b3lyp opt")
        self.assertEqual(
            [(s, l) for s, l, _ in upper],
            [(s, l) for s, l, _ in lower],
            "case-insensitive flag not applied to the keyword rule",
        )

    def test_indented_bang_is_still_a_route_line(self):
        """is_route uses text.strip(), so leading whitespace still counts."""
        self.assert_highlighted("   ! B3LYP Opt")


class TestBlockLines(HighlighterTestBase):
    """Branch 2: ^%, ^*, ^$ and the `end` rule apply on any line."""

    def test_percent_block_highlighted(self):
        self.assert_highlighted("%scf maxiter 200 end")

    def test_pal_block_highlighted(self):
        self.assert_highlighted("%pal nprocs 4 end")

    def test_maxcore_block_highlighted(self):
        self.assert_highlighted("%maxcore 4000")

    def test_pal_is_case_insensitive(self):
        self.assert_highlighted("%PAL nprocs 4 end")

    def test_end_keyword_highlighted(self):
        self.assert_highlighted("end")

    def test_end_keyword_case_insensitive(self):
        self.assert_highlighted("END")

    def test_coordinate_header_highlighted(self):
        self.assert_highlighted("*xyz 0 1")

    def test_coordinate_terminator_highlighted(self):
        self.assert_highlighted("*")

    def test_new_job_separator_highlighted(self):
        self.assert_highlighted("$new_job")

    def test_new_job_case_insensitive(self):
        self.assert_highlighted("$NEW_JOB")


class TestComments(HighlighterTestBase):
    """Branch 1: the comment rule applies on every line."""

    def test_full_line_comment_highlighted(self):
        self.assert_highlighted("# a comment")

    def test_trailing_comment_highlighted(self):
        self.assert_highlighted("%maxcore 4000  # inline note")

    def test_comment_on_plain_line_highlighted(self):
        self.assert_highlighted("some text # trailing")


class TestPlainLines(HighlighterTestBase):
    def test_coordinate_row_not_highlighted(self):
        self.assert_not_highlighted("  C   0.000000   0.000000   0.000000")

    def test_empty_line(self):
        self.assert_not_highlighted("")

    def test_whitespace_only_line(self):
        self.assert_not_highlighted("     ")


class TestHighlightBlockRobustness(HighlighterTestBase):
    def test_full_input_file_does_not_raise(self):
        doc = QTextDocument()
        hl = self.Highlighter(doc)
        doc.setPlainText(
            "# Generated by MoleditPy\n"
            "%pal nprocs 4 end\n"
            "%maxcore 4000\n"
            "! B3LYP def2-SVP Opt Freq\n"
            "\n"
            "*xyz 0 1\n"
            " C   0.0   0.0   0.0\n"
            " H   1.0   0.0   0.0\n"
            "*\n"
            "\n"
            "$new_job\n"
        )
        hl.rehighlight()
        # 11 newline-terminated lines -> 12 blocks (the trailing empty one).
        self.assertEqual(12, doc.blockCount())

    def test_very_long_line(self):
        self.formats_for("! " + "B3LYP " * 500)


if __name__ == "__main__":
    unittest.main()
