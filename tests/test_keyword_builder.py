"""
tests/test_keyword_builder.py

Unit tests for OrcaKeywordBuilderDialog logic in keyword_builder.py.

PyQt6 and RDKit are stubbed so no display or Qt installation is needed.
Tests cover:
  - get_inferred_category()        pure method, no Qt
  - update_preview() / route_line  job-type → keyword mapping
  - parse_route()                  round-trip: keyword string → widget state
  - get_constraints_text()         constraint and scan block generation
"""

import os
import sys
import types
import importlib.util
import unittest
from unittest.mock import MagicMock, patch

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Qt / RDKit stubs
# ---------------------------------------------------------------------------

class _Base:
    """Generic no-op base class for Qt widget stubs used in class hierarchies."""
    def __init__(self, *args, **kwargs):
        pass


def _install_stubs():
    pyqt6 = sys.modules.get("PyQt6") or types.ModuleType("PyQt6")
    qt_widgets = types.ModuleType("PyQt6.QtWidgets")
    qt_core = types.ModuleType("PyQt6.QtCore")
    qt_gui = types.ModuleType("PyQt6.QtGui")

    # Classes used as base classes must be real classes, not MagicMock,
    # to avoid MRO conflicts (MagicMock already inherits from object).
    for name in ["QDialog", "QWidget"]:
        setattr(qt_widgets, name, _Base)

    for name in [
        "QVBoxLayout", "QHBoxLayout", "QLabel", "QLineEdit",
        "QSpinBox", "QPushButton", "QGroupBox", "QComboBox", "QTextEdit",
        "QTabWidget", "QCheckBox", "QFormLayout", "QTableWidget",
        "QTableWidgetItem", "QCompleter", "QPlainTextEdit", "QGridLayout",
        "QSizePolicy", "QAbstractItemView",
    ]:
        setattr(qt_widgets, name, MagicMock)

    qt_core.Qt = MagicMock()
    qt_core.QRegularExpression = MagicMock
    qt_core.QTimer = MagicMock

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


