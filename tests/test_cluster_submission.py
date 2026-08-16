"""Tests for Submit to Cluster workflow and auto-closing in ORCA Input Generator Pro."""

from __future__ import annotations

import os
import types
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")

from orca_input_generator_pro.main_dialog import OrcaSetupDialogPro


def test_orca_main_dialog_submit_to_cluster_accepts(tmp_path):
    target = os.path.join(str(tmp_path), "test.inp")
    with open(target, "w", encoding="utf-8") as f:
        f.write("! HF def2-SVP")

    dlg = types.SimpleNamespace(
        current_inp_file=target,
        _is_modified=MagicMock(return_value=False),
        parent=MagicMock(return_value=None),
        accept=MagicMock(),
    )

    with patch("orca_input_generator_pro.main_dialog.cluster_link.submit_to_cluster", return_value=True):
        OrcaSetupDialogPro.submit_to_cluster(dlg)
        assert dlg.accept.called


def test_orca_main_dialog_submit_to_cluster_handles_failure(tmp_path):
    target = os.path.join(str(tmp_path), "test.inp")
    with open(target, "w", encoding="utf-8") as f:
        f.write("! HF def2-SVP")

    dlg = types.SimpleNamespace(
        current_inp_file=target,
        _is_modified=MagicMock(return_value=False),
        parent=MagicMock(return_value=None),
        accept=MagicMock(),
    )

    with patch("orca_input_generator_pro.main_dialog.cluster_link.submit_to_cluster", return_value=False):
        with patch("orca_input_generator_pro.main_dialog.QMessageBox.warning") as mock_warn:
            OrcaSetupDialogPro.submit_to_cluster(dlg)
            assert not dlg.accept.called
            assert mock_warn.called

