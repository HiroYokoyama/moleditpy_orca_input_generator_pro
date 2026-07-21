"""
tests/test_keyword_builder_extended.py

Additional coverage for OrcaKeywordBuilderDialog in keyword_builder.py, focused
on areas not exercised by tests/test_keyword_builder.py or
tests/test_parse_route_extended.py:

  - setup_ui() / setup_*_tab() builders + connect_signals() (structural
    coverage: widgets get created and wired)
  - update_method_list() across every method-type category
  - update_ui_state() enable/disable + visibility branches
  - enforce_scf_mutual_exclusion / enforce_slowconv_mutual_exclusion /
    enforce_opt_mutual_exclusion
  - Constraint table plumbing: add_constraint, remove_constraint,
    clear_all_constraints, _capture_constraints/_restore_constraints,
    store_state/restore_state, on_scan_checkbox_state_changed,
    _add_parsed_constraint, on_atom_picked, clear_selection,
    update_selection_display
  - get_route()
  - update_preview() branches not covered elsewhere (F12/DLPNO/relativistic/
    population/property/verbosity/RI/spin-orbit/broken-symmetry/MOREAD
    keywords, NEB/MD/IRC/EnGrad/NumGrad/NumHess/ESD/GOAT job types, Freq
    sub-options)
  - get_extra_blocks_text() SCF-guess / broken-symmetry / MOREAD blocks
"""

import contextlib
import os
import sys
import types
import importlib.util
import unittest
from unittest.mock import MagicMock

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Qt / RDKit stubs (same pattern as test_keyword_builder.py)
# ---------------------------------------------------------------------------


class _Base:
    def __init__(self, *args, **kwargs):
        pass


def _install_stubs():
    if "PyQt6" in sys.modules:
        return

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


def _load_module(name, relpath):
    full_name = f"orca_input_generator_pro.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    path = os.path.join(_REPO_ROOT, "orca_input_generator_pro", relpath)
    spec = importlib.util.spec_from_file_location(full_name, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "orca_input_generator_pro"
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


_constants = _load_module("constants", "constants.py")
sys.modules["orca_input_generator_pro.constants"] = _constants

_mixins_mod = sys.modules.get("orca_input_generator_pro.mixins")
if _mixins_mod is None:
    _mixins_mod = types.ModuleType("orca_input_generator_pro.mixins")

    class _FakeMixin:
        def __init__(self):
            self.selection_labels = []

        def enable_picking(self):
            pass

        def disable_picking(self):
            pass

        def clear_selection_labels(self):
            pass

        def show_atom_labels_for(self, *a, **k):
            pass

    _mixins_mod.Dialog3DPickingMixin = _FakeMixin
    sys.modules["orca_input_generator_pro.mixins"] = _mixins_mod

_builder_mod = _load_module("keyword_builder", "keyword_builder.py")
OrcaKeywordBuilderDialog = _builder_mod.OrcaKeywordBuilderDialog


@contextlib.contextmanager
def _patch_builder(**kwargs):
    """Temporarily replace module-level names in keyword_builder.py."""
    orig = {}
    for k, v in kwargs.items():
        orig[k] = getattr(_builder_mod, k)
        setattr(_builder_mod, k, v)
    try:
        yield
    finally:
        for k, v in orig.items():
            setattr(_builder_mod, k, v)


# ---------------------------------------------------------------------------
# Lightweight fake widgets with real internal state (unlike bare MagicMock)
# ---------------------------------------------------------------------------


class _FakeCombo:
    def __init__(self, items=None, editable=True):
        self._items = list(items or [])
        self._index = 0 if self._items else -1
        self._editable = editable
        self._enabled = True

    def addItems(self, items):
        self._items.extend(items)
        if self._index == -1 and self._items:
            self._index = 0

    def addItem(self, item):
        self._items.append(item)
        if self._index == -1:
            self._index = 0

    def clear(self):
        self._items = []
        self._index = -1

    def count(self):
        return len(self._items)

    def currentText(self):
        if 0 <= self._index < len(self._items):
            return self._items[self._index]
        return ""

    def setCurrentText(self, text):
        if text in self._items:
            self._index = self._items.index(text)
        else:
            self._items.append(text)
            self._index = len(self._items) - 1

    def setCurrentIndex(self, i):
        self._index = i

    def currentIndex(self):
        return self._index

    def itemText(self, i):
        return self._items[i]

    def blockSignals(self, b):
        pass

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, v):
        self._enabled = v

    def isEditable(self):
        return self._editable


class _FakeCheck:
    def __init__(self, checked=False, enabled=True):
        self._checked = checked
        self._enabled = enabled
        self._text = ""

    def isChecked(self):
        return self._checked

    def setChecked(self, v):
        self._checked = bool(v)

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, v):
        self._enabled = v

    def setText(self, t):
        self._text = t

    def text(self):
        return self._text

    def blockSignals(self, b):
        pass


class _FakeVisible:
    def __init__(self, visible=False):
        self._visible = visible

    def setVisible(self, v):
        self._visible = v

    def isVisible(self):
        return self._visible


class _FakeTabs:
    def __init__(self):
        self._enabled = {}

    def indexOf(self, widget):
        return 0

    def setTabEnabled(self, idx, enabled):
        self._enabled[idx] = enabled

    def isTabEnabled(self, idx):
        return self._enabled.get(idx, True)


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


# ---------------------------------------------------------------------------
# Full dialog builder for update_ui_state()/update_preview() interplay
# ---------------------------------------------------------------------------


def _ui_dialog(method="B3LYP", job="Single Point Energy (SP)", solv_model="None"):
    dlg = types.SimpleNamespace()
    dlg.ui_ready = True

    dlg.method_name = _FakeCombo([method])
    dlg.basis_set = _FakeCombo(["def2-SVP"])
    dlg.aux_basis = _FakeCombo(["Auto (Def2/J, etc)"])
    dlg.dispersion = _FakeCombo(["None"])
    dlg.rijcosx = _FakeCheck(False)
    dlg.solv_model = _FakeCombo([solv_model])
    dlg.solvent = _FakeCombo(["Water"])
    dlg.job_type = _FakeCombo([job])
    dlg.opt_group = _FakeVisible()
    dlg.freq_group = _FakeVisible()
    dlg.neb_group = _FakeVisible()
    dlg.cabs_basis = _FakeCombo(["None"])
    dlg.pno_preset = _FakeCombo(["Default"])
    dlg.tabs = _FakeTabs()
    dlg.tab_tddft = object()
    dlg.tddft_enable = _FakeCheck(False)

    dlg.get_inferred_category = lambda text: OrcaKeywordBuilderDialog.get_inferred_category(
        dlg, text
    )
    return dlg


def _run_update_ui_state(dlg):
    OrcaKeywordBuilderDialog.update_ui_state(dlg)
    return dlg


