"""
tests/test_constants.py

Data-quality tests for orca_input_generator_pro/constants.py.
No Qt or RDKit needed — constants.py is pure data.

Covers:
  - ALL_ORCA_METHODS: type, non-empty, no duplicates, known entries present,
    no whitespace padding
  - ALL_ORCA_BASIS_SETS: same checks + spelling of key entries
  - get_inferred_category coverage via representative methods for every category
    including Multireference and Double Hybrid (not covered in test_keyword_builder.py)
"""

import os
import sys
import types
import importlib.util
import unittest
from unittest.mock import MagicMock

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Load constants.py directly — no Qt needed
# ---------------------------------------------------------------------------

def _load_constants():
    path = os.path.join(_REPO_ROOT, "orca_input_generator_pro", "constants.py")
    spec = importlib.util.spec_from_file_location(
        "orca_input_generator_pro.constants", path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_constants = _load_constants()


# ---------------------------------------------------------------------------
# Load __init__ with stubs so we can call get_inferred_category
# (it lives in keyword_builder, loaded indirectly via test_keyword_builder —
#  but we can also load keyword_builder standalone here)
# ---------------------------------------------------------------------------

def _install_stubs():
    """Install minimal Qt/RDKit stubs into sys.modules if not already present."""
    if "PyQt6" in sys.modules:
        return  # already installed by another test module

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
        "QVBoxLayout", "QHBoxLayout", "QLabel", "QLineEdit",
        "QSpinBox", "QPushButton", "QGroupBox", "QComboBox", "QTextEdit",
        "QTabWidget", "QCheckBox", "QFormLayout", "QTableWidget",
        "QTableWidgetItem", "QCompleter", "QPlainTextEdit", "QGridLayout",
        "QSizePolicy", "QAbstractItemView", "QMessageBox", "QFileDialog",
        "QInputDialog", "QApplication",
    ]:
        setattr(qt_widgets, name, MagicMock)

    qt_core.Qt = MagicMock()
    qt_core.QRegularExpression = MagicMock
    qt_core.QTimer = MagicMock

    qt_gui.QFont = MagicMock
    qt_gui.QPalette = MagicMock
    qt_gui.QColor = MagicMock
    qt_gui.QSyntaxHighlighter = type("QSyntaxHighlighter", (), {"__init__": lambda s, *a, **k: None})
    qt_gui.QTextCharFormat = MagicMock
    qt_gui.QAction = MagicMock
    qt_gui.QIcon = MagicMock

    pyqt6.QtWidgets = qt_widgets
    pyqt6.QtCore = qt_core
    pyqt6.QtGui = qt_gui

    sys.modules.update({
        "PyQt6": pyqt6,
        "PyQt6.QtWidgets": qt_widgets,
        "PyQt6.QtCore": qt_core,
        "PyQt6.QtGui": qt_gui,
        "rdkit": MagicMock(),
        "rdkit.Chem": MagicMock(),
        "rdkit.Chem.rdMolTransforms": MagicMock(),
    })


_install_stubs()


def _load_keyword_builder():
    key = "orca_input_generator_pro.keyword_builder"
    if key in sys.modules:
        return sys.modules[key]

    # Ensure constants and mixins are in sys.modules first
    sys.modules["orca_input_generator_pro.constants"] = _constants

    mixins_mod = types.ModuleType("orca_input_generator_pro.mixins")

    class _FakeMixin:
        pass

    mixins_mod.Dialog3DPickingMixin = _FakeMixin
    sys.modules["orca_input_generator_pro.mixins"] = mixins_mod

    path = os.path.join(_REPO_ROOT, "orca_input_generator_pro", "keyword_builder.py")
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "orca_input_generator_pro"
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


_kb_mod = _load_keyword_builder()
OrcaKeywordBuilderDialog = _kb_mod.OrcaKeywordBuilderDialog


def _cat(method_text):
    """Call get_inferred_category on a throw-away dialog namespace."""
    import types as t
    dlg = t.SimpleNamespace()
    return OrcaKeywordBuilderDialog.get_inferred_category(dlg, method_text)


# ---------------------------------------------------------------------------
# Tests: ALL_ORCA_METHODS
# ---------------------------------------------------------------------------

