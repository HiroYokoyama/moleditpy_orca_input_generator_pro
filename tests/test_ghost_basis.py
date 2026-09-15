"""
tests/test_ghost_basis.py

Per-atom ghost basis on ORCA coordinate lines.

A ghost ("El:") means three different things -- counterpoise wants the
element's full basis, a NICS probe wants none, midbond functions want a
specific one -- and the molecule does not say which, so the treatment is
chosen per ghost symbol in the Ghost Atoms box.

Requested in HiroYokoyama/moleditpy_nics_placer#1.
"""

import os
import sys
import types
import importlib.util
import unittest
from unittest.mock import MagicMock

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


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
        "QHeaderView",
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


_const = _load_mod("constants", "constants.py")
_main = _load_mod("main_dialog", "main_dialog.py")
Dialog = _main.OrcaSetupDialogPro

BARE = _const.GHOST_BARE_BASIS
FULL = _const.GHOST_MODE_FULL
NICS = _const.GHOST_MODE_BARE
CUSTOM = _const.GHOST_MODE_CUSTOM


class _Pos:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class _Atom:
    def __init__(self, symbol, custom=None):
        self._symbol = symbol
        self._custom = custom

    def HasProp(self, key):
        return key == "custom_symbol" and self._custom is not None

    def GetProp(self, key):
        return self._custom

    def GetSymbol(self):
        return self._symbol


class _Conf:
    def __init__(self, positions):
        self._positions = positions

    def GetAtomPosition(self, i):
        return self._positions[i]


class _Mol:
    """Just enough RDKit surface for get_coords_lines and the ghost scan."""

    def __init__(self, atoms, positions):
        self._atoms = atoms
        self._conf = _Conf(positions)

    def GetNumAtoms(self):
        return len(self._atoms)

    def GetAtomWithIdx(self, i):
        return self._atoms[i]

    def GetAtoms(self):
        return list(self._atoms)

    def GetConformer(self):
        return self._conf


def _dialog(mol):
    """A bare object carrying only what the ghost code path touches."""
    d = Dialog.__new__(Dialog)
    d.mol = mol
    d.get_molecule = None
    d.ghost_basis = {}
    d._ghost_symbols_shown = None
    return d


def _molecule_with_probe():
    atoms = [_Atom("C"), _Atom("O"), _Atom("*", "H:")]
    positions = [_Pos(0.0, 0.0, 0.0), _Pos(1.0, 0.0, 0.0), _Pos(0.0, 0.0, 1.0)]
    return _Mol(atoms, positions)


class TestGhostDetection(unittest.TestCase):
    def test_only_colon_symbols_count_as_ghosts(self):
        mol = _Mol(
            [_Atom("C"), _Atom("*", "H:"), _Atom("*", "Bq"), _Atom("C", "C:")],
            [_Pos(0, 0, 0)] * 4,
        )
        self.assertEqual(_dialog(mol)._ghost_symbols(), {"H:": 1, "C:": 1})

    def test_ghosts_are_counted_per_symbol(self):
        mol = _Mol([_Atom("*", "H:") for _ in range(5)], [_Pos(0, 0, 0)] * 5)
        self.assertEqual(_dialog(mol)._ghost_symbols(), {"H:": 5})

    def test_molecule_without_ghosts_reports_none(self):
        mol = _Mol([_Atom("C"), _Atom("H")], [_Pos(0, 0, 0)] * 2)
        self.assertEqual(_dialog(mol)._ghost_symbols(), {})


class TestCoordinateLines(unittest.TestCase):
    def test_default_leaves_the_line_untouched(self):
        lines = _dialog(_molecule_with_probe()).get_coords_lines()
        self.assertEqual(len(lines), 3)
        self.assertNotIn("NewGTO", lines[2])
        self.assertTrue(lines[2].strip().startswith("H:"))

    def test_bare_appends_the_manual_recipe(self):
        d = _dialog(_molecule_with_probe())
        d.ghost_basis = {"H:": (NICS, "")}
        lines = d.get_coords_lines()
        self.assertTrue(lines[2].endswith(BARE))
        self.assertIn("NewAuxJGTO", lines[2])

    def test_bare_does_not_touch_real_atoms(self):
        d = _dialog(_molecule_with_probe())
        d.ghost_basis = {"H:": (NICS, "")}
        lines = d.get_coords_lines()
        self.assertNotIn("NewGTO", lines[0])
        self.assertNotIn("NewGTO", lines[1])

    def test_counterpoise_ghost_keeps_its_basis(self):
        """A C: ghost left on Full must stay exactly as it is today."""
        mol = _Mol([_Atom("C", "C:"), _Atom("O")], [_Pos(0, 0, 0), _Pos(1, 0, 0)])
        d = _dialog(mol)
        d.ghost_basis = {"C:": (FULL, "")}
        self.assertNotIn("NewGTO", d.get_coords_lines()[0])

    def test_symbols_are_treated_independently(self):
        """NICS probes bare, counterpoise ghosts untouched, in one molecule."""
        mol = _Mol([_Atom("*", "H:"), _Atom("C", "C:")], [_Pos(0, 0, 0), _Pos(1, 0, 0)])
        d = _dialog(mol)
        d.ghost_basis = {"H:": (NICS, ""), "C:": (FULL, "")}
        lines = d.get_coords_lines()
        self.assertIn("NewGTO", lines[0])
        self.assertNotIn("NewGTO", lines[1])

    def test_custom_text_is_passed_through_verbatim(self):
        d = _dialog(_molecule_with_probe())
        d.ghost_basis = {"H:": (CUSTOM, "NewGTO S 1 1 0.05 1 end")}
        self.assertTrue(d.get_coords_lines()[2].endswith("NewGTO S 1 1 0.05 1 end"))

    def test_blank_custom_falls_back_to_the_default(self):
        d = _dialog(_molecule_with_probe())
        d.ghost_basis = {"H:": (CUSTOM, "   ")}
        self.assertNotIn("NewGTO", d.get_coords_lines()[2])


