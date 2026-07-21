"""
tests/test_init_extended.py

Extended coverage for orca_input_generator_pro/__init__.py, focused on the
run() function and the on_reset() "dialog still open" deferral path, neither
of which tests/test_plugin_integration.py exercises (that file only tests
initialize()'s registration contract and the save/load/reset handlers in
isolation, via a StubPluginContext, without ever calling run()).

run() constructs a real OrcaSetupDialogPro, so this file loads a private,
real-PyQt6/RDKit-bound copy of the whole plugin module tree -- see
tests/test_main_dialog_extended.py's module docstring for why (sibling test
modules unconditionally clobber sys.modules["PyQt6*"]/["rdkit"] and reuse the
shared "orca_input_generator_pro.*" sys.modules cache slots, independent of
collection order).
"""

import os
import sys
import json
import types
import shutil
import tempfile
import importlib
import importlib.util
import unittest
from unittest.mock import patch, MagicMock

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PRIV_PKG = "_oigp_real_qt_copy"  # shared with test_main_dialog_extended.py


def _real_module(name):
    cur = sys.modules.get(name)
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
    return importlib.import_module(name)


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


_init_mod = _load_private("__init__", "__init__.py")
_load_private("constants", "constants.py")
_load_private("highlighter", "highlighter.py")
_load_private("mixins", "mixins.py")
_load_private("keyword_builder", "keyword_builder.py")
main_dialog_mod = _load_private("main_dialog", "main_dialog.py")

from rdkit import Chem
from rdkit.Chem import AllChem


def _make_water():
    m = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(m, randomSeed=42)
    return m


from PyQt6.QtWidgets import QWidget


class _RealMW(QWidget):
    """Stand-in main window: a real QWidget (run() passes it as the new
    dialog's Qt parent) with plain instance attributes (no MagicMock
    auto-attrs), so hasattr(mw, "init_manager") behaves like the real app."""

    def __init__(self, title="untitled", current_mol=None, init_manager=None):
        super().__init__()
        self._title = title
        self.current_mol = current_mol
        if init_manager is not None:
            self.init_manager = init_manager

    def windowTitle(self):
        return self._title


class StubPluginContext:
    def __init__(self, main_window=None):
        self._main_window = main_window if main_window is not None else _RealMW()
        self._export_actions = []
        self._save_handlers = []
        self._load_handlers = []
        self._reset_handlers = []
        self._windows = {}
        self.mark_project_modified_call_count = 0

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

    def register_window(self, window_id, window):
        self._windows[window_id] = window

    def get_window(self, window_id):
        return self._windows.get(window_id)

    def mark_project_modified(self):
        self.mark_project_modified_call_count += 1

    @property
    def current_molecule(self):
        return getattr(self._main_window, "current_mol", None)


class _BaseInitTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        settings_path = os.path.join(self._tmpdir, "settings.json")
        patcher = patch.object(main_dialog_mod, "SETTINGS_FILE", settings_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: shutil.rmtree(self._tmpdir, ignore_errors=True))

        _init_mod._context = None
        _init_mod._dialog_opened = False
        _init_mod.current_settings.clear()
        _init_mod.current_settings.update(_init_mod.get_default_settings())

        def _cleanup_context():
            _init_mod._context = None
            _init_mod._dialog_opened = False

        self.addCleanup(_cleanup_context)


# ---------------------------------------------------------------------------
# run() -- no molecule loaded
# ---------------------------------------------------------------------------


class TestRunNoMolecule(_BaseInitTestCase):
    def test_warns_and_returns_without_context(self):
        mw = _RealMW(current_mol=None)
        with patch.object(_init_mod, "QMessageBox") as mock_box:
            _init_mod.run(mw)
        mock_box.warning.assert_called_once()
        self.assertFalse(_init_mod._dialog_opened)

    def test_warns_when_context_current_molecule_none(self):
        ctx = StubPluginContext(main_window=_RealMW(current_mol=None))
        _init_mod._context = ctx
        with patch.object(_init_mod, "QMessageBox") as mock_box:
            _init_mod.run(None)
        mock_box.warning.assert_called_once()

    def test_molecule_lookup_exception_is_caught(self):
        class _Boom:
            current_mol = property(lambda self: (_ for _ in ()).throw(RuntimeError()))

        with patch.object(_init_mod, "QMessageBox") as mock_box:
            _init_mod.run(_Boom())
        mock_box.warning.assert_called_once()


