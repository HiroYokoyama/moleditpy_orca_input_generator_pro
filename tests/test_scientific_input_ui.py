"""Exercise import/refresh and builders with actual host chemistry/Qt types."""

import sys
from unittest.mock import patch

from . import test_input_loading_ui as loading_tests
from .test_main_dialog_extended import (
    _make_water,
    _real_module,
    _RealDialogTestCase,
    keyword_builder_mod,
    main_dialog_mod,
)


class TestScientificInput(_RealDialogTestCase):
    def setUp(self):
        _RealDialogTestCase.setUp(self)
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

    make_dialog = loading_tests.TestInputLoading.make_dialog

    def test_ghost_import_refresh_keeps_basis_only_atom_and_electron_count(self):
        dialog = self.make_dialog({})
        dialog.restore_input_text("! HF def2-SVP\n* xyz 0 2\nH 0 0 0\nH: 0 0 1\n*\n")
        dialog.refresh_input_preview()
        assert "H:" in dialog.preview_text.toPlainText()
        assert main_dialog_mod._electron_count(dialog.mol, 0) == 1

    def test_bohr_import_refresh_preserves_bond_length(self):
        dialog = self.make_dialog({})
        dialog.restore_input_text(
            "! HF def2-SVP Bohrs\n* xyz 0 1\nH 0 0 0\nH 0 0 1\n*\n"
        )
        dialog.refresh_input_preview()
        from .test_input_parsing import loader

        _, rows, _ = loader.parse_input(dialog.preview_text.toPlainText(), "orca")
        assert abs(rows[1][3] - 0.529177210903) < 1e-6

    def test_hessian_option_uses_geom_block(self):
        builder = keyword_builder_mod.OrcaKeywordBuilderDialog(
            None, "! HF def2-SVP Opt"
        )
        self.addCleanup(builder.deleteLater)
        builder.opt_calcfc.setChecked(True)
        result = builder.get_route()
        assert "Calc_Hess true" in result
        assert "CalcFC" not in result and "CalcHess" not in result

    def test_numfreq_does_not_depend_on_dialog_visibility(self):
        builder = keyword_builder_mod.OrcaKeywordBuilderDialog(
            None, "! HF def2-SVP NumFreq"
        )
        self.addCleanup(builder.deleteLater)
        assert "NumFreq" in builder.get_route()
        assert " Freq" not in builder.get_route()

    def test_builder_does_not_inject_default_basis(self):
        builder = keyword_builder_mod.OrcaKeywordBuilderDialog(None, "! HF NMR")
        self.addCleanup(builder.deleteLater)
        assert "def2-SVP" not in builder.get_route()

    def test_basis_count_rejects_impossible_spin(self):
        dialog = self.make_dialog({}, mol=_make_water())
        dialog.charge_spin.setValue(10)
        dialog.mult_spin.setValue(3)
        assert dialog.mult_spin.palette() != dialog.default_palette

    def test_md_template_has_a_run_after_initialization(self):
        dialog = self.make_dialog({}, mol=_make_water())
        dialog.block_combo.setCurrentText("%md ... end")
        dialog.insert_block_template()
        text = dialog.generate_input_content()
        assert "Initvel     300_K" in text
        assert "Thermostat  NHC 300_K Timecon 10.0_fs" in text
        assert text.count("Run         2000") == 1
        assert text.index("Initvel") < text.index("Run         2000")
        assert "TotalTime" not in text and "NHCQ" not in text

    def test_compound_keeps_nested_coordinates_inside_block(self):
        dialog = self.make_dialog({}, mol=_make_water())
        dialog.block_combo.setCurrentText("%compound ... EndRun")
        dialog.insert_block_template()
        text = dialog.generate_input_content()
        assert "Read_Geom(1);" in text
        assert text.count("%compound") == 1
        assert text.index("New_Step") < text.index("* xyzfile") < text.index("Step_End")
        assert "* xyz 0 1" not in text
        assert text.rstrip().endswith("end")

    def test_fragment_template_defines_groups_after_coordinates(self):
        dialog = self.make_dialog({}, mol=_make_water())
        dialog.block_combo.setCurrentText("%frag (BSSE/Counterpoise)")
        dialog.insert_block_template()
        text = dialog.generate_input_content()
        assert "Definition" in text and "1 {0 1 2} end" in text
        assert "GhostFrags {2} end" in text
        assert text.index("* xyz") < text.index("%frag")
        assert "NFrags" not in text

    def test_linear_reference_plane_falls_back_without_nan_coordinates(self):
        mol = _make_water()
        from rdkit import Chem

        editable = Chem.RWMol(mol)
        editable.AddAtom(Chem.Atom("H"))
        mol = editable.GetMol()
        conf = Chem.Conformer(4)
        for index in range(4):
            conf.SetAtomPosition(index, (0.0, 0.0, float(index)))
        mol.RemoveAllConformers()
        mol.AddConformer(conf)
        dialog = self.make_dialog({}, mol=mol)
        dialog.coord_format_combo.setCurrentText("Internal (* gzmt)")
        text = dialog.generate_input_content()
        assert "nan" not in text.lower()
        assert "Falling back to XYZ" in text or "using Cartesian" in text
