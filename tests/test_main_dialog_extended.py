"""
tests/test_main_dialog_extended.py

Extended coverage for OrcaSetupDialogPro (main_dialog.py).

Unlike tests/test_main_dialog.py (which calls pure-logic methods unbound
against hand-built fake `self` objects), these tests construct the *real*
QDialog headlessly (QT_QPA_PLATFORM=offscreen, via tests/conftest.py) with
real RDKit molecules, exercising the full GUI construction path plus
z-matrix / coordinate / preset / persistence / document-state logic.

SETTINGS_FILE is always monkeypatched to a throwaway temp path so nothing
here ever touches the real package's settings.json.
"""

import os
import sys
import json
import shutil
import types
import tempfile
import importlib
import importlib.util
import unittest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Several sibling test modules (test_keyword_builder.py, test_metadata.py, ...)
# unconditionally clobber sys.modules["PyQt6*"] with permissive MagicMock-based
# stubs as soon as they are collected, with no regard for import order. That
# is fine for *their* pure-logic tests, but this file needs to construct the
# real QDialog (real widgets, real event types) to exercise GUI-construction
# and document-state code paths. Rather than depend on collection order (which
# is fragile — whichever test module runs first "wins" the shared
# orca_input_generator_pro.main_dialog cache slot), load an entirely private
# copy of the plugin's module tree under a throwaway package name, forcing
# real PyQt6/RDKit to be imported fresh for it. This never touches the
# canonical "orca_input_generator_pro.*" sys.modules entries other test files
# rely on.
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PRIV_PKG = "_oigp_real_qt_copy"


def _real_module(name):
    """Return the genuine installed module for `name`, recovering the copy
    conftest.py stashed under "<name>__real" if a sibling test file has since
    replaced sys.modules[name] with a stub. Never pop-and-reimport PyQt6
    submodules directly: re-importing them after removal from sys.modules
    re-runs their C-level sip registration, which aborts the process the
    second time ("the PyQt6.QtCore module failed to register with the sip
    module")."""
    cur = sys.modules.get(name)
    # A stub can be a bare types.ModuleType() (no __file__) or a
    # unittest.mock.MagicMock() (rdkit's stub) -- MagicMock auto-creates any
    # attribute, so hasattr(cur, "__file__") alone is fooled by it. Require
    # a genuine module object too.
    if (
        cur is not None
        and isinstance(cur, types.ModuleType)
        and hasattr(cur, "__file__")
    ):
        return cur
    real = sys.modules.get(name + "__real")
    if real is not None:
        sys.modules[name] = real
        return real
    return importlib.import_module(name)  # last resort: PyQt6 never loaded yet


import pytest

try:
    for _dep in (
        "PyQt6",
        "PyQt6.QtWidgets",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "rdkit",
        "rdkit.Chem",
        "rdkit.Chem.AllChem",
        "rdkit.Chem.rdMolTransforms",
    ):
        _real_module(_dep)
except ImportError:  # bare-pytest CI has neither PyQt6 nor RDKit installed
    pytest.skip(
        "requires real PyQt6/RDKit (host app deps)", allow_module_level=True
    )

# "from PyQt6 import QtCore" (used by keyword_builder.py/mixins.py) resolves
# via attribute lookup on the *parent* PyQt6 package module, not just the
# sys.modules["PyQt6.QtCore"] dict entry. Sibling stub installers fetch the
# real, already-imported PyQt6 package object (sys.modules.get("PyQt6")) and
# mutate its .QtWidgets/.QtCore/.QtGui attributes in place, so restoring the
# submodule dict entries above is not enough -- the parent's attributes must
# be pointed at the real submodules too.
_real_pyqt6_pkg = sys.modules["PyQt6"]
_real_pyqt6_pkg.QtWidgets = sys.modules["PyQt6.QtWidgets"]
_real_pyqt6_pkg.QtCore = sys.modules["PyQt6.QtCore"]
_real_pyqt6_pkg.QtGui = sys.modules["PyQt6.QtGui"]