# ===========================================================================
# 1. setup_ui / setup_*_tab / connect_signals -- structural coverage
# ===========================================================================


class _AutoAttrMeta(type):
    """Lets `ClassName.SomeEnum.Value` class-attribute chains (e.g.
    QSizePolicy.Policy.Expanding) resolve to auto-generated mocks, mirroring
    how MagicMock already does this for instances."""

    def __getattr__(cls, name):
        return MagicMock()


class _SafeMock(MagicMock, metaclass=_AutoAttrMeta):
    """MagicMock that ignores constructor args (real Qt widgets take a text/
    parent arg positionally, which unittest.mock would otherwise interpret
    as `spec=`, crippling the resulting mock)."""

    def __init__(self, *a, **k):
        super().__init__()


class _ComboMock(_SafeMock):
    pass


class _CheckMock(_SafeMock):
    pass


class _SpinMock(_SafeMock):
    pass


class _TextEditMock(_SafeMock):
    pass


class _PlainTextEditMock(_SafeMock):
    pass


# All widget/layout classes touched by setup_ui()/setup_*_tab()/connect_signals(),
# patched uniformly so these structural tests behave the same whether the
# ambient PyQt6 in sys.modules is the real bindings or another test file's stub.
_STRUCTURAL_PATCH = dict(
    QVBoxLayout=_SafeMock,
    QLabel=_SafeMock,
    QLineEdit=_SafeMock,
    QSpinBox=_SpinMock,
    QPushButton=_SafeMock,
    QGroupBox=_SafeMock,
    QHBoxLayout=_SafeMock,
    QComboBox=_ComboMock,
    QTextEdit=_TextEditMock,
    QTabWidget=_SafeMock,
    QCheckBox=_CheckMock,
    QWidget=_SafeMock,
    QFormLayout=_SafeMock,
    QTableWidget=_SafeMock,
    QCompleter=_SafeMock,
    QPlainTextEdit=_PlainTextEditMock,
    QGridLayout=_SafeMock,
    QSizePolicy=_SafeMock,
    QScrollArea=_SafeMock,
)


class TestSetupUiStructural(unittest.TestCase):
    """Runs the real widget-builder methods; only checks they complete and
    populate the expected attributes (statement coverage for the GUI
    construction code, which is otherwise entirely unexercised)."""

    def _new_dialog(self):
        dlg = types.SimpleNamespace()
        dlg.tab_job = MagicMock()
        dlg.tab_method = MagicMock()
        dlg.tab_solvation = MagicMock()
        dlg.tab_tddft = MagicMock()
        dlg.tab_constraints = MagicMock()
        dlg.tab_props = MagicMock()
        dlg.tabs = MagicMock()
        dlg.update_ui_state = MagicMock()
        dlg.update_preview = MagicMock()
        dlg.update_method_list = MagicMock()
        dlg.setup_job_tab = lambda: OrcaKeywordBuilderDialog.setup_job_tab(dlg)
        dlg.setup_method_tab = lambda: OrcaKeywordBuilderDialog.setup_method_tab(dlg)
        dlg.setup_solvation_tab = lambda: OrcaKeywordBuilderDialog.setup_solvation_tab(
            dlg
        )
        dlg.setup_tddft_tab = lambda: OrcaKeywordBuilderDialog.setup_tddft_tab(dlg)
        dlg.setup_constraints_tab = (
            lambda: OrcaKeywordBuilderDialog.setup_constraints_tab(dlg)
        )
        dlg.setup_props_tab = lambda: OrcaKeywordBuilderDialog.setup_props_tab(dlg)
        dlg.connect_signals = lambda: OrcaKeywordBuilderDialog.connect_signals(dlg)
        dlg.add_constraint = MagicMock()
        dlg.remove_constraint = MagicMock()
        dlg.clear_all_constraints = MagicMock()
        dlg.update_selection_display = MagicMock()
        dlg.enforce_scf_mutual_exclusion = MagicMock()
        dlg.enforce_slowconv_mutual_exclusion = MagicMock()
        dlg.enforce_opt_mutual_exclusion = MagicMock()
        dlg.on_tab_changed = MagicMock()
        dlg.reject = MagicMock()
        dlg.accept = MagicMock()
        dlg.setLayout = MagicMock()
        return dlg

    def test_setup_method_tab_populates_widgets(self):
        with _patch_builder(**_STRUCTURAL_PATCH):
            dlg = self._new_dialog()
            OrcaKeywordBuilderDialog.setup_method_tab(dlg)
        self.assertTrue(hasattr(dlg, "method_type"))
        self.assertTrue(hasattr(dlg, "method_name"))
        self.assertTrue(hasattr(dlg, "basis_set"))
        self.assertTrue(hasattr(dlg, "aux_basis"))
        self.assertTrue(hasattr(dlg, "cabs_basis"))
        dlg.update_method_list.assert_called()

    def test_setup_job_tab_populates_widgets(self):
        with _patch_builder(**_STRUCTURAL_PATCH):
            dlg = self._new_dialog()
            OrcaKeywordBuilderDialog.setup_job_tab(dlg)
        self.assertTrue(hasattr(dlg, "job_type"))
        self.assertTrue(hasattr(dlg, "scf_group"))
        self.assertTrue(hasattr(dlg, "opt_group"))
        self.assertTrue(hasattr(dlg, "freq_group"))
        self.assertTrue(hasattr(dlg, "neb_group"))
        self.assertTrue(hasattr(dlg, "iter256_chk"))

    def test_setup_solvation_tab_populates_widgets(self):
        with _patch_builder(**_STRUCTURAL_PATCH):
            dlg = self._new_dialog()
            OrcaKeywordBuilderDialog.setup_solvation_tab(dlg)
        self.assertTrue(hasattr(dlg, "solv_model"))
        self.assertTrue(hasattr(dlg, "solvent"))
        self.assertTrue(hasattr(dlg, "dispersion"))

    def test_setup_props_tab_populates_widgets(self):
        with _patch_builder(**_STRUCTURAL_PATCH):
            dlg = self._new_dialog()
            OrcaKeywordBuilderDialog.setup_props_tab(dlg)
        self.assertTrue(hasattr(dlg, "rijcosx"))
        self.assertTrue(hasattr(dlg, "grid_combo"))
        self.assertTrue(hasattr(dlg, "bs_chk"))
        self.assertTrue(hasattr(dlg, "moread_file"))
        self.assertTrue(hasattr(dlg, "cosx_chk"))

    def test_setup_tddft_tab_populates_widgets(self):
        with _patch_builder(**_STRUCTURAL_PATCH):
            dlg = self._new_dialog()
            OrcaKeywordBuilderDialog.setup_tddft_tab(dlg)
        self.assertTrue(hasattr(dlg, "tddft_enable"))
        self.assertTrue(hasattr(dlg, "tddft_nroots"))
        self.assertTrue(hasattr(dlg, "tddft_tda"))

    def test_setup_constraints_tab_populates_widgets(self):
        with _patch_builder(**_STRUCTURAL_PATCH):
            dlg = self._new_dialog()
            OrcaKeywordBuilderDialog.setup_constraints_tab(dlg)
        self.assertTrue(hasattr(dlg, "constraint_table"))
        self.assertTrue(hasattr(dlg, "btn_add_const"))
        self.assertTrue(hasattr(dlg, "btn_remove_const"))
        self.assertTrue(hasattr(dlg, "btn_clear_const"))

    def test_setup_ui_full_flow_runs_to_completion(self):
        with _patch_builder(**_STRUCTURAL_PATCH):
            dlg = self._new_dialog()
            # setup_ui creates its own tab_* widgets, so drop the pre-set ones
            for attr in [
                "tab_job",
                "tab_method",
                "tab_solvation",
                "tab_tddft",
                "tab_constraints",
                "tab_props",
                "tabs",
            ]:
                delattr(dlg, attr)
            OrcaKeywordBuilderDialog.setup_ui(dlg)
        self.assertTrue(dlg.ui_ready)
        dlg.update_ui_state.assert_called()
        dlg.update_preview.assert_called()

    def test_connect_signals_wires_mutual_exclusion(self):
        with _patch_builder(**_STRUCTURAL_PATCH):
            dlg = self._new_dialog()
            OrcaKeywordBuilderDialog.setup_method_tab(dlg)
            OrcaKeywordBuilderDialog.setup_job_tab(dlg)
            OrcaKeywordBuilderDialog.setup_solvation_tab(dlg)
            OrcaKeywordBuilderDialog.setup_props_tab(dlg)
            OrcaKeywordBuilderDialog.setup_tddft_tab(dlg)
            OrcaKeywordBuilderDialog.connect_signals(dlg)

        # SCF exclusivity boxes wire `clicked` to enforce_scf_mutual_exclusion
        dlg.scf_sloppy.clicked.connect.assert_any_call(dlg.enforce_scf_mutual_exclusion)
        dlg.scf_tight.clicked.connect.assert_any_call(dlg.enforce_scf_mutual_exclusion)
        # SlowConv exclusivity
        dlg.scf_slowconv.clicked.connect.assert_any_call(
            dlg.enforce_slowconv_mutual_exclusion
        )
        # Opt convergence exclusivity
        dlg.opt_tight.clicked.connect.assert_any_call(dlg.enforce_opt_mutual_exclusion)
        dlg.opt_loose.clicked.connect.assert_any_call(dlg.enforce_opt_mutual_exclusion)
        # Editable combo also connects currentTextChanged
        dlg.method_name._editable = True
        # Plain checkboxes get toggled -> update_preview
        dlg.pop_nbo.toggled.connect.assert_any_call(dlg.update_preview)
        # Spin boxes get valueChanged -> update_preview
        dlg.tddft_nroots.valueChanged.connect.assert_any_call(dlg.update_preview)
        # Line edits wired at the end of connect_signals
        dlg.moread_file.textChanged.connect.assert_any_call(dlg.update_preview)
        dlg.bs_spins.textChanged.connect.assert_any_call(dlg.update_preview)


