"""Tests for Keyword Builder Search Tab in ORCA Input Generator Pro."""

from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")

from orca_input_generator_pro.keyword_builder import OrcaKeywordBuilderDialog


def test_orca_keyword_builder_search_tab():
    dlg = types.SimpleNamespace(
        _search_catalog=[],
        tab_search=MagicMock(),
        custom_keywords=MagicMock(),
        preview_label=MagicMock(),
        method_name=MagicMock(),
        basis_set=MagicMock(),
        job_type=MagicMock(),
        dispersion=MagicMock(),
        solv_model=MagicMock(),
        solvent=MagicMock(),
        search_filter_input=MagicMock(),
        search_category_combo=MagicMock(),
        search_table=MagicMock(),
        font=MagicMock(),
        update_preview=MagicMock(),
        _filter_search_table=MagicMock(),
    )
    dlg._populate_search_database = lambda: OrcaKeywordBuilderDialog._populate_search_database(dlg)
    dlg._apply_search_item = lambda kw, cat, btn=None: OrcaKeywordBuilderDialog._apply_search_item(dlg, kw, cat, btn)

    dlg._populate_search_database()
    assert len(dlg._search_catalog) > 0

    # Test applying a method
    dlg._apply_search_item("wB97X-D3", "Methods / Functionals")
    dlg.method_name.setCurrentText.assert_called_with("wB97X-D3")

    # Test applying OptH
    dlg._apply_search_item("OptH", "Job Types")
    dlg.job_type.setCurrentText.assert_called_with("Optimize H Only (OptH)")

    # Test applying basis set
    dlg._apply_search_item("def2-TZVP", "Basis Sets")
    dlg.basis_set.setCurrentText.assert_called_with("def2-TZVP")




def test_orca_search_keeps_unmapped_advanced_keyword():
    dlg = types.SimpleNamespace(_search_extra_keywords=[], update_preview=MagicMock())
    dlg._add_search_keyword = lambda keyword: OrcaKeywordBuilderDialog._add_search_keyword(dlg, keyword)
    dlg._apply_search_item = lambda keyword, category, btn=None: OrcaKeywordBuilderDialog._apply_search_item(dlg, keyword, category, btn)

    dlg._apply_search_item("EPRNMR", "Properties / Advanced")

    assert dlg._search_extra_keywords == ["EPRNMR"]


def test_orca_search_numfreq_selects_a_frequency_job():
    dlg = types.SimpleNamespace(job_type=MagicMock(), freq_num=MagicMock(), _search_extra_keywords=[], update_preview=MagicMock())
    dlg._add_search_keyword = lambda keyword: OrcaKeywordBuilderDialog._add_search_keyword(dlg, keyword)
    dlg._apply_search_item = lambda keyword, category, btn=None: OrcaKeywordBuilderDialog._apply_search_item(dlg, keyword, category, btn)

    dlg._apply_search_item("NumFreq", "Job Types")

    dlg.job_type.setCurrentText.assert_called_once_with("Frequency Only (Freq)")
    dlg.freq_num.setChecked.assert_called_once_with(True)


def test_orca_search_moread_ticks_the_checkbox_not_raw_text():
    # moread_chk is what actually emits "MOREAD" and surfaces the MO File
    # field the %moinp directive needs. Regression for a bug where this fell
    # through to the raw-keyword fallback: MOREAD ended up in the route with
    # no %moinp block and no visible control showing anything was set.
    dlg = types.SimpleNamespace(moread_chk=MagicMock(), _search_extra_keywords=[], update_preview=MagicMock())
    dlg._add_search_keyword = lambda keyword: OrcaKeywordBuilderDialog._add_search_keyword(dlg, keyword)
    dlg._apply_search_item = lambda keyword, category, btn=None: OrcaKeywordBuilderDialog._apply_search_item(dlg, keyword, category, btn)

    dlg._apply_search_item("MOREAD", "Properties / Advanced")

    dlg.moread_chk.setChecked.assert_called_once_with(True)
    assert dlg._search_extra_keywords == []


def test_orca_search_loose_scf_wires_the_checkbox_not_raw_text():
    # scf_loose (and the other SCF tiers besides Tight/VeryTight) have their
    # own mutually-exclusive checkboxes. Regression for a bug where applying
    # e.g. LooseSCF via search fell through to the raw-keyword fallback,
    # leaving scf_loose unchecked -- so a later manual pick of a different
    # SCF tier produced two contradictory SCF convergence directives.
    dlg = types.SimpleNamespace(scf_loose=MagicMock(), _search_extra_keywords=[], update_preview=MagicMock())
    dlg._add_search_keyword = lambda keyword: OrcaKeywordBuilderDialog._add_search_keyword(dlg, keyword)
    dlg._apply_search_item = lambda keyword, category, btn=None: OrcaKeywordBuilderDialog._apply_search_item(dlg, keyword, category, btn)

    dlg._apply_search_item("LooseSCF", "Convergence & Grids")

    dlg.scf_loose.setChecked.assert_called_once_with(True)
    assert dlg._search_extra_keywords == []