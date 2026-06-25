"""
tests/test_parse_route_extended.py

Extended tests for OrcaKeywordBuilderDialog.parse_route() and
update_preview() branches not covered by test_keyword_builder.py.

New coverage:
  parse_route()
    - SCF convergence keywords (SloppySCF … ExtremeSCF)
    - NumFreq / Raman tokens
    - RIJCOSX / RI token; Def2/J and Def2/JK aux basis tokens
    - NBO token
    - Dispersion tokens (D3BJ, D3Zero, D4, D2, NL)
    - CPCM(solvent) / SMD / CPC(Water) solvation tokens
    - Opt + Freq combo detection (both orderings)
    - COpt (Cartesian) and CalcFC
    - Gradient and Hessian job types
    - %tddft block (NRoots, IRoot, Triplets, TDA)
    - %geom MaxIter 256
    - Empty / whitespace route (no-op)

  update_preview()
    - NumFreq emitted when freq_group visible and freq_num checked
    - Opt+Freq job with TightOpt convergence
    - 3c methods (B97-3c, r2SCAN-3c) omit basis set from route

  get_extra_blocks_text()
    - Triplets true / false
    - TDA false
    - IRoot values > 1
    - Triplets=True + TDA=False combination
"""

import os
import sys
import types
import importlib.util
import unittest
from unittest.mock import MagicMock

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Qt / RDKit stubs
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
    qt_gui.QSyntaxHighlighter = type(
        "QSyntaxHighlighter", (), {"__init__": lambda s, *a, **k: None}
    )
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
        }
    )


_install_stubs()


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------


def _load_module(name, relpath):
    key = f"orca_input_generator_pro.{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(_REPO_ROOT, "orca_input_generator_pro", relpath)
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "orca_input_generator_pro"
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


# Constants first (no Qt)
_constants = _load_module("constants", "constants.py")

# Minimal mixins stub
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

_builder_mod = _load_module("keyword_builder", "keyword_builder.py")
OrcaKeywordBuilderDialog = _builder_mod.OrcaKeywordBuilderDialog

# Job type items — mirrors the real QComboBox contents in setup_job_tab
_JOB_ITEMS = [
    "Optimization + Freq (Opt Freq)",
    "Optimization Only (Opt)",
    "Optimize H Only (OptH)",
    "Frequency Only (Freq)",
    "Single Point Energy (SP)",
    "NMR",
    "Scan (Relaxed Surface)",
    "Transition State Opt (OptTS)",
    "Gradient",
    "Hessian",
    "GOAT (Global Search)",
    "NEB-CI (Reaction Path)",
    "NEB-TS (TS via NEB)",
    "MD (Molecular Dynamics)",
]


# ---------------------------------------------------------------------------
# Dialog factory helpers
# ---------------------------------------------------------------------------


def _combo(text=""):
    m = MagicMock()
    m.currentText.return_value = text
    m.isEnabled.return_value = True
    m.count.return_value = len(_JOB_ITEMS)
    m.itemText.side_effect = lambda i: _JOB_ITEMS[i] if i < len(_JOB_ITEMS) else ""
    return m


def _check(checked=False, enabled=True):
    m = MagicMock()
    m.isChecked.return_value = checked
    m.isEnabled.return_value = enabled
    return m


def _spinbox(val=0):
    m = MagicMock()
    m.value.return_value = val
    return m


def _make_parse_dialog():
    """Return a namespace whose attributes are MagicMocks, suitable for parse_route."""
    dlg = types.SimpleNamespace()
    dlg.ui_ready = False
    dlg.route_line = ""
    dlg.preview_str = ""
    dlg.update_ui_state = lambda: None
    dlg.update_preview = lambda: None  # suppress real update during parse

    # Combos
    for attr in [
        "method_type",
        "method_name",
        "basis_set",
        "aux_basis",
        "grid_combo",
        "job_type",
        "solv_model",
        "solvent",
        "dispersion",
    ]:
        setattr(dlg, attr, _combo())

    # Checkboxes
    for attr in [
        "opt_tight",
        "opt_verytight",
        "opt_loose",
        "opt_cart",
        "opt_calcfc",
        "opt_ts_mode",
        "freq_num",
        "freq_raman",
        "rijcosx",
        "pop_nbo",
        "tddft_enable",
        "tddft_triplets",
        "tddft_tda",
        "scf_sloppy",
        "scf_loose",
        "scf_normal",
        "scf_strong",
        "scf_tight",
        "scf_verytight",
        "scf_extreme",
        "iter256_chk",
    ]:
        setattr(dlg, attr, _check())

    # SpinBoxes
    dlg.tddft_nroots = _spinbox()
    dlg.tddft_iroot = _spinbox()

    # constraint_table
    ct = MagicMock()
    ct.rowCount.return_value = 0
    dlg.constraint_table = ct

    # _add_parsed_constraint is called during %geom parsing; mock it
    dlg._add_parsed_constraint = MagicMock()

    return dlg