# ===========================================================================
# 2. update_method_list()
# ===========================================================================


class TestUpdateMethodList(unittest.TestCase):
    def _dlg(self, mtype, current_text=""):
        dlg = types.SimpleNamespace()
        dlg.method_type = _FakeCombo([mtype])
        dlg.method_name = _FakeCombo([current_text] if current_text else [])
        if current_text:
            dlg.method_name.setCurrentText(current_text)
        dlg.update_ui_state = lambda: None
        dlg.update_preview = lambda: None
        return dlg

    def test_gga_hybrid_populates_and_resets_index(self):
        dlg = self._dlg("DFT (GGA/Hybrid/Meta)", current_text="XTB2")
        OrcaKeywordBuilderDialog.update_method_list(dlg)
        self.assertIn("B3LYP", dlg.method_name._items)
        self.assertEqual(dlg.method_name.currentText(), "B3LYP")

    def test_range_separated_populates(self):
        dlg = self._dlg("DFT (Range-Separated)")
        OrcaKeywordBuilderDialog.update_method_list(dlg)
        self.assertIn("CAM-B3LYP", dlg.method_name._items)

    def test_double_hybrid_populates(self):
        dlg = self._dlg("DFT (Double Hybrid)")
        OrcaKeywordBuilderDialog.update_method_list(dlg)
        self.assertIn("B2PLYP", dlg.method_name._items)

    def test_hf_mp2_populates(self):
        dlg = self._dlg("Wavefunction (HF/MP2)")
        OrcaKeywordBuilderDialog.update_method_list(dlg)
        self.assertIn("MP2", dlg.method_name._items)

    def test_coupled_cluster_populates(self):
        dlg = self._dlg("Wavefunction (Coupled Cluster)")
        OrcaKeywordBuilderDialog.update_method_list(dlg)
        self.assertIn("CCSD(T)", dlg.method_name._items)

    def test_multireference_populates(self):
        dlg = self._dlg("Wavefunction (Multireference)")
        OrcaKeywordBuilderDialog.update_method_list(dlg)
        self.assertIn("CASSCF", dlg.method_name._items)

    def test_semi_empirical_populates(self):
        dlg = self._dlg("Semi-Empirical")
        OrcaKeywordBuilderDialog.update_method_list(dlg)
        self.assertIn("XTB2", dlg.method_name._items)

    def test_all_methods_preserves_current_text(self):
        dlg = self._dlg("All Methods", current_text="PBE0")
        OrcaKeywordBuilderDialog.update_method_list(dlg)
        self.assertEqual(dlg.method_name.currentText(), "PBE0")

    def test_all_methods_no_current_text_keeps_default_index(self):
        dlg = self._dlg("All Methods")
        OrcaKeywordBuilderDialog.update_method_list(dlg)
        # No prior text: first item should be selected by default
        self.assertGreater(dlg.method_name.count(), 0)


# ===========================================================================
# 3. update_ui_state()
# ===========================================================================


