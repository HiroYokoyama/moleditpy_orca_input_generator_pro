"""Input recovery uses no GUI or chemistry imports."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "input_loading_parser",
    Path(__file__).parents[1] / "orca_input_generator_pro" / "input_loading.py",
)
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)

ORCA = """# water
%pal nprocs 16 end
%maxcore 3456
! PBE0 def2-TZVP Opt
%scf
  MaxIter 777
end
* xyz -1 2
O 0 0 0
H 0 0 1D0
*
%plots
  dim1 100
end
"""
GAUSSIAN = """%nprocshared=12
%mem=2048MB
%oldchk=previous.chk
%chk=custom.chk
#p PBE0/def2TZVP Opt
 SCF=(XQC,MaxCycle=777)

water
title line two

-1 2
O 0 0 0
H 0 0 1D0

additional input

"""


def test_orca_resources_keywords_and_pre_post_blocks():
    settings, rows, notes = loader.parse_input(ORCA, "orca")
    assert settings["nproc"] == 16
    assert settings["maxcore"] == 3456
    assert settings["charge"] == -1 and settings["mult"] == 2
    assert "MaxIter 777" in settings["adv"]
    assert "%plots" in settings["adv_post"]
    assert len(rows) == 2 and rows[-1][-1] == 1
    assert not notes


def test_gaussian_resources_multiline_route_and_tail():
    settings, rows, notes = loader.parse_input(GAUSSIAN, "gaussian")
    assert settings["nproc"] == 12
    assert settings["mem_val"] == 2048 and settings["mem_unit"] == "MB"
    assert settings["chk"] == "custom.chk"
    assert settings["oldchk"] == "previous.chk"
    assert "MaxCycle=777" in settings["route"]
    assert settings["tail"] == "additional input"
    assert settings["charge"] == -1 and settings["mult"] == 2
    assert len(rows) == 2 and not notes


def test_extra_jobs_are_not_mistaken_for_first_geometry():
    _, rows, notes = loader.parse_input(
        ORCA + "$new_job\n! Freq\n* xyzfile 0 1 next.xyz\n", "orca"
    )
    assert len(rows) == 2
    assert any("Additional jobs" in note for note in notes)


def test_external_xyz_uses_input_directory(tmp_path):
    (tmp_path / "coords file.xyz").write_text("2\nwater\nO 0 0 0\nH 0 0 1\n")
    text = '! HF\n* xyzfile 0 1 "coords file.xyz"\n'
    _, rows, notes = loader.parse_input(text, "orca", str(tmp_path / "input.inp"))
    assert len(rows) == 2 and not notes


def test_missing_external_xyz_is_reported_without_losing_conditions(tmp_path):
    settings, rows, notes = loader.parse_input(
        "! HF\n* xyzfile 0 1 absent.xyz\n", "orca", str(tmp_path / "job.inp")
    )
    assert settings["route"] == "! HF"
    assert not rows and notes


def test_internal_geometry_is_not_guessed_from_old_molecule():
    _, rows, notes = loader.parse_input(
        "! HF\n* gzmt 0 1\nO\nH 1 unresolved\n*\n", "orca"
    )
    assert not rows and notes


def test_internal_coordinates_and_gaussian_variables():
    rows = loader.internal_rows(["O", "H 1 R", "H 1 R 2 A"], "R=0.96\nA=104.5")
    assert len(rows) == 3
    assert rows[1][-1] == pytest.approx(0.96)
    assert sum(value * value for value in rows[2][1:]) == pytest.approx(0.96**2)
    text = "# HF/3-21G\n\nwater\n\n0 1\nO\nH 1 R\nH 1 R 2 A\n\nR=0.96\nA=104.5\n\n"
    settings, rows, notes = loader.parse_input(text, "gaussian")
    assert len(rows) == 3 and not notes
    assert settings["coord_format"] == "Z-Matrix (variables)"


def test_orca_internal_fixed_columns():
    text = "! HF\n* int 0 1\nO 0 0 0 0 0 0\nH 1 0 0 .96 0 0\nH 1 2 0 .96 104.5 0\n*\n"
    _, rows, notes = loader.parse_input(text, "orca")
    assert len(rows) == 3 and not notes


def test_zmatrix_reference_and_variable_errors_are_safe():
    for rows in (["O", "H 2 1.0"], ["O", "H 1 __import__('os')"], ["O", "H 1 -1.0"]):
        with pytest.raises(ValueError):
            loader.internal_rows(rows)


@pytest.mark.parametrize(
    "kind,text",
    [
        ("orca", "not input"),
        ("gaussian", "not input"),
        ("orca", "! HF\n* xyz 0 1\nH 0 0 0"),
    ],
)
def test_invalid_files_fail_before_modifying_dialog(kind, text):
    with pytest.raises(ValueError):
        loader.parse_input(text, kind)


def test_nonfinite_coordinates_are_rejected():
    with pytest.raises(ValueError):
        loader.cartesian_rows(["H nan 0 0"])


def test_bohr_coordinates_are_converted_for_the_viewer():
    for kind, text in (
        ("orca", "! HF Bohrs\n* xyz 0 1\nH 0 0 1\n*\n"),
        ("gaussian", "# HF Units=Bohr\n\ntitle\n\n0 1\nH 0 0 1\n\n"),
    ):
        _, rows, _ = loader.parse_input(text, kind)
        assert rows[0][-1] == pytest.approx(0.529177210903)


def test_utf16_bom_and_binary_rejection(tmp_path):
    path = tmp_path / "input.inp"
    path.write_text(ORCA, encoding="utf-16")
    assert loader.read_input(path).startswith("# water")
    path.write_bytes(b"binary\0content")
    with pytest.raises(ValueError):
        loader.read_input(path)