class TestSuffixHelper(unittest.TestCase):
    def test_unknown_symbol_is_full_basis(self):
        self.assertEqual(_dialog(_molecule_with_probe())._ghost_suffix("Xx:"), "")

    def test_ghosts_need_xyz_only_when_an_override_is_active(self):
        d = _dialog(_molecule_with_probe())
        self.assertFalse(d._ghosts_need_xyz())
        d.ghost_basis = {"H:": (FULL, "")}
        self.assertFalse(d._ghosts_need_xyz())
        d.ghost_basis = {"H:": (NICS, "")}
        self.assertTrue(d._ghosts_need_xyz())


class TestRestore(unittest.TestCase):
    def test_round_trip(self):
        d = _dialog(_molecule_with_probe())
        d._restore_ghost_basis({"H:": [NICS, ""], "C:": [CUSTOM, "NewGTO ... end"]})
        self.assertEqual(d.ghost_basis["H:"], (NICS, ""))
        self.assertEqual(d.ghost_basis["C:"], (CUSTOM, "NewGTO ... end"))

    def test_unknown_mode_is_dropped(self):
        d = _dialog(_molecule_with_probe())
        d._restore_ghost_basis({"H:": ["Nonsense", ""], "C:": [NICS, ""]})
        self.assertNotIn("H:", d.ghost_basis)
        self.assertIn("C:", d.ghost_basis)

    def test_malformed_payload_is_ignored_not_raised(self):
        d = _dialog(_molecule_with_probe())
        d.ghost_basis = {"H:": (NICS, "")}
        d._restore_ghost_basis("not a mapping")
        self.assertEqual(d.ghost_basis, {"H:": (NICS, "")})

    def test_empty_payload_clears(self):
        d = _dialog(_molecule_with_probe())
        d.ghost_basis = {"H:": (NICS, "")}
        d._restore_ghost_basis({})
        self.assertEqual(d.ghost_basis, {})


if __name__ == "__main__":
    unittest.main()


class TestBulkApply(unittest.TestCase):
    def _dialog_with_two_symbols(self):
        d = _dialog(_molecule_with_probe())
        d._ghost_symbols_shown = {"H:": 200, "C:": 3}
        d._populate_ghost_table = lambda counts: None
        d.update_preview = lambda: None
        return d

    def test_all_bare_hits_every_symbol(self):
        d = self._dialog_with_two_symbols()
        d._set_all_ghost_modes(NICS)
        self.assertEqual(d.ghost_basis["H:"][0], NICS)
        self.assertEqual(d.ghost_basis["C:"][0], NICS)

    def test_all_full_restores_the_default(self):
        d = self._dialog_with_two_symbols()
        d.ghost_basis = {"H:": (NICS, ""), "C:": (NICS, "")}
        d._set_all_ghost_modes(FULL)
        self.assertEqual(d._ghost_suffix("H:"), "")
        self.assertEqual(d._ghost_suffix("C:"), "")

    def test_custom_text_survives_a_bulk_switch(self):
        """Flipping to Bare and back must not discard what the user typed."""
        d = self._dialog_with_two_symbols()
        d.ghost_basis = {"H:": (CUSTOM, "NewGTO S 1 1 0.05 1 end")}
        d._set_all_ghost_modes(NICS)
        d._set_all_ghost_modes(CUSTOM)
        self.assertEqual(d.ghost_basis["H:"][1], "NewGTO S 1 1 0.05 1 end")

    def test_bulk_apply_with_no_ghosts_is_a_noop(self):
        d = _dialog(_molecule_with_probe())
        d._ghost_symbols_shown = None
        d._populate_ghost_table = lambda counts: None
        d.update_preview = lambda: None
        d._set_all_ghost_modes(NICS)
        self.assertEqual(d.ghost_basis, {})