class TestUpdateUiState(unittest.TestCase):
    def test_semi_empirical_disables_basis_and_dispersion(self):
        dlg = _ui_dialog(method="XTB2")
        _run_update_ui_state(dlg)
        self.assertFalse(dlg.basis_set.isEnabled())
        self.assertFalse(dlg.aux_basis.isEnabled())
        self.assertFalse(dlg.dispersion.isEnabled())
        self.assertFalse(dlg.rijcosx.isEnabled())
        self.assertFalse(dlg.rijcosx.isChecked())

    def test_3c_method_disables_basis(self):
        dlg = _ui_dialog(method="B97-3c")
        _run_update_ui_state(dlg)
        self.assertFalse(dlg.basis_set.isEnabled())
        self.assertIn("built-in", dlg.rijcosx.text())

    def test_normal_dft_enables_basis_and_rijcosx(self):
        dlg = _ui_dialog(method="B3LYP")
        _run_update_ui_state(dlg)
        self.assertTrue(dlg.basis_set.isEnabled())
        self.assertTrue(dlg.rijcosx.isEnabled())
        self.assertIn("RIJCOSX", dlg.rijcosx.text())

    def test_wavefunction_rijcosx_label_says_ri(self):
        dlg = _ui_dialog(method="MP2")
        _run_update_ui_state(dlg)
        self.assertIn("RI", dlg.rijcosx.text())

    def test_alpb_reset_for_non_semi_empirical(self):
        dlg = _ui_dialog(method="B3LYP", solv_model="ALPB")
        _run_update_ui_state(dlg)
        self.assertEqual(dlg.solv_model.currentText(), "None")

    def test_alpb_kept_for_semi_empirical(self):
        dlg = _ui_dialog(method="XTB2", solv_model="ALPB")
        _run_update_ui_state(dlg)
        self.assertEqual(dlg.solv_model.currentText(), "ALPB")

    def test_cpc_water_disables_solvent(self):
        dlg = _ui_dialog(solv_model="CPC(Water) (Short)")
        _run_update_ui_state(dlg)
        self.assertFalse(dlg.solvent.isEnabled())

    def test_none_solvation_disables_solvent(self):
        dlg = _ui_dialog(solv_model="None")
        _run_update_ui_state(dlg)
        self.assertFalse(dlg.solvent.isEnabled())

    def test_solvated_enables_solvent(self):
        dlg = _ui_dialog(solv_model="CPCM")
        _run_update_ui_state(dlg)
        self.assertTrue(dlg.solvent.isEnabled())

    def test_opt_job_shows_opt_group_and_hides_freq(self):
        dlg = _ui_dialog(job="Optimization Only (Opt)")
        _run_update_ui_state(dlg)
        self.assertTrue(dlg.opt_group.isVisible())
        self.assertFalse(dlg.freq_group.isVisible())

    def test_freq_job_shows_freq_group(self):
        dlg = _ui_dialog(job="Frequency Only (Freq)")
        _run_update_ui_state(dlg)
        self.assertTrue(dlg.freq_group.isVisible())
        self.assertFalse(dlg.opt_group.isVisible())

    def test_neb_job_shows_neb_group(self):
        dlg = _ui_dialog(job="NEB (Nudged Elastic Band)")
        _run_update_ui_state(dlg)
        self.assertTrue(dlg.neb_group.isVisible())

    def test_scan_job_treated_as_opt(self):
        dlg = _ui_dialog(job="Scan (Relaxed Surface)")
        _run_update_ui_state(dlg)
        self.assertTrue(dlg.opt_group.isVisible())

    def test_f12_method_enables_cabs_basis(self):
        dlg = _ui_dialog(method="CCSD(T)-F12")
        _run_update_ui_state(dlg)
        self.assertTrue(dlg.cabs_basis.isEnabled())

    def test_non_f12_method_disables_cabs_basis(self):
        dlg = _ui_dialog(method="B3LYP")
        _run_update_ui_state(dlg)
        self.assertFalse(dlg.cabs_basis.isEnabled())

    def test_dlpno_method_enables_pno_preset(self):
        dlg = _ui_dialog(method="DLPNO-CCSD(T)")
        _run_update_ui_state(dlg)
        self.assertTrue(dlg.pno_preset.isEnabled())

    def test_non_dlpno_disables_pno_preset(self):
        dlg = _ui_dialog(method="B3LYP")
        _run_update_ui_state(dlg)
        self.assertFalse(dlg.pno_preset.isEnabled())

    def test_dft_method_enables_tddft_tab(self):
        dlg = _ui_dialog(method="B3LYP")
        _run_update_ui_state(dlg)
        self.assertTrue(dlg.tabs.isTabEnabled(0))

    def test_cc_method_disables_tddft_tab_and_unchecks(self):
        dlg = _ui_dialog(method="CCSD(T)")
        dlg.tddft_enable = _FakeCheck(True)
        _run_update_ui_state(dlg)
        self.assertFalse(dlg.tabs.isTabEnabled(0))
        self.assertFalse(dlg.tddft_enable.isChecked())

    def test_not_ui_ready_is_noop(self):
        dlg = _ui_dialog(method="B3LYP")
        dlg.ui_ready = False
        # Sabotage a widget so any real work would raise
        dlg.basis_set = None
        OrcaKeywordBuilderDialog.update_ui_state(dlg)  # must not raise


# ===========================================================================
# 4. Mutual exclusion enforcers
# ===========================================================================


class TestMutualExclusion(unittest.TestCase):
    def _scf_dlg(self):
        dlg = types.SimpleNamespace()
        for name in [
            "scf_sloppy",
            "scf_loose",
            "scf_normal",
            "scf_strong",
            "scf_tight",
            "scf_verytight",
            "scf_extreme",
        ]:
            setattr(dlg, name, _FakeCheck(False))
        dlg.update_preview = lambda: None
        return dlg

    def test_checking_one_scf_box_unchecks_others(self):
        dlg = self._scf_dlg()
        dlg.scf_tight.setChecked(True)
        dlg.sender = lambda: dlg.scf_tight
        OrcaKeywordBuilderDialog.enforce_scf_mutual_exclusion(dlg)
        self.assertTrue(dlg.scf_tight.isChecked())
        for name in ["scf_sloppy", "scf_loose", "scf_normal", "scf_strong",
                     "scf_verytight", "scf_extreme"]:
            self.assertFalse(getattr(dlg, name).isChecked())

    def test_unchecking_sender_is_noop(self):
        dlg = self._scf_dlg()
        dlg.scf_loose.setChecked(True)
        dlg.scf_tight.setChecked(False)
        dlg.sender = lambda: dlg.scf_tight
        OrcaKeywordBuilderDialog.enforce_scf_mutual_exclusion(dlg)
        # scf_tight is unchecked -> function returns early, scf_loose untouched
        self.assertTrue(dlg.scf_loose.isChecked())

    def test_slowconv_mutual_exclusion(self):
        dlg = types.SimpleNamespace()
        dlg.scf_slowconv = _FakeCheck(True)
        dlg.scf_veryslowconv = _FakeCheck(True)
        dlg.update_preview = lambda: None
        dlg.sender = lambda: dlg.scf_slowconv
        OrcaKeywordBuilderDialog.enforce_slowconv_mutual_exclusion(dlg)
        self.assertTrue(dlg.scf_slowconv.isChecked())
        self.assertFalse(dlg.scf_veryslowconv.isChecked())

    def test_opt_mutual_exclusion(self):
        dlg = types.SimpleNamespace()
        dlg.opt_tight = _FakeCheck(False)
        dlg.opt_verytight = _FakeCheck(True)
        dlg.opt_loose = _FakeCheck(True)
        dlg.update_preview = lambda: None
        dlg.sender = lambda: dlg.opt_loose
        OrcaKeywordBuilderDialog.enforce_opt_mutual_exclusion(dlg)
        self.assertTrue(dlg.opt_loose.isChecked())
        self.assertFalse(dlg.opt_verytight.isChecked())


