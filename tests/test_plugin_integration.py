"""
tests/test_plugin_integration.py

Integration tests verifying the ORCA Input Generator Pro plugin's contract
with the MoleditPy main-application PluginContext interface.

Two execution modes
-------------------
1. **Stub mode** (always runs, including CI):
   A StubPluginContext mirrors the real PluginContext API so that all contract
   tests pass without installing the main app.

2. **Real-context mode** (runs only when the main app source is present):
   If python_molecular_editor/moleditpy/src is found relative to this repo
   (local dev) OR via the CI_MAIN_APP_SRC environment variable, the tests are
   re-run using the actual PluginContext class to verify true compatibility.
   Skipped with pytest.mark.skipif when not available.

CI setup
--------
The GitHub Actions workflow optionally clones the main app before running:

    - name: Clone main app
      run: git clone --depth 1 \\
             https://github.com/HiroYokoyama/python_molecular_editor.git \\
             ../python_molecular_editor || true

Then set CI_MAIN_APP_SRC in the test step's env block to activate
real-context mode.
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
    pyqt6 = sys.modules.get("PyQt6") or types.ModuleType("PyQt6")
    qt_widgets = types.ModuleType("PyQt6.QtWidgets")
    qt_core = types.ModuleType("PyQt6.QtCore")
    qt_gui = types.ModuleType("PyQt6.QtGui")
    for name in [
        "QDialog", "QVBoxLayout", "QHBoxLayout", "QLabel", "QLineEdit",
        "QSpinBox", "QPushButton", "QGroupBox", "QComboBox", "QTextEdit",
        "QTabWidget", "QCheckBox", "QWidget", "QFormLayout", "QTableWidget",
        "QTableWidgetItem", "QCompleter", "QPlainTextEdit", "QGridLayout",
        "QSizePolicy", "QMessageBox", "QFileDialog", "QApplication",
        "QAbstractItemView",
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
        "pyvista": MagicMock(),
    })


_install_stubs()


def _load_init():
    key = "orca_input_generator_pro"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(_REPO_ROOT, "orca_input_generator_pro", "__init__.py")
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = key
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


_init_mod = _load_init()


# ---------------------------------------------------------------------------
# Stub PluginContext (no main app required)
# ---------------------------------------------------------------------------

class StubPluginContext:
    """Minimal stub that mirrors the PluginContext public API used by initialize()."""

    def __init__(self):
        self._main_window = MagicMock()
        self._export_actions = []
        self._save_handlers = []
        self._load_handlers = []
        self._reset_handlers = []

    def get_main_window(self):
        return self._main_window

    def add_export_action(self, label, callback):
        self._export_actions.append((label, callback))

    def register_save_handler(self, fn):
        self._save_handlers.append(fn)

    def register_load_handler(self, fn):
        self._load_handlers.append(fn)

    def register_document_reset_handler(self, fn):
        self._reset_handlers.append(fn)


# ---------------------------------------------------------------------------
# 1. initialize() registration contract
# ---------------------------------------------------------------------------

class TestInitializeContract(unittest.TestCase):
    def setUp(self):
        self.ctx = StubPluginContext()
        # Reset module-level settings before each test
        _init_mod.current_settings.clear()
        _init_mod.current_settings.update(_init_mod.get_default_settings())
        _init_mod.initialize(self.ctx)

    def test_export_action_registered(self):
        self.assertEqual(len(self.ctx._export_actions), 1)

    def test_export_action_label_is_string(self):
        label, _ = self.ctx._export_actions[0]
        self.assertIsInstance(label, str)
        self.assertTrue(len(label) > 0)

    def test_export_action_callback_is_callable(self):
        _, cb = self.ctx._export_actions[0]
        self.assertTrue(callable(cb))

    def test_save_handler_registered(self):
        self.assertEqual(len(self.ctx._save_handlers), 1)

    def test_load_handler_registered(self):
        self.assertEqual(len(self.ctx._load_handlers), 1)

    def test_reset_handler_registered(self):
        self.assertEqual(len(self.ctx._reset_handlers), 1)


# ---------------------------------------------------------------------------
# 2. Persistence handlers
# ---------------------------------------------------------------------------

class TestPersistenceHandlers(unittest.TestCase):
    def setUp(self):
        self.ctx = StubPluginContext()
        _init_mod.current_settings.clear()
        _init_mod.current_settings.update(_init_mod.get_default_settings())
        _init_mod._dialog_opened = False
        _init_mod.initialize(self.ctx)
        self.save = self.ctx._save_handlers[0]
        self.load = self.ctx._load_handlers[0]
        self.reset = self.ctx._reset_handlers[0]

    # --- save guard: dialog not yet opened ---

    def test_save_returns_none_before_dialog_opened(self):
        self.assertIsNone(self.save())

    def test_save_returns_dict_after_dialog_opened(self):
        _init_mod._dialog_opened = True
        self.assertIsInstance(self.save(), dict)

    def test_save_returns_current_settings_reference_after_dialog_opened(self):
        _init_mod._dialog_opened = True
        self.assertIs(self.save(), _init_mod.current_settings)

    # --- load ---

    def test_load_updates_nproc(self):
        self.load({"nproc": 16})
        self.assertEqual(_init_mod.current_settings["nproc"], 16)

    def test_load_updates_maxcore(self):
        self.load({"maxcore": 4000})
        self.assertEqual(_init_mod.current_settings["maxcore"], 4000)

    def test_load_ignores_non_dict(self):
        before = dict(_init_mod.current_settings)
        self.load("not a dict")
        self.assertEqual(_init_mod.current_settings, before)

    def test_load_ignores_empty_dict(self):
        before = dict(_init_mod.current_settings)
        self.load({})
        self.assertEqual(_init_mod.current_settings, before)

    def test_load_sets_dialog_opened_flag(self):
        _init_mod._dialog_opened = False
        self.load({"nproc": 8})
        self.assertTrue(_init_mod._dialog_opened)
        self.assertIsInstance(self.save(), dict)

    def test_load_empty_does_not_set_flag(self):
        _init_mod._dialog_opened = False
        self.load({})
        self.assertFalse(_init_mod._dialog_opened)

    def test_load_strips_charge_and_mult(self):
        self.load({"nproc": 8, "charge": 2, "mult": 3})
        self.assertEqual(_init_mod.current_settings["nproc"], 8)
        self.assertNotIn("charge", _init_mod.current_settings)
        self.assertNotIn("mult", _init_mod.current_settings)

    # --- reset ---

    def test_reset_restores_defaults(self):
        self.load({"nproc": 99, "maxcore": 99999})
        self.reset()
        defaults = _init_mod.get_default_settings()
        self.assertEqual(_init_mod.current_settings["nproc"], defaults["nproc"])
        self.assertEqual(_init_mod.current_settings["maxcore"], defaults["maxcore"])

    def test_reset_clears_dialog_opened_flag(self):
        _init_mod._dialog_opened = True
        self.reset()
        self.assertFalse(_init_mod._dialog_opened)
        self.assertIsNone(self.save())

    # --- roundtrip ---

    def test_roundtrip_save_load(self):
        _init_mod._dialog_opened = True
        self.load({"nproc": 8, "maxcore": 3000, "route": "! B3LYP def2-SVP Opt"})
        saved = dict(self.save())
        # Reset and reload
        self.reset()
        _init_mod._dialog_opened = True
        self.load(saved)
        self.assertEqual(_init_mod.current_settings["nproc"], 8)
        self.assertEqual(_init_mod.current_settings["route"], "! B3LYP def2-SVP Opt")


# ---------------------------------------------------------------------------
# 3. Real PluginContext (optional — local dev or CI with cloned main app)
# ---------------------------------------------------------------------------

_MAIN_APP_CANDIDATES = [
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..",
                     "python_molecular_editor", "moleditpy", "src")
    ),
    os.environ.get("CI_MAIN_APP_SRC", ""),
]
_MAIN_APP_SRC = next(
    (p for p in _MAIN_APP_CANDIDATES if p and os.path.isdir(p)),
    None,
)
HAS_MAIN_APP = _MAIN_APP_SRC is not None

try:
    import pytest
    _skipif = pytest.mark.skipif(
        not HAS_MAIN_APP,
        reason="main app not found; set CI_MAIN_APP_SRC or place at "
               "../python_molecular_editor/moleditpy/src",
    )
except ImportError:
    def _skipif(cls):
        return unittest.skip("pytest not available for skipif")(cls)


@_skipif
class TestWithRealPluginContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAS_MAIN_APP:
            return
        if _MAIN_APP_SRC not in sys.path:
            sys.path.insert(0, _MAIN_APP_SRC)
        from moleditpy.plugins.plugin_interface import PluginContext
        cls.PluginContext = PluginContext
        mock_manager = MagicMock()
        mock_manager.get_main_window.return_value = MagicMock()
        cls.real_ctx = PluginContext(mock_manager, "ORCA Input Generator Pro")

    def test_real_initialize_does_not_raise(self):
        _init_mod.current_settings.clear()
        _init_mod.current_settings.update(_init_mod.get_default_settings())
        try:
            _init_mod.initialize(self.real_ctx)
        except Exception as e:
            self.fail(f"initialize(real_context) raised: {e}")

    def test_real_context_is_plugincontext_instance(self):
        self.assertIsInstance(self.real_ctx, self.PluginContext)

    def test_stub_interface_matches_real(self):
        methods_used = [
            "add_export_action",
            "register_save_handler",
            "register_load_handler",
            "register_document_reset_handler",
            "get_main_window",
        ]
        for method in methods_used:
            self.assertTrue(
                hasattr(self.PluginContext, method),
                f"Real PluginContext is missing method: {method}",
            )


if __name__ == "__main__":
    unittest.main()
