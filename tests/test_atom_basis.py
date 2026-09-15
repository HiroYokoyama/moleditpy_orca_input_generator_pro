"""
tests/test_atom_basis.py

Per-atom basis overrides on ORCA coordinate lines.

A ghost ("El:") means three different things -- counterpoise wants the
element's full basis, a NICS probe wants none, midbond functions want a
specific one -- and the molecule does not say which, so the treatment is
chosen per symbol in the Per-atom Basis box, which lists every species.

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
DEFAULT = _const.BASIS_MODE_DEFAULT
NICS = _const.BASIS_MODE_BARE
CUSTOM = _const.BASIS_MODE_CUSTOM


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
    d.atom_basis = {}
    d._basis_symbols_shown = None
    return d


def _molecule_with_probe():
    atoms = [_Atom("C"), _Atom("O"), _Atom("*", "H:")]
    positions = [_Pos(0.0, 0.0, 0.0), _Pos(1.0, 0.0, 0.0), _Pos(0.0, 0.0, 1.0)]
    return _Mol(atoms, positions)


class TestSymbolScan(unittest.TestCase):
    def test_every_species_is_listed_not_only_ghosts(self):
        mol = _Mol(
            [_Atom("C"), _Atom("*", "H:"), _Atom("*", "Bq"), _Atom("C", "C:")],
            [_Pos(0, 0, 0)] * 4,
        )
        self.assertEqual(
            _dialog(mol)._atom_symbols(), {"C": 1, "H:": 1, "Bq": 1, "C:": 1}
        )

    def test_symbols_are_counted(self):
        mol = _Mol([_Atom("*", "H:") for _ in range(5)], [_Pos(0, 0, 0)] * 5)
        self.assertEqual(_dialog(mol)._atom_symbols(), {"H:": 5})

    def test_plain_molecule_lists_its_elements(self):
        mol = _Mol([_Atom("C"), _Atom("H")], [_Pos(0, 0, 0)] * 2)
        self.assertEqual(_dialog(mol)._atom_symbols(), {"C": 1, "H": 1})

    def test_only_a_trailing_colon_marks_a_ghost(self):
        d = _dialog(_molecule_with_probe())
        self.assertTrue(d._is_ghost("H:"))
        self.assertFalse(d._is_ghost("Bq"))
        self.assertFalse(d._is_ghost("C"))

    def test_ghosts_sort_ahead_of_real_elements(self):
        d = _dialog(_molecule_with_probe())
        order = sorted(["O", "C", "H:", "C:"], key=d._sort_key)
        self.assertEqual(order, ["C:", "H:", "C", "O"])


class TestCoordinateLines(unittest.TestCase):
    def test_default_leaves_the_line_untouched(self):
        lines = _dialog(_molecule_with_probe()).get_coords_lines()
        self.assertEqual(len(lines), 3)
        self.assertNotIn("NewGTO", lines[2])
        self.assertTrue(lines[2].strip().startswith("H:"))

    def test_bare_appends_the_manual_recipe(self):
        d = _dialog(_molecule_with_probe())
        d.atom_basis = {"H:": (NICS, "")}
        lines = d.get_coords_lines()
        self.assertTrue(lines[2].endswith(BARE))
        self.assertIn("NewAuxJGTO", lines[2])

    def test_bare_does_not_touch_real_atoms(self):
        d = _dialog(_molecule_with_probe())
        d.atom_basis = {"H:": (NICS, "")}
        lines = d.get_coords_lines()
        self.assertNotIn("NewGTO", lines[0])
        self.assertNotIn("NewGTO", lines[1])

    def test_counterpoise_ghost_keeps_its_basis(self):
        """A C: ghost left on Full must stay exactly as it is today."""
        mol = _Mol([_Atom("C", "C:"), _Atom("O")], [_Pos(0, 0, 0), _Pos(1, 0, 0)])
        d = _dialog(mol)
        d.atom_basis = {"C:": (DEFAULT, "")}
        self.assertNotIn("NewGTO", d.get_coords_lines()[0])

    def test_symbols_are_treated_independently(self):
        """NICS probes bare, counterpoise ghosts untouched, in one molecule."""
        mol = _Mol([_Atom("*", "H:"), _Atom("C", "C:")], [_Pos(0, 0, 0), _Pos(1, 0, 0)])
        d = _dialog(mol)
        d.atom_basis = {"H:": (NICS, ""), "C:": (DEFAULT, "")}
        lines = d.get_coords_lines()
        self.assertIn("NewGTO", lines[0])
        self.assertNotIn("NewGTO", lines[1])

    def test_custom_text_is_passed_through_verbatim(self):
        d = _dialog(_molecule_with_probe())
        d.atom_basis = {"H:": (CUSTOM, "NewGTO S 1 1 0.05 1 end")}
        self.assertTrue(d.get_coords_lines()[2].endswith("NewGTO S 1 1 0.05 1 end"))

    def test_blank_custom_falls_back_to_the_default(self):
        d = _dialog(_molecule_with_probe())
        d.atom_basis = {"H:": (CUSTOM, "   ")}
        self.assertNotIn("NewGTO", d.get_coords_lines()[2])


class TestSuffixHelper(unittest.TestCase):
    def test_unknown_symbol_is_full_basis(self):
        self.assertEqual(_dialog(_molecule_with_probe())._basis_suffix("Xx:"), "")

    def test_basis_needs_xyz_only_when_an_override_is_active(self):
        d = _dialog(_molecule_with_probe())
        self.assertFalse(d._basis_needs_xyz())
        d.atom_basis = {"H:": (DEFAULT, "")}
        self.assertFalse(d._basis_needs_xyz())
        d.atom_basis = {"H:": (NICS, "")}
        self.assertTrue(d._basis_needs_xyz())


class TestRestore(unittest.TestCase):
    def test_round_trip(self):
        d = _dialog(_molecule_with_probe())
        d._restore_atom_basis({"H:": [NICS, ""], "C:": [CUSTOM, "NewGTO ... end"]})
        self.assertEqual(d.atom_basis["H:"], (NICS, ""))
        self.assertEqual(d.atom_basis["C:"], (CUSTOM, "NewGTO ... end"))

    def test_unknown_mode_is_dropped(self):
        d = _dialog(_molecule_with_probe())
        d._restore_atom_basis({"H:": ["Nonsense", ""], "C:": [NICS, ""]})
        self.assertNotIn("H:", d.atom_basis)
        self.assertIn("C:", d.atom_basis)

    def test_malformed_payload_is_ignored_not_raised(self):
        d = _dialog(_molecule_with_probe())
        d.atom_basis = {"H:": (NICS, "")}
        d._restore_atom_basis("not a mapping")
        self.assertEqual(d.atom_basis, {"H:": (NICS, "")})

    def test_empty_payload_clears(self):
        d = _dialog(_molecule_with_probe())
        d.atom_basis = {"H:": (NICS, "")}
        d._restore_atom_basis({})
        self.assertEqual(d.atom_basis, {})


class TestRealElementOverrides(unittest.TestCase):
    def test_custom_basis_on_a_real_element(self):
        """The point of generalising: give one element a bigger basis."""
        d = _dialog(_molecule_with_probe())
        d.atom_basis = {"O": (CUSTOM, 'NewGTO "def2-TZVP" end')}
        lines = d.get_coords_lines()
        self.assertTrue(lines[1].endswith('NewGTO "def2-TZVP" end'))
        self.assertNotIn("NewGTO", lines[0])
        self.assertNotIn("NewGTO", lines[2])

    def test_bare_is_ignored_on_a_real_element(self):
        """A real atom with no basis is nonsense; Bare must not reach it."""
        d = _dialog(_molecule_with_probe())
        d.atom_basis = {"C": (NICS, "")}
        self.assertEqual(d._basis_suffix("C"), "")
        self.assertNotIn("NewGTO", d.get_coords_lines()[0])

    def test_real_and_ghost_overrides_coexist(self):
        d = _dialog(_molecule_with_probe())
        d.atom_basis = {
            "H:": (NICS, ""),
            "O": (CUSTOM, 'NewGTO "def2-TZVP" end'),
        }
        lines = d.get_coords_lines()
        self.assertNotIn("NewGTO", lines[0])
        self.assertTrue(lines[1].endswith('NewGTO "def2-TZVP" end'))
        self.assertTrue(lines[2].endswith(BARE))


class TestLegacySettings(unittest.TestCase):
    def test_v380_full_basis_label_still_loads(self):
        """3.8.0 persisted 'Full basis (default)'; it must not be dropped."""
        d = _dialog(_molecule_with_probe())
        d._restore_atom_basis({"H:": ["Full basis (default)", ""]})
        self.assertEqual(d.atom_basis["H:"], (DEFAULT, ""))
        self.assertEqual(d._basis_suffix("H:"), "")


if __name__ == "__main__":
    unittest.main()