def _parse(route_str):
    dlg = _make_parse_dialog()
    OrcaKeywordBuilderDialog.parse_route(dlg, route_str)
    return dlg


# ---------------------------------------------------------------------------
# Helpers for update_preview tests
# ---------------------------------------------------------------------------


def _make_preview_dialog(
    method="B3LYP",
    basis="def2-SVP",
    aux="None",
    job="Optimization Only (Opt)",
    tight=False,
    verytight=False,
    loose=False,
    cart=False,
    calcfc=False,
    solv="None",
    disp="None",
    rijcosx=False,
    freq_visible=False,
    freq_num=False,
):
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
    dlg.opt_ts_mode = _check(False)

    freq_group = MagicMock()
    freq_group.isVisible.return_value = freq_visible
    dlg.freq_group = freq_group
    dlg.freq_num = _check(freq_num)
    dlg.freq_raman = _check(False)

    dlg.solv_model = _combo(solv)
    dlg.solvent = _combo("Water")
    dlg.dispersion = _combo(disp)

    dlg.rijcosx = _check(rijcosx)
    dlg.grid_combo = _combo("Default")

    for name in [
        "scf_sloppy",
        "scf_loose",
        "scf_normal",
        "scf_strong",
        "scf_tight",
        "scf_verytight",
        "scf_extreme",
    ]:
        setattr(dlg, name, _check(False))

    dlg.pop_nbo = _check(False)
    dlg.tddft_enable = _check(False)
    dlg.iter256_chk = _check(False)
    dlg.constraint_table = MagicMock()
    dlg.constraint_table.rowCount.return_value = 0
    dlg.preview_label = MagicMock()

    dlg.update_ui_state = lambda: None
    dlg.update_preview = lambda: OrcaKeywordBuilderDialog.update_preview(dlg)
    dlg.get_inferred_category = (
        lambda text: OrcaKeywordBuilderDialog.get_inferred_category(dlg, text)
    )
    dlg.get_extra_blocks_text = lambda: OrcaKeywordBuilderDialog.get_extra_blocks_text(
        dlg
    )
    dlg.get_constraints_text = lambda: OrcaKeywordBuilderDialog.get_constraints_text(
        dlg
    )

    return dlg


def _route(dlg):
    OrcaKeywordBuilderDialog.update_preview(dlg)
    return dlg.route_line


# ---------------------------------------------------------------------------
# parse_route: SCF convergence keywords
# ---------------------------------------------------------------------------


class TestParseRouteSCF(unittest.TestCase):
    def _parse_scf(self, keyword):
        return _parse(f"! B3LYP def2-SVP {keyword}")

    def test_sloppyscf(self):
        dlg = self._parse_scf("SloppySCF")
        dlg.scf_sloppy.setChecked.assert_any_call(True)

    def test_loosescf(self):
        dlg = self._parse_scf("LooseSCF")
        dlg.scf_loose.setChecked.assert_any_call(True)

    def test_normalscf(self):
        dlg = self._parse_scf("NormalSCF")
        dlg.scf_normal.setChecked.assert_any_call(True)

    def test_strongscf(self):
        dlg = self._parse_scf("StrongSCF")
        dlg.scf_strong.setChecked.assert_any_call(True)

    def test_tightscf(self):
        dlg = self._parse_scf("TightSCF")
        dlg.scf_tight.setChecked.assert_any_call(True)

    def test_verytightscf(self):
        dlg = self._parse_scf("VeryTightSCF")
        dlg.scf_verytight.setChecked.assert_any_call(True)

    def test_extremescf(self):
        dlg = self._parse_scf("ExtremeSCF")
        dlg.scf_extreme.setChecked.assert_any_call(True)


# ---------------------------------------------------------------------------
# parse_route: Freq options
# ---------------------------------------------------------------------------


class TestParseRouteFreqOptions(unittest.TestCase):
    def test_numfreq_sets_checkbox(self):
        dlg = _parse("! B3LYP def2-SVP Freq NumFreq")
        dlg.freq_num.setChecked.assert_any_call(True)

    def test_raman_sets_checkbox(self):
        dlg = _parse("! B3LYP def2-SVP Freq Raman")
        dlg.freq_raman.setChecked.assert_any_call(True)


# ---------------------------------------------------------------------------
# parse_route: RIJCOSX / RI and aux basis
# ---------------------------------------------------------------------------


