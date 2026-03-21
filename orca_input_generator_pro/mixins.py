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
        if (obj == self.main_window.plotter.interactor and 
            event.type() == QtCore.QEvent.Type.MouseButtonPress and 
            event.button() == Qt.MouseButton.LeftButton):
            self._mouse_press_pos = event.pos()
            self._mouse_moved = False
            try:
                interactor = self.main_window.plotter.interactor
                click_pos = interactor.GetEventPosition()
                picker = self.main_window.plotter.picker
                picker.Pick(click_pos[0], click_pos[1], 0, self.main_window.plotter.renderer)
                if picker.GetActor() is self.main_window.atom_actor:
                    picked_position = np.array(picker.GetPickPosition())
                    distances = np.linalg.norm(self.main_window.atom_positions_3d - picked_position, axis=1)
                    closest_atom_idx = np.argmin(distances)
                    if 0 <= closest_atom_idx < self.mol.GetNumAtoms():
                        self.on_atom_picked(int(closest_atom_idx))
                        self._mouse_press_pos = None
                        return True
            except Exception as e: print(f"Picking Error: {e}")
        elif (obj == self.main_window.plotter.interactor and event.type() == QtCore.QEvent.Type.MouseMove):
            if hasattr(self, "_mouse_press_pos") and self._mouse_press_pos is not None:
                if (event.pos() - self._mouse_press_pos).manhattanLength() > 3:
                    self._mouse_moved = True
        elif (obj == self.main_window.plotter.interactor and event.type() == QtCore.QEvent.Type.MouseButtonRelease):
            if getattr(self, "_mouse_press_pos", None) is not None and not getattr(self, "_mouse_moved", False):
                self.clear_selection()
            self._mouse_press_pos = None
        return super().eventFilter(obj, event)

    def enable_picking(self):
        self.main_window.plotter.interactor.installEventFilter(self)
        self.picking_enabled = True

    def disable_picking(self):
        if getattr(self, "picking_enabled", False):
            self.main_window.plotter.interactor.removeEventFilter(self)
            self.picking_enabled = False
        self.clear_selection_labels()

    def clear_selection_labels(self):
        for label_actor in getattr(self, "selection_labels", []):
            try: self.main_window.plotter.remove_actor(label_actor)
            except: pass
        self.selection_labels = []