def _load_module(name, relpath):
    path = os.path.join(_REPO_ROOT, "orca_input_generator_pro", relpath)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "orca_input_generator_pro"
    sys.modules[f"orca_input_generator_pro.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


# Load constants first (no Qt), then the builder
_constants = _load_module("constants", "constants.py")
sys.modules["orca_input_generator_pro.constants"] = _constants

_mixins = types.ModuleType("orca_input_generator_pro.mixins")


class _FakeMixin:
    pass


_mixins.Dialog3DPickingMixin = _FakeMixin
sys.modules["orca_input_generator_pro.mixins"] = _mixins

_builder_mod = _load_module("keyword_builder", "keyword_builder.py")
OrcaKeywordBuilderDialog = _builder_mod.OrcaKeywordBuilderDialog


# ---------------------------------------------------------------------------
# Mock dialog factory
# ---------------------------------------------------------------------------

def _combo(text, enabled=True):
    m = MagicMock()
    m.currentText.return_value = text
    m.isEnabled.return_value = enabled
    return m


def _check(checked=False, enabled=True):
    m = MagicMock()
    m.isChecked.return_value = checked
    m.isEnabled.return_value = enabled
    return m


def _make_dialog(
    method="B3LYP",
    basis="def2-SVP",
    aux="None",
    job="Optimization Only (Opt)",
    tight=False, verytight=False, loose=False,
    cart=False, calcfc=False,
    solv="None",
    disp="None",
    rijcosx=False,
):
    """Return a lightweight namespace that satisfies update_preview()."""
    dlg = types.SimpleNamespace()
    dlg.ui_ready = True
    dlg.route_line = ""
    dlg.preview_str = ""

    dlg.method_name = _combo(method)
    dlg.method_type = _combo("DFT (GGA/Hybrid/mGGA)")
    dlg.basis_set = _combo(basis)
    dlg.aux_basis = _combo(aux)

    dlg.job_type = _combo(job)
    dlg.opt_tight = _check(tight)
    dlg.opt_verytight = _check(verytight)
    dlg.opt_loose = _check(loose)
    dlg.opt_cart = _check(cart)
    dlg.opt_calcfc = _check(calcfc)

    freq_group = MagicMock()
    freq_group.isVisible.return_value = False
    dlg.freq_group = freq_group
    dlg.freq_num = _check(False)
    dlg.freq_raman = _check(False)

    dlg.solv_model = _combo(solv)
    dlg.solvent = _combo("Water")
    dlg.dispersion = _combo(disp)

    dlg.rijcosx = _check(rijcosx)
    dlg.grid_combo = _combo("Default")

    for name in ["scf_sloppy", "scf_loose", "scf_normal", "scf_strong",
                 "scf_tight", "scf_verytight", "scf_extreme"]:
        setattr(dlg, name, _check(False))

    dlg.pop_nbo = _check(False)
    dlg.tddft_enable = MagicMock()
    dlg.constraint_table = None
    dlg.preview_label = MagicMock()

    # Bind real methods
    dlg.update_ui_state = lambda: None
    dlg.update_preview = lambda: OrcaKeywordBuilderDialog.update_preview(dlg)
    dlg.get_inferred_category = lambda text: OrcaKeywordBuilderDialog.get_inferred_category(dlg, text)
    dlg.get_extra_blocks_text = lambda: ""

    return dlg


def _route(dlg):
    """Call update_preview and return the resulting route_line."""
    OrcaKeywordBuilderDialog.update_preview(dlg)
    return dlg.route_line


# ---------------------------------------------------------------------------
# Tests: get_inferred_category
# ---------------------------------------------------------------------------

class TestGetInferredCategory(unittest.TestCase):
    def _cat(self, method):
        dlg = _make_dialog()
        return OrcaKeywordBuilderDialog.get_inferred_category(dlg, method)

    def test_empty_returns_all_methods(self):
        self.assertEqual(self._cat(""), "All Methods")

    def test_b3lyp_is_hybrid_dft(self):
        cat = self._cat("B3LYP")
        self.assertIn("DFT", cat)

    def test_cam_b3lyp_is_range_separated(self):
        self.assertEqual(self._cat("CAM-B3LYP"), "DFT (Range-Separated)")

    def test_b2plyp_is_double_hybrid(self):
        self.assertEqual(self._cat("B2PLYP"), "DFT (Double Hybrid)")

    def test_wb97xd3_is_range_separated(self):
        self.assertEqual(self._cat("wB97X-D3"), "DFT (Range-Separated)")

    def test_xtb2_is_semi_empirical(self):
        cat = self._cat("XTB2")
        self.assertIn("Semi-Empirical", cat)

    def test_hf_is_wavefunction(self):
        cat = self._cat("HF")
        self.assertIn("Wavefunction", cat)

    def test_dlpno_ccsd_is_wavefunction(self):
        cat = self._cat("DLPNO-CCSD(T)")
        self.assertIn("Wavefunction", cat)

    def test_case_insensitive(self):
        self.assertEqual(self._cat("b3lyp"), self._cat("B3LYP"))


# ---------------------------------------------------------------------------
# Tests: update_preview — job type → keyword
# ---------------------------------------------------------------------------

class TestRouteJobType(unittest.TestCase):
    def _kw(self, job, **kwargs):
        return _route(_make_dialog(job=job, **kwargs))

    def test_opt_only_emits_opt(self):
        r = self._kw("Optimization Only (Opt)")
        self.assertIn("Opt", r)
        self.assertNotIn("Freq", r)

    def test_opt_freq_emits_opt_and_freq(self):
        r = self._kw("Optimization + Freq (Opt Freq)")
        self.assertIn("Opt", r)
        self.assertIn("Freq", r)

    def test_freq_only_emits_freq_not_opt(self):
        r = self._kw("Frequency Only (Freq)")
        self.assertIn("Freq", r)
        self.assertNotIn(" Opt", r)

    def test_opth_emits_opth(self):
        r = self._kw("Optimize H Only (OptH)")
        self.assertIn("OptH", r)

    def test_opth_does_not_emit_bare_opt(self):
        # "OptH" is not the same as "Opt" job
        r = self._kw("Optimize H Only (OptH)")
        # route should contain "OptH" but the Opt keyword must come from OptH, not "Opt " alone
        tokens = r.split()
        self.assertIn("OptH", tokens)
        self.assertNotIn("Opt", tokens)  # no standalone "Opt" token

    def test_optts_emits_optts(self):
        r = self._kw("Transition State Opt (OptTS)")
        self.assertIn("OptTS", r)

    def test_sp_emits_no_job_keyword(self):
        r = self._kw("Single Point Energy (SP)")
        self.assertNotIn("Opt", r)
        self.assertNotIn("Freq", r)
        self.assertNotIn("SP", r)

    def test_nmr_emits_nmr(self):
        r = self._kw("NMR")
        self.assertIn("NMR", r)

    def test_scan_emits_opt(self):
        r = self._kw("Scan (Relaxed Surface)")
        self.assertIn("Opt", r)

    def test_gradient_emits_gradient(self):
        r = self._kw("Gradient")
        self.assertIn("Gradient", r)

    def test_hessian_emits_hessian(self):
        r = self._kw("Hessian")
        self.assertIn("Hessian", r)


class TestRouteConvergence(unittest.TestCase):
    def test_tight_opt_replaces_opt(self):
        r = _route(_make_dialog(job="Optimization Only (Opt)", tight=True))
        self.assertIn("TightOpt", r)
        self.assertNotIn(" Opt ", r)  # standalone Opt should not appear

    def test_verytight_opt(self):
        r = _route(_make_dialog(job="Optimization Only (Opt)", verytight=True))
        self.assertIn("VeryTightOpt", r)

    def test_loose_opt(self):
        r = _route(_make_dialog(job="Optimization Only (Opt)", loose=True))
        self.assertIn("LooseOpt", r)

    def test_opth_with_tight_opt(self):
        r = _route(_make_dialog(job="Optimize H Only (OptH)", tight=True))
        self.assertIn("OptH", r)
        self.assertIn("TightOpt", r)

    def test_optts_with_tight_opt(self):
        r = _route(_make_dialog(job="Transition State Opt (OptTS)", tight=True))
        self.assertIn("OptTS", r)
        self.assertIn("TightOpt", r)


class TestRouteMethodBasis(unittest.TestCase):
    def test_method_in_route(self):
        r = _route(_make_dialog(method="PBE0", basis="def2-TZVP"))
        self.assertIn("PBE0", r)

    def test_basis_in_route(self):
        r = _route(_make_dialog(method="B3LYP", basis="def2-TZVP"))
        self.assertIn("def2-TZVP", r)

    def test_route_starts_with_exclamation(self):
        r = _route(_make_dialog())
        self.assertTrue(r.startswith("!"), f"Route must start with '!': {r!r}")

    def test_dispersion_d3bj(self):
        r = _route(_make_dialog(disp="D3BJ"))
        self.assertIn("D3BJ", r)

    def test_solvation_cpcm(self):
        dlg = _make_dialog(solv="CPCM")
        r = _route(dlg)
        self.assertIn("CPCM", r)


# ---------------------------------------------------------------------------
# Tests: parse_route — round-trip keyword → widget state
# ---------------------------------------------------------------------------

class TestParseRoute(unittest.TestCase):
    def _parse(self, route_str):
        dlg = _make_dialog()
        # Give parse_route proper combo mocks that record setCurrentText
        for attr in ["job_type", "method_type", "method_name", "basis_set",
                     "aux_basis", "solv_model", "solvent", "dispersion",
                     "grid_combo"]:
            m = MagicMock()
            m.currentText.return_value = ""
            m.count.return_value = 20
            m.itemText.return_value = ""
            setattr(dlg, attr, m)
        dlg.ui_ready = False  # parse_route sets this
        dlg.constraint_table = MagicMock()
        OrcaKeywordBuilderDialog.parse_route(dlg, route_str)
        return dlg

    def test_opt_sets_opt_job(self):
        dlg = self._parse("! B3LYP def2-SVP Opt")
        dlg.job_type.setCurrentText.assert_any_call("Optimization Only (Opt)")

    def test_opth_sets_opth_job(self):
        dlg = self._parse("! B3LYP def2-SVP OptH")
        dlg.job_type.setCurrentText.assert_any_call("Optimize H Only (OptH)")

    def test_optts_sets_optts_job(self):
        dlg = self._parse("! B3LYP def2-SVP OptTS")
        dlg.job_type.setCurrentText.assert_any_call("Transition State Opt (OptTS)")

    def test_freq_sets_freq_job(self):
        dlg = self._parse("! B3LYP def2-SVP Freq")
        dlg.job_type.setCurrentText.assert_any_call("Frequency Only (Freq)")

    def test_tightopt_sets_tight_checkbox(self):
        dlg = self._parse("! B3LYP def2-SVP TightOpt")
        dlg.opt_tight.setChecked.assert_any_call(True)

    def test_verytightopt_sets_verytight_checkbox(self):
        dlg = self._parse("! B3LYP def2-SVP VeryTightOpt")
        dlg.opt_verytight.setChecked.assert_any_call(True)

    def test_looseopt_sets_loose_checkbox(self):
        dlg = self._parse("! B3LYP def2-SVP LooseOpt")
        dlg.opt_loose.setChecked.assert_any_call(True)


# ---------------------------------------------------------------------------
# Tests: get_constraints_text
# ---------------------------------------------------------------------------

class TestGetConstraintsText(unittest.TestCase):
    def _make_table(self, rows):
        """
        rows: list of dicts with keys type, indices, value, is_scan,
                                       start, end, steps
        """
        table = MagicMock()
        table.rowCount.return_value = len(rows)

        def item(r, col):
            row = rows[r]
            mapping = {0: "type", 1: "indices", 2: "value",
                       4: "start", 5: "end", 6: "steps"}
            key = mapping.get(col)
            if key is None:
                return None
            m = MagicMock()
            m.text.return_value = str(row.get(key, ""))
            return m

        def cell_widget(r, col):
            if col != 3:
                return None
            widget = MagicMock()
            chk = MagicMock()
            chk.isChecked.return_value = rows[r].get("is_scan", False)
            widget.findChild.return_value = chk
            return widget

        table.item.side_effect = item
        table.cellWidget.side_effect = cell_widget
        return table

    def _text(self, rows):
        dlg = types.SimpleNamespace()
        dlg.constraint_table = self._make_table(rows)
        # QCheckBox stub for findChild
        _builder_mod.QCheckBox = MagicMock
        return OrcaKeywordBuilderDialog.get_constraints_text(dlg)

    def test_empty_table_returns_empty(self):
        self.assertEqual(self._text([]), "")

    def test_position_constraint(self):
        t = self._text([{"type": "Position", "indices": "3", "value": "", "is_scan": False}])
        self.assertIn("{ C 3 C }", t)
        self.assertIn("Constraints", t)

    def test_distance_constraint(self):
        t = self._text([{"type": "Distance", "indices": "0 1", "value": "1.5", "is_scan": False}])
        self.assertIn("{ B 0 1 1.5 C }", t)

    def test_angle_constraint(self):
        t = self._text([{"type": "Angle", "indices": "0 1 2", "value": "109.5", "is_scan": False}])
        self.assertIn("{ A 0 1 2 109.5 C }", t)

    def test_dihedral_constraint(self):
        t = self._text([{"type": "Dihedral", "indices": "0 1 2 3", "value": "180.0", "is_scan": False}])
        self.assertIn("{ D 0 1 2 3 180.0 C }", t)

    def test_scan_uses_scan_block(self):
        t = self._text([{
            "type": "Distance", "indices": "0 1", "value": "1.5",
            "is_scan": True, "start": "1.2", "end": "2.0", "steps": "10"
        }])
        self.assertIn("Scan", t)
        self.assertIn("B 0 1 = 1.2, 2.0, 10", t)
        self.assertNotIn("Constraints", t)

    def test_mixed_constraint_and_scan(self):
        t = self._text([
            {"type": "Position", "indices": "0", "value": "", "is_scan": False},
            {"type": "Distance", "indices": "1 2", "value": "1.4",
             "is_scan": True, "start": "1.0", "end": "2.0", "steps": "5"},
        ])
        self.assertIn("Constraints", t)
        self.assertIn("Scan", t)


if __name__ == "__main__":
    unittest.main()
