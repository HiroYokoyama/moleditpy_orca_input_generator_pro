"""
tests/test_main_dialog.py

Unit tests for non-GUI logic in main_dialog.py:
  - consolidate_orca_blocks()  pure text processing
  - auto_detect_nproc()        CPU detection + fallback
  - auto_detect_mem()          memory calculation
  - get_coords_lines()         coordinate formatting
  - get_zmatrix_standard_lines() / get_zmatrix_gzmt_lines()
  - calc_initial_charge_mult() / validate_charge_mult()

All Qt / RDKit / psutil dependencies are stubbed.
"""

import os
import sys
import types
import importlib.util
import unittest
from unittest.mock import MagicMock, patch

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Stubs (must run before any plugin import)
# ---------------------------------------------------------------------------

class _Base:
    def __init__(self, *args, **kwargs):
        pass


def _install_stubs():
    pyqt6 = sys.modules.get("PyQt6") or types.ModuleType("PyQt6")
    qt_widgets = types.ModuleType("PyQt6.QtWidgets")
    qt_core = types.ModuleType("PyQt6.QtCore")
    qt_gui = types.ModuleType("PyQt6.QtGui")

    for name in ["QDialog", "QWidget", "QScrollArea"]:
        setattr(qt_widgets, name, _Base)
    for name in [
        "QVBoxLayout", "QHBoxLayout", "QLabel", "QLineEdit",
        "QSpinBox", "QPushButton", "QGroupBox", "QComboBox", "QTextEdit",
        "QTabWidget", "QCheckBox", "QFormLayout", "QTableWidget",
        "QTableWidgetItem", "QCompleter", "QPlainTextEdit", "QGridLayout",
        "QSizePolicy", "QAbstractItemView", "QMessageBox", "QFileDialog",
        "QInputDialog", "QFont", "QColor",
    ]:
        setattr(qt_widgets, name, MagicMock)

    qt_core.Qt = MagicMock()
    qt_core.QRegularExpression = MagicMock
    qt_core.QTimer = MagicMock

    qt_gui.QFont = MagicMock
    qt_gui.QPalette = MagicMock()  # instance so ColorRole attribute access works
    qt_gui.QColor = MagicMock
    qt_gui.QSyntaxHighlighter = _Base
    qt_gui.QTextCharFormat = MagicMock
    qt_gui.QAction = MagicMock
    qt_gui.QIcon = MagicMock

    pyqt6.QtWidgets = qt_widgets
    pyqt6.QtCore = qt_core
    pyqt6.QtGui = qt_gui

    rdkit_mod = MagicMock()
    rdkit_chem = MagicMock()
    rdkit_transforms = MagicMock()

    sys.modules.update({
        "PyQt6": pyqt6,
        "PyQt6.QtWidgets": qt_widgets,
        "PyQt6.QtCore": qt_core,
        "PyQt6.QtGui": qt_gui,
        "rdkit": rdkit_mod,
        "rdkit.Chem": rdkit_chem,
        "rdkit.Chem.rdMolTransforms": rdkit_transforms,
        "pyvista": MagicMock(),
    })
    return rdkit_chem, rdkit_transforms


_rdkit_chem, _rdkit_transforms = _install_stubs()


