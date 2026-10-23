"""Physical unit and checkpoint semantics, without optional GUI dependencies."""

import math

import pytest

from .test_input_parsing import loader


@pytest.mark.parametrize(
    "kind,route",
    [
        ("orca", "! HF def2-SVP Bohrs"),
        ("gaussian", "# HF/STO-3G Units=Bohr"),
    ],
)
def test_cartesian_bohr_export_matches_physical_coordinates(kind, route):
    exported = loader.coordinates_for_route(["H 0 0 0.529177210903"], kind, route)
    assert float(exported[0].split()[3]) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize(
    "style,row,index",
    [
        ("Internal (* int)", "H 1 0 0 0.529177210903 90 60", 4),
        ("Internal (* gzmt)", "H 1 0.529177210903 2 90 3 60", 2),
    ],
)
def test_orca_internal_export_converts_only_distances(style, row, index):
    result = loader.coordinates_for_route([row], "orca", "! HF Bohrs", style)[0].split()
    assert float(result[index]) == pytest.approx(1.0, abs=1e-9)
    assert float(result[5 if index == 4 else 4]) == 90
    assert float(result[6]) == 60


def test_gaussian_radian_zmatrix_recovers_right_angle():
    text = "# HF/STO-3G Units=(Bohr,Rad)\n\ntitle\n\n0 1\nO\nH 1 1\nH 1 1 2 1.5707963267948966\n\n"
    _, rows, notes = loader.parse_input(text, "gaussian")
    assert not notes
    vectors = [row[1:] for row in rows[1:]]
    assert sum(a * b for a, b in zip(*vectors)) == pytest.approx(0, abs=1e-12)
    for vector in vectors:
        assert math.sqrt(sum(x * x for x in vector)) == pytest.approx(0.529177210903)


def test_gaussian_variable_zmatrix_exports_selected_units():
    lines = ["H 1 B2", "Variables:", " B2=0.529177210903", " A3=90.0"]
    exported = loader.coordinates_for_route(
        lines, "gaussian", "# HF Units=(Bohr,Rad)", "Z-Matrix (variables)"
    )
    assert exported[0] == "H 1 B2"
    assert float(exported[2].split("=")[1]) == pytest.approx(1.0)
    assert float(exported[3].split("=")[1]) == pytest.approx(math.pi / 2)


def test_allcheck_recovers_basis_tail_without_mistaking_it_for_title():
    tail = "H 0\nSTO-3G\n****"
    settings, rows, _ = loader.parse_input(
        "# HF/Gen Geom=(Connectivity,AllCheck)\n\n" + tail + "\n\n", "gaussian"
    )
    assert not rows
    assert settings["tail"] == tail
    assert settings["comment"] == ""


def test_orca_last_unit_keyword_wins_and_comments_are_not_units():
    assert loader.coordinate_units("! Bohrs Angs # Bohrs", "orca")[0] == 1.0
    assert loader.coordinate_units("! Angs Bohrs", "orca")[0] == 0.529177210903