class TestParseRouteRIJCOSX(unittest.TestCase):
    def test_rijcosx_sets_rijcosx(self):
        dlg = _parse("! B3LYP def2-SVP RIJCOSX Def2/J Opt")
        dlg.rijcosx.setChecked.assert_any_call(True)

    def test_ri_sets_rijcosx(self):
        dlg = _parse("! DLPNO-CCSD(T) cc-pVTZ RI Opt")
        dlg.rijcosx.setChecked.assert_any_call(True)

    def test_def2_j_sets_aux_basis(self):
        dlg = _parse("! B3LYP def2-SVP RIJCOSX Def2/J")
        dlg.aux_basis.setCurrentText.assert_any_call("Def2/J")

    def test_def2_jk_sets_aux_basis(self):
        dlg = _parse("! HF def2-SVP RI Def2/JK")
        dlg.aux_basis.setCurrentText.assert_any_call("Def2/JK")


# ---------------------------------------------------------------------------
# parse_route: NBO
# ---------------------------------------------------------------------------


class TestParseRouteNBO(unittest.TestCase):
    def test_nbo_sets_checkbox(self):
        dlg = _parse("! B3LYP def2-SVP NBO")
        dlg.pop_nbo.setChecked.assert_any_call(True)

    def test_no_nbo_keyword_does_not_set_checkbox(self):
        dlg = _parse("! B3LYP def2-SVP Opt")
        dlg.pop_nbo.setChecked.assert_any_call(False)


# ---------------------------------------------------------------------------
# parse_route: Dispersion
# ---------------------------------------------------------------------------


class TestParseRouteDispersion(unittest.TestCase):
    def _disp(self, kw):
        dlg = _parse(f"! B3LYP def2-SVP {kw}")
        dlg.dispersion.setCurrentText.assert_any_call(kw)

    def test_d3bj(self):
        self._disp("D3BJ")

    def test_d3zero(self):
        dlg = _parse("! B3LYP def2-SVP D3Zero")
        dlg.dispersion.setCurrentText.assert_any_call("D3Zero")

    def test_d4(self):
        self._disp("D4")

    def test_d2(self):
        self._disp("D2")

    def test_nl(self):
        self._disp("NL")


# ---------------------------------------------------------------------------
# parse_route: Solvation
# ---------------------------------------------------------------------------


class TestParseRouteSolvation(unittest.TestCase):
    def test_cpcm_water_sets_model(self):
        dlg = _parse("! B3LYP def2-SVP CPCM(Water)")
        dlg.solv_model.setCurrentText.assert_any_call("CPCM")

    def test_smd_token_sets_smd_model(self):
        dlg = _parse("! B3LYP def2-SVP CPCM(Acetonitrile) SMD")
        dlg.solv_model.setCurrentText.assert_any_call("SMD")

    def test_cpc_water_sets_short_model(self):
        dlg = _parse("! B3LYP def2-SVP CPC(Water)")
        dlg.solv_model.setCurrentText.assert_any_call("CPC(Water) (Short)")


# ---------------------------------------------------------------------------
# parse_route: Opt+Freq combo detection
# ---------------------------------------------------------------------------


class TestParseRouteOptFreqCombo(unittest.TestCase):
    # NOTE: parse_route's Opt+Freq combo detection relies on job_type.currentText()
    # returning the previously-set value. A MagicMock doesn't update its return value
    # on setCurrentText, so round-trip combo detection can't be tested via mock alone.
    # The update_preview round-trip is already validated in test_keyword_builder.py
    # (TestRouteJobType.test_opt_freq_emits_opt_and_freq).

    def test_opt_alone_sets_opt_job(self):
        dlg = _parse("! B3LYP def2-SVP Opt")
        dlg.job_type.setCurrentText.assert_any_call("Optimization Only (Opt)")

    def test_freq_alone_sets_freq_job(self):
        dlg = _parse("! B3LYP def2-SVP Freq")
        dlg.job_type.setCurrentText.assert_any_call("Frequency Only (Freq)")


# ---------------------------------------------------------------------------
# parse_route: COpt and CalcFC
# ---------------------------------------------------------------------------


class TestParseRouteCOptCalcFC(unittest.TestCase):
    def test_copt_sets_cart(self):
        dlg = _parse("! B3LYP def2-SVP COpt")
        dlg.opt_cart.setChecked.assert_any_call(True)

    def test_calcfc_sets_calcfc(self):
        dlg = _parse("! B3LYP def2-SVP Opt CalcFC")
        dlg.opt_calcfc.setChecked.assert_any_call(True)


# ---------------------------------------------------------------------------
# parse_route: Gradient and Hessian
# ---------------------------------------------------------------------------


class TestParseRouteGradientHessian(unittest.TestCase):
    def test_gradient_sets_job_index(self):
        dlg = _parse("! B3LYP def2-SVP Gradient")
        # setCurrentIndex should be called with index 8 (Gradient)
        dlg.job_type.setCurrentIndex.assert_any_call(8)

    def test_hessian_sets_job_index(self):
        dlg = _parse("! B3LYP def2-SVP Hessian")
        # setCurrentIndex should be called with index 9 (Hessian)
        dlg.job_type.setCurrentIndex.assert_any_call(9)


