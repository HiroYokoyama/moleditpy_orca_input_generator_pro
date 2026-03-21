import os
from PyQt6.QtWidgets import QMessageBox

PLUGIN_NAME = "ORCA Input Generator Pro"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR = "HiroYokoyama"
PLUGIN_DESCRIPTION = "Advanced ORCA Input Generator with Preview and Presets."
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")

def run(mw):
    from .main_dialog import OrcaSetupDialogPro
    mol = getattr(mw, 'current_mol', None)
    if not mol:
        QMessageBox.warning(mw, PLUGIN_NAME, "No molecule loaded.")
        return
    filename = getattr(mw, 'current_file_path', None)
    if not filename:
         filename = getattr(mw, 'current_file_name', None)
    if not filename and hasattr(mw, 'windowTitle'):
         title = mw.windowTitle()
         filename = title.split(" - ")[0].strip() if " - " in title else title.strip()
    if hasattr(mw, 'orca_dialog') and mw.orca_dialog and mw.orca_dialog.isVisible():
        mw.orca_dialog.raise_()
        mw.orca_dialog.activateWindow()
        return
    mw.orca_dialog = OrcaSetupDialogPro(parent=mw, mol=mol, filename=filename)
    mw.orca_dialog.show()

def initialize(context):
    def show_dialog():
        mw = context.get_main_window()
        run(mw)
    context.add_export_action("ORCA Input...", show_dialog)