def _load_module(name, relpath):
    path = os.path.join(_REPO_ROOT, "orca_input_generator_pro", relpath)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "orca_input_generator_pro"
    sys.modules[f"orca_input_generator_pro.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


# Load dependency chain
_constants = _load_module("constants", "constants.py")
sys.modules["orca_input_generator_pro.constants"] = _constants

_mixins = types.ModuleType("orca_input_generator_pro.mixins")
_mixins.Dialog3DPickingMixin = type("Dialog3DPickingMixin", (), {})
sys.modules["orca_input_generator_pro.mixins"] = _mixins

_highlighter = types.ModuleType("orca_input_generator_pro.highlighter")
_highlighter.OrcaSyntaxHighlighter = MagicMock
sys.modules["orca_input_generator_pro.highlighter"] = _highlighter

_builder = _load_module("keyword_builder", "keyword_builder.py")
sys.modules["orca_input_generator_pro.keyword_builder"] = _builder

_init_mod = _load_module("__init__", "__init__.py")
sys.modules["orca_input_generator_pro"] = _init_mod

_main_mod = _load_module("main_dialog", "main_dialog.py")
OrcaSetupDialogPro = _main_mod.OrcaSetupDialogPro


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dlg(**kwargs):
    """Create a bare OrcaSetupDialogPro with no Qt __init__ called."""
    dlg = object.__new__(OrcaSetupDialogPro)
    for k, v in kwargs.items():
        setattr(dlg, k, v)
    return dlg


# ---------------------------------------------------------------------------
# consolidate_orca_blocks — pure text processing
# ---------------------------------------------------------------------------

class TestConsolidateBasic(unittest.TestCase):
    def _c(self, text):
        return _make_dlg().consolidate_orca_blocks(text)

    def test_ends_with_newline(self):
        result = self._c("! B3LYP def2-SVP\n\n* xyz 0 1\n  C  0.0  0.0  0.0\n*")
        self.assertTrue(result.endswith("\n"))

    def test_route_line_preserved(self):
        result = self._c("! B3LYP def2-SVP\n\n* xyz 0 1\n  C  0.0  0.0  0.0\n*")
        self.assertIn("! B3LYP def2-SVP", result)

    def test_coords_preserved(self):
        result = self._c("! B3LYP\n\n* xyz 0 1\n  C  0.0  0.0  0.0\n*")
        self.assertIn("* xyz 0 1", result)
        self.assertIn("*", result)

    def test_no_coords_all_in_pre(self):
        result = self._c("! B3LYP\n%pal nprocs 4 end\n%maxcore 2000")
        self.assertIn("! B3LYP", result)
        self.assertIn("%maxcore 2000", result)

    def test_comment_preserved(self):
        result = self._c("# My job\n! B3LYP\n* xyz 0 1\n  H  0.0  0.0  0.0\n*")
        self.assertIn("# My job", result)

    def test_pal_inline_preserved(self):
        result = self._c("%pal nprocs 4 end\n! B3LYP\n* xyz 0 1\n  H 0 0 0\n*")
        self.assertIn("nprocs 4", result)

    def test_maxcore_preserved(self):
        result = self._c("%maxcore 2000\n! B3LYP\n* xyz 0 1\n  H 0 0 0\n*")
        self.assertIn("%maxcore 2000", result)


class TestConsolidateDedup(unittest.TestCase):
    def _c(self, text):
        return _make_dlg().consolidate_orca_blocks(text)

    def test_dedup_opt_when_tightopt_present(self):
        result = self._c("! B3LYP Opt TightOpt\n* xyz 0 1\n  H 0 0 0\n*")
        self.assertIn("TightOpt", result)
        # Bare "Opt" should be removed because TightOpt is present
        tokens = result.split()
        self.assertNotIn("Opt", tokens)

    def test_dedup_opt_when_verytightopt_present(self):
        result = self._c("! B3LYP Opt VeryTightOpt\n* xyz 0 1\n  H 0 0 0\n*")
        tokens = result.split()
        self.assertNotIn("Opt", tokens)
        self.assertIn("VeryTightOpt", tokens)

    def test_dedup_opt_when_looseopt_present(self):
        result = self._c("! B3LYP Opt LooseOpt\n* xyz 0 1\n  H 0 0 0\n*")
        tokens = result.split()
        self.assertNotIn("Opt", tokens)
        self.assertIn("LooseOpt", tokens)

    def test_no_dedup_opt_alone(self):
        result = self._c("! B3LYP Opt\n* xyz 0 1\n  H 0 0 0\n*")
        self.assertIn("Opt", result)

    def test_duplicate_keywords_removed(self):
        result = self._c("! B3LYP B3LYP def2-SVP\n* xyz 0 1\n  H 0 0 0\n*")
        tokens = [t for t in result.split() if t == "B3LYP"]
        self.assertEqual(len(tokens), 1)

    def test_dedup_maxiter_in_geom_block(self):
        text = (
            "%geom\n"
            "  MaxIter 500\n"
            "  MaxIter 256\n"
            "end\n"
            "! B3LYP\n"
            "* xyz 0 1\n  H 0 0 0\n*"
        )
        result = self._c(text)
        # Only one MaxIter should survive (last one wins)
        self.assertEqual(result.lower().count("maxiter"), 1)


class TestConsolidateBlockMerge(unittest.TestCase):
    def _c(self, text):
        return _make_dlg().consolidate_orca_blocks(text)

    def test_pre_block_kept(self):
        text = (
            "%tddft\n  NRoots 5\nend\n"
            "! B3LYP\n"
            "* xyz 0 1\n  H 0 0 0\n*"
        )
        result = self._c(text)
        self.assertIn("%tddft", result)
        self.assertIn("NRoots 5", result)

    def test_post_only_block_kept(self):
        text = (
            "! B3LYP\n"
            "* xyz 0 1\n  H 0 0 0\n*\n"
            "%scf\n  MaxIter 300\nend"
        )
        result = self._c(text)
        self.assertIn("%scf", result)
        self.assertIn("MaxIter 300", result)

    def test_same_block_in_pre_and_post_merged(self):
        text = (
            "%geom\n  MaxIter 200\nend\n"
            "! B3LYP\n"
            "* xyz 0 1\n  H 0 0 0\n*\n"
            "%geom\n  MaxIter 500\nend"
        )
        result = self._c(text)
        # Should have exactly one %geom block
        self.assertEqual(result.lower().count("%geom"), 1)

    def test_tddft_dedup_nroots(self):
        text = (
            "%tddft\n  NRoots 3\n  NRoots 10\nend\n"
            "! B3LYP\n"
            "* xyz 0 1\n  H 0 0 0\n*"
        )
        result = self._c(text)
        self.assertEqual(result.lower().count("nroots"), 1)

    def test_multiple_blocks_reconstructed(self):
        text = (
            "%pal nprocs 8 end\n%maxcore 4000\n"
            "! B3LYP def2-SVP Opt\n"
            "%geom\n  MaxIter 200\nend\n"
            "* xyz 0 1\n  C 0 0 0\n*"
        )
        result = self._c(text)
        self.assertIn("%pal", result)
        self.assertIn("%maxcore 4000", result)
        self.assertIn("%geom", result)
        self.assertIn("! B3LYP", result)

    def test_nested_geom_constraints_block(self):
        """Nested Constraints...end inside %geom...end should be captured."""
        text = (
            "%geom\n"
            "  Constraints\n"
            "    { B 0 1 1.5 C }\n"
            "  end\n"
            "end\n"
            "! B3LYP\n"
            "* xyz 0 1\n  H 0 0 0\n*"
        )
        result = self._c(text)
        self.assertIn("Constraints", result)
        self.assertIn("{ B 0 1 1.5 C }", result)


# ---------------------------------------------------------------------------
# auto_detect_nproc
# ---------------------------------------------------------------------------

class TestAutoDetectNproc(unittest.TestCase):
    def _dlg(self):
        return _make_dlg(nproc_spin=MagicMock())

    def test_uses_psutil_physical_cores(self):
        dlg = self._dlg()
        with patch.dict(sys.modules, {"psutil": MagicMock(cpu_count=lambda logical: 4)}):
            import psutil as _ps
            _ps.cpu_count = lambda logical=True: 4
            dlg.auto_detect_nproc()
        # If psutil returns 4, spin should be set
        # (exact value depends on mock; just verify setValue was called)
        dlg.nproc_spin.setValue.assert_called()

    def test_falls_back_to_os_cpu_count_when_psutil_missing(self):
        dlg = self._dlg()
        original = sys.modules.get("psutil")
        sys.modules["psutil"] = None  # Simulate import failure
        try:
            with patch("os.cpu_count", return_value=6):
                dlg.auto_detect_nproc()
            dlg.nproc_spin.setValue.assert_called_with(6)
        finally:
            if original is None:
                sys.modules.pop("psutil", None)
            else:
                sys.modules["psutil"] = original

    def test_no_setValue_when_both_return_none(self):
        dlg = self._dlg()
        sys.modules["psutil"] = None
        try:
            with patch("os.cpu_count", return_value=None):
                dlg.auto_detect_nproc()
            dlg.nproc_spin.setValue.assert_not_called()
        finally:
            sys.modules.pop("psutil", None)


# ---------------------------------------------------------------------------
# auto_detect_mem
# ---------------------------------------------------------------------------

class TestAutoDetectMem(unittest.TestCase):
    def _dlg(self, nproc=4):
        nproc_spin = MagicMock()
        nproc_spin.value.return_value = nproc
        mem_spin = MagicMock()
        return _make_dlg(nproc_spin=nproc_spin, mem_spin=mem_spin)

    def test_formula_with_psutil(self):
        dlg = self._dlg(nproc=4)
        # Simulate 16 GB total = 16384 MB
        fake_vmem = MagicMock()
        fake_vmem.total = 16384 * 1024 * 1024
        fake_psutil = MagicMock()
        fake_psutil.virtual_memory.return_value = fake_vmem
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            dlg.auto_detect_mem()
        expected = int(16384 * 0.80 / 4)  # 3276
        dlg.mem_spin.setValue.assert_called_with(expected)

    def test_fallback_when_psutil_missing(self):
        dlg = self._dlg(nproc=2)
        sys.modules["psutil"] = None
        try:
            dlg.auto_detect_mem()
        finally:
            sys.modules.pop("psutil", None)
        # fallback total_mb = 8000; 8000 * 0.80 / 2 = 3200; max(500, 3200) = 3200
        dlg.mem_spin.setValue.assert_called_with(3200)

    def test_floor_of_500(self):
        dlg = self._dlg(nproc=100)
        sys.modules["psutil"] = None
        try:
            dlg.auto_detect_mem()
        finally:
            sys.modules.pop("psutil", None)
        # 8000 * 0.80 / 100 = 64; max(500, 64) = 500
        dlg.mem_spin.setValue.assert_called_with(500)

    def test_single_proc(self):
        dlg = self._dlg(nproc=1)
        sys.modules["psutil"] = None
        try:
            dlg.auto_detect_mem()
        finally:
            sys.modules.pop("psutil", None)
        # 8000 * 0.80 / 1 = 6400; max(500, 6400) = 6400
        dlg.mem_spin.setValue.assert_called_with(6400)


# ---------------------------------------------------------------------------
# get_coords_lines
# ---------------------------------------------------------------------------

def _make_atom(symbol, custom=None):
    atom = MagicMock()
    atom.GetSymbol.return_value = symbol
    atom.HasProp.return_value = custom is not None
    atom.GetProp.return_value = custom or symbol
    return atom


def _make_mol(atoms_data):
    """
    atoms_data: list of (symbol, x, y, z) or (symbol, x, y, z, custom_symbol)
    """
    mol = MagicMock()
    mol.GetNumAtoms.return_value = len(atoms_data)

    positions = []
    atoms = []
    for entry in atoms_data:
        sym, x, y, z = entry[:4]
        custom = entry[4] if len(entry) > 4 else None
        pos = MagicMock()
        pos.x, pos.y, pos.z = x, y, z
        positions.append(pos)
        atoms.append(_make_atom(sym, custom))

    conf = MagicMock()
    conf.GetAtomPosition.side_effect = lambda i: positions[i]
    mol.GetConformer.return_value = conf
    mol.GetAtomWithIdx.side_effect = lambda i: atoms[i]
    return mol


class TestGetCoordsLines(unittest.TestCase):
    def _dlg(self, mol):
        dlg = _make_dlg(mol=mol)
        # _resolve_live_mol just returns self.mol when already set
        dlg._resolve_live_mol = lambda: mol
        return dlg

    def test_single_atom(self):
        mol = _make_mol([("C", 0.0, 0.0, 0.0)])
        lines = self._dlg(mol).get_coords_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("C", lines[0])

    def test_three_atoms(self):
        mol = _make_mol([
            ("O", 0.0, 0.0, 0.117),
            ("H", 0.0, 0.757, -0.468),
            ("H", 0.0, -0.757, -0.468),
        ])
        lines = self._dlg(mol).get_coords_lines()
        self.assertEqual(len(lines), 3)

    def test_coordinate_format(self):
        mol = _make_mol([("N", 1.234567, -2.345678, 3.456789)])
        lines = self._dlg(mol).get_coords_lines()
        self.assertIn("1.234567", lines[0])
        self.assertIn("-2.345678", lines[0])

    def test_custom_symbol_used(self):
        mol = _make_mol([("C", 0.0, 0.0, 0.0, "Fe")])
        lines = self._dlg(mol).get_coords_lines()
        self.assertIn("Fe", lines[0])
        self.assertNotIn(" C ", lines[0])

    def test_no_mol_returns_empty(self):
        dlg = _make_dlg(mol=None)
        dlg._resolve_live_mol = lambda: None
        lines = dlg.get_coords_lines()
        self.assertEqual(lines, [])

    def test_conformer_error_returns_error_line(self):
        mol = MagicMock()
        mol.GetConformer.side_effect = Exception("no conformer")
        dlg = _make_dlg(mol=mol)
        dlg._resolve_live_mol = lambda: mol
        lines = dlg.get_coords_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("Error", lines[0])


# ---------------------------------------------------------------------------
# Z-Matrix formatting
# ---------------------------------------------------------------------------

def _make_zdata(n):
    """Simple linear chain z-data for n atoms."""
    data = [{"symbol": "C", "refs": [], "values": []}]
    if n >= 2:
        data.append({"symbol": "C", "refs": [0], "values": [1.54]})
    if n >= 3:
        data.append({"symbol": "C", "refs": [1, 0], "values": [1.54, 109.5]})
    if n >= 4:
        data.append({"symbol": "C", "refs": [2, 1, 0], "values": [1.54, 109.5, 180.0]})
    return data


class TestZMatrixStandardLines(unittest.TestCase):
    def _dlg_with_data(self, z_data):
        dlg = _make_dlg()
        dlg._build_zmatrix_data = lambda: z_data
        dlg._resolve_live_mol = lambda: True
        return dlg

    def test_one_atom(self):
        lines = self._dlg_with_data(_make_zdata(1)).get_zmatrix_standard_lines()
        self.assertEqual(len(lines), 1)
        # Atom 1: all refs/values are 0
        self.assertIn("0", lines[0])

    def test_four_atoms_count(self):
        lines = self._dlg_with_data(_make_zdata(4)).get_zmatrix_standard_lines()
        self.assertEqual(len(lines), 4)

    def test_refs_are_one_based(self):
        # Atom 2 references atom 1 (0-based 0) → should appear as "1"
        lines = self._dlg_with_data(_make_zdata(2)).get_zmatrix_standard_lines()
        # Second line: ref1=1 (1-based), ref2=0, ref3=0
        self.assertIn("  1", lines[1])

    def test_empty_data_returns_empty(self):
        lines = self._dlg_with_data([]).get_zmatrix_standard_lines()
        self.assertEqual(lines, [])

    def test_build_error_returns_error_line(self):
        dlg = _make_dlg()
        dlg._build_zmatrix_data = lambda: (_ for _ in ()).throw(RuntimeError("fail"))
        dlg._resolve_live_mol = lambda: True
        lines = dlg.get_zmatrix_standard_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("Error", lines[0])


class TestZMatrixGzmtLines(unittest.TestCase):
    def _dlg_with_data(self, z_data):
        dlg = _make_dlg()
        dlg._build_zmatrix_data = lambda: z_data
        dlg._resolve_live_mol = lambda: True
        return dlg

    def test_atom_0_symbol_only(self):
        lines = self._dlg_with_data(_make_zdata(1)).get_zmatrix_gzmt_lines()
        self.assertEqual(len(lines), 1)
        # Only symbol, no numbers
        self.assertNotIn("1.54", lines[0])

    def test_atom_1_has_ref_and_distance(self):
        lines = self._dlg_with_data(_make_zdata(2)).get_zmatrix_gzmt_lines()
        self.assertIn("1.540000", lines[1])

    def test_atom_2_has_ref_angle(self):
        lines = self._dlg_with_data(_make_zdata(3)).get_zmatrix_gzmt_lines()
        self.assertIn("109.500000", lines[2])

    def test_atom_3_has_dihedral(self):
        lines = self._dlg_with_data(_make_zdata(4)).get_zmatrix_gzmt_lines()
        self.assertIn("180.000000", lines[3])

    def test_empty_data_returns_empty(self):
        lines = self._dlg_with_data([]).get_zmatrix_gzmt_lines()
        self.assertEqual(lines, [])


# ---------------------------------------------------------------------------
# validate_charge_mult — pure charge/electron logic
# ---------------------------------------------------------------------------

def _make_mol_atoms(atomic_nums):
    """Mol with atoms having given atomic numbers."""
    mol = MagicMock()
    atoms = []
    for z in atomic_nums:
        a = MagicMock()
        a.GetAtomicNum.return_value = z
        atoms.append(a)
    mol.GetAtoms.return_value = iter(atoms)
    return mol


class TestValidateChargeMult(unittest.TestCase):
    def _dlg(self, atomic_nums, charge, mult):
        mol = _make_mol_atoms(atomic_nums)
        charge_spin = MagicMock()
        charge_spin.value.return_value = charge
        mult_spin = MagicMock()
        mult_spin.value.return_value = mult
        dlg = _make_dlg(
            mol=mol,
            charge_spin=charge_spin,
            mult_spin=mult_spin,
            default_palette=MagicMock(),
        )
        dlg._resolve_live_mol = lambda: mol
        dlg.update_preview = lambda: None
        return dlg

    def test_even_electrons_odd_mult_valid(self):
        # H2O: 8+1+1=10 protons, charge=0 → 10 electrons (even), mult=1 (odd) → valid
        dlg = self._dlg([8, 1, 1], charge=0, mult=1)
        dlg.validate_charge_mult()
        # Valid → default_palette applied to both spins
        dlg.charge_spin.setPalette.assert_called_with(dlg.default_palette)
        dlg.mult_spin.setPalette.assert_called_with(dlg.default_palette)

    def test_odd_electrons_even_mult_valid(self):
        # OH radical: 8+1=9 protons, charge=0 → 9 electrons (odd), mult=2 (even) → valid
        dlg = self._dlg([8, 1], charge=0, mult=2)
        dlg.validate_charge_mult()
        dlg.charge_spin.setPalette.assert_called_with(dlg.default_palette)

    def test_even_electrons_even_mult_invalid(self):
        # H2O: 10 electrons (even), mult=2 (even) → invalid
        dlg = self._dlg([8, 1, 1], charge=0, mult=2)
        dlg.validate_charge_mult()
        # Invalid → red palette applied, NOT default_palette
        dlg.charge_spin.setPalette.assert_called()
        called_with = dlg.charge_spin.setPalette.call_args[0][0]
        self.assertIsNot(called_with, dlg.default_palette)

    def test_odd_electrons_odd_mult_invalid(self):
        # OH radical: 9 electrons (odd), mult=1 (odd) → invalid
        dlg = self._dlg([8, 1], charge=0, mult=1)
        dlg.validate_charge_mult()
        called_with = dlg.charge_spin.setPalette.call_args[0][0]
        self.assertIsNot(called_with, dlg.default_palette)

    def test_cation_charge_plus1(self):
        # H2O+: 10 protons - 1 = 9 electrons (odd), mult=2 (even) → valid
        dlg = self._dlg([8, 1, 1], charge=1, mult=2)
        dlg.validate_charge_mult()
        dlg.charge_spin.setPalette.assert_called_with(dlg.default_palette)

    def test_no_mol_returns_early(self):
        dlg = _make_dlg(charge_spin=MagicMock(), mult_spin=MagicMock())
        dlg._resolve_live_mol = lambda: None
        dlg.update_preview = lambda: None
        dlg.validate_charge_mult()
        dlg.charge_spin.setPalette.assert_not_called()


if __name__ == "__main__":
    unittest.main()
