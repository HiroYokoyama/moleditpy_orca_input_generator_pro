from PyQt6 import QtCore
from PyQt6.QtCore import Qt
import numpy as np

# --- 3D Picking Mixin (Simplified for Plugin) ---
class Dialog3DPickingMixin:
    """Provides 3D atom picking for dialogs."""
    def __init__(self):
        self.picking_enabled = False
        self.selection_labels = []

    def eventFilter(self, obj, event):
        v3d = getattr(self.main_window, "view_3d_manager", None)
        if not v3d or not getattr(v3d, "plotter", None):
            return super().eventFilter(obj, event)

        if (obj == v3d.plotter.interactor and 
            event.type() == QtCore.QEvent.Type.MouseButtonPress and 
            event.button() == Qt.MouseButton.LeftButton):
            self._mouse_press_pos = event.pos()
            self._mouse_moved = False
            try:
                interactor = v3d.plotter.interactor
                click_pos = interactor.GetEventPosition()
                picker = v3d.plotter.picker
                picker.Pick(click_pos[0], click_pos[1], 0, v3d.plotter.renderer)
                if picker.GetActor() is v3d.atom_actor:
                    picked_position = np.array(picker.GetPickPosition())
                    atom_positions = getattr(v3d, "atom_positions_3d", None)
                    if atom_positions is None:
                        return super().eventFilter(obj, event)
                    distances = np.linalg.norm(atom_positions - picked_position, axis=1)
                    closest_atom_idx = np.argmin(distances)
                    if 0 <= closest_atom_idx < self.mol.GetNumAtoms():
                        self.on_atom_picked(int(closest_atom_idx))
                        self._mouse_press_pos = None
                        return True
            except Exception as e: print(f"Picking Error: {e}")
        elif (obj == v3d.plotter.interactor and event.type() == QtCore.QEvent.Type.MouseMove):
            if hasattr(self, "_mouse_press_pos") and self._mouse_press_pos is not None:
                if (event.pos() - self._mouse_press_pos).manhattanLength() > 3:
                    self._mouse_moved = True
        elif (obj == v3d.plotter.interactor and event.type() == QtCore.QEvent.Type.MouseButtonRelease):
            if getattr(self, "_mouse_press_pos", None) is not None and not getattr(self, "_mouse_moved", False):
                self.clear_selection()
            self._mouse_press_pos = None
        return super().eventFilter(obj, event)

    def enable_picking(self):
        v3d = getattr(self.main_window, "view_3d_manager", None)
        if v3d and getattr(v3d, "plotter", None):
            v3d.plotter.interactor.installEventFilter(self)
            self.picking_enabled = True

    def disable_picking(self):
        if getattr(self, "picking_enabled", False):
            v3d = getattr(self.main_window, "view_3d_manager", None)
            if v3d and getattr(v3d, "plotter", None):
                v3d.plotter.interactor.removeEventFilter(self)
            self.picking_enabled = False
        self.clear_selection_labels()

    def clear_selection_labels(self):
        for label_actor in getattr(self, "selection_labels", []):
            try:
                v3d = getattr(self.main_window, "view_3d_manager", None)
                if v3d and getattr(v3d, "plotter", None):
                    v3d.plotter.remove_actor(label_actor)
            except: pass
        self.selection_labels = []