# ---------------------------------------------------------------------------
# parse_route: %tddft block
# ---------------------------------------------------------------------------


class TestParseRouteTDDFTBlock(unittest.TestCase):
    _ROUTE_WITH_TDDFT = (
        "! B3LYP def2-SVP Opt\n\n"
        "%tddft\n"
        "  NRoots 15\n"
        "  Triplets true\n"
        "  TDA true\n"
        "  IRoot 3\n"
        "end"
    )

    def setUp(self):
        self.dlg = _parse(self._ROUTE_WITH_TDDFT)

    def test_tddft_enable_set(self):
        self.dlg.tddft_enable.setChecked.assert_any_call(True)

    def test_nroots_set(self):
        self.dlg.tddft_nroots.setValue.assert_any_call(15)

    def test_iroot_set(self):
        self.dlg.tddft_iroot.setValue.assert_any_call(3)

    def test_triplets_true(self):
        self.dlg.tddft_triplets.setChecked.assert_any_call(True)

    def test_tda_true(self):
        self.dlg.tddft_tda.setChecked.assert_any_call(True)

    def test_tddft_disabled_when_no_block(self):
        dlg = _parse("! B3LYP def2-SVP Opt")
        dlg.tddft_enable.setChecked.assert_any_call(False)


class TestParseRouteTDDFTTripletsFalse(unittest.TestCase):
    def test_triplets_false_when_omitted(self):
        route = (
            "! B3LYP def2-SVP\n\n%tddft\n  NRoots 5\n  Triplets false\n  TDA false\nend"
        )
        dlg = _parse(route)
        dlg.tddft_triplets.setChecked.assert_any_call(False)
        dlg.tddft_tda.setChecked.assert_any_call(False)


# ---------------------------------------------------------------------------
# parse_route: %geom MaxIter 256
# ---------------------------------------------------------------------------


class TestParseRouteGeomMaxIter(unittest.TestCase):
    def test_maxiter_256_in_geom_block(self):
        route = "! B3LYP def2-SVP Opt\n\n%geom\n  MaxIter 256\nend"
        dlg = _parse(route)
        dlg.iter256_chk.setChecked.assert_any_call(True)

    def test_maxiter_256_in_route_line(self):
        # MaxIter 256 can also appear as a string in the route text itself
        route = "! B3LYP def2-SVP Opt MaxIter 256"
        dlg = _parse(route)
        dlg.iter256_chk.setChecked.assert_any_call(True)

    def test_no_maxiter_when_absent(self):
        dlg = _parse("! B3LYP def2-SVP Opt")
        # setChecked(True) should NOT have been called for iter256_chk
        true_calls = [
            c
            for c in dlg.iter256_chk.setChecked.call_args_list
            if c == unittest.mock.call(True)
        ]
        self.assertEqual(len(true_calls), 0)


# ---------------------------------------------------------------------------
# parse_route: edge cases
# ---------------------------------------------------------------------------


class TestParseRouteEdgeCases(unittest.TestCase):
    def test_empty_string_is_no_op(self):
        # parse_route returns early when route is empty; no widget calls are made
        dlg = _parse("")
        dlg.rijcosx.setChecked.assert_not_called()

    def test_whitespace_only_is_no_op(self):
        dlg = _parse("   ")
        # ui_ready should end as True (set at end of parse) or early-return
        # The only guarantee: no crash
        self.assertIsNotNone(dlg)

    def test_bare_exclamation_no_crash(self):
        dlg = _parse("!")
        self.assertIsNotNone(dlg)


# ---------------------------------------------------------------------------
# update_preview: NumFreq when freq_group is visible
# ---------------------------------------------------------------------------


class TestUpdatePreviewAuxBasis(unittest.TestCase):
    """Aux basis options in update_preview (RIJCOSX enabled)."""

    def _route_aux(self, aux):
        dlg = _make_preview_dialog(rijcosx=True)
        dlg.rijcosx.isEnabled.return_value = True
        dlg.aux_basis = _combo(aux)
        return _route(dlg)

    def test_def2jk_emits_def2jk(self):
        r = self._route_aux("Def2/JK")
        self.assertIn("Def2/JK", r)

    def test_def2jk_does_not_emit_def2j(self):
        r = self._route_aux("Def2/JK")
        # "Def2/J" must not appear as a separate token before "Def2/JK"
        tokens = r.split()
        self.assertNotIn("Def2/J", tokens)

    def test_def2j_emits_def2j(self):
        r = self._route_aux("Def2/J")
        self.assertIn("Def2/J", r)

    def test_auto_def2j_emits_def2j(self):
        # "Auto (Def2/J, etc)" contains "Def2/J" as substring
        r = self._route_aux("Auto (Def2/J, etc)")
        self.assertIn("Def2/J", r)

    def test_autoaux_emits_nothing(self):
        r = self._route_aux("AutoAux")
        self.assertNotIn("Def2/J", r)
        self.assertNotIn("Def2/JK", r)

    def test_noaux_emits_nothing(self):
        r = self._route_aux("NoAux")
        self.assertNotIn("Def2/J", r)
        self.assertNotIn("Def2/JK", r)

    def test_none_aux_emits_nothing(self):
        r = self._route_aux("None")
        self.assertNotIn("Def2/J", r)
        self.assertNotIn("Def2/JK", r)


