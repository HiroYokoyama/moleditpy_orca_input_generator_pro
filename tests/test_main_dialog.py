"""
tests/test_main_dialog.py

Tests for pure-logic methods in OrcaSetupDialogPro (main_dialog.py).
No Qt instantiation needed — methods are called unbound with self=None.

Covers:
  consolidate_orca_blocks()
    - basic round-trip (no blocks)
    - duplicate % blocks merged
    - MaxIter deduplicated in %geom and %scf (last wins)
    - NRoots / IRoot deduplicated in %tddft
    - redundant bare 'Opt' removed when TightOpt/VeryTightOpt/LooseOpt present
    - duplicate ! tokens removed
    - %pal and %maxcore preserved
    - post-coord blocks stay after coordinates
    - pre+post same block merged into pre-coord zone
    - one-liner %block handled
    - no coordinates block (no crash)
"""

import os
import sys
import types
import importlib.util
import unittest
from unittest.mock import MagicMock

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


def _install_stubs():
    if "PyQt6" in sys.modules:
        return

    class _Base:
        def __init__(self, *a, **kw):
            pass

    pyqt6 = types.ModuleType("PyQt6")
    qt_widgets = types.ModuleType("PyQt6.QtWidgets")
    qt_core = types.ModuleType("PyQt6.QtCore")
    qt_gui = types.ModuleType("PyQt6.QtGui")

    for name in ["QDialog", "QWidget", "QScrollArea"]:
        setattr(qt_widgets, name, _Base)
    for name in [
        "QVBoxLayout",
        "QHBoxLayout",
        "QLabel",
        "QLineEdit",
        "QSpinBox",
        "QPushButton",
        "QGroupBox",
        "QComboBox",
        "QTextEdit",
        "QTabWidget",
        "QCheckBox",
        "QFormLayout",
        "QTableWidget",
        "QTableWidgetItem",
        "QCompleter",
        "QPlainTextEdit",
        "QGridLayout",
        "QSizePolicy",
        "QAbstractItemView",
        "QMessageBox",
        "QFileDialog",
        "QInputDialog",
        "QApplication",
    ]:
        setattr(qt_widgets, name, MagicMock)

    qt_core.Qt = MagicMock()
    qt_core.QRegularExpression = MagicMock
    qt_core.QTimer = MagicMock

    qt_gui.QFont = MagicMock
    qt_gui.QPalette = MagicMock
    qt_gui.QColor = MagicMock
    qt_gui.QSyntaxHighlighter = _Base
    qt_gui.QTextCharFormat = MagicMock
    qt_gui.QAction = MagicMock
    qt_gui.QIcon = MagicMock
    qt_gui.QKeySequence = MagicMock
    qt_gui.QShortcut = MagicMock

    pyqt6.QtWidgets = qt_widgets
    pyqt6.QtCore = qt_core
    pyqt6.QtGui = qt_gui

    sys.modules.update(
        {
            "PyQt6": pyqt6,
            "PyQt6.QtWidgets": qt_widgets,
            "PyQt6.QtCore": qt_core,
            "PyQt6.QtGui": qt_gui,
            "rdkit": MagicMock(),
            "rdkit.Chem": MagicMock(),
            "rdkit.Chem.rdMolTransforms": MagicMock(),
            "pyvista": MagicMock(),
        }
    )


_install_stubs()


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------