# ===========================================================================
# 5. Constraint table plumbing
# ===========================================================================


class _Idx:
    def __init__(self, row):
        self._row = row

    def row(self):
        return self._row


class _FakeItem:
    def __init__(self, text=""):
        self._text = text
        self._flags = 0
        self._fg = None

    def text(self):
        return self._text

    def setText(self, t):
        self._text = t

    def setTextAlignment(self, *a, **k):
        pass

    def flags(self):
        return self._flags

    def setFlags(self, f):
        self._flags = f

    def setForeground(self, c):
        self._fg = c


class _FakeCheckBoxWidget:
    def __init__(self):
        self._checked = False
        self._callbacks = []

    def isChecked(self):
        return self._checked

    def setChecked(self, v):
        v = bool(v)
        changed = v != self._checked
        self._checked = v
        if changed:
            for cb in self._callbacks:
                cb()

    class _Signal:
        def __init__(self, owner):
            self._owner = owner

        def connect(self, fn):
            self._owner._callbacks.append(fn)

    @property
    def stateChanged(self):
        return _FakeCheckBoxWidget._Signal(self)


class _FakeContainerWidget:
    def __init__(self, *a, **k):
        self._child = None

    def findChild(self, cls):
        return self._child


class _FakeHBoxLayout:
    def __init__(self, parent=None):
        self._parent = parent

    def addWidget(self, w):
        if self._parent is not None:
            self._parent._child = w

    def setAlignment(self, *a, **k):
        pass

    def setContentsMargins(self, *a, **k):
        pass


class _FakeQt:
    class AlignmentFlag:
        AlignCenter = 1

    class ItemFlag:
        ItemIsEnabled = 2

    class GlobalColor:
        black = "black"
        gray = "gray"


class _FakeTable:
    def __init__(self):
        self._rows = []
        self.selected_rows = []

    def rowCount(self):
        return len(self._rows)

    def setRowCount(self, n):
        if n == 0:
            self._rows = []
        else:
            self._rows = self._rows[:n]

    def insertRow(self, row):
        self._rows.insert(row, {"items": {}, "widget": None})

    def removeRow(self, row):
        del self._rows[row]

    def setItem(self, row, col, item):
        self._rows[row]["items"][col] = item

    def item(self, row, col):
        return self._rows[row]["items"].get(col)

    def setCellWidget(self, row, col, widget):
        self._rows[row]["widget"] = widget

    def cellWidget(self, row, col):
        return self._rows[row]["widget"]

    def selectedIndexes(self):
        out = []
        for r in self.selected_rows:
            out.append(_Idx(r))
        return out


_CONSTRAINT_PATCH = dict(
    QTableWidgetItem=_FakeItem,
    QCheckBox=_FakeCheckBoxWidget,
    QWidget=_FakeContainerWidget,
    QHBoxLayout=_FakeHBoxLayout,
    Qt=_FakeQt,
)


def _constraints_dialog(mol=None):
    dlg = types.SimpleNamespace()
    dlg.constraint_table = _FakeTable()
    dlg.selected_atoms = []
    dlg.mol = mol
    dlg.selection_label = MagicMock()
    dlg.btn_add_const = MagicMock()
    dlg.ui_ready = True
    dlg.job_type = _FakeCombo(["Single Point Energy (SP)"])
    dlg.show_atom_labels_for = lambda *a, **k: None
    dlg.update_preview = lambda: None
    dlg.update_selection_display = (
        lambda: OrcaKeywordBuilderDialog.update_selection_display(dlg)
    )
    dlg.on_scan_checkbox_state_changed = (
        lambda r, chk: OrcaKeywordBuilderDialog.on_scan_checkbox_state_changed(
            dlg, r, chk
        )
    )
    return dlg