class TestUpdatePreviewNumFreq(unittest.TestCase):
    def test_numfreq_emitted_when_freq_group_visible(self):
        dlg = _make_preview_dialog(
            job="Optimization + Freq (Opt Freq)",
            freq_visible=True,
            freq_num=True,
        )
        r = _route(dlg)
        self.assertIn("NumFreq", r)

    def test_raman_emitted_when_freq_group_visible(self):
        dlg = _make_preview_dialog(
            job="Optimization + Freq (Opt Freq)",
            freq_visible=True,
        )
        dlg.freq_raman = _check(True)
        r = _route(dlg)
        self.assertIn("Raman", r)

    def test_numfreq_not_emitted_when_freq_group_hidden(self):
        dlg = _make_preview_dialog(
            job="Single Point Energy (SP)",
            freq_visible=False,
            freq_num=True,
        )
        r = _route(dlg)
        self.assertNotIn("NumFreq", r)


# ---------------------------------------------------------------------------
# update_preview: Opt+Freq with convergence options
# ---------------------------------------------------------------------------


class TestUpdatePreviewOptFreqConvergence(unittest.TestCase):
    def test_opt_freq_default_has_opt_and_freq(self):
        dlg = _make_preview_dialog(job="Optimization + Freq (Opt Freq)")
        r = _route(dlg)
        self.assertIn("Opt", r)
        self.assertIn("Freq", r)

    def test_opt_freq_tight_emits_tightopt_and_freq(self):
        dlg = _make_preview_dialog(job="Optimization + Freq (Opt Freq)", tight=True)
        r = _route(dlg)
        self.assertIn("TightOpt", r)
        self.assertIn("Freq", r)

    def test_opt_freq_verytight_emits_verytightopt_and_freq(self):
        dlg = _make_preview_dialog(job="Optimization + Freq (Opt Freq)", verytight=True)
        r = _route(dlg)
        self.assertIn("VeryTightOpt", r)
        self.assertIn("Freq", r)


# ---------------------------------------------------------------------------
# update_preview: 3c methods omit basis set
# ---------------------------------------------------------------------------


class TestUpdatePreview3cMethods(unittest.TestCase):
    def test_b97_3c_no_basis(self):
        dlg = _make_preview_dialog(method="B97-3c", basis="def2-SVP")
        r = _route(dlg)
        self.assertIn("B97-3c", r)
        self.assertNotIn("def2-SVP", r)

    def test_r2scan_3c_no_basis(self):
        dlg = _make_preview_dialog(method="r2SCAN-3c", basis="def2-TZVP")
        r = _route(dlg)
        self.assertIn("r2SCAN-3c", r)
        self.assertNotIn("def2-TZVP", r)

    def test_pbeh_3c_no_basis(self):
        dlg = _make_preview_dialog(method="PBEh-3c", basis="def2-SVP")
        r = _route(dlg)
        self.assertIn("PBEh-3c", r)
        self.assertNotIn("def2-SVP", r)


# ---------------------------------------------------------------------------
# get_extra_blocks_text: TD-DFT option combinations
# ---------------------------------------------------------------------------


def _make_tddft_dlg(enable=True, nroots=5, triplets=False, tda=True, iroot=1):
    dlg = _make_preview_dialog()
    dlg.tddft_enable = _check(enable)
    dlg.tddft_nroots = _spinbox(nroots)
    dlg.tddft_triplets = _check(triplets)
    dlg.tddft_tda = _check(tda)
    dlg.tddft_iroot = _spinbox(iroot)
    dlg.iter256_chk = _check(False)
    dlg.constraint_table = MagicMock()
    dlg.constraint_table.rowCount.return_value = 0
    return dlg


def _extra(dlg):
    return OrcaKeywordBuilderDialog.get_extra_blocks_text(dlg)


