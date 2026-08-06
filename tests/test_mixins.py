"""
tests/test_mixins.py

Coverage for Dialog3DPickingMixin (mixins.py) -- 3D atom picking used by
OrcaKeywordBuilderDialog (and, via the same mixin, other MoleditPy plugin
dialogs). Builds a real headless QDialog combining the mixin with QDialog,
and drives eventFilter()/enable_picking()/disable_picking()/
clear_selection_labels()/show_atom_labels_for() with MagicMock stand-ins for
main_window.view_3d_manager.plotter (no real VTK/pyvista needed).
"""

import os
import sys
import types
import importlib
import importlib.util
import unittest
from unittest.mock import MagicMock, patch

import pytest

np = pytest.importorskip("numpy")  # host dep; absent in bare-pytest CI

# ---------------------------------------------------------------------------
# Several sibling test modules (test_keyword_builder.py, test_main_dialog.py,
# ...) fake out orca_input_generator_pro.mixins with a stub Dialog3DPickingMixin
# and/or clobber sys.modules["PyQt6*"] with permissive stub modules, with no
# regard for import order -- whichever test file is collected first "wins"
# the shared cache slots. Load a fully private copy of mixins.py against
# genuine PyQt6 (recovered from the "__real" stash conftest.py sets aside)
# so this file's coverage always exercises the genuine module regardless of
# what other test files have done to the canonical sys.modules entries.
# ---------------------------------------------------------------------------

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


try:
    for _dep in ("PyQt6", "PyQt6.QtWidgets", "PyQt6.QtCore", "PyQt6.QtGui"):
        _real_module(_dep)
except ImportError:  # bare-pytest CI has no PyQt6 installed
    pytest.skip("requires real PyQt6 (host app dep)", allow_module_level=True)

_real_pyqt6_pkg = sys.modules["PyQt6"]
_real_pyqt6_pkg.QtWidgets = sys.modules["PyQt6.QtWidgets"]
_real_pyqt6_pkg.QtCore = sys.modules["PyQt6.QtCore"]
_real_pyqt6_pkg.QtGui = sys.modules["PyQt6.QtGui"]


