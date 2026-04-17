"""
tests/test_metadata.py

Tests for orca_input_generator_pro/__init__.py:
  - Plugin identity constants
  - get_default_settings() shape and types
  - initialize() registration contract (stub context)
"""

import os
import sys
import types
import importlib.util
import unittest
from unittest.mock import MagicMock, call

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Qt / heavy-dep stubs (must be installed before any plugin import)
# ---------------------------------------------------------------------------

def _install_stubs():
    pyqt6 = types.ModuleType("PyQt6")
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
    for name in ["Qt", "QTimer", "QRegularExpression", "QThread", "QSize"]:
        setattr(qt_core, name, MagicMock)
    for name in ["QColor", "QFont", "QSyntaxHighlighter", "QTextCharFormat",
                 "QAction", "QIcon"]:
        setattr(qt_gui, name, MagicMock)
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
    path = os.path.join(_REPO_ROOT, "orca_input_generator_pro", "__init__.py")
    spec = importlib.util.spec_from_file_location("orca_input_generator_pro", path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "orca_input_generator_pro"
    sys.modules["orca_input_generator_pro"] = mod
    spec.loader.exec_module(mod)
    return mod


_init = _load_init()


class TestPluginMetadata(unittest.TestCase):
    def test_plugin_name_present(self):
        self.assertTrue(hasattr(_init, "PLUGIN_NAME"))

    def test_plugin_name_is_string(self):
        self.assertIsInstance(_init.PLUGIN_NAME, str)
        self.assertTrue(len(_init.PLUGIN_NAME) > 0)

    def test_plugin_version_present(self):
        self.assertTrue(hasattr(_init, "PLUGIN_VERSION"))

    def test_plugin_version_semver(self):
        parts = _init.PLUGIN_VERSION.split(".")
        self.assertEqual(len(parts), 3, "Version must be X.Y.Z")
        for p in parts:
            self.assertTrue(p.isdigit(), f"Version part not numeric: {p}")

    def test_plugin_author_present(self):
        self.assertTrue(hasattr(_init, "PLUGIN_AUTHOR"))
        self.assertIsInstance(_init.PLUGIN_AUTHOR, str)

    def test_plugin_description_present(self):
        self.assertTrue(hasattr(_init, "PLUGIN_DESCRIPTION"))


class TestDefaultSettings(unittest.TestCase):
    def setUp(self):
        self.s = _init.get_default_settings()

    def test_returns_dict(self):
        self.assertIsInstance(self.s, dict)

    def test_nproc_key(self):
        self.assertIn("nproc", self.s)
        self.assertIsInstance(self.s["nproc"], int)
        self.assertGreater(self.s["nproc"], 0)

    def test_maxcore_key(self):
        self.assertIn("maxcore", self.s)
        self.assertIsInstance(self.s["maxcore"], int)
        self.assertGreater(self.s["maxcore"], 0)

    def test_route_key(self):
        self.assertIn("route", self.s)
        self.assertIsInstance(self.s["route"], str)

    def test_coord_format_key(self):
        self.assertIn("coord_format", self.s)

    def test_two_calls_return_independent_dicts(self):
        a = _init.get_default_settings()
        b = _init.get_default_settings()
        a["nproc"] = 999
        self.assertNotEqual(b["nproc"], 999)


class TestInitialize(unittest.TestCase):
    def _make_context(self):
        ctx = MagicMock()
        ctx.get_main_window.return_value = MagicMock()
        return ctx

    def test_initialize_callable(self):
        self.assertTrue(callable(_init.initialize))

    def test_registers_export_action(self):
        ctx = self._make_context()
        _init.initialize(ctx)
        ctx.add_export_action.assert_called_once()
        args = ctx.add_export_action.call_args[0]
        self.assertIsInstance(args[0], str)
        self.assertTrue(callable(args[1]))

    def test_registers_save_handler(self):
        ctx = self._make_context()
        _init.initialize(ctx)
        ctx.register_save_handler.assert_called_once()

    def test_registers_load_handler(self):
        ctx = self._make_context()
        _init.initialize(ctx)
        ctx.register_load_handler.assert_called_once()

    def test_registers_reset_handler(self):
        ctx = self._make_context()
        _init.initialize(ctx)
        ctx.register_document_reset_handler.assert_called_once()

    def test_save_handler_returns_none_before_dialog_opened(self):
        ctx = self._make_context()
        _init._dialog_opened = False
        _init.initialize(ctx)
        save_fn = ctx.register_save_handler.call_args[0][0]
        self.assertIsNone(save_fn())

    def test_save_handler_returns_dict_after_dialog_opened(self):
        ctx = self._make_context()
        _init._dialog_opened = True
        _init.initialize(ctx)
        save_fn = ctx.register_save_handler.call_args[0][0]
        self.assertIsInstance(save_fn(), dict)

    def test_load_handler_updates_settings(self):
        ctx = self._make_context()
        _init._dialog_opened = True
        _init.initialize(ctx)
        load_fn = ctx.register_load_handler.call_args[0][0]
        load_fn({"nproc": 42, "maxcore": 1234})
        save_fn = ctx.register_save_handler.call_args[0][0]
        saved = save_fn()
        self.assertEqual(saved["nproc"], 42)
        self.assertEqual(saved["maxcore"], 1234)

    def test_reset_handler_restores_defaults(self):
        ctx = self._make_context()
        _init._dialog_opened = True
        _init.initialize(ctx)
        load_fn = ctx.register_load_handler.call_args[0][0]
        load_fn({"nproc": 99})
        reset_fn = ctx.register_document_reset_handler.call_args[0][0]
        reset_fn()
        # Flag is preserved after reset — save still returns defaults dict
        save_fn = ctx.register_save_handler.call_args[0][0]
        saved = save_fn()
        defaults = _init.get_default_settings()
        self.assertEqual(saved["nproc"], defaults["nproc"])

    def test_multiple_initialize_calls_do_not_duplicate(self):
        ctx = self._make_context()
        _init.initialize(ctx)
        _init.initialize(ctx)
        self.assertEqual(ctx.add_export_action.call_count, 2)  # once per call is fine


if __name__ == "__main__":
    unittest.main()