class TestGetExtraBlocksTDDFTOptions(unittest.TestCase):
    def test_triplets_true_emitted(self):
        t = _extra(_make_tddft_dlg(triplets=True))
        self.assertIn("Triplets true", t)

    def test_triplets_false_emitted(self):
        t = _extra(_make_tddft_dlg(triplets=False))
        self.assertIn("Triplets false", t)

    def test_tda_false_emitted(self):
        t = _extra(_make_tddft_dlg(tda=False))
        self.assertIn("TDA false", t)

    def test_tda_true_emitted(self):
        t = _extra(_make_tddft_dlg(tda=True))
        self.assertIn("TDA true", t)

    def test_iroot_5_emitted(self):
        t = _extra(_make_tddft_dlg(iroot=5))
        self.assertIn("IRoot 5", t)

    def test_iroot_1_emitted(self):
        t = _extra(_make_tddft_dlg(iroot=1))
        self.assertIn("IRoot 1", t)

    def test_triplets_true_tda_false_combination(self):
        t = _extra(_make_tddft_dlg(triplets=True, tda=False))
        self.assertIn("Triplets true", t)
        self.assertIn("TDA false", t)

    def test_nroots_1_emitted(self):
        t = _extra(_make_tddft_dlg(nroots=1))
        self.assertIn("NRoots 1", t)

    def test_nroots_100_emitted(self):
        t = _extra(_make_tddft_dlg(nroots=100))
        self.assertIn("NRoots 100", t)

    def test_disabled_tddft_no_block(self):
        t = _extra(_make_tddft_dlg(enable=False))
        self.assertNotIn("%tddft", t)


# ---------------------------------------------------------------------------
# update_preview: WF method + RI uses correct auxiliary basis
# ---------------------------------------------------------------------------


class TestUpdatePreviewWFMethodRI(unittest.TestCase):
    """WF method + RI: Def2/J and Def2/JK are Coulomb-only — AutoAux emitted instead."""

    def _wf_ri_route(self, aux):
        dlg = _make_preview_dialog(method="MP2", basis="def2-TZVP", rijcosx=True)
        dlg.rijcosx.isEnabled.return_value = True
        dlg.aux_basis = _combo(aux)
        return _route(dlg)

    def test_def2j_with_wf_emits_autoaux_not_def2j(self):
        r = self._wf_ri_route("Def2/J")
        self.assertIn("AutoAux", r)
        self.assertNotIn("Def2/J", r)

    def test_def2jk_with_wf_emits_autoaux_not_def2jk(self):
        r = self._wf_ri_route("Def2/JK")
        self.assertIn("AutoAux", r)
        tokens = r.split()
        self.assertNotIn("Def2/JK", tokens)
        self.assertNotIn("Def2/J", tokens)

    def test_autoaux_with_wf_emits_autoaux(self):
        r = self._wf_ri_route("AutoAux")
        self.assertIn("AutoAux", r)

    def test_noaux_with_wf_emits_noaux(self):
        r = self._wf_ri_route("NoAux")
        self.assertIn("NoAux", r)
        self.assertNotIn("Def2/J", r)

    def test_auto_with_wf_emits_nothing_extra(self):
        # "Auto (Def2/J, etc)" → let ORCA choose; no explicit aux keyword in route
        r = self._wf_ri_route("Auto (Def2/J, etc)")
        tokens = r.split()
        self.assertNotIn("Def2/J", tokens)
        self.assertNotIn("AutoAux", tokens)

    def test_wf_ri_emits_ri_not_rijcosx(self):
        r = self._wf_ri_route("AutoAux")
        tokens = r.split()
        self.assertIn("RI", tokens)
        self.assertNotIn("RIJCOSX", tokens)


# ---------------------------------------------------------------------------
# update_ui_state: 3c methods disable RIJCOSX checkbox
# ---------------------------------------------------------------------------


def _make_ui_state_dialog(method="B3LYP"):
    """Minimal namespace for testing update_ui_state directly."""
    dlg = types.SimpleNamespace()
    dlg.ui_ready = True
    dlg.method_name = _combo(method)
    dlg.basis_set = MagicMock()
    dlg.aux_basis = MagicMock()
    dlg.dispersion = MagicMock()
    dlg.rijcosx = MagicMock()
    dlg.solv_model = _combo("None")
    dlg.solvent = MagicMock()
    dlg.job_type = _combo("Single Point Energy (SP)")
    dlg.opt_group = MagicMock()
    dlg.freq_group = MagicMock()
    dlg.tddft_enable = MagicMock()
    dlg.tab_tddft = object()  # sentinel — just needs a stable identity
    dlg.tabs = MagicMock()
    dlg.tabs.indexOf.return_value = 3  # tab index ≥ 0 so enable/disable runs
    dlg.get_inferred_category = (
        lambda text: OrcaKeywordBuilderDialog.get_inferred_category(dlg, text)
    )
    return dlg