# ---------------------------------------------------------------------------
# run() -- filename detection
# ---------------------------------------------------------------------------


class TestRunFilenameDetection(_BaseInitTestCase):
    def _run_and_capture_filename(self, mw):
        captured = {}

        class _FakeDialog:
            def __init__(self, parent, mol, filename, persistent_settings,
                         mark_modified, get_molecule):
                captured["filename"] = filename

            def show(self):
                pass

        with patch.object(main_dialog_mod, "OrcaSetupDialogPro", _FakeDialog):
            with patch.dict(sys.modules, {f"{_PRIV_PKG}.main_dialog": main_dialog_mod}):
                _init_mod.run(mw)
        return captured.get("filename")

    def test_init_manager_current_file_path_used(self):
        im = types.SimpleNamespace(current_file_path="/abs/path/job.pmeprj")
        mw = _RealMW(current_mol=_make_water(), init_manager=im)
        filename = self._run_and_capture_filename(mw)
        self.assertEqual(filename, "/abs/path/job.pmeprj")

    def test_window_title_fallback_with_dash(self):
        mw = _RealMW(title="water.pmeprj - MoleditPy", current_mol=_make_water())
        filename = self._run_and_capture_filename(mw)
        self.assertEqual(filename, "water.pmeprj")

    def test_window_title_fallback_without_dash(self):
        mw = _RealMW(title="MoleditPy", current_mol=_make_water())
        filename = self._run_and_capture_filename(mw)
        self.assertEqual(filename, "MoleditPy")

    def test_init_manager_attribute_error_falls_back_to_title(self):
        class _BadMW(_RealMW):
            @property
            def init_manager(self):
                raise RuntimeError("boom")

        mw = _BadMW(title="fallback.pmeprj - X", current_mol=_make_water())
        filename = self._run_and_capture_filename(mw)
        self.assertEqual(filename, "fallback.pmeprj")


# ---------------------------------------------------------------------------
# run() -- dialog already open
# ---------------------------------------------------------------------------


class TestRunExistingDialog(_BaseInitTestCase):
    def test_visible_existing_dialog_is_raised_not_recreated(self):
        ctx = StubPluginContext(main_window=_RealMW(current_mol=_make_water()))
        existing = MagicMock()
        existing.isVisible.return_value = True
        ctx.register_window("dialog", existing)
        _init_mod._context = ctx

        with patch.object(main_dialog_mod, "OrcaSetupDialogPro") as mock_cls:
            _init_mod.run(None)

        existing.raise_.assert_called_once()
        existing.activateWindow.assert_called_once()
        mock_cls.assert_not_called()

    def test_hidden_existing_dialog_is_replaced(self):
        ctx = StubPluginContext(main_window=_RealMW(current_mol=_make_water()))
        existing = MagicMock()
        existing.isVisible.return_value = False
        ctx.register_window("dialog", existing)
        _init_mod._context = ctx

        with patch.object(main_dialog_mod, "OrcaSetupDialogPro") as mock_cls:
            mock_cls.return_value = MagicMock()
            _init_mod.run(None)

        mock_cls.assert_called_once()


# ---------------------------------------------------------------------------
# run() -- full flow constructs a real dialog and registers it
# ---------------------------------------------------------------------------