def _load_mod(name, relpath, pkg="orca_input_generator_pro"):
    full_name = f"{pkg}.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    path = os.path.join(_REPO_ROOT, pkg, relpath)
    spec = importlib.util.spec_from_file_location(full_name, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = pkg
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


_load_mod("constants", "constants.py")

_mixins = types.ModuleType("orca_input_generator_pro.mixins")


class _FakeMixin:
    def __init__(self):
        self.selection_labels = []

    def enable_picking(self):
        pass

    def disable_picking(self):
        pass

    def clear_selection_labels(self):
        pass


_mixins.Dialog3DPickingMixin = _FakeMixin
sys.modules["orca_input_generator_pro.mixins"] = _mixins

_load_mod("keyword_builder", "keyword_builder.py")

# main_dialog.py imports the highlighter; provide a lightweight fake only if a
# real module (loaded by a sibling test file in the same pytest session) isn't
# already cached in sys.modules -- never clobber a real one, since that would
# break later test modules that expect the real class objects.
if "orca_input_generator_pro.highlighter" not in sys.modules:
    _hl_mod = types.ModuleType("orca_input_generator_pro.highlighter")
    _hl_mod.OrcaSyntaxHighlighter = MagicMock
    sys.modules["orca_input_generator_pro.highlighter"] = _hl_mod

_main_mod = _load_mod("main_dialog", "main_dialog.py")
OrcaSetupDialogPro = _main_mod.OrcaSetupDialogPro


def consolidate(text):
    """Call consolidate_orca_blocks as unbound — self not needed."""
    return OrcaSetupDialogPro.consolidate_orca_blocks(None, text)


def _make_doc_dlg(saved_content="! B3LYP\n", current_content=None, inp_file=None):
    """Minimal namespace for testing document-state helpers."""
    dlg = types.SimpleNamespace()
    dlg.current_inp_file = inp_file
    dlg._saved_inp_content = saved_content
    dlg._current_content = (
        current_content if current_content is not None else saved_content
    )
    pt = MagicMock()
    pt.toPlainText.return_value = (
        current_content if current_content is not None else saved_content
    )
    dlg.preview_text = pt
    dlg._is_modified = lambda: OrcaSetupDialogPro._is_modified(dlg)
    return dlg


# ---------------------------------------------------------------------------
# Tests: basic structure
# ---------------------------------------------------------------------------


class TestConsolidateBasic(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(consolidate("").strip(), "")

    def test_route_preserved(self):
        text = "! B3LYP def2-SVP Opt\n\n* xyz 0 1\n  C 0 0 0\n*"
        self.assertIn("! B3LYP def2-SVP Opt", consolidate(text))

    def test_maxcore_preserved(self):
        text = "%maxcore 2000\n! B3LYP def2-SVP\n\n* xyz 0 1\n  H 0 0 0\n*"
        self.assertIn("%maxcore 2000", consolidate(text))

    def test_pal_preserved(self):
        text = "%pal nprocs 4 end\n%maxcore 2000\n! B3LYP\n\n* xyz 0 1\n  H 0 0 0\n*"
        self.assertIn("nprocs 4", consolidate(text))

    def test_comment_preserved(self):
        text = "# My job\n! B3LYP def2-SVP\n\n* xyz 0 1\n  H 0 0 0\n*"
        self.assertIn("# My job", consolidate(text))

    def test_output_ends_with_newline(self):
        text = "! B3LYP def2-SVP\n\n* xyz 0 1\n  H 0 0 0\n*"
        self.assertTrue(consolidate(text).endswith("\n"))

    def test_coords_preserved(self):
        text = "! B3LYP def2-SVP\n\n* xyz 0 1\n  C  0.0  0.0  0.0\n*"
        result = consolidate(text)
        self.assertIn("* xyz 0 1", result)
        self.assertIn("C  0.0  0.0  0.0", result)


# ---------------------------------------------------------------------------
# Tests: % block merging
# ---------------------------------------------------------------------------


class TestConsolidateMergeBlocks(unittest.TestCase):
    def test_two_geom_blocks_merged(self):
        text = (
            "%geom\n  MaxIter 256\nend\n\n"
            "! B3LYP def2-SVP Opt\n\n"
            "* xyz 0 1\n  H 0 0 0\n*\n\n"
            "%geom\n  Calc_Hess true\nend"
        )
        result = consolidate(text)
        self.assertEqual(result.lower().count("%geom"), 1)
        self.assertIn("MaxIter 256", result)
        self.assertIn("Calc_Hess true", result)

    def test_two_tddft_blocks_merged(self):
        text = (
            "%tddft\n  NRoots 10\nend\n\n"
            "! B3LYP def2-SVP\n\n"
            "* xyz 0 1\n  H 0 0 0\n*\n\n"
            "%tddft\n  IRoot 2\nend"
        )
        result = consolidate(text)
        self.assertEqual(result.lower().count("%tddft"), 1)
        self.assertIn("NRoots 10", result)
        self.assertIn("IRoot 2", result)

    def test_two_scf_blocks_merged(self):
        text = (
            "%scf\n  MaxIter 100\nend\n\n"
            "! B3LYP def2-SVP\n\n"
            "* xyz 0 1\n  H 0 0 0\n*\n\n"
            "%scf\n  DIIS true\nend"
        )
        result = consolidate(text)
        self.assertEqual(result.lower().count("%scf"), 1)


# ---------------------------------------------------------------------------
# Tests: keyword deduplication within blocks
# ---------------------------------------------------------------------------


class TestConsolidateDedup(unittest.TestCase):
    def test_maxiter_deduped_in_geom_last_wins(self):
        text = (
            "%geom\n  MaxIter 125\nend\n\n"
            "! B3LYP def2-SVP Opt\n\n"
            "* xyz 0 1\n  H 0 0 0\n*\n\n"
            "%geom\n  MaxIter 256\nend"
        )
        result = consolidate(text)
        self.assertEqual(result.count("MaxIter"), 1)
        self.assertIn("MaxIter 256", result)
        self.assertNotIn("MaxIter 125", result)

    def test_maxiter_deduped_in_scf(self):
        text = (
            "%scf\n  MaxIter 100\nend\n\n"
            "! B3LYP def2-SVP\n\n"
            "* xyz 0 1\n  H 0 0 0\n*\n\n"
            "%scf\n  MaxIter 200\nend"
        )
        result = consolidate(text)
        self.assertEqual(result.count("MaxIter"), 1)

    def test_nroots_deduped_in_tddft(self):
        text = (
            "%tddft\n  NRoots 5\nend\n\n"
            "! B3LYP def2-SVP\n\n"
            "* xyz 0 1\n  H 0 0 0\n*\n\n"
            "%tddft\n  NRoots 20\nend"
        )
        result = consolidate(text)
        self.assertEqual(result.lower().count("nroots"), 1)

    def test_iroot_deduped_in_tddft(self):
        text = (
            "%tddft\n  NRoots 10\n  IRoot 1\nend\n\n"
            "! B3LYP def2-SVP\n\n"
            "* xyz 0 1\n  H 0 0 0\n*\n\n"
            "%tddft\n  IRoot 3\nend"
        )
        result = consolidate(text)
        self.assertEqual(result.lower().count("iroot"), 1)
        self.assertIn("IRoot 3", result)
        self.assertNotIn("IRoot 1", result)

    def test_maxiter_not_deduped_in_tddft(self):
        # MaxIter is only deduped in scf/geom, not in tddft
        text = (
            "! B3LYP def2-SVP\n\n"
            "* xyz 0 1\n  H 0 0 0\n*\n\n"
            "%tddft\n  NRoots 10\n  MaxIter 200\nend"
        )
        result = consolidate(text)
        self.assertIn("MaxIter 200", result)

    def test_maxdim_deduped_in_tddft(self):
        text = (
            "%tddft\n  NRoots 10\n  MaxDim 5\nend\n\n"
            "! B3LYP def2-SVP\n\n"
            "* xyz 0 1\n  H 0 0 0\n*\n\n"
            "%tddft\n  MaxDim 20\nend"
        )
        result = consolidate(text)
        # MaxDim is in d_keys for tddft
        self.assertEqual(result.lower().count("maxdim"), 1)


# ---------------------------------------------------------------------------
# Tests: ! route line deduplication
# ---------------------------------------------------------------------------


class TestConsolidateRouteDedup(unittest.TestCase):
    def _route_line(self, result):
        for line in result.splitlines():
            if line.strip().startswith("!"):
                return line.strip()
        return ""

    def test_duplicate_tokens_removed(self):
        text = "! B3LYP def2-SVP Opt B3LYP\n\n* xyz 0 1\n  H 0 0 0\n*"
        route = self._route_line(consolidate(text))
        self.assertEqual(route.split().count("B3LYP"), 1)

    def test_opt_removed_when_tightopt_present(self):
        text = "! B3LYP def2-SVP Opt TightOpt\n\n* xyz 0 1\n  H 0 0 0\n*"
        route = self._route_line(consolidate(text))
        tokens = route.split()
        self.assertIn("TightOpt", tokens)
        self.assertNotIn("Opt", tokens)

    def test_opt_removed_when_verytightopt_present(self):
        text = "! B3LYP def2-SVP Opt VeryTightOpt\n\n* xyz 0 1\n  H 0 0 0\n*"
        route = self._route_line(consolidate(text))
        tokens = route.split()
        self.assertIn("VeryTightOpt", tokens)
        self.assertNotIn("Opt", tokens)

    def test_opt_removed_when_looseopt_present(self):
        text = "! B3LYP def2-SVP Opt LooseOpt\n\n* xyz 0 1\n  H 0 0 0\n*"
        route = self._route_line(consolidate(text))
        tokens = route.split()
        self.assertIn("LooseOpt", tokens)
        self.assertNotIn("Opt", tokens)

    def test_opt_kept_without_specific_opt(self):
        text = "! B3LYP def2-SVP Opt\n\n* xyz 0 1\n  H 0 0 0\n*"
        route = self._route_line(consolidate(text))
        self.assertIn("Opt", route.split())

    def test_exclamation_kept_once(self):
        text = "! B3LYP def2-SVP\n\n* xyz 0 1\n  H 0 0 0\n*"
        route = self._route_line(consolidate(text))
        self.assertTrue(route.startswith("!"))
        self.assertEqual(route.split().count("!"), 1)


# ---------------------------------------------------------------------------
# Tests: post-coordinate placement
# ---------------------------------------------------------------------------


class TestConsolidatePostCoord(unittest.TestCase):
    def test_post_block_placed_after_coords(self):
        text = (
            "! B3LYP def2-SVP\n\n"
            "* xyz 0 1\n  H 0 0 0\n*\n\n"
            "%eprnmr\n  NUCLEI = ALL H {SHIFT}\nend"
        )
        result = consolidate(text)
        coord_pos = result.find("* xyz 0 1")
        eprnmr_pos = result.find("%eprnmr")
        self.assertGreater(
            eprnmr_pos, coord_pos, "post-coord block must come after coordinates"
        )

    def test_pre_and_post_same_name_merged_before_coords(self):
        text = (
            "%tddft\n  NRoots 10\nend\n\n"
            "! B3LYP def2-SVP\n\n"
            "* xyz 0 1\n  H 0 0 0\n*\n\n"
            "%tddft\n  IRoot 2\nend"
        )
        result = consolidate(text)
        coord_pos = result.find("* xyz 0 1")
        tddft_pos = result.find("%tddft")
        if coord_pos != -1 and tddft_pos != -1:
            self.assertLess(
                tddft_pos,
                coord_pos,
                "merged tddft block must appear before coordinates",
            )


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestConsolidateEdgeCases(unittest.TestCase):
    def test_no_coords_no_crash(self):
        text = "%maxcore 2000\n! B3LYP def2-SVP"
        result = consolidate(text)
        self.assertIn("B3LYP", result)

    def test_only_comment(self):
        result = consolidate("# just a comment")
        self.assertIn("# just a comment", result)

    def test_oneliner_pal_block(self):
        text = "%pal nprocs 8 end\n%maxcore 4000\n! B3LYP\n\n* xyz 0 1\n  H 0 0 0\n*"
        result = consolidate(text)
        self.assertIn("8", result)
        self.assertIn("4000", result)

    def test_single_geom_block_not_duplicated(self):
        text = (
            "%geom\n  MaxIter 256\nend\n\n"
            "! B3LYP def2-SVP Opt\n\n"
            "* xyz 0 1\n  H 0 0 0\n*"
        )
        result = consolidate(text)
        self.assertEqual(result.lower().count("%geom"), 1)

    def test_whitespace_only_input(self):
        result = consolidate("   \n\n  ")
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# Helpers for generate_second_job_content tests
# ---------------------------------------------------------------------------


def _sj_dlg(
    *,
    nproc=4,
    sj_maxcore=4000,
    sj_kw="! DLPNO-CCSD(T) def2-TZVP TightSCF",
    sj_coord="xyzfile  (optimized geometry from Job 1)",
    sj_xyz="myjob.xyz",
    sj_adv="",
    charge=0,
    mult=1,
    filename=None,
):
    """Minimal namespace for generate_second_job_content tests."""
    dlg = types.SimpleNamespace()

    nproc_spin = MagicMock()
    nproc_spin.value.return_value = nproc
    dlg.nproc_spin = nproc_spin

    sj_mem = MagicMock()
    sj_mem.value.return_value = sj_maxcore
    dlg.second_job_mem_spin = sj_mem

    sj_kw_edit = MagicMock()
    sj_kw_edit.toPlainText.return_value = sj_kw
    dlg.second_job_keywords = sj_kw_edit

    sj_coord_combo = MagicMock()
    sj_coord_combo.currentText.return_value = sj_coord
    dlg.second_job_coord_src = sj_coord_combo

    sj_xyz_edit = MagicMock()
    sj_xyz_edit.text.return_value = sj_xyz
    dlg.second_job_xyz_name = sj_xyz_edit

    sj_adv_edit = MagicMock()
    sj_adv_edit.toPlainText.return_value = sj_adv
    dlg.second_job_adv = sj_adv_edit

    charge_spin = MagicMock()
    charge_spin.value.return_value = charge
    dlg.charge_spin = charge_spin
    mult_spin = MagicMock()
    mult_spin.value.return_value = mult
    dlg.mult_spin = mult_spin

    dlg.filename = filename
    dlg.get_coords_lines = lambda: ["  C   0.000000   0.000000   0.000000"]

    return dlg


# ---------------------------------------------------------------------------
# Tests: generate_second_job_content
# ---------------------------------------------------------------------------


class TestGenerateSecondJobContent(unittest.TestCase):
    def test_xyzfile_mode_emits_xyzfile_line(self):
        dlg = _sj_dlg(sj_xyz="water-opt.xyz")
        result = OrcaSetupDialogPro.generate_second_job_content(dlg)
        self.assertIn("* xyzfile 0 1 water-opt.xyz", result)
        self.assertNotIn("* xyz 0 1", result)

    def test_xyzfile_fallback_from_filename(self):
        dlg = _sj_dlg(sj_xyz="", filename="/path/to/water.mol")
        result = OrcaSetupDialogPro.generate_second_job_content(dlg)
        self.assertIn("* xyzfile 0 1 water.xyz", result)

    def test_xyzfile_fallback_no_filename(self):
        dlg = _sj_dlg(sj_xyz="", filename=None)
        result = OrcaSetupDialogPro.generate_second_job_content(dlg)
        self.assertIn("* xyzfile 0 1 PREVJOB.xyz", result)

    def test_copy_mode_emits_coord_block(self):
        dlg = _sj_dlg(sj_coord="Copy Job 1 coordinates  (same geometry)")
        result = OrcaSetupDialogPro.generate_second_job_content(dlg)
        self.assertIn("* xyz 0 1", result)
        self.assertIn("C   0.000000", result)
        self.assertTrue(result.rstrip().endswith("*"))

    def test_resources_inherit_nproc_from_job1(self):
        dlg = _sj_dlg(nproc=8, sj_maxcore=6000)
        result = OrcaSetupDialogPro.generate_second_job_content(dlg)
        self.assertIn("%pal nprocs 8 end", result)
        self.assertIn("%maxcore 6000", result)

    def test_single_proc_omits_pal(self):
        dlg = _sj_dlg(nproc=1, sj_maxcore=2000)
        result = OrcaSetupDialogPro.generate_second_job_content(dlg)
        self.assertNotIn("%pal", result)
        self.assertIn("%maxcore 2000", result)

    def test_bare_keywords_get_exclamation_prepended(self):
        dlg = _sj_dlg(sj_kw="DLPNO-CCSD(T) def2-TZVP")
        result = OrcaSetupDialogPro.generate_second_job_content(dlg)
        self.assertIn("! DLPNO-CCSD(T) def2-TZVP", result)

    def test_keywords_with_exclamation_not_doubled(self):
        dlg = _sj_dlg(sj_kw="! DLPNO-CCSD(T) def2-TZVP")
        result = OrcaSetupDialogPro.generate_second_job_content(dlg)
        self.assertEqual(result.count("!"), 1)

    def test_optional_adv_blocks_included(self):
        dlg = _sj_dlg(sj_adv="%geom MaxIter 500 end")
        result = OrcaSetupDialogPro.generate_second_job_content(dlg)
        self.assertIn("%geom MaxIter 500 end", result)


# ---------------------------------------------------------------------------
# Tests: $new_job boundary in output
# ---------------------------------------------------------------------------


class TestNewJobBoundary(unittest.TestCase):
    def test_new_job_separator_present(self):
        first = consolidate("! B3LYP def2-SVP Opt\n\n* xyz 0 1\n  C 0 0 0\n*\n")
        second = "! DLPNO-CCSD(T) def2-TZVP\n\n* xyzfile 0 1 job.xyz"
        full = first.rstrip("\n") + "\n\n$new_job\n\n" + second + "\n"
        self.assertIn("$new_job", full)
        self.assertIn("DLPNO-CCSD(T)", full)
        self.assertIn("xyzfile 0 1 job.xyz", full)

    def test_consolidate_does_not_emit_new_job(self):
        result = consolidate("! B3LYP def2-SVP Opt\n\n* xyz 0 1\n  C 0 0 0\n*\n")
        self.assertNotIn("$new_job", result)

    def test_new_job_comes_after_first_coord_block(self):
        first = consolidate("! B3LYP def2-SVP Opt\n\n* xyz 0 1\n  C 0 0 0\n*\n")
        second = "! DLPNO-CCSD(T) def2-TZVP\n\n* xyzfile 0 1 job.xyz"
        full = first.rstrip("\n") + "\n\n$new_job\n\n" + second + "\n"
        coord_pos = full.find("* xyz 0 1")
        new_job_pos = full.find("$new_job")
        self.assertGreater(new_job_pos, coord_pos)


# ---------------------------------------------------------------------------
# Tests: insert_block_template — %mrci correct ORCA syntax
# ---------------------------------------------------------------------------


def _insert_template(block_label):
    """Call insert_block_template unbound, return text inserted into adv_edit."""
    inserted = []

    dlg = types.SimpleNamespace()
    dlg.block_combo = MagicMock()
    dlg.block_combo.currentText.return_value = block_label

    text_edit = MagicMock()
    cursor = MagicMock()
    cursor.insertText.side_effect = lambda t: inserted.append(t)
    text_edit.textCursor.return_value = cursor

    dlg.adv_tabs = MagicMock()
    dlg.adv_tabs.currentWidget.return_value = text_edit

    from PyQt6.QtWidgets import QTextEdit as _QTE  # noqa: F401 — used by isinstance check
    import PyQt6.QtWidgets as _qtw

    _qtw.QTextEdit = type("QTextEdit", (), {})
    text_edit.__class__ = _qtw.QTextEdit

    OrcaSetupDialogPro.insert_block_template(dlg)
    return "".join(inserted)


# ---------------------------------------------------------------------------
# Tests: document state (_is_modified, _update_title)
# ---------------------------------------------------------------------------


class TestIsModified(unittest.TestCase):
    def test_no_file_never_modified(self):
        dlg = _make_doc_dlg(inp_file=None)
        self.assertFalse(OrcaSetupDialogPro._is_modified(dlg))

    def test_no_saved_content_never_modified(self):
        dlg = _make_doc_dlg(inp_file="/tmp/x.inp")
        dlg._saved_inp_content = None
        self.assertFalse(OrcaSetupDialogPro._is_modified(dlg))

    def test_identical_content_not_modified(self):
        dlg = _make_doc_dlg(
            inp_file="/tmp/x.inp", saved_content="A", current_content="A"
        )
        self.assertFalse(OrcaSetupDialogPro._is_modified(dlg))

    def test_changed_content_is_modified(self):
        dlg = _make_doc_dlg(
            inp_file="/tmp/x.inp", saved_content="A", current_content="B"
        )
        self.assertTrue(OrcaSetupDialogPro._is_modified(dlg))


class TestUpdateTitle(unittest.TestCase):
    def _run(self, **kw):
        dlg = _make_doc_dlg(**kw)
        dlg.setWindowTitle = MagicMock()
        OrcaSetupDialogPro._update_title(dlg)
        return dlg.setWindowTitle.call_args[0][0]

    def test_no_file_shows_plugin_name_and_star(self):
        title = self._run(inp_file=None)
        from orca_input_generator_pro import PLUGIN_NAME

        self.assertIn(PLUGIN_NAME, title)
        self.assertIn("*", title)  # unsaved document always shows *

    def test_saved_file_shows_basename(self):
        title = self._run(
            inp_file="/path/to/job.inp", saved_content="A", current_content="A"
        )
        self.assertIn("job.inp", title)
        self.assertNotIn("*", title)

    def test_modified_file_shows_asterisk(self):
        title = self._run(
            inp_file="/path/to/job.inp", saved_content="A", current_content="B"
        )
        self.assertIn("job.inp", title)
        self.assertIn("*", title)


class TestInsertBlockTemplateMrci(unittest.TestCase):
    def test_mrci_uses_newblock_not_NewBlocks(self):
        t = _insert_template("%mrci ... end")
        self.assertNotIn("NewBlocks", t)

    def test_mrci_has_newblock_keyword(self):
        t = _insert_template("%mrci ... end")
        self.assertIn("newblock", t)

    def test_mrci_has_refs_cas(self):
        t = _insert_template("%mrci ... end")
        self.assertIn("refs cas", t)

    def test_mrci_has_citype(self):
        t = _insert_template("%mrci ... end")
        self.assertIn("CIType", t)

    def test_mrci_has_nroots(self):
        t = _insert_template("%mrci ... end")
        self.assertIn("nroots", t)

    def test_mrci_outer_block_closed(self):
        t = _insert_template("%mrci ... end")
        self.assertTrue(t.strip().endswith("end"))


class TestInsertBlockTemplateRocis(unittest.TestCase):
    def _t(self):
        return _insert_template("%rocis ... end")

    def test_rocis_has_nroots(self):
        self.assertIn("NRoots", self._t())

    def test_rocis_has_maxdim(self):
        self.assertIn("MaxDim", self._t())

    def test_rocis_has_doquad(self):
        self.assertIn("DoQuad", self._t())

    def test_rocis_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateCasscf(unittest.TestCase):
    def _t(self):
        return _insert_template("%casscf ... end")

    def test_casscf_has_nel(self):
        self.assertIn("Nel", self._t())

    def test_casscf_has_norb(self):
        self.assertIn("Norb", self._t())

    def test_casscf_has_nroots(self):
        self.assertIn("nroots", self._t())

    def test_casscf_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateMd(unittest.TestCase):
    def _t(self):
        return _insert_template("%md ... end")

    def test_md_has_timestep(self):
        self.assertIn("TimeStep", self._t())

    def test_md_has_totaltime(self):
        self.assertIn("TotalTime", self._t())

    def test_md_has_temp(self):
        self.assertIn("Temp", self._t())

    def test_md_has_thermostat(self):
        self.assertIn("Thermostat", self._t())

    def test_md_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateNeb(unittest.TestCase):
    def _t(self):
        return _insert_template("%neb ... end")

    def test_neb_starts_with_percent_neb(self):
        self.assertTrue(self._t().strip().startswith("%neb"))

    def test_neb_has_product(self):
        self.assertIn("Product", self._t())

    def test_neb_has_nimages(self):
        self.assertIn("NImages", self._t())

    def test_neb_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


# ---------------------------------------------------------------------------
# Tests: _auto_insert_blocks_for_route
# ---------------------------------------------------------------------------


def _auto_dlg(adv_content="", post_adv_content=""):
    dlg = types.SimpleNamespace()
    adv = MagicMock()
    adv.toPlainText.return_value = adv_content
    dlg.adv_edit = adv
    post_adv = MagicMock()
    post_adv.toPlainText.return_value = post_adv_content
    dlg.post_adv_edit = post_adv
    return dlg


class TestAutoInsertBlocksForRoute(unittest.TestCase):
    def test_neb_ci_inserts_neb_block(self):
        dlg = _auto_dlg()
        OrcaSetupDialogPro._auto_insert_blocks_for_route(dlg, "! B3LYP def2-SVP NEB-CI")
        dlg.adv_edit.setPlainText.assert_called_once()
        inserted = dlg.adv_edit.setPlainText.call_args[0][0]
        self.assertIn("%neb", inserted)
        self.assertIn("Product", inserted)

    def test_neb_ts_inserts_neb_block(self):
        dlg = _auto_dlg()
        OrcaSetupDialogPro._auto_insert_blocks_for_route(dlg, "! B3LYP def2-SVP NEB-TS")
        inserted = dlg.adv_edit.setPlainText.call_args[0][0]
        self.assertIn("%neb", inserted)

    def test_md_inserts_md_block(self):
        dlg = _auto_dlg()
        OrcaSetupDialogPro._auto_insert_blocks_for_route(dlg, "! B3LYP def2-SVP MD")
        dlg.adv_edit.setPlainText.assert_called_once()
        inserted = dlg.adv_edit.setPlainText.call_args[0][0]
        self.assertIn("%md", inserted)
        self.assertIn("TimeStep", inserted)

    def test_existing_neb_not_duplicated(self):
        dlg = _auto_dlg(adv_content="%neb\n  Product x.xyz\nend\n")
        OrcaSetupDialogPro._auto_insert_blocks_for_route(dlg, "! B3LYP def2-SVP NEB-CI")
        dlg.adv_edit.setPlainText.assert_not_called()

    def test_existing_md_not_duplicated(self):
        dlg = _auto_dlg(adv_content="%md\n  TimeStep 0.5\nend\n")
        OrcaSetupDialogPro._auto_insert_blocks_for_route(dlg, "! B3LYP def2-SVP MD")
        dlg.adv_edit.setPlainText.assert_not_called()

    def test_opt_route_no_insert(self):
        dlg = _auto_dlg()
        OrcaSetupDialogPro._auto_insert_blocks_for_route(dlg, "! B3LYP def2-SVP Opt")
        dlg.adv_edit.setPlainText.assert_not_called()

    def test_neb_in_post_adv_not_duplicated(self):
        dlg = _auto_dlg(post_adv_content="%neb\n  Product x.xyz\nend\n")
        OrcaSetupDialogPro._auto_insert_blocks_for_route(dlg, "! B3LYP def2-SVP NEB-CI")
        dlg.adv_edit.setPlainText.assert_not_called()


class TestInsertBlockTemplateMp2(unittest.TestCase):
    def _t(self):
        return _insert_template("%mp2 ... end")

    def test_mp2_starts_with_percent_mp2(self):
        self.assertTrue(self._t().strip().startswith("%mp2"))

    def test_mp2_has_ri(self):
        self.assertIn("RI", self._t())

    def test_mp2_has_density(self):
        self.assertIn("Density", self._t())

    def test_mp2_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateFreq(unittest.TestCase):
    def _t(self):
        return _insert_template("%freq ... end")

    def test_freq_starts_with_percent_freq(self):
        self.assertTrue(self._t().strip().startswith("%freq"))

    def test_freq_has_temp(self):
        self.assertIn("Temp", self._t())

    def test_freq_has_pressure(self):
        self.assertIn("Pressure", self._t())

    def test_freq_has_vcd_comment(self):
        self.assertIn("doVCD", self._t())

    def test_freq_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateLoc(unittest.TestCase):
    def _t(self):
        return _insert_template("%loc ... end")

    def test_loc_starts_with_percent_loc(self):
        self.assertTrue(self._t().strip().startswith("%loc"))

    def test_loc_has_locmet(self):
        self.assertIn("LocMet", self._t())

    def test_loc_has_pipek_mezey(self):
        self.assertIn("PipekMezey", self._t())

    def test_loc_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateEsd(unittest.TestCase):
    def _t(self):
        return _insert_template("%esd ... end")

    def test_esd_starts_with_percent_esd(self):
        self.assertTrue(self._t().strip().startswith("%esd"))

    def test_esd_has_esdflag(self):
        self.assertIn("ESDFLAG", self._t())

    def test_esd_has_gshessian(self):
        self.assertIn("GSHESSIAN", self._t())

    def test_esd_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateMdci(unittest.TestCase):
    def _t(self):
        return _insert_template("%mdci ... end")

    def test_mdci_starts_with_percent_mdci(self):
        self.assertTrue(self._t().strip().startswith("%mdci"))

    def test_mdci_has_tcutpno(self):
        self.assertIn("TCutPNO", self._t())

    def test_mdci_has_tcutpairs(self):
        self.assertIn("TCutPairs", self._t())

    def test_mdci_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateCompound(unittest.TestCase):
    def _t(self):
        return _insert_template("%compound ... EndRun")

    def test_compound_contains_percent_compound(self):
        self.assertIn("%Compound", self._t())

    def test_compound_has_new_step(self):
        self.assertIn("New_Step", self._t())

    def test_compound_has_step_end(self):
        self.assertIn("Step_End", self._t())

    def test_compound_ends_with_endrun(self):
        t = self._t().strip()
        self.assertTrue(t.endswith("EndRun") or "EndRun" in t)


class TestInsertBlockTemplateBasis(unittest.TestCase):
    def _t(self):
        return _insert_template("%basis ... end")

    def test_basis_starts_with_percent_basis(self):
        self.assertTrue(self._t().strip().startswith("%basis"))

    def test_basis_has_basis_keyword(self):
        self.assertIn("Basis", self._t())

    def test_basis_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateCpcm(unittest.TestCase):
    def _t(self):
        return _insert_template("%cpcm ... end")

    def test_cpcm_starts_with_percent_cpcm(self):
        self.assertTrue(self._t().strip().startswith("%cpcm"))

    def test_cpcm_has_epsilon(self):
        self.assertIn("Epsilon", self._t())

    def test_cpcm_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateRel(unittest.TestCase):
    def _t(self):
        return _insert_template("%rel ... end")

    def test_rel_starts_with_percent_rel(self):
        self.assertTrue(self._t().strip().startswith("%rel"))

    def test_rel_has_method(self):
        self.assertIn("method", self._t())

    def test_rel_has_order(self):
        self.assertIn("order", self._t())

    def test_rel_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateDft(unittest.TestCase):
    def _t(self):
        return _insert_template("%dft ... end")

    def test_starts_with_percent_dft(self):
        self.assertTrue(self._t().strip().startswith("%dft"))

    def test_has_grid(self):
        self.assertIn("Grid", self._t())

    def test_has_gridx(self):
        self.assertIn("GridX", self._t())

    def test_has_defgrid2(self):
        self.assertIn("DefGrid2", self._t())

    def test_block_closed(self):
        self.assertTrue(self._t().strip().endswith("end"))


class TestInsertBlockTemplateFrag(unittest.TestCase):
    def _t(self):
        return _insert_template("%frag (BSSE/Counterpoise)")

    def test_contains_percent_frag(self):
        self.assertIn("%frag", self._t())

    def test_has_nfrags(self):
        self.assertIn("NFrags", self._t())

    def test_has_fragment_definitions(self):
        self.assertIn("Frag1", self._t())
        self.assertIn("Frag2", self._t())

    def test_has_charge_and_mult(self):
        self.assertIn("Charge1", self._t())
        self.assertIn("Mult1", self._t())

    def test_has_ghost_frags_companion(self):
        self.assertIn("GhostFrags", self._t())

    def test_block_closed(self):
        self.assertIn("end", self._t())


class TestConsolidateMoinpDirective(unittest.TestCase):
    """
    Regression test: %moinp "file.gbw" is a single-line directive with no
    "end" terminator. consolidate_orca_blocks()'s parse_zone() used to only
    special-case %pal and %maxcore this way; %moinp fell through to the
    generic multi-line %block parser, which scans forward for a bare "end"
    line to close the block. Since %moinp itself never has one, the parser
    swallowed every following block up to the *next* block's "end" as if it
    were %moinp's own content — corrupting the input and losing the MO
    filename (the text after "%moinp" on its own line was discarded too).
    """

    def test_moinp_filename_preserved(self):
        text = (
            '! B3LYP def2-SVP MOREAD\n\n'
            '%moinp "prev.gbw"\n\n'
            '* xyz 0 1\n  H 0 0 0\n*'
        )
        out = consolidate(text)
        self.assertIn('%moinp "prev.gbw"', out)

    def test_moinp_does_not_swallow_following_block(self):
        text = (
            '! B3LYP def2-SVP MOREAD Opt\n\n'
            '%moinp "prev.gbw"\n\n'
            "%geom\n"
            "  Constraints\n"
            "    {B 0 1 C}\n"
            "  end\n"
            "end\n\n"
            "* xyz 0 1\n  H 0 0 0\n  H 0 0 1\n*"
        )
        out = consolidate(text)
        # %geom must remain its own top-level block, not nested text
        # inside a runaway %moinp ... end wrapper.
        self.assertIn("\n%geom\n", "\n" + out)
        self.assertIn("Constraints", out)
        self.assertIn('%moinp "prev.gbw"', out)

    def test_moinp_survives_alongside_tddft_block(self):
        text = (
            "! B3LYP def2-SVP MOREAD TDDFT\n\n"
            '%moinp "prev.gbw"\n\n'
            "%tddft\n"
            "  NRoots 5\n"
            "end\n\n"
            "* xyz 0 1\n  H 0 0 0\n*"
        )
        out = consolidate(text)
        self.assertIn("\n%tddft\n", "\n" + out)
        self.assertIn("NRoots 5", out)
        self.assertIn('%moinp "prev.gbw"', out)

    def test_moinp_alone_round_trips(self):
        text = '%moinp "run1.gbw"\n! B3LYP def2-SVP\n\n* xyz 0 1\n  H 0 0 0\n*'
        out = consolidate(text)
        self.assertIn('%moinp "run1.gbw"', out)
        self.assertIn("! B3LYP def2-SVP", out)


if __name__ == "__main__":
    unittest.main()