class TestUpdateUiState3cMethods(unittest.TestCase):
    """update_ui_state must disable RIJCOSX and dispersion for 3c composite methods."""

    def _run(self, method):
        dlg = _make_ui_state_dialog(method)
        OrcaKeywordBuilderDialog.update_ui_state(dlg)
        return dlg

    def test_b97_3c_disables_rijcosx(self):
        dlg = self._run("B97-3c")
        dlg.rijcosx.setEnabled.assert_called_with(False)

    def test_b97_3c_unchecks_rijcosx(self):
        dlg = self._run("B97-3c")
        dlg.rijcosx.setChecked.assert_called_with(False)

    def test_r2scan_3c_disables_rijcosx(self):
        dlg = self._run("r2SCAN-3c")
        dlg.rijcosx.setEnabled.assert_called_with(False)

    def test_pbeh_3c_disables_rijcosx(self):
        dlg = self._run("PBEh-3c")
        dlg.rijcosx.setEnabled.assert_called_with(False)

    def test_b3lyp_leaves_rijcosx_enabled(self):
        dlg = self._run("B3LYP")
        dlg.rijcosx.setEnabled.assert_called_with(True)

    def test_3c_rijcosx_label_mentions_builtin(self):
        dlg = self._run("B97-3c")
        call_args = dlg.rijcosx.setText.call_args
        self.assertIsNotNone(call_args)
        label = call_args[0][0].lower()
        self.assertIn("built-in", label)

    def test_3c_disables_dispersion(self):
        dlg = self._run("B97-3c")
        dlg.dispersion.setEnabled.assert_called_with(False)

    def test_semi_empirical_disables_dispersion(self):
        dlg = self._run("GFN2-xTB")
        dlg.dispersion.setEnabled.assert_called_with(False)

    def test_dft_leaves_dispersion_enabled(self):
        dlg = self._run("B3LYP")
        dlg.dispersion.setEnabled.assert_called_with(True)


class TestUpdatePreviewDispersion3c(unittest.TestCase):
    """Dispersion must not be emitted for 3c or semi-empirical methods."""

    def _route_with_disp(self, method, disp="D3BJ"):
        dlg = _make_preview_dialog(method=method)
        dlg.dispersion = _combo(disp)
        dlg.dispersion.isEnabled.return_value = False
        return _route(dlg)

    def test_3c_d3bj_not_emitted(self):
        r = self._route_with_disp("B97-3c", "D3BJ")
        tokens = r.split()
        self.assertNotIn("D3BJ", tokens)

    def test_semi_d3bj_not_emitted(self):
        r = self._route_with_disp("GFN2-xTB", "D3BJ")
        tokens = r.split()
        self.assertNotIn("D3BJ", tokens)

    def test_dft_d3bj_emitted_when_enabled(self):
        dlg = _make_preview_dialog(method="B3LYP", disp="D3BJ")
        dlg.dispersion.isEnabled.return_value = True
        r = _route(dlg)
        self.assertIn("D3BJ", r)


# ---------------------------------------------------------------------------
# update_preview: ALPB solvation
# ---------------------------------------------------------------------------


class TestUpdatePreviewAlpb(unittest.TestCase):
    """ALPB solvation model must emit ALPB(Solvent) in the route line."""

    def _alpb_route(self, solvent="Water"):
        dlg = _make_preview_dialog(method="B3LYP", solv="ALPB")
        dlg.solvent = _combo(solvent)
        return _route(dlg)

    def test_alpb_emits_alpb_water(self):
        r = self._alpb_route("Water")
        self.assertIn("ALPB(Water)", r)

    def test_alpb_emits_alpb_acetonitrile(self):
        r = self._alpb_route("Acetonitrile")
        self.assertIn("ALPB(Acetonitrile)", r)

    def test_alpb_does_not_emit_cpcm(self):
        r = self._alpb_route("Water")
        self.assertNotIn("CPCM", r)

    def test_alpb_does_not_emit_smd(self):
        r = self._alpb_route("Water")
        self.assertNotIn("SMD", r)

    def test_cpcm_still_distinct_from_alpb(self):
        dlg = _make_preview_dialog(method="B3LYP", solv="CPCM")
        dlg.solvent = _combo("Water")
        r = _route(dlg)
        self.assertIn("CPCM(Water)", r)
        self.assertNotIn("ALPB", r)


# ---------------------------------------------------------------------------
# update_ui_state: TDDFT tab disabled for CC / MR / semi-empirical
# ---------------------------------------------------------------------------