class TestConstraintTablePlumbing(unittest.TestCase):
    def test_add_constraint_position(self):
        with _patch_builder(**_CONSTRAINT_PATCH):
            fake_mol = MagicMock()
            dlg = _constraints_dialog(mol=fake_mol)
            dlg.selected_atoms = [3]
            OrcaKeywordBuilderDialog.add_constraint(dlg)
        self.assertEqual(dlg.constraint_table.rowCount(), 1)
        self.assertEqual(dlg.constraint_table.item(0, 0).text(), "Position")
        self.assertEqual(dlg.constraint_table.item(0, 1).text(), "3")
        self.assertEqual(dlg.selected_atoms, [])

    def test_add_constraint_distance_uses_bond_length(self):
        with _patch_builder(rdMolTransforms=MagicMock(), **_CONSTRAINT_PATCH):
            _builder_mod.rdMolTransforms.GetBondLength.return_value = 1.234
            fake_mol = MagicMock()
            dlg = _constraints_dialog(mol=fake_mol)
            dlg.selected_atoms = [0, 1]
            OrcaKeywordBuilderDialog.add_constraint(dlg)
        self.assertEqual(dlg.constraint_table.item(0, 0).text(), "Distance")
        self.assertEqual(dlg.constraint_table.item(0, 2).text(), "1.234")

    def test_add_constraint_angle_uses_angle_deg(self):
        with _patch_builder(rdMolTransforms=MagicMock(), **_CONSTRAINT_PATCH):
            _builder_mod.rdMolTransforms.GetAngleDeg.return_value = 109.471
            dlg = _constraints_dialog(mol=MagicMock())
            dlg.selected_atoms = [0, 1, 2]
            OrcaKeywordBuilderDialog.add_constraint(dlg)
        self.assertEqual(dlg.constraint_table.item(0, 0).text(), "Angle")
        self.assertEqual(dlg.constraint_table.item(0, 2).text(), "109.471")

    def test_add_constraint_dihedral_uses_dihedral_deg(self):
        with _patch_builder(rdMolTransforms=MagicMock(), **_CONSTRAINT_PATCH):
            _builder_mod.rdMolTransforms.GetDihedralDeg.return_value = 180.0
            dlg = _constraints_dialog(mol=MagicMock())
            dlg.selected_atoms = [0, 1, 2, 3]
            OrcaKeywordBuilderDialog.add_constraint(dlg)
        self.assertEqual(dlg.constraint_table.item(0, 0).text(), "Dihedral")
        self.assertEqual(dlg.constraint_table.item(0, 2).text(), "180.000")

    def test_add_constraint_noop_without_mol(self):
        with _patch_builder(**_CONSTRAINT_PATCH):
            dlg = _constraints_dialog(mol=None)
            dlg.selected_atoms = [1, 2]
            OrcaKeywordBuilderDialog.add_constraint(dlg)
        self.assertEqual(dlg.constraint_table.rowCount(), 0)

    def test_add_constraint_noop_without_selection(self):
        with _patch_builder(**_CONSTRAINT_PATCH):
            dlg = _constraints_dialog(mol=MagicMock())
            dlg.selected_atoms = []
            OrcaKeywordBuilderDialog.add_constraint(dlg)
        self.assertEqual(dlg.constraint_table.rowCount(), 0)

    def test_scan_checkbox_switches_job_to_scan(self):
        with _patch_builder(rdMolTransforms=MagicMock(), **_CONSTRAINT_PATCH):
            _builder_mod.rdMolTransforms.GetBondLength.return_value = 1.5
            dlg = _constraints_dialog(mol=MagicMock())
            dlg.selected_atoms = [0, 1]
            OrcaKeywordBuilderDialog.add_constraint(dlg)
            chk_widget = dlg.constraint_table.cellWidget(0, 3)
            chk = chk_widget.findChild(None)
            chk.setChecked(True)
        self.assertEqual(dlg.job_type.currentText(), "Scan (Relaxed Surface)")

    def test_remove_constraint_removes_selected_rows(self):
        with _patch_builder(rdMolTransforms=MagicMock(), **_CONSTRAINT_PATCH):
            dlg = _constraints_dialog(mol=MagicMock())
            _builder_mod.rdMolTransforms.GetBondLength.return_value = 1.0
            dlg.selected_atoms = [0]
            OrcaKeywordBuilderDialog.add_constraint(dlg)
            dlg.selected_atoms = [1]
            OrcaKeywordBuilderDialog.add_constraint(dlg)
            self.assertEqual(dlg.constraint_table.rowCount(), 2)
            dlg.constraint_table.selected_rows = [0]
            OrcaKeywordBuilderDialog.remove_constraint(dlg)
        self.assertEqual(dlg.constraint_table.rowCount(), 1)

    def test_clear_all_constraints_empties_table(self):
        with _patch_builder(**_CONSTRAINT_PATCH):
            dlg = _constraints_dialog(mol=MagicMock())
            dlg.selected_atoms = [0]
            OrcaKeywordBuilderDialog.add_constraint(dlg)
            OrcaKeywordBuilderDialog.clear_all_constraints(dlg)
        self.assertEqual(dlg.constraint_table.rowCount(), 0)

    def test_capture_and_restore_constraints_round_trip(self):
        with _patch_builder(**_CONSTRAINT_PATCH):
            dlg = _constraints_dialog(mol=MagicMock())
            dlg.selected_atoms = [0]
            OrcaKeywordBuilderDialog.add_constraint(dlg)
            captured = OrcaKeywordBuilderDialog._capture_constraints(dlg)
            OrcaKeywordBuilderDialog.clear_all_constraints(dlg)
            self.assertEqual(dlg.constraint_table.rowCount(), 0)
            OrcaKeywordBuilderDialog._restore_constraints(dlg, captured)
        self.assertEqual(dlg.constraint_table.rowCount(), 1)
        self.assertEqual(dlg.constraint_table.item(0, 0).text(), "Position")

    def test_add_parsed_constraint_scan(self):
        with _patch_builder(**_CONSTRAINT_PATCH):
            dlg = _constraints_dialog(mol=None)
            OrcaKeywordBuilderDialog._add_parsed_constraint(
                dlg, "Distance", "0 1", "1.2", True, end="2.0", steps="5"
            )
        self.assertEqual(dlg.constraint_table.rowCount(), 1)
        self.assertEqual(dlg.constraint_table.item(0, 5).text(), "2.0")
        self.assertEqual(dlg.constraint_table.item(0, 6).text(), "5")

    def test_on_scan_checkbox_state_changed_disables_columns_when_off(self):
        with _patch_builder(**_CONSTRAINT_PATCH):
            dlg = _constraints_dialog(mol=None)
            OrcaKeywordBuilderDialog._add_parsed_constraint(
                dlg, "Distance", "0 1", "1.2", True, end="2.0", steps="5"
            )
            chk = dlg.constraint_table.cellWidget(0, 3).findChild(None)
            chk.setChecked(False)
        item = dlg.constraint_table.item(0, 4)
        self.assertEqual(item.flags() & _FakeQt.ItemFlag.ItemIsEnabled, 0)


class TestSelectionHelpers(unittest.TestCase):
    def _dlg(self):
        dlg = types.SimpleNamespace()
        dlg.selected_atoms = []
        dlg.constraint_table = _FakeTable()
        dlg.selection_label = MagicMock()
        dlg.btn_add_const = MagicMock()
        dlg.show_atom_labels_for = lambda *a, **k: None
        return dlg

    def test_on_atom_picked_adds_atom(self):
        dlg = self._dlg()
        dlg.update_selection_display = lambda: None
        OrcaKeywordBuilderDialog.on_atom_picked(dlg, 5)
        self.assertEqual(dlg.selected_atoms, [5])

    def test_on_atom_picked_toggles_off(self):
        dlg = self._dlg()
        dlg.update_selection_display = lambda: None
        dlg.selected_atoms = [5]
        OrcaKeywordBuilderDialog.on_atom_picked(dlg, 5)
        self.assertEqual(dlg.selected_atoms, [])

    def test_on_atom_picked_caps_at_four_atoms(self):
        dlg = self._dlg()
        dlg.update_selection_display = lambda: None
        dlg.selected_atoms = [1, 2, 3, 4]
        OrcaKeywordBuilderDialog.on_atom_picked(dlg, 5)
        self.assertEqual(dlg.selected_atoms, [2, 3, 4, 5])

    def test_clear_selection_empties_list(self):
        dlg = self._dlg()
        dlg.update_selection_display = lambda: None
        dlg.selected_atoms = [1, 2]
        OrcaKeywordBuilderDialog.clear_selection(dlg)
        self.assertEqual(dlg.selected_atoms, [])

    def test_update_selection_display_no_atoms(self):
        dlg = self._dlg()
        OrcaKeywordBuilderDialog.update_selection_display(dlg)
        dlg.selection_label.setText.assert_called_with("Selected atoms: None")
        dlg.btn_add_const.setEnabled.assert_called_with(False)

    def test_update_selection_display_with_atoms(self):
        dlg = self._dlg()
        dlg.selected_atoms = [2, 5]
        OrcaKeywordBuilderDialog.update_selection_display(dlg)
        dlg.btn_add_const.setEnabled.assert_called_with(True)
        (txt,), _kw = dlg.selection_label.setText.call_args
        self.assertIn("2, 5", txt)
        self.assertIn("Distance", txt)


# ===========================================================================
# 6. store_state / restore_state
# ===========================================================================


class _DummySpin:
    """Distinct placeholder so isinstance(widget, QSpinBox) doesn't match
    every object the way `object` itself would."""