class TestAllOrcaMethodsList(unittest.TestCase):
    def setUp(self):
        self.methods = _constants.ALL_ORCA_METHODS

    def test_is_list(self):
        self.assertIsInstance(self.methods, list)

    def test_non_empty(self):
        self.assertGreater(len(self.methods), 50,
                           "Expected more than 50 methods in ALL_ORCA_METHODS")

    def test_all_strings(self):
        for m in self.methods:
            self.assertIsInstance(m, str, f"Non-string entry: {m!r}")

    def test_no_empty_strings(self):
        for m in self.methods:
            self.assertGreater(len(m), 0, "Empty string found in ALL_ORCA_METHODS")

    def test_no_exact_duplicates(self):
        seen = set()
        for m in self.methods:
            self.assertNotIn(m, seen, f"Exact duplicate in ALL_ORCA_METHODS: {m!r}")
            seen.add(m)

    def test_known_case_variants_are_intentional(self):
        # GFN1-XTB/GFN1-xTB and GFN2-XTB/GFN2-xTB are intentional case variants
        # (ORCA accepts both spellings). Verify both forms are present.
        self.assertIn("GFN1-XTB", self.methods)
        self.assertIn("GFN1-xTB", self.methods)
        self.assertIn("GFN2-XTB", self.methods)
        self.assertIn("GFN2-xTB", self.methods)

    def test_no_leading_trailing_whitespace(self):
        for m in self.methods:
            self.assertEqual(m, m.strip(),
                             f"Method has extra whitespace: {m!r}")

    # Spot-check key methods
    def test_b3lyp_present(self):
        self.assertIn("B3LYP", self.methods)

    def test_pbe0_present(self):
        self.assertIn("PBE0", self.methods)

    def test_hf_present(self):
        self.assertIn("HF", self.methods)

    def test_mp2_present(self):
        self.assertIn("MP2", self.methods)

    def test_ccsd_t_present(self):
        self.assertIn("CCSD(T)", self.methods)

    def test_dlpno_ccsd_t_present(self):
        self.assertIn("DLPNO-CCSD(T)", self.methods)

    def test_cam_b3lyp_present(self):
        self.assertIn("CAM-B3LYP", self.methods)

    def test_xtb2_present(self):
        self.assertIn("XTB2", self.methods)

    def test_casscf_present(self):
        self.assertIn("CASSCF", self.methods)

    def test_nevpt2_present(self):
        self.assertIn("NEVPT2", self.methods)

    def test_b2plyp_present(self):
        self.assertIn("B2PLYP", self.methods)

    def test_wb97x_d3_present(self):
        self.assertIn("wB97X-D3", self.methods)


# ---------------------------------------------------------------------------
# Tests: ALL_ORCA_BASIS_SETS
# ---------------------------------------------------------------------------

class TestAllOrcaBasisSetsList(unittest.TestCase):
    def setUp(self):
        self.basis_sets = _constants.ALL_ORCA_BASIS_SETS

    def test_is_list(self):
        self.assertIsInstance(self.basis_sets, list)

    def test_non_empty(self):
        self.assertGreater(len(self.basis_sets), 50,
                           "Expected more than 50 basis sets in ALL_ORCA_BASIS_SETS")

    def test_all_strings(self):
        for b in self.basis_sets:
            self.assertIsInstance(b, str, f"Non-string entry: {b!r}")

    def test_no_empty_strings(self):
        for b in self.basis_sets:
            self.assertGreater(len(b), 0, "Empty string found in ALL_ORCA_BASIS_SETS")

    def test_no_exact_duplicates(self):
        seen = set()
        for b in self.basis_sets:
            self.assertNotIn(b, seen,
                             f"Exact duplicate in ALL_ORCA_BASIS_SETS: {b!r}")
            seen.add(b)

    def test_no_leading_trailing_whitespace(self):
        for b in self.basis_sets:
            self.assertEqual(b, b.strip(),
                             f"Basis set has extra whitespace: {b!r}")

    # Spot-check key basis sets
    def test_def2_svp_present(self):
        self.assertIn("def2-SVP", self.basis_sets)

    def test_def2_tzvp_present(self):
        self.assertIn("def2-TZVP", self.basis_sets)

    def test_def2_qzvp_present(self):
        self.assertIn("def2-QZVP", self.basis_sets)

    def test_cc_pvdz_present(self):
        self.assertIn("cc-pVDZ", self.basis_sets)

    def test_cc_pvtz_present(self):
        self.assertIn("cc-pVTZ", self.basis_sets)

    def test_6_31g_star_present(self):
        self.assertIn("6-31G*", self.basis_sets)

    def test_6_311g_present(self):
        self.assertIn("6-311G", self.basis_sets)

    def test_sto_3g_present(self):
        self.assertIn("STO-3G", self.basis_sets)

    def test_def2_qzvppd_spelling(self):
        # Correct spelling is def2-QZVPPD (with Z); verify it is present
        self.assertIn("def2-QZVPPD", self.basis_sets)

    def test_aug_cc_pvtz_present(self):
        self.assertIn("aug-cc-pVTZ", self.basis_sets)

    def test_epr_ii_present(self):
        self.assertIn("EPR-II", self.basis_sets)