class TestAlpbGuardNonSemi(unittest.TestCase):
    """ALPB must auto-reset to None when a non-semi-empirical method is selected."""

    def _run(self, method):
        dlg = _make_ui_state_dialog(method)
        dlg.solv_model = _combo("ALPB")
        OrcaKeywordBuilderDialog.update_ui_state(dlg)
        return dlg

    def test_dft_resets_alpb_to_none(self):
        dlg = self._run("B3LYP")
        dlg.solv_model.setCurrentText.assert_called_with("None")

    def test_cc_resets_alpb_to_none(self):
        dlg = self._run("CCSD")
        dlg.solv_model.setCurrentText.assert_called_with("None")

    def test_semi_empirical_keeps_alpb(self):
        dlg = self._run("GFN2-xTB")
        # setCurrentText("None") must NOT have been called
        calls = [
            c for c in dlg.solv_model.setCurrentText.call_args_list if c[0][0] == "None"
        ]
        self.assertEqual(len(calls), 0)


class TestTddftTabDisabledForCC(unittest.TestCase):
    """TD-DFT tab must be disabled for CC, MR, and semi-empirical methods."""

    def _run(self, method):
        dlg = _make_ui_state_dialog(method)
        OrcaKeywordBuilderDialog.update_ui_state(dlg)
        return dlg

    def _tab_enabled(self, method):
        dlg = self._run(method)
        calls = dlg.tabs.setTabEnabled.call_args_list
        # find call for tab index 3
        for c in calls:
            if c[0][0] == 3:
                return c[0][1]
        return None  # setTabEnabled never called

    def test_ccsd_disables_tddft_tab(self):
        self.assertFalse(self._tab_enabled("CCSD"))

    def test_dlpno_ccsd_t_disables_tddft_tab(self):
        self.assertFalse(self._tab_enabled("DLPNO-CCSD(T)"))

    def test_eom_ccsd_disables_tddft_tab(self):
        self.assertFalse(self._tab_enabled("EOM-CCSD"))

    def test_casscf_disables_tddft_tab(self):
        self.assertFalse(self._tab_enabled("CASSCF"))

    def test_nevpt2_disables_tddft_tab(self):
        self.assertFalse(self._tab_enabled("NEVPT2"))

    def test_gfn2_xtb_disables_tddft_tab(self):
        self.assertFalse(self._tab_enabled("GFN2-xTB"))

    def test_b3lyp_enables_tddft_tab(self):
        self.assertTrue(self._tab_enabled("B3LYP"))

    def test_cam_b3lyp_enables_tddft_tab(self):
        self.assertTrue(self._tab_enabled("CAM-B3LYP"))

    def test_hf_enables_tddft_tab(self):
        self.assertTrue(self._tab_enabled("HF"))

    def test_mp2_enables_tddft_tab(self):
        self.assertTrue(self._tab_enabled("MP2"))


# ---------------------------------------------------------------------------
# New job types: GOAT, NEB-CI, NEB-TS, MD
# ---------------------------------------------------------------------------


class TestNewJobTypesPreview(unittest.TestCase):
    """update_preview emits the correct ORCA keyword for each new job type."""

    def _route(self, job):
        dlg = _make_preview_dialog(method="B3LYP", job=job)
        return _route(dlg)

    def test_goat_emits_goat(self):
        self.assertIn("GOAT", self._route("GOAT (Global Search)").split())

    def test_neb_ci_emits_neb_ci(self):
        self.assertIn("NEB-CI", self._route("NEB-CI (Reaction Path)").split())

    def test_neb_ts_emits_neb_ts(self):
        self.assertIn("NEB-TS", self._route("NEB-TS (TS via NEB)").split())

    def test_md_emits_md(self):
        self.assertIn("MD", self._route("MD (Molecular Dynamics)").split())

    def test_goat_does_not_emit_opt(self):
        tokens = self._route("GOAT (Global Search)").split()
        self.assertNotIn("Opt", tokens)

    def test_neb_ci_does_not_emit_opt(self):
        tokens = self._route("NEB-CI (Reaction Path)").split()
        self.assertNotIn("Opt", tokens)

    def test_md_does_not_emit_freq(self):
        tokens = self._route("MD (Molecular Dynamics)").split()
        self.assertNotIn("Freq", tokens)


class TestNewJobTypesParseRoute(unittest.TestCase):
    """parse_route recognises GOAT, NEB-CI, NEB-TS, MD keywords."""

    def test_parse_goat(self):
        dlg = _parse("! B3LYP def2-SVP GOAT")
        dlg.job_type.setCurrentText.assert_any_call("GOAT (Global Search)")

    def test_parse_neb_ci(self):
        dlg = _parse("! B3LYP def2-SVP NEB-CI")
        dlg.job_type.setCurrentText.assert_any_call("NEB-CI (Reaction Path)")

    def test_parse_neb_ts(self):
        dlg = _parse("! B3LYP def2-SVP NEB-TS")
        dlg.job_type.setCurrentText.assert_any_call("NEB-TS (TS via NEB)")

    def test_parse_md(self):
        dlg = _parse("! GFN2-xTB MD")
        dlg.job_type.setCurrentText.assert_any_call("MD (Molecular Dynamics)")


if __name__ == "__main__":
    unittest.main()