class TestStoreRestoreState(unittest.TestCase):
    def test_store_and_restore_roundtrip(self):
        with _patch_builder(
            QComboBox=_FakeCombo, QCheckBox=_FakeCheck, QSpinBox=_DummySpin
        ):
            dlg = types.SimpleNamespace()
            dlg.my_combo = _FakeCombo(["A", "B"])
            dlg.my_combo.setCurrentText("B")
            dlg.my_check = _FakeCheck(True)
            dlg.constraint_table = _FakeTable()
            dlg.update_preview = lambda: None

            def _capture():
                return OrcaKeywordBuilderDialog._capture_constraints(dlg)

            dlg._capture_constraints = _capture
            OrcaKeywordBuilderDialog.store_state(dlg)
            self.assertEqual(dlg._saved_state["my_combo"], "B")
            self.assertTrue(dlg._saved_state["my_check"])

            dlg.my_combo.setCurrentText("A")
            dlg.my_check.setChecked(False)

            def _restore(data):
                OrcaKeywordBuilderDialog._restore_constraints(dlg, data)

            dlg._restore_constraints = _restore
            OrcaKeywordBuilderDialog.restore_state(dlg)
        self.assertEqual(dlg.my_combo.currentText(), "B")
        self.assertTrue(dlg.my_check.isChecked())
        self.assertTrue(dlg.ui_ready)

    def test_restore_state_without_prior_save_is_noop(self):
        dlg = types.SimpleNamespace()
        OrcaKeywordBuilderDialog.restore_state(dlg)  # must not raise


# ===========================================================================
# 7. get_route()
# ===========================================================================


class TestGetRoute(unittest.TestCase):
    def test_get_route_returns_preview_str(self):
        dlg = types.SimpleNamespace()
        dlg.preview_str = "! B3LYP def2-SVP Opt"
        self.assertEqual(OrcaKeywordBuilderDialog.get_route(dlg), dlg.preview_str)


# ===========================================================================
# 8. update_preview() -- additional branches
# ===========================================================================


def _preview_dialog(**overrides):
    """A MagicMock-driven dialog covering every widget used in update_preview()."""
    dlg = types.SimpleNamespace()
    dlg.ui_ready = True
    dlg.route_line = ""
    dlg.preview_str = ""
    dlg.update_ui_state = lambda: None

    dlg.method_name = _combo("B3LYP")
    dlg.basis_set = _combo("def2-SVP")
    dlg.aux_basis = _combo("None")
    dlg.cabs_basis = _combo("None")
    dlg.cabs_basis.isEnabled.return_value = False
    dlg.rijcosx = _check(False)

    dlg.job_type = _combo("Single Point Energy (SP)")
    dlg.neb_variant = _combo("NEB-TS")
    dlg.opt_tight = _check(False)
    dlg.opt_verytight = _check(False)
    dlg.opt_loose = _check(False)
    dlg.opt_cart = _check(False)
    dlg.opt_calcfc = _check(False)
    dlg.opt_ts_mode = _check(False)

    freq_group = MagicMock()
    freq_group.isVisible.return_value = False
    dlg.freq_group = freq_group
    dlg.freq_num = _check(False)
    dlg.freq_raman = _check(False)

    dlg.solv_model = _combo("None")
    dlg.solvent = _combo("Water")
    dlg.dispersion = _combo("None")

    for name in [
        "scf_sloppy", "scf_loose", "scf_normal", "scf_strong",
        "scf_tight", "scf_verytight", "scf_extreme",
        "scf_slowconv", "scf_veryslowconv",
    ]:
        setattr(dlg, name, _check(False))

    dlg.grid_combo = _combo("Default")
    dlg.relativistic = _combo("None")
    dlg.pno_preset = _combo("Default")
    dlg.pno_preset.isEnabled.return_value = False

    for name in [
        "pop_nbo", "pop_npa", "pop_chelpg", "pop_hirshfeld",
        "uco_chk", "uno_chk", "somo_chk", "fod_chk", "optrot_chk",
        "pol_chk", "hyperpol_chk", "epr_chk", "zfs_chk",
        "nori_chk", "bs_chk", "moread_chk", "somf_chk",
        "keepdens_chk", "keepints_chk", "cosx_chk",
    ]:
        setattr(dlg, name, _check(False))

    dlg.print_level = _combo("Default")
    dlg.frozen_core_combo = _combo("Default")
    dlg.scf_guess = _combo("Default")
    dlg.moread_file = MagicMock()
    dlg.moread_file.text.return_value = ""
    dlg.bs_spins = MagicMock()
    dlg.bs_spins.text.return_value = "1,1"
    dlg.preview_label = MagicMock()
    dlg.iter256_chk = _check(False)
    dlg.constraint_table = MagicMock()
    dlg.constraint_table.rowCount.return_value = 0
    dlg.tddft_enable = _check(False)

    dlg.get_inferred_category = (
        lambda text: OrcaKeywordBuilderDialog.get_inferred_category(dlg, text)
    )
    dlg.get_extra_blocks_text = (
        lambda: OrcaKeywordBuilderDialog.get_extra_blocks_text(dlg)
    )
    dlg.get_constraints_text = (
        lambda: OrcaKeywordBuilderDialog.get_constraints_text(dlg)
    )

    for k, v in overrides.items():
        setattr(dlg, k, v)
    return dlg


def _preview_route(dlg):
    OrcaKeywordBuilderDialog.update_preview(dlg)
    return dlg.route_line


class TestUpdatePreviewJobTypes(unittest.TestCase):
    def test_engrad(self):
        dlg = _preview_dialog(job_type=_combo("EnGrad (Single Point + Gradient)"))
        self.assertIn("EnGrad", _preview_route(dlg))

    def test_numgrad(self):
        dlg = _preview_dialog(job_type=_combo("NumGrad (Numerical Gradient)"))
        self.assertIn("NumGrad", _preview_route(dlg))

    def test_numhess(self):
        dlg = _preview_dialog(job_type=_combo("NumHess (Numerical Hessian only)"))
        self.assertIn("NumHess", _preview_route(dlg))

    def test_esd_abs(self):
        dlg = _preview_dialog(job_type=_combo("ESD(ABS) (Vibronic Absorption)"))
        self.assertIn("ESD(ABS)", _preview_route(dlg))

    def test_esd_fluor(self):
        dlg = _preview_dialog(job_type=_combo("ESD(FLUOR) (Vibronic Fluorescence)"))
        self.assertIn("ESD(FLUOR)", _preview_route(dlg))

    def test_goat(self):
        dlg = _preview_dialog(job_type=_combo("GOAT (Global Search)"))
        self.assertIn("GOAT", _preview_route(dlg))

    def test_neb_uses_variant(self):
        dlg = _preview_dialog(
            job_type=_combo("NEB (Nudged Elastic Band)"),
            neb_variant=_combo("ZOOM-NEB-TS"),
        )
        self.assertIn("ZOOM-NEB-TS", _preview_route(dlg))

    def test_md(self):
        dlg = _preview_dialog(job_type=_combo("MD (Molecular Dynamics)"))
        self.assertIn("MD", _preview_route(dlg))

    def test_irc(self):
        dlg = _preview_dialog(job_type=_combo("IRC (Intrinsic Reaction Coordinate)"))
        self.assertIn("IRC", _preview_route(dlg))

    def test_opt_ts_mode_adds_calchess(self):
        dlg = _preview_dialog(job_type=_combo("Transition State Opt (OptTS)"))
        dlg.opt_ts_mode = _check(True)
        self.assertIn("CalcHess", _preview_route(dlg))

    def test_freq_options_visible(self):
        freq_group = MagicMock()
        freq_group.isVisible.return_value = True
        dlg = _preview_dialog(
            job_type=_combo("Frequency Only (Freq)"), freq_group=freq_group
        )
        dlg.freq_num = _check(True)
        dlg.freq_raman = _check(True)
        r = _preview_route(dlg)
        self.assertIn("NumFreq", r)
        self.assertIn("Raman", r)