# ---------------------------------------------------------------------------
# Tests: get_inferred_category — categories not covered by test_keyword_builder.py
# ---------------------------------------------------------------------------

class TestGetInferredCategoryExtended(unittest.TestCase):
    """
    Covers the category branches that test_keyword_builder.py misses:
      - DFT (GGA/Hybrid/Meta) representative methods
      - Double Hybrid
      - Wavefunction HF/MP2 (UHF, ROHF, RI-MP2, etc.)
      - Wavefunction (Multireference)
      - Unknown → All Methods fallback
    """

    def test_pbe_is_dft_gga(self):
        self.assertIn("DFT", _cat("PBE"))

    def test_pbe0_is_dft_gga(self):
        self.assertIn("DFT", _cat("PBE0"))

    def test_m06_2x_is_dft_gga(self):
        self.assertIn("DFT", _cat("M06-2X"))

    def test_scan_is_dft_gga(self):
        self.assertIn("DFT", _cat("SCAN"))

    def test_tpss_is_dft_gga(self):
        self.assertIn("DFT", _cat("TPSS"))

    def test_b2gp_plyp_is_double_hybrid(self):
        self.assertEqual(_cat("B2GP-PLYP"), "DFT (Double Hybrid)")

    def test_dsd_blyp_is_double_hybrid(self):
        self.assertEqual(_cat("DSD-BLYP"), "DFT (Double Hybrid)")

    def test_pwpb95_is_double_hybrid(self):
        self.assertEqual(_cat("PWPB95"), "DFT (Double Hybrid)")

    def test_uhf_is_wavefunction_hf_mp2(self):
        self.assertEqual(_cat("UHF"), "Wavefunction (HF/MP2)")

    def test_rohf_is_wavefunction_hf_mp2(self):
        self.assertEqual(_cat("ROHF"), "Wavefunction (HF/MP2)")

    def test_ri_mp2_is_wavefunction_hf_mp2(self):
        self.assertEqual(_cat("RI-MP2"), "Wavefunction (HF/MP2)")

    def test_scs_mp2_is_wavefunction_hf_mp2(self):
        self.assertEqual(_cat("SCS-MP2"), "Wavefunction (HF/MP2)")

    def test_ccsd_is_wavefunction_cc(self):
        self.assertEqual(_cat("CCSD"), "Wavefunction (Coupled Cluster)")

    def test_casscf_is_multireference(self):
        self.assertEqual(_cat("CASSCF"), "Wavefunction (Multireference)")

    def test_nevpt2_is_multireference(self):
        self.assertEqual(_cat("NEVPT2"), "Wavefunction (Multireference)")

    def test_mrci_is_multireference(self):
        self.assertEqual(_cat("MRCI"), "Wavefunction (Multireference)")

    def test_dlpno_nevpt2_is_multireference(self):
        self.assertEqual(_cat("DLPNO-NEVPT2"), "Wavefunction (Multireference)")

    def test_gfn1_xtb_is_semi_empirical(self):
        self.assertEqual(_cat("GFN1-XTB"), "Semi-Empirical")

    def test_pm6_is_semi_empirical(self):
        self.assertEqual(_cat("PM6"), "Semi-Empirical")

    def test_completely_unknown_returns_all_methods(self):
        self.assertEqual(_cat("TOTALLY_UNKNOWN_METHOD_XYZ"), "All Methods")

    def test_empty_string_returns_all_methods(self):
        self.assertEqual(_cat(""), "All Methods")

    def test_category_lookup_is_case_insensitive(self):
        # CASSCF lowercase should still be Multireference
        self.assertEqual(_cat("casscf"), _cat("CASSCF"))

    def test_double_hybrid_case_insensitive(self):
        self.assertEqual(_cat("b2plyp"), _cat("B2PLYP"))


if __name__ == "__main__":
    unittest.main()