def _load_private_mixins():
    full_name = f"{_PRIV_PKG}.mixins"
    if full_name in sys.modules:
        return sys.modules[full_name]
    path = os.path.join(_REPO_ROOT, "orca_input_generator_pro", "mixins.py")
    spec = importlib.util.spec_from_file_location(full_name, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = _PRIV_PKG
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


mixins_mod = _load_private_mixins()
Dialog3DPickingMixin = mixins_mod.Dialog3DPickingMixin

from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtCore import QEvent, Qt, QPointF
from PyQt6.QtGui import QMouseEvent

_app = QApplication.instance() or QApplication([])


class _PickingDialog(Dialog3DPickingMixin, QDialog):
    def __init__(self, main_window=None, mol=None):
        QDialog.__init__(self)
        Dialog3DPickingMixin.__init__(self)
        self.main_window = main_window
        self.mol = mol
        self.picked = []
        self.cleared = False

    def on_atom_picked(self, idx):
        self.picked.append(idx)

    def clear_selection(self):
        self.cleared = True


def _make_interactor():
    """A real QObject (for super().eventFilter()'s C++ type check and for
    identity comparisons) with MagicMock instance attributes standing in for
    the VTK-side API (installEventFilter/GetEventPosition/...) so calls on it
    can still be asserted/configured like a mock."""
    interactor = QDialog()
    interactor.installEventFilter = MagicMock()
    interactor.removeEventFilter = MagicMock()
    interactor.GetEventPosition = MagicMock(return_value=(1, 2))
    return interactor


def _make_mw(has_plotter=True, atom_positions=None, atom_actor="ACTOR"):
    mw = MagicMock()
    if not has_plotter:
        mw.view_3d_manager = None
        return mw
    v3d = MagicMock()
    v3d.plotter = MagicMock()
    # super().eventFilter(obj, event) requires a genuine QObject -- a
    # MagicMock for "obj" fails PyQt6's C++ type checking even on the
    # fall-through path, so the interactor must be a real (if otherwise
    # inert) QObject, not a mock.
    v3d.plotter.interactor = _make_interactor()
    v3d.atom_actor = atom_actor
    v3d.atom_positions_3d = atom_positions
    mw.view_3d_manager = v3d
    return mw


def _mouse_event(event_type, pos=(0, 0), button=Qt.MouseButton.LeftButton):
    return QMouseEvent(
        event_type,
        QPointF(*pos),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )


class _FakeMol:
    def __init__(self, n_atoms):
        self._n = n_atoms

    def GetNumAtoms(self):
        return self._n


# ---------------------------------------------------------------------------
# enable_picking / disable_picking
# ---------------------------------------------------------------------------


class TestEnableDisablePicking(unittest.TestCase):
    def test_enable_with_plotter_installs_filter(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        dlg.enable_picking()
        mw.view_3d_manager.plotter.interactor.installEventFilter.assert_called_once_with(
            dlg
        )
        self.assertTrue(dlg.picking_enabled)

    def test_enable_without_view_3d_manager_no_crash(self):
        mw = _make_mw(has_plotter=False)
        dlg = _PickingDialog(main_window=mw)
        dlg.enable_picking()
        self.assertFalse(dlg.picking_enabled)

    def test_enable_without_plotter_attr_no_crash(self):
        mw = MagicMock()
        v3d = MagicMock()
        v3d.plotter = None
        mw.view_3d_manager = v3d
        dlg = _PickingDialog(main_window=mw)
        dlg.enable_picking()
        self.assertFalse(dlg.picking_enabled)

    def test_disable_removes_filter_and_clears_labels(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        dlg.enable_picking()
        dlg.selection_labels = ["actor1", "actor2"]
        dlg.disable_picking()
        mw.view_3d_manager.plotter.interactor.removeEventFilter.assert_called_once_with(
            dlg
        )
        self.assertFalse(dlg.picking_enabled)
        self.assertEqual(dlg.selection_labels, [])

    def test_disable_when_not_enabled_still_clears_labels(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        dlg.selection_labels = ["actor1"]
        dlg.disable_picking()
        mw.view_3d_manager.plotter.interactor.removeEventFilter.assert_not_called()
        self.assertEqual(dlg.selection_labels, [])


# ---------------------------------------------------------------------------
# clear_selection_labels / clear_atom_labels alias
# ---------------------------------------------------------------------------


class TestClearSelectionLabels(unittest.TestCase):
    def test_removes_each_actor_via_plotter(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        dlg.selection_labels = ["a1", "a2", "a3"]
        dlg.clear_selection_labels()
        self.assertEqual(
            mw.view_3d_manager.plotter.remove_actor.call_count, 3
        )
        self.assertEqual(dlg.selection_labels, [])

    def test_no_view_3d_manager_no_crash(self):
        mw = _make_mw(has_plotter=False)
        dlg = _PickingDialog(main_window=mw)
        dlg.selection_labels = ["a1"]
        dlg.clear_selection_labels()
        self.assertEqual(dlg.selection_labels, [])

    def test_remove_actor_exception_is_caught(self):
        mw = _make_mw()
        mw.view_3d_manager.plotter.remove_actor.side_effect = RuntimeError("boom")
        dlg = _PickingDialog(main_window=mw)
        dlg.selection_labels = ["a1"]
        dlg.clear_selection_labels()  # must not raise
        self.assertEqual(dlg.selection_labels, [])

    def test_clear_atom_labels_is_alias(self):
        self.assertIs(
            Dialog3DPickingMixin.clear_atom_labels,
            Dialog3DPickingMixin.clear_selection_labels,
        )

    def test_empty_labels_no_crash(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        dlg.clear_selection_labels()
        self.assertEqual(dlg.selection_labels, [])


# ---------------------------------------------------------------------------
# show_atom_labels_for
# ---------------------------------------------------------------------------


class TestShowAtomLabelsFor(unittest.TestCase):
    def test_no_view_3d_manager_returns_early(self):
        mw = _make_mw(has_plotter=False)
        dlg = _PickingDialog(main_window=mw)
        dlg.show_atom_labels_for([(0, "H1")])  # must not raise

    def test_adds_label_for_each_valid_atom(self):
        positions = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        mw = _make_mw(atom_positions=positions)
        dlg = _PickingDialog(main_window=mw)
        dlg.show_atom_labels_for([(0, "H1"), (1, "H2")])
        self.assertEqual(
            mw.view_3d_manager.plotter.add_point_labels.call_count, 2
        )
        self.assertEqual(len(dlg.selection_labels), 2)

    def test_skips_out_of_range_index(self):
        positions = np.array([[0.0, 0.0, 0.0]])
        mw = _make_mw(atom_positions=positions)
        dlg = _PickingDialog(main_window=mw)
        dlg.show_atom_labels_for([(5, "Ghost")])
        mw.view_3d_manager.plotter.add_point_labels.assert_not_called()
        self.assertEqual(dlg.selection_labels, [])

    def test_none_atom_positions_no_labels_added(self):
        mw = _make_mw(atom_positions=None)
        dlg = _PickingDialog(main_window=mw)
        dlg.show_atom_labels_for([(0, "H1")])
        mw.view_3d_manager.plotter.add_point_labels.assert_not_called()

    def test_clears_existing_labels_first(self):
        positions = np.array([[0.0, 0.0, 0.0]])
        mw = _make_mw(atom_positions=positions)
        dlg = _PickingDialog(main_window=mw)
        dlg.selection_labels = ["old_actor"]
        dlg.show_atom_labels_for([(0, "H1")])
        mw.view_3d_manager.plotter.remove_actor.assert_called_once_with("old_actor")

    def test_camera_position_restored(self):
        positions = np.array([[0.0, 0.0, 0.0]])
        mw = _make_mw(atom_positions=positions)
        mw.view_3d_manager.plotter.camera_position = "CAMPOS"
        dlg = _PickingDialog(main_window=mw)
        dlg.show_atom_labels_for([(0, "H1")])
        self.assertEqual(mw.view_3d_manager.plotter.camera_position, "CAMPOS")

    def test_camera_position_read_failure_is_tolerated(self):
        positions = np.array([[0.0, 0.0, 0.0]])
        mw = _make_mw(atom_positions=positions)
        type(mw.view_3d_manager.plotter).camera_position = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("no camera"))
        )
        dlg = _PickingDialog(main_window=mw)
        dlg.show_atom_labels_for([(0, "H1")])  # must not raise


# ---------------------------------------------------------------------------
# eventFilter
# ---------------------------------------------------------------------------


class TestEventFilter(unittest.TestCase):
    def test_no_view_3d_manager_falls_through_to_super(self):
        mw = _make_mw(has_plotter=False)
        dlg = _PickingDialog(main_window=mw)
        event = _mouse_event(QEvent.Type.MouseButtonPress)
        result = dlg.eventFilter(dlg, event)
        self.assertFalse(result)

    def test_no_plotter_falls_through(self):
        mw = MagicMock()
        v3d = MagicMock()
        v3d.plotter = None
        mw.view_3d_manager = v3d
        dlg = _PickingDialog(main_window=mw)
        event = _mouse_event(QEvent.Type.MouseButtonPress)
        result = dlg.eventFilter(dlg, event)
        self.assertFalse(result)

    def test_np_none_falls_through(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        event = _mouse_event(QEvent.Type.MouseButtonPress)
        with patch.object(mixins_mod, "np", None):
            result = dlg.eventFilter(dlg, event)
        self.assertFalse(result)

    def test_press_picks_atom_when_actor_matches(self):
        positions = np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
        mw = _make_mw(atom_positions=positions, atom_actor="ATOM_ACTOR")
        picker = mw.view_3d_manager.plotter.picker
        picker.GetActor.return_value = "ATOM_ACTOR"
        picker.GetPickPosition.return_value = (0.1, 0.0, 0.0)
        mw.view_3d_manager.plotter.interactor.GetEventPosition.return_value = (1, 2)

        dlg = _PickingDialog(main_window=mw, mol=_FakeMol(2))
        event = _mouse_event(
            QEvent.Type.MouseButtonPress, pos=(10, 20)
        )
        result = dlg.eventFilter(mw.view_3d_manager.plotter.interactor, event)
        self.assertTrue(result)
        self.assertEqual(dlg.picked, [0])

    def test_press_no_match_actor_falls_through(self):
        positions = np.array([[0.0, 0.0, 0.0]])
        mw = _make_mw(atom_positions=positions, atom_actor="ATOM_ACTOR")
        picker = mw.view_3d_manager.plotter.picker
        picker.GetActor.return_value = "SOMETHING_ELSE"
        mw.view_3d_manager.plotter.interactor.GetEventPosition.return_value = (1, 2)

        dlg = _PickingDialog(main_window=mw, mol=_FakeMol(1))
        event = _mouse_event(QEvent.Type.MouseButtonPress)
        result = dlg.eventFilter(mw.view_3d_manager.plotter.interactor, event)
        self.assertFalse(result)
        self.assertEqual(dlg.picked, [])

    def test_press_atom_positions_none_falls_through(self):
        mw = _make_mw(atom_positions=None, atom_actor="ATOM_ACTOR")
        picker = mw.view_3d_manager.plotter.picker
        picker.GetActor.return_value = "ATOM_ACTOR"
        mw.view_3d_manager.plotter.interactor.GetEventPosition.return_value = (1, 2)

        dlg = _PickingDialog(main_window=mw, mol=_FakeMol(1))
        event = _mouse_event(QEvent.Type.MouseButtonPress)
        result = dlg.eventFilter(mw.view_3d_manager.plotter.interactor, event)
        self.assertFalse(result)

    def test_press_closest_atom_out_of_range_falls_through(self):
        # atom_positions has only 1 row, but mol reports 0 atoms -> idx 0 is
        # out of range for GetNumAtoms(), so on_atom_picked must not fire.
        positions = np.array([[0.0, 0.0, 0.0]])
        mw = _make_mw(atom_positions=positions, atom_actor="ATOM_ACTOR")
        picker = mw.view_3d_manager.plotter.picker
        picker.GetActor.return_value = "ATOM_ACTOR"
        picker.GetPickPosition.return_value = (0.0, 0.0, 0.0)
        mw.view_3d_manager.plotter.interactor.GetEventPosition.return_value = (1, 2)

        dlg = _PickingDialog(main_window=mw, mol=_FakeMol(0))
        event = _mouse_event(QEvent.Type.MouseButtonPress)
        result = dlg.eventFilter(mw.view_3d_manager.plotter.interactor, event)
        self.assertFalse(result)
        self.assertEqual(dlg.picked, [])

    def test_press_exception_is_caught_and_falls_through(self):
        mw = _make_mw(atom_positions=np.array([[0.0, 0.0, 0.0]]))
        mw.view_3d_manager.plotter.picker.Pick.side_effect = RuntimeError("vtk boom")
        mw.view_3d_manager.plotter.interactor.GetEventPosition.return_value = (1, 2)

        dlg = _PickingDialog(main_window=mw, mol=_FakeMol(1))
        event = _mouse_event(QEvent.Type.MouseButtonPress)
        result = dlg.eventFilter(mw.view_3d_manager.plotter.interactor, event)
        self.assertFalse(result)

    def test_press_wrong_object_falls_through_without_picking(self):
        mw = _make_mw(atom_positions=np.array([[0.0, 0.0, 0.0]]))
        dlg = _PickingDialog(main_window=mw, mol=_FakeMol(1))
        event = _mouse_event(QEvent.Type.MouseButtonPress)
        other_obj = QDialog()
        result = dlg.eventFilter(other_obj, event)
        self.assertFalse(result)
        self.assertEqual(dlg.picked, [])

    def test_mouse_move_sets_moved_flag_past_threshold(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        dlg._mouse_press_pos = QPointF(0, 0).toPoint()
        move_event = _mouse_event(QEvent.Type.MouseMove, pos=(10, 10))
        dlg.eventFilter(mw.view_3d_manager.plotter.interactor, move_event)
        self.assertTrue(dlg._mouse_moved)

    def test_mouse_move_below_threshold_does_not_set_flag(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        dlg._mouse_press_pos = QPointF(0, 0).toPoint()
        dlg._mouse_moved = False
        move_event = _mouse_event(QEvent.Type.MouseMove, pos=(1, 1))
        dlg.eventFilter(mw.view_3d_manager.plotter.interactor, move_event)
        self.assertFalse(dlg._mouse_moved)

    def test_mouse_move_no_press_pos_no_crash(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        dlg._mouse_press_pos = None
        move_event = _mouse_event(QEvent.Type.MouseMove, pos=(10, 10))
        dlg.eventFilter(mw.view_3d_manager.plotter.interactor, move_event)  # no crash

    def test_release_without_move_clears_selection(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        dlg._mouse_press_pos = QPointF(0, 0).toPoint()
        dlg._mouse_moved = False
        release_event = _mouse_event(QEvent.Type.MouseButtonRelease)
        dlg.eventFilter(mw.view_3d_manager.plotter.interactor, release_event)
        self.assertTrue(dlg.cleared)
        self.assertIsNone(dlg._mouse_press_pos)

    def test_release_after_move_does_not_clear_selection(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        dlg._mouse_press_pos = QPointF(0, 0).toPoint()
        dlg._mouse_moved = True
        release_event = _mouse_event(QEvent.Type.MouseButtonRelease)
        dlg.eventFilter(mw.view_3d_manager.plotter.interactor, release_event)
        self.assertFalse(dlg.cleared)

    def test_release_without_prior_press_no_crash(self):
        mw = _make_mw()
        dlg = _PickingDialog(main_window=mw)
        dlg._mouse_press_pos = None
        release_event = _mouse_event(QEvent.Type.MouseButtonRelease)
        dlg.eventFilter(mw.view_3d_manager.plotter.interactor, release_event)  # no crash
        self.assertFalse(dlg.cleared)


if __name__ == "__main__":
    unittest.main()