class TestUpdatePreviewMethodOptions(unittest.TestCase):
    def test_f12_cabs_basis_included(self):
        dlg = _preview_dialog(method_name=_combo("CCSD(T)-F12"))
        dlg.cabs_basis = _combo("cc-pVTZ-F12-CABS", enabled=True)
        r = _preview_route(dlg)
        self.assertIn("cc-pVTZ-F12-CABS", r)

    def test_relativistic_zora(self):
        dlg = _preview_dialog(relativistic=_combo("ZORA"))
        self.assertIn("ZORA", _preview_route(dlg))

    def test_dlpno_pno_preset(self):
        dlg = _preview_dialog(method_name=_combo("DLPNO-CCSD(T)"))
        dlg.pno_preset = _combo("TightPNO", enabled=True)
        r = _preview_route(dlg)
        self.assertIn("TightPNO", r)

    def test_pno_preset_ignored_when_disabled(self):
        dlg = _preview_dialog()
        dlg.pno_preset = _combo("TightPNO", enabled=False)
        r = _preview_route(dlg)
        self.assertNotIn("TightPNO", r)

    def test_print_level_largeprint(self):
        dlg = _preview_dialog(print_level=_combo("LargePrint"))
        self.assertIn("LargePrint", _preview_route(dlg))

    def test_nori_flag(self):
        dlg = _preview_dialog()
        dlg.nori_chk = _check(True)
        self.assertIn("NoRI", _preview_route(dlg))

    def test_frozen_core(self):
        dlg = _preview_dialog(frozen_core_combo=_combo("FrozenCore"))
        self.assertIn("FrozenCore", _preview_route(dlg))

    def test_cosx_flag(self):
        dlg = _preview_dialog()
        dlg.cosx_chk = _check(True)
        self.assertIn("COSX", _preview_route(dlg))

    def test_somf_flag(self):
        dlg = _preview_dialog()
        dlg.somf_chk = _check(True)
        self.assertIn("RI-SOMF(1X)", _preview_route(dlg))

    def test_keepdens_and_keepints(self):
        dlg = _preview_dialog()
        dlg.keepdens_chk = _check(True)
        dlg.keepints_chk = _check(True)
        r = _preview_route(dlg)
        self.assertIn("KeepDens", r)
        self.assertIn("KeepInts", r)

    def test_broken_symmetry_adds_uks(self):
        dlg = _preview_dialog()
        dlg.bs_chk = _check(True)
        self.assertIn("UKS", _preview_route(dlg))

    def test_moread_adds_moread_keyword(self):
        dlg = _preview_dialog()
        dlg.moread_chk = _check(True)
        self.assertIn("MOREAD", _preview_route(dlg))

    def test_population_and_property_flags(self):
        dlg = _preview_dialog()
        for name, kw in [
            ("pop_npa", "NPA"), ("pop_chelpg", "CHELPG"), ("pop_hirshfeld", "Hirshfeld"),
            ("uco_chk", "UCO"), ("uno_chk", "UNO"), ("somo_chk", "SOMO"),
            ("fod_chk", "FOD"), ("optrot_chk", "OptRot"), ("pol_chk", "Polarizability"),
            ("hyperpol_chk", "Hyperpol"), ("epr_chk", "EPR"), ("zfs_chk", "ZFS"),
        ]:
            setattr(dlg, name, _check(True))
        r = _preview_route(dlg)
        for kw in ["NPA", "CHELPG", "Hirshfeld", "UCO", "UNO", "SOMO", "FOD",
                   "OptRot", "Polarizability", "Hyperpol", "EPR", "ZFS"]:
            self.assertIn(kw, r)

    def test_slowconv_flags(self):
        dlg = _preview_dialog()
        dlg.scf_slowconv = _check(True)
        self.assertIn("SlowConv", _preview_route(dlg))

    def test_veryslowconv_flag(self):
        dlg = _preview_dialog()
        dlg.scf_veryslowconv = _check(True)
        self.assertIn("VerySlowConv", _preview_route(dlg))


# ===========================================================================
# 9. get_extra_blocks_text() -- SCF guess / broken symmetry / MOREAD
# ===========================================================================


class TestGetExtraBlocksExtended(unittest.TestCase):
    def _dlg(self, **overrides):
        dlg = _preview_dialog(**overrides)
        return dlg

    def test_scf_guess_block(self):
        dlg = self._dlg(scf_guess=_combo("Hueckel"))
        t = OrcaKeywordBuilderDialog.get_extra_blocks_text(dlg)
        self.assertIn("%scf", t)
        self.assertIn("Guess Hueckel", t)

    def test_broken_symmetry_block(self):
        dlg = self._dlg()
        dlg.bs_chk = _check(True)
        dlg.bs_spins = MagicMock()
        dlg.bs_spins.text.return_value = "1,-1"
        t = OrcaKeywordBuilderDialog.get_extra_blocks_text(dlg)
        self.assertIn("BrokenSym 1,-1", t)

    def test_moread_block_with_filename(self):
        dlg = self._dlg()
        dlg.moread_chk = _check(True)
        dlg.moread_file = MagicMock()
        dlg.moread_file.text.return_value = "previous.gbw"
        t = OrcaKeywordBuilderDialog.get_extra_blocks_text(dlg)
        self.assertIn('%moinp "previous.gbw"', t)

    def test_moread_checked_but_empty_filename_no_block(self):
        dlg = self._dlg()
        dlg.moread_chk = _check(True)
        dlg.moread_file = MagicMock()
        dlg.moread_file.text.return_value = "   "
        t = OrcaKeywordBuilderDialog.get_extra_blocks_text(dlg)
        self.assertNotIn("%moinp", t)


if __name__ == "__main__":
    unittest.main()