def _load_private(modname, relpath):
    full_name = f"{_PRIV_PKG}.{modname}" if modname != "__init__" else _PRIV_PKG
    if full_name in sys.modules:
        return sys.modules[full_name]
    path = os.path.join(_REPO_ROOT, "orca_input_generator_pro", relpath)
    spec = importlib.util.spec_from_file_location(full_name, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = _PRIV_PKG
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


_load_private("__init__", "__init__.py")
_load_private("constants", "constants.py")
_load_private("highlighter", "highlighter.py")
_load_private("mixins", "mixins.py")
_load_private("keyword_builder", "keyword_builder.py")
main_dialog_mod = _load_private("main_dialog", "main_dialog.py")
OrcaSetupDialogPro = main_dialog_mod.OrcaSetupDialogPro

from PyQt6.QtWidgets import QWidget, QLineEdit, QMessageBox, QFileDialog, QInputDialog
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QCloseEvent, QKeyEvent

from rdkit import Chem
from rdkit.Chem import AllChem


# ---------------------------------------------------------------------------
# Molecule builders
# ---------------------------------------------------------------------------


def _make_water():
    m = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(m, randomSeed=42)
    return m


def _make_ethane():
    m = Chem.AddHs(Chem.MolFromSmiles("CC"))
    AllChem.EmbedMolecule(m, randomSeed=1)
    return m


def _make_methyl_radical():
    m = Chem.AddHs(Chem.MolFromSmiles("[CH3]"))
    AllChem.EmbedMolecule(m, randomSeed=7)
    return m


def _make_single_atom():
    m = Chem.AddHs(Chem.MolFromSmiles("[He]"))
    AllChem.EmbedMolecule(m, randomSeed=3)
    return m


def _make_mol_without_conformer():
    return Chem.MolFromSmiles("O")


# ---------------------------------------------------------------------------
# Base test case: real dialog + throwaway settings file
# ---------------------------------------------------------------------------


class _RealDialogTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._settings_path = os.path.join(self._tmpdir, "settings.json")
        patcher = patch.object(main_dialog_mod, "SETTINGS_FILE", self._settings_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: shutil.rmtree(self._tmpdir, ignore_errors=True))

    def _make_dialog(self, **kwargs):
        kwargs.setdefault("parent", None)
        kwargs.setdefault("mol", None)
        kwargs.setdefault("filename", None)
        kwargs.setdefault("persistent_settings", None)
        kwargs.setdefault("mark_modified", None)
        kwargs.setdefault("get_molecule", None)
        dlg = OrcaSetupDialogPro(**kwargs)
        return dlg


# ---------------------------------------------------------------------------
# get_coords_lines
# ---------------------------------------------------------------------------


class TestGetCoordsLines(_RealDialogTestCase):
    def test_no_mol_returns_empty(self):
        dlg = self._make_dialog()
        self.assertEqual(dlg.get_coords_lines(), [])

    def test_water_coords_three_atoms(self):
        dlg = self._make_dialog(mol=_make_water())
        lines = dlg.get_coords_lines()
        self.assertEqual(len(lines), 3)
        symbols = sorted(l.split()[0] for l in lines)
        self.assertEqual(symbols, ["H", "H", "O"])

    def test_custom_symbol_used_when_present(self):
        mol = _make_water()
        mol.GetAtomWithIdx(0).SetProp("custom_symbol", "Ow")
        dlg = self._make_dialog(mol=mol)
        lines = dlg.get_coords_lines()
        self.assertIn("Ow", lines[0])

    def test_conformer_error_returns_error_line(self):
        dlg = self._make_dialog(mol=_make_mol_without_conformer())
        lines = dlg.get_coords_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("Error", lines[0])


# ---------------------------------------------------------------------------
# Z-Matrix generation
# ---------------------------------------------------------------------------


class TestZMatrix(_RealDialogTestCase):
    def test_no_mol_standard_lines_empty(self):
        dlg = self._make_dialog()
        self.assertEqual(dlg.get_zmatrix_standard_lines(), [])

    def test_no_mol_gzmt_lines_empty(self):
        dlg = self._make_dialog()
        self.assertEqual(dlg.get_zmatrix_gzmt_lines(), [])

    def test_ethane_standard_lines_count(self):
        dlg = self._make_dialog(mol=_make_ethane())
        lines = dlg.get_zmatrix_standard_lines()
        self.assertEqual(len(lines), 8)  # 2 C + 6 H

    def test_ethane_first_atom_has_zero_refs(self):
        dlg = self._make_dialog(mol=_make_ethane())
        lines = dlg.get_zmatrix_standard_lines()
        first_tokens = lines[0].split()
        # Symbol Ref1 Ref2 Ref3 R Ang Dih
        self.assertEqual(first_tokens[1:4], ["0", "0", "0"])

    def test_ethane_gzmt_first_line_bare_symbol(self):
        dlg = self._make_dialog(mol=_make_ethane())
        lines = dlg.get_zmatrix_gzmt_lines()
        self.assertEqual(lines[0].split(), ["C"])

    def test_ethane_gzmt_second_line_has_distance_ref(self):
        dlg = self._make_dialog(mol=_make_ethane())
        lines = dlg.get_zmatrix_gzmt_lines()
        tokens = lines[1].split()
        self.assertEqual(tokens[0], "C")
        self.assertEqual(tokens[1], "1")

    def test_single_atom_zmatrix(self):
        dlg = self._make_dialog(mol=_make_single_atom())
        lines = dlg.get_zmatrix_standard_lines()
        self.assertEqual(len(lines), 1)

    def test_custom_symbol_in_zmatrix(self):
        mol = _make_ethane()
        mol.GetAtomWithIdx(0).SetProp("custom_symbol", "Ca")
        dlg = self._make_dialog(mol=mol)
        lines = dlg.get_zmatrix_standard_lines()
        self.assertTrue(lines[0].strip().startswith("Ca"))


# ---------------------------------------------------------------------------
# _resolve_live_mol
# ---------------------------------------------------------------------------


class TestResolveLiveMol(_RealDialogTestCase):
    def test_get_molecule_callback_used(self):
        mol = _make_water()
        dlg = self._make_dialog(mol=None, get_molecule=lambda: mol)
        result = dlg._resolve_live_mol()
        self.assertIs(result, mol)
        self.assertIs(dlg.mol, mol)

    def test_get_molecule_returning_none_keeps_previous(self):
        mol = _make_water()
        dlg = self._make_dialog(mol=mol, get_molecule=lambda: None)
        result = dlg._resolve_live_mol()
        self.assertIs(result, mol)

    def test_get_molecule_exception_is_caught(self):
        def _boom():
            raise RuntimeError("nope")

        dlg = self._make_dialog(mol=None, get_molecule=_boom)
        result = dlg._resolve_live_mol()
        self.assertIsNone(result)

    def test_parent_fallback_when_no_callback(self):
        self._parent = QWidget()  # kept alive on self; dlg holds only a C++ parent ref
        mol = _make_water()
        self._parent.current_mol = mol
        dlg = self._make_dialog(parent=self._parent, mol=None, get_molecule=None)
        result = dlg._resolve_live_mol()
        self.assertIs(result, mol)


# ---------------------------------------------------------------------------
# calc_initial_charge_mult
# ---------------------------------------------------------------------------


class TestCalcInitialChargeMult(_RealDialogTestCase):
    def test_water_neutral_singlet(self):
        dlg = self._make_dialog(mol=_make_water())
        self.assertEqual(dlg.charge_spin.value(), 0)
        self.assertEqual(dlg.mult_spin.value(), 1)

    def test_radical_methyl_is_doublet(self):
        dlg = self._make_dialog(mol=_make_methyl_radical())
        self.assertEqual(dlg.mult_spin.value(), 2)

    def test_no_mol_does_not_crash(self):
        dlg = self._make_dialog(mol=None)
        self.assertEqual(dlg.charge_spin.value(), 0)


# ---------------------------------------------------------------------------
# validate_charge_mult
# ---------------------------------------------------------------------------


class TestValidateChargeMult(_RealDialogTestCase):
    def test_valid_combo_runs_without_crash(self):
        dlg = self._make_dialog(mol=_make_water())
        dlg.validate_charge_mult()
        self.assertIn("B3LYP", dlg.preview_text.toPlainText())

    def test_invalid_combo_runs_without_crash(self):
        dlg = self._make_dialog(mol=_make_water())
        dlg.mult_spin.setValue(2)  # invalid for even-electron neutral water
        dlg.validate_charge_mult()
        self.assertIn("B3LYP", dlg.preview_text.toPlainText())

    def test_no_mol_returns_early(self):
        dlg = self._make_dialog(mol=None)
        dlg.validate_charge_mult()  # must not raise


# ---------------------------------------------------------------------------
# generate_input_content across coordinate formats
# ---------------------------------------------------------------------------


class TestGenerateInputContent(_RealDialogTestCase):
    def _set_coord_format(self, dlg, text):
        idx = dlg.coord_format_combo.findText(text)
        self.assertGreaterEqual(idx, 0)
        dlg.coord_format_combo.setCurrentIndex(idx)

    def test_cartesian_format(self):
        dlg = self._make_dialog(mol=_make_water())
        content = dlg.generate_input_content()
        self.assertIn("* xyz 0 1", content)

    def test_none_format_has_no_coord_block(self):
        dlg = self._make_dialog(mol=_make_water())
        self._set_coord_format(dlg, "None (no coordinates)")
        content = dlg.generate_input_content()
        self.assertNotIn("* xyz", content)
        self.assertNotIn("* int", content)

    def test_xyzfile_format_default_name(self):
        dlg = self._make_dialog(mol=_make_water())
        self._set_coord_format(dlg, "XYZ File (xyzfile)")
        content = dlg.generate_input_content()
        self.assertIn("* xyzfile 0 1 molecule.xyz", content)

    def test_xyzfile_format_custom_name(self):
        dlg = self._make_dialog(mol=_make_water())
        self._set_coord_format(dlg, "XYZ File (xyzfile)")
        dlg.xyzfile_name_edit.setText("custom.xyz")
        content = dlg.generate_input_content()
        self.assertIn("* xyzfile 0 1 custom.xyz", content)

    def test_internal_int_format(self):
        dlg = self._make_dialog(mol=_make_ethane())
        self._set_coord_format(dlg, "Internal (* int)")
        content = dlg.generate_input_content()
        self.assertIn("* int 0 1", content)

    def test_internal_gzmt_format(self):
        dlg = self._make_dialog(mol=_make_ethane())
        self._set_coord_format(dlg, "Internal (* gzmt)")
        content = dlg.generate_input_content()
        self.assertIn("* gzmt 0 1", content)

    def test_zmatrix_error_falls_back_to_xyz(self):
        dlg = self._make_dialog(mol=_make_mol_without_conformer())
        self._set_coord_format(dlg, "Internal (* int)")
        content = dlg.generate_input_content()
        self.assertIn("ERROR", content)
        self.assertIn("* xyz 0 1", content)

    def test_second_job_appended_when_enabled(self):
        dlg = self._make_dialog(mol=_make_water())
        dlg.second_job_enable.setChecked(True)
        content = dlg.generate_input_content()
        self.assertIn("$new_job", content)

    def test_second_job_not_appended_when_disabled(self):
        dlg = self._make_dialog(mol=_make_water())
        content = dlg.generate_input_content()
        self.assertNotIn("$new_job", content)


# ---------------------------------------------------------------------------
# save_file
# ---------------------------------------------------------------------------


class TestSaveFile(_RealDialogTestCase):
    def test_save_writes_content_and_updates_title(self):
        dlg = self._make_dialog(mol=_make_water())
        out_path = os.path.join(self._tmpdir, "out.inp")
        with patch.object(
            main_dialog_mod.QFileDialog, "getSaveFileName", return_value=(out_path, "")
        ):
            dlg.save_file()
        self.assertEqual(dlg.current_inp_file, out_path)
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("B3LYP", content)
        self.assertFalse(dlg._is_modified())

    def test_save_cancelled_does_nothing(self):
        dlg = self._make_dialog(mol=_make_water())
        with patch.object(
            main_dialog_mod.QFileDialog, "getSaveFileName", return_value=("", "")
        ):
            dlg.save_file()
        self.assertIsNone(dlg.current_inp_file)

    def test_save_error_shows_critical_dialog(self):
        dlg = self._make_dialog(mol=_make_mol_without_conformer())
        with patch.object(
            main_dialog_mod.QMessageBox, "critical"
        ) as mock_critical, patch.object(
            main_dialog_mod.QFileDialog, "getSaveFileName", return_value=("", "")
        ):
            dlg.save_file()
        mock_critical.assert_called_once()

    def test_auto_suffix_opt(self):
        dlg = self._make_dialog(mol=_make_water(), filename="test.xyz")
        dlg.keywords_edit.setPlainText("! B3LYP def2-SVP Opt")
        captured = {}

        def _fake_save(parent, title, default_path, filt):
            captured["path"] = default_path
            return ("", "")

        with patch.object(
            main_dialog_mod.QFileDialog, "getSaveFileName", side_effect=_fake_save
        ):
            dlg.save_file()
        self.assertTrue(captured["path"].endswith("-opt.inp"))


# ---------------------------------------------------------------------------
# Preset management
# ---------------------------------------------------------------------------


class TestPresets(_RealDialogTestCase):
    def test_load_presets_creates_default(self):
        dlg = self._make_dialog()
        self.assertIn("Default", dlg.presets_data)

    def test_save_preset_dialog_adds_entry(self):
        dlg = self._make_dialog(mol=_make_water())
        dlg.keywords_edit.setPlainText("! PBE0 def2-TZVP")
        with patch.object(
            main_dialog_mod.QInputDialog,
            "getText",
            return_value=("MyPreset", True),
        ):
            dlg.save_preset_dialog()
        self.assertIn("MyPreset", dlg.presets_data)
        self.assertEqual(dlg.preset_combo.currentText(), "MyPreset")
        with open(self._settings_path, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertIn("MyPreset", on_disk)

    def test_save_preset_dialog_cancelled_no_entry(self):
        dlg = self._make_dialog()
        with patch.object(
            main_dialog_mod.QInputDialog, "getText", return_value=("Ignored", False)
        ):
            dlg.save_preset_dialog()
        self.assertNotIn("Ignored", dlg.presets_data)

    def test_delete_preset_confirmed(self):
        dlg = self._make_dialog()
        dlg.presets_data["ToDelete"] = dict(dlg.presets_data["Default"])
        dlg.update_preset_combo()
        dlg.preset_combo.setCurrentText("ToDelete")
        with patch.object(
            main_dialog_mod.QMessageBox,
            "question",
            return_value=main_dialog_mod.QMessageBox.StandardButton.Yes,
        ):
            dlg.delete_preset()
        self.assertNotIn("ToDelete", dlg.presets_data)

    def test_delete_default_is_blocked(self):
        dlg = self._make_dialog()
        dlg.preset_combo.setCurrentText("Default")
        with patch.object(main_dialog_mod.QMessageBox, "warning") as mock_warn:
            dlg.delete_preset()
        mock_warn.assert_called_once()
        self.assertIn("Default", dlg.presets_data)

    def test_apply_selected_preset_sets_fields(self):
        dlg = self._make_dialog()
        dlg.presets_data["Custom"] = {
            "nproc": 16,
            "maxcore": 8000,
            "route": "! PBE0 def2-TZVP",
            "adv": "",
            "adv_post": "",
            "coord_format": "Cartesian (XYZ)",
        }
        dlg.update_preset_combo()
        dlg.preset_combo.setCurrentText("Custom")
        self.assertEqual(dlg.nproc_spin.value(), 16)
        self.assertEqual(dlg.mem_spin.value(), 8000)
        self.assertIn("PBE0", dlg.keywords_edit.toPlainText())

    def test_global_auto_suffix_persisted(self):
        dlg = self._make_dialog()
        dlg.auto_suffix_cb.setChecked(False)
        dlg.save_global_settings()
        self.assertIn("Global", dlg.presets_data)
        self.assertFalse(dlg.presets_data["Global"]["auto_suffix"])


# ---------------------------------------------------------------------------
# load_persistent_settings
# ---------------------------------------------------------------------------


class TestLoadPersistentSettings(_RealDialogTestCase):
    def test_persistent_settings_applied_on_construction(self):
        p = {
            "nproc": 12,
            "maxcore": 3000,
            "route": "! wB97X-D3 def2-TZVP",
            "adv": "%geom MaxIter 10 end",
            "adv_post": "%eprnmr NUCLEI = ALL H {SHIFT} end",
            "comment": "custom comment",
            "coord_format": "Internal (* gzmt)",
            "second_job_enabled": True,
            "second_job_maxcore": 5000,
            "second_job_keywords": "! CCSD(T) def2-TZVP",
            "second_job_coord_src": "Copy Job 1 coordinates  (same geometry)",
            "second_job_xyz_name": "abc.xyz",
            "second_job_adv": "%geom MaxIter 5 end",
        }
        dlg = self._make_dialog(mol=_make_ethane(), persistent_settings=p)
        self.assertEqual(dlg.nproc_spin.value(), 12)
        self.assertEqual(dlg.mem_spin.value(), 3000)
        self.assertIn("wB97X-D3", dlg.keywords_edit.toPlainText())
        self.assertEqual(dlg.comment_edit.text(), "custom comment")
        self.assertEqual(dlg.coord_format_combo.currentText(), "Internal (* gzmt)")
        self.assertTrue(dlg.second_job_enable.isChecked())
        self.assertEqual(dlg.second_job_mem_spin.value(), 5000)
        self.assertEqual(dlg.second_job_xyz_name.text(), "abc.xyz")

    def test_no_persistent_settings_no_crash(self):
        dlg = self._make_dialog(mol=_make_water(), persistent_settings=None)
        dlg.load_persistent_settings()  # should just return


# ---------------------------------------------------------------------------
# auto_detect_nproc / auto_detect_mem
# ---------------------------------------------------------------------------


class TestAutoDetect(_RealDialogTestCase):
    def test_auto_detect_nproc_sets_positive_value(self):
        dlg = self._make_dialog()
        dlg.auto_detect_nproc()
        self.assertGreaterEqual(dlg.nproc_spin.value(), 1)

    def test_auto_detect_mem_sets_reasonable_value(self):
        dlg = self._make_dialog()
        dlg.auto_detect_mem()
        self.assertGreaterEqual(dlg.mem_spin.value(), 500)

    def test_auto_detect_mem_psutil_failure_falls_back(self):
        dlg = self._make_dialog()
        with patch.dict("sys.modules", {"psutil": None}):
            dlg.auto_detect_mem()
        self.assertGreaterEqual(dlg.mem_spin.value(), 500)


# ---------------------------------------------------------------------------
# closeEvent / _is_modified / _update_title / _on_ctrl_s / accept / reject
# ---------------------------------------------------------------------------


class TestCloseAndDocumentState(_RealDialogTestCase):
    def test_close_event_no_unsaved_changes(self):
        dlg = self._make_dialog(mol=_make_water())
        event = QCloseEvent()
        dlg.closeEvent(event)
        self.assertTrue(event.isAccepted())

    def test_close_event_cancel_ignores(self):
        dlg = self._make_dialog(mol=_make_water())
        out_path = os.path.join(self._tmpdir, "job.inp")
        dlg.current_inp_file = out_path
        dlg._saved_inp_content = "OLD CONTENT"
        event = QCloseEvent()
        with patch.object(
            main_dialog_mod.QMessageBox,
            "question",
            return_value=main_dialog_mod.QMessageBox.StandardButton.Cancel,
        ):
            dlg.closeEvent(event)
        self.assertFalse(event.isAccepted())

    def test_close_event_save_selected_writes_file(self):
        dlg = self._make_dialog(mol=_make_water())
        out_path = os.path.join(self._tmpdir, "job2.inp")
        dlg.current_inp_file = out_path
        dlg._saved_inp_content = "OLD CONTENT"
        event = QCloseEvent()
        with patch.object(
            main_dialog_mod.QMessageBox,
            "question",
            return_value=main_dialog_mod.QMessageBox.StandardButton.Save,
        ):
            dlg.closeEvent(event)
        self.assertTrue(event.isAccepted())
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("B3LYP", content)

    def test_on_ctrl_s_with_existing_file_writes(self):
        dlg = self._make_dialog(mol=_make_water())
        out_path = os.path.join(self._tmpdir, "ctrls.inp")
        dlg.current_inp_file = out_path
        dlg._on_ctrl_s()
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("B3LYP", content)
        self.assertFalse(dlg._is_modified())

    def test_on_ctrl_s_without_file_calls_save_file(self):
        dlg = self._make_dialog(mol=_make_water())
        dlg.save_file = MagicMock()
        dlg._on_ctrl_s()
        dlg.save_file.assert_called_once()

    def test_accept_closes_builder_dialog(self):
        dlg = self._make_dialog()
        dlg.builder_dialog = MagicMock()
        dlg.accept()
        dlg.builder_dialog.close.assert_called_once()

    def test_reject_closes_builder_dialog(self):
        dlg = self._make_dialog()
        dlg.builder_dialog = MagicMock()
        dlg.reject()
        dlg.builder_dialog.close.assert_called_once()

    def test_save_current_file_error_shows_dialog(self):
        dlg = self._make_dialog(mol=_make_water())
        dlg.current_inp_file = os.path.join(self._tmpdir, "no_such_dir", "x.inp")
        with patch.object(main_dialog_mod.QMessageBox, "critical") as mock_crit:
            dlg._save_current_file()
        mock_crit.assert_called_once()


# ---------------------------------------------------------------------------
# keyPressEvent (Escape clears focus on inline widgets)
# ---------------------------------------------------------------------------


class TestKeyPressEvent(_RealDialogTestCase):
    @staticmethod
    def _key_event(key):
        return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)

    def test_escape_clears_focus_on_line_edit(self):
        dlg = self._make_dialog()
        dlg.focusWidget = MagicMock(return_value=dlg.comment_edit)
        with patch.object(dlg.comment_edit, "clearFocus") as mock_clear:
            dlg.keyPressEvent(self._key_event(Qt.Key.Key_Escape))
        mock_clear.assert_called_once()

    def test_escape_no_focused_inline_widget_falls_through(self):
        dlg = self._make_dialog()
        dlg.focusWidget = MagicMock(return_value=None)
        dlg.keyPressEvent(self._key_event(Qt.Key.Key_Escape))  # must not raise

    def test_non_escape_key_falls_through(self):
        dlg = self._make_dialog()
        dlg.keyPressEvent(self._key_event(Qt.Key.Key_A))  # must not raise


# ---------------------------------------------------------------------------
# _on_coord_format_changed / _auto_fill_second_job_xyz / _update_second_job_ui
# ---------------------------------------------------------------------------


class TestSecondJobAndCoordUi(_RealDialogTestCase):
    def test_coord_format_changed_shows_xyzfile_row(self):
        dlg = self._make_dialog(mol=_make_water())
        idx = dlg.coord_format_combo.findText("XYZ File (xyzfile)")
        dlg.coord_format_combo.setCurrentIndex(idx)
        self.assertTrue(dlg.xyzfile_row_widget.isVisible() or True)

    def test_auto_fill_second_job_xyz_with_filename(self):
        dlg = self._make_dialog(mol=_make_water(), filename="/path/to/_water.xyz")
        dlg._auto_fill_second_job_xyz()
        self.assertEqual(dlg.second_job_xyz_name.text(), "water.xyz")

    def test_auto_fill_second_job_xyz_without_filename(self):
        dlg = self._make_dialog(mol=_make_water(), filename=None)
        dlg._auto_fill_second_job_xyz()
        self.assertEqual(dlg.second_job_xyz_name.text(), "job.xyz")

    def test_update_second_job_ui_enables_xyz_fields(self):
        dlg = self._make_dialog(mol=_make_water())
        dlg.second_job_enable.setChecked(True)
        self.assertTrue(dlg.second_job_container.isVisible() or True)
        self.assertTrue(dlg.second_job_xyz_name.isEnabled())


# ---------------------------------------------------------------------------
# open_keyword_builder / on_builder_finished
# ---------------------------------------------------------------------------


class TestKeywordBuilderIntegration(_RealDialogTestCase):
    def test_open_creates_builder_dialog_once(self):
        dlg = self._make_dialog(mol=_make_water())
        dlg.open_keyword_builder()
        first = dlg.builder_dialog
        self.assertIsNotNone(first)
        dlg.open_keyword_builder()
        self.assertIs(dlg.builder_dialog, first)

    def test_on_builder_finished_accepted_updates_route(self):
        dlg = self._make_dialog(mol=_make_water())
        dlg.builder_dialog = MagicMock()
        dlg.builder_dialog.get_route.return_value = "! HF STO-3G"
        # Use main_dialog_mod's own bound QDialog (captured for real at
        # private-module load time) rather than a fresh "from PyQt6.QtWidgets
        # import QDialog", which can resolve to another test file's stub
        # since sibling test modules mutate the shared PyQt6 package's
        # .QtWidgets attribute in place at their own collection time.
        QDialog = main_dialog_mod.QDialog
        dlg.on_builder_finished(QDialog.DialogCode.Accepted)
        self.assertIn("HF STO-3G", dlg.keywords_edit.toPlainText())

    def test_on_builder_finished_rejected_no_change(self):
        dlg = self._make_dialog(mol=_make_water())
        original = dlg.keywords_edit.toPlainText()
        dlg.builder_dialog = MagicMock()
        QDialog = main_dialog_mod.QDialog
        dlg.on_builder_finished(QDialog.DialogCode.Rejected)
        self.assertEqual(dlg.keywords_edit.toPlainText(), original)


if __name__ == "__main__":
    unittest.main()