class TestRunFullFlow(_BaseInitTestCase):
    def test_creates_and_registers_real_dialog(self):
        ctx = StubPluginContext(main_window=_RealMW(current_mol=_make_water()))
        _init_mod._context = ctx

        _init_mod.run(None)

        dlg = ctx.get_window("dialog")
        self.assertIsNotNone(dlg)
        self.assertIsInstance(dlg, main_dialog_mod.OrcaSetupDialogPro)
        self.assertTrue(_init_mod._dialog_opened)

    def test_mark_modified_callback_delegates_to_context(self):
        ctx = StubPluginContext(main_window=_RealMW(current_mol=_make_water()))
        _init_mod._context = ctx
        _init_mod.run(None)
        dlg = ctx.get_window("dialog")
        before = ctx.mark_project_modified_call_count
        dlg.mark_modified()
        self.assertEqual(ctx.mark_project_modified_call_count, before + 1)

    def test_get_molecule_callback_uses_context(self):
        mol = _make_water()
        ctx = StubPluginContext(main_window=_RealMW(current_mol=mol))
        _init_mod._context = ctx
        _init_mod.run(None)
        dlg = ctx.get_window("dialog")
        self.assertIs(dlg.get_molecule(), mol)

    def test_without_context_uses_mw_current_mol_directly(self):
        mw = _RealMW(current_mol=_make_water())
        _init_mod._context = None
        with patch.object(main_dialog_mod, "OrcaSetupDialogPro") as mock_cls:
            mock_cls.return_value = MagicMock()
            _init_mod.run(mw)
        mock_cls.assert_called_once()
        _, kwargs = mock_cls.call_args
        self.assertIs(kwargs["mol"], mw.current_mol)
        # _context is None here, so the _get_molecule closure falls back to
        # getattr(mw, "current_mol", None) instead of context.current_molecule.
        self.assertIs(kwargs["get_molecule"](), mw.current_mol)


# ---------------------------------------------------------------------------
# initialize()'s show_dialog closure (lines 104-106)
# ---------------------------------------------------------------------------


class TestShowDialogClosure(_BaseInitTestCase):
    def test_show_dialog_invokes_run_with_context_main_window(self):
        ctx = StubPluginContext(main_window=_RealMW(current_mol=None))
        _init_mod.initialize(ctx)
        label, show_dialog = ctx._export_actions[0]
        with patch.object(_init_mod, "QMessageBox") as mock_box:
            show_dialog()
        mock_box.warning.assert_called_once()


# ---------------------------------------------------------------------------
# on_reset() -- dialog present, close cancelled / errors
# ---------------------------------------------------------------------------


class TestOnResetDialogPresent(_BaseInitTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = StubPluginContext()
        _init_mod.initialize(self.ctx)
        self.reset = self.ctx._reset_handlers[0]

    def test_close_succeeds_and_dialog_hidden_resets_defaults(self):
        dlg = MagicMock()
        dlg.isVisible.return_value = False
        self.ctx.register_window("dialog", dlg)
        _init_mod._dialog_opened = True
        _init_mod.current_settings["nproc"] = 99

        self.reset()

        dlg.close.assert_called_once()
        self.assertFalse(_init_mod._dialog_opened)
        self.assertEqual(
            _init_mod.current_settings["nproc"],
            _init_mod.get_default_settings()["nproc"],
        )

    def test_close_cancelled_defers_reset(self):
        dlg = MagicMock()
        dlg.isVisible.return_value = True  # user hit Cancel on unsaved-changes prompt
        self.ctx.register_window("dialog", dlg)
        _init_mod._dialog_opened = True
        _init_mod.current_settings["nproc"] = 77

        self.reset()

        dlg.close.assert_called_once()
        self.assertTrue(_init_mod._dialog_opened)  # not cleared -- deferred
        self.assertEqual(_init_mod.current_settings["nproc"], 77)

    def test_close_raises_is_caught_and_reset_proceeds(self):
        dlg = MagicMock()
        dlg.close.side_effect = RuntimeError("boom")
        self.ctx.register_window("dialog", dlg)
        _init_mod._dialog_opened = True

        self.reset()  # must not raise

        self.assertFalse(_init_mod._dialog_opened)

    def test_no_dialog_registered_resets_directly(self):
        _init_mod._dialog_opened = True
        _init_mod.current_settings["nproc"] = 55

        self.reset()

        self.assertFalse(_init_mod._dialog_opened)
        self.assertEqual(
            _init_mod.current_settings["nproc"],
            _init_mod.get_default_settings()["nproc"],
        )


if __name__ == "__main__":
    unittest.main()
