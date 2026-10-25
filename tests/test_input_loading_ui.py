"""Real-widget checks for authoritative text and conditional project storage."""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from .test_input_parsing import ORCA as INPUT
from .test_main_dialog_extended import (
    _make_water,
    _real_module,
    _RealDialogTestCase,
    main_dialog_mod,
)


class TestInputLoading(_RealDialogTestCase):
    def setUp(self):
        super().setUp()
        modules = {
            name: _real_module(name)
            for name in (
                "PySide6",
                "PySide6.QtCore",
                "PySide6.QtWidgets",
                "rdkit",
                "rdkit.Chem",
            )
        }
        context = patch.dict(sys.modules, modules)
        context.start()
        self.addCleanup(context.stop)
        chemistry = patch.object(modules["rdkit"], "Chem", modules["rdkit.Chem"])
        chemistry.start()
        self.addCleanup(chemistry.stop)

    def make_dialog(self, state=None, **kwargs):
        dialog = self._make_dialog(persistent_settings=state, **kwargs)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_normal_generation_and_refresh_do_not_store_full_text(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        assert "input_text" not in state
        original = dialog.preview_text.toPlainText()
        dialog.preview_text.setPlainText(original + "\ncustom instruction\n")
        assert state["input_text"].endswith("custom instruction\n")
        assert not dialog.input_settings_widget.isEnabled()
        dialog.update_preview()
        assert "custom instruction" in dialog.preview_text.toPlainText()
        dialog.refresh_input_preview()
        assert "input_text" not in state
        assert dialog.input_settings_widget.isEnabled()

    def test_saving_generated_input_does_not_create_a_text_override(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        destination = Path(self._tmpdir) / "generated.inp"
        with patch.object(
            main_dialog_mod.QFileDialog,
            "getSaveFileName",
            return_value=(str(destination), ""),
        ):
            dialog.save_file()
        assert destination.is_file()
        assert "input_text" not in state
        assert not dialog._text_override

    def test_reverting_direct_edits_drops_redundant_text(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        original = dialog.preview_text.toPlainText()
        dialog.preview_text.setPlainText(original + "\nextra\n")
        dialog.preview_text.setPlainText(original)
        assert "input_text" not in state
        assert dialog.input_settings_widget.isEnabled()

    def test_imported_charge_survives_even_when_source_matches_generated_text(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        dialog.charge_spin.setValue(1)
        source = dialog.preview_text.toPlainText()
        assert "input_text" not in state
        dialog.restore_input_text(source)
        assert state["input_text"] == source
        reopened = self.make_dialog(json.loads(json.dumps(state)), mol=_make_water())
        assert reopened.charge_spin.value() == 1
        assert reopened.preview_text.toPlainText() == source
        reopened.refresh_input_preview()
        assert "input_text" not in reopened.persistent_settings

    def test_import_displays_structure_recovers_conditions_and_keeps_source(self):
        source = Path(self._tmpdir) / "source.inp"
        source.write_text(INPUT, encoding="utf-8")
        before = source.read_bytes()
        state, displayed = {}, Mock()
        dialog = self.make_dialog(state, display_molecule=displayed)
        assert dialog.load_input_file(str(source))
        assert dialog.preview_text.toPlainText() == INPUT
        assert state["input_text"] == INPUT
        assert dialog.charge_spin.value() == -1
        assert dialog.mult_spin.value() == 2
        assert dialog.nproc_spin.value() == 16
        displayed.assert_called_once()
        mol = displayed.call_args.args[0]
        assert mol.GetNumAtoms() == 2
        assert mol.GetConformer().GetAtomPosition(1).z == 1
        assert source.read_bytes() == before
        assert not dialog._is_modified()

    def test_project_round_trip_preserves_complex_and_edited_text(self):
        text = INPUT + "\n# retained <verbatim> custom data\n"
        state = {"input_text": text}
        dialog = self.make_dialog(state)
        assert dialog.preview_text.toPlainText() == text
        edited = text + "# edited in Preview\n"
        dialog.preview_text.setPlainText(edited)
        project_data = json.loads(json.dumps(state))
        restored = self.make_dialog(project_data)
        assert restored.preview_text.toPlainText() == edited
        assert project_data["input_text"] == edited
        restored.refresh_input_preview()
        assert "input_text" not in project_data

    def test_unfinished_and_empty_project_edits_restore_verbatim(self):
        for text in ("unfinished <input>", ""):
            with self.subTest(text=text):
                dialog = self.make_dialog({"input_text": text})
                assert dialog.preview_text.toPlainText() == text

    def test_explicit_save_keeps_original_checkpoint_and_unknown_instructions(self):
        state = {"input_text": INPUT + "# extra\n"}
        dialog = self.make_dialog(state)
        destination = Path(self._tmpdir) / "other-name.inp"
        dialog.current_inp_file = str(destination)
        dialog._save_current_file()
        assert destination.read_text(encoding="utf-8") == state["input_text"]

    def test_invalid_or_cancelled_load_keeps_existing_text(self):
        dialog = self.make_dialog({}, mol=_make_water())
        before = dialog.preview_text.toPlainText()
        bad = Path(self._tmpdir) / "bad.input"
        bad.write_text("invalid input")
        with patch.object(main_dialog_mod.QMessageBox, "warning"):
            assert not dialog.load_input_file(str(bad))
        assert dialog.preview_text.toPlainText() == before

    def test_replacing_unfiled_direct_edits_can_be_cancelled(self):
        dialog = self.make_dialog({"input_text": INPUT})
        source = Path(self._tmpdir) / "other.input"
        source.write_text(INPUT)
        with patch.object(
            main_dialog_mod.QMessageBox,
            "question",
            return_value=main_dialog_mod.QMessageBox.StandardButton.No,
        ):
            assert not dialog.load_input_file(str(source))
        assert dialog.preview_text.toPlainText() == INPUT
        valid = Path(self._tmpdir) / "valid.input"
        valid.write_text(INPUT)
        with patch.object(dialog, "_confirm_discard", return_value=False):
            assert not dialog.load_input_file(str(valid))
        assert dialog.preview_text.toPlainText() == INPUT

    def project_roundtrip(self, state):
        from .test_input_json import project_writer

        path = Path(self._tmpdir) / "roundtrip.pmeprj"
        plugin = sys.modules[main_dialog_mod.__package__]
        with (
            patch.object(plugin, "current_settings", state),
            patch.object(plugin, "_dialog_opened", True),
            patch.object(plugin, "_context", None),
        ):
            context = Mock()
            plugin.initialize(context)
            save = context.register_save_handler.call_args.args[0]
            load = context.register_load_handler.call_args.args[0]
            project_writer()(
                str(path),
                {
                    "format": "PME Project",
                    "version": "1.0",
                    "plugins": {"generator": save()},
                },
            )
            restored = json.loads(path.read_text(encoding="utf-8"))["plugins"][
                "generator"
            ]
            plugin.current_settings = {}
            plugin._dialog_opened = False
            load(restored)
            return save()

    def test_generated_charge_and_spin_survive_project_without_full_text(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        dialog.charge_spin.setValue(1)
        dialog.mult_spin.setValue(2)
        expected = dialog.preview_text.toPlainText()
        assert "input_text" not in state
        reopened = self.make_dialog(self.project_roundtrip(state), mol=_make_water())
        assert reopened.charge_spin.value() == 1
        assert reopened.mult_spin.value() == 2
        assert reopened.preview_text.toPlainText() == expected
        assert "input_text" not in reopened.persistent_settings

    def test_project_text_does_not_replace_project_molecule(self):
        mol = _make_water()
        mol.SetProp("project_marker", "preserve")
        displayed = Mock()
        state = self.project_roundtrip({"input_text": INPUT})
        dialog = self.make_dialog(state, mol=mol, display_molecule=displayed)
        assert dialog.mol is mol
        assert dialog.mol.GetProp("project_marker") == "preserve"
        displayed.assert_not_called()
        assert dialog.preview_text.toPlainText() == INPUT

    def test_imported_large_resources_survive_project(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        dialog.nproc_spin.setMaximum(512)
        dialog.nproc_spin.setValue(512)
        expected = dialog.preview_text.toPlainText()
        reopened = self.make_dialog(self.project_roundtrip(state), mol=_make_water())
        assert reopened.nproc_spin.value() == 512
        assert reopened.preview_text.toPlainText() == expected

    def test_external_xyz_filename_survives_project(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        dialog.coord_format_combo.setCurrentText("XYZ File")
        dialog.xyzfile_name_edit.setText("custom geometry.xyz")
        expected = dialog.preview_text.toPlainText()
        assert "input_text" not in state
        reopened = self.make_dialog(self.project_roundtrip(state), mol=_make_water())
        assert reopened.xyzfile_name_edit.text() == "custom geometry.xyz"
        assert reopened.preview_text.toPlainText() == expected

    def test_manual_charge_is_ignored_for_changed_molecule(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        dialog.charge_spin.setValue(1)
        mol = _make_water()
        mol.GetAtomWithIdx(0).SetFormalCharge(-1)
        reopened = self.make_dialog(self.project_roundtrip(state), mol=mol)
        assert reopened.charge_spin.value() == -1

    def test_large_negative_manual_charge_survives_project(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        dialog.charge_spin.setMinimum(-30)
        dialog.charge_spin.setValue(-20)
        reopened = self.make_dialog(self.project_roundtrip(state), mol=_make_water())
        assert reopened.charge_spin.value() == -20

    def test_charge_sensitive_import_remains_authoritative_after_repeated_loads(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        dialog.charge_spin.setValue(1)
        source = dialog.preview_text.toPlainText()
        dialog.restore_input_text(source)
        for _ in range(2):
            state = self.project_roundtrip(state)
            dialog = self.make_dialog(state, mol=_make_water())
            assert state["input_text"] == source
            assert dialog.charge_spin.value() == 1

    def test_complex_edited_multijob_text_survives_project_and_export(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        separator = "$new_job" if dialog.INPUT_KIND == "orca" else "--Link1--"
        source = (
            INPUT
            + "\n"
            + separator
            + '\n# unknown directives 日本語 "x"\n%custom <tag>\n'
        )
        dialog.preview_text.setPlainText(source)
        reopened = self.make_dialog(self.project_roundtrip(state), mol=_make_water())
        assert reopened.preview_text.toPlainText() == source
        destination = Path(self._tmpdir) / "exported.input"
        with patch.object(
            main_dialog_mod.QFileDialog,
            "getSaveFileName",
            return_value=(str(destination), ""),
        ):
            reopened.save_file()
        assert destination.read_text(encoding="utf-8") == source
        assert reopened.persistent_settings["input_text"] == source

    def test_failed_export_preserves_existing_file_and_preview(self):
        dialog = self.make_dialog({}, mol=_make_water())
        destination = Path(self._tmpdir) / "existing.input"
        destination.write_text("previous input", encoding="utf-8")
        original = dialog.preview_text.toPlainText()
        with (
            patch.object(
                main_dialog_mod.QFileDialog,
                "getSaveFileName",
                return_value=(str(destination), ""),
            ),
            patch("os.replace", side_effect=OSError("disk failure")),
            patch.object(main_dialog_mod.QMessageBox, "critical") as error,
        ):
            dialog.save_file()
        error.assert_called_once()
        assert destination.read_text(encoding="utf-8") == "previous input"
        assert dialog.preview_text.toPlainText() == original
        assert dialog.current_inp_file is None
        assert not list(destination.parent.glob(".moleditpy-input-*"))

    def test_small_positive_memory_survives_project(self):
        state = {}
        dialog = self.make_dialog(state, mol=_make_water())
        dialog.mem_spin.setMinimum(1)
        dialog.mem_spin.setValue(10)
        expected = dialog.preview_text.toPlainText()
        reopened = self.make_dialog(self.project_roundtrip(state), mol=_make_water())
        assert reopened.mem_spin.value() == 10
        assert reopened.preview_text.toPlainText() == expected
