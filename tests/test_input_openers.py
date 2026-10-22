"""Registry and deferred-drop integration without a native drop event."""

import sys
import types
from unittest.mock import Mock, patch

import pytest

from .test_plugin_integration import _init_mod

EXTENSIONS = [".inp"]
VALID_INPUT = "! HF STO-3G\n* xyz 0 1\nH 0 0 0\nH 0 0 0.74\n*\n"


@pytest.fixture
def registered():
    context = Mock()
    openers = {}
    drops = []
    context.register_file_opener.side_effect = lambda ext, callback, priority=0: (
        openers.update({ext: (callback, priority)})
    )
    context.register_drop_handler.side_effect = lambda callback, priority=0: (
        drops.append((callback, priority))
    )
    previous = _init_mod._context
    _init_mod.initialize(context)
    yield context, openers, drops
    _init_mod._context = previous


@pytest.fixture
def input_path(tmp_path):
    path = tmp_path / ("input" + EXTENSIONS[0].upper())
    path.write_text(VALID_INPUT, encoding="utf-8")
    return str(path)


def test_extensions_and_priority(registered):
    _, openers, drops = registered
    assert set(openers) == set(EXTENSIONS)
    assert all(priority == 100 for _, priority in openers.values())
    assert drops[0][1] == 100


@pytest.mark.parametrize("extension", EXTENSIONS)
def test_registered_opener_loads_input(registered, input_path, extension):
    context, openers, _ = registered
    with patch.object(_init_mod, "run", return_value=True) as run:
        openers[extension][0](input_path)
    run.assert_called_once_with(context.get_main_window(), input_file=input_path)


def test_invalid_input_does_not_open_dialog(registered, tmp_path):
    _, openers, drops = registered
    path = tmp_path / ("other" + EXTENSIONS[0])
    path.write_bytes(b"not a chemistry input\x00")
    with patch.object(_init_mod, "run") as run:
        with pytest.raises(ValueError):
            openers[EXTENSIONS[0]][0](str(path))
        assert drops[0][0](str(path)) is False
    run.assert_not_called()


def test_cancel_is_not_reported_as_success(registered, input_path):
    _, openers, _ = registered
    with patch.object(_init_mod, "run", return_value=False):
        with pytest.raises(RuntimeError, match="cancelled"):
            openers[EXTENSIONS[0]][0](input_path)


def test_drop_declines_other_extensions(registered):
    _, _, drops = registered
    with patch.object(_init_mod, "run") as run:
        assert drops[0][0]("other.xyz") is False
    run.assert_not_called()


@pytest.mark.parametrize("result", [True, False])
def test_drop_defers_loading_and_only_updates_path_on_success(
    registered, input_path, result
):
    context, _, drops = registered
    timer = Mock()
    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.QTimer = timer
    with (
        patch.dict(sys.modules, {"PySide6.QtCore": qtcore}),
        patch.object(_init_mod, "run", return_value=result) as run,
    ):
        assert drops[0][0](input_path) is True
        run.assert_not_called()
        delay, owner, callback = timer.singleShot.call_args.args
        assert delay == 0
        assert owner is context.get_main_window()
        callback()
    run.assert_called_once_with(context.get_main_window(), input_file=input_path)
    if result:
        context.set_current_file.assert_called_once_with(input_path)
    else:
        context.set_current_file.assert_not_called()


def test_queued_failure_is_contained(registered, input_path):
    context, _, drops = registered
    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.QTimer = Mock()
    with (
        patch.dict(sys.modules, {"PySide6.QtCore": qtcore}),
        patch.object(_init_mod, "run", side_effect=RuntimeError("failed")),
        patch.object(_init_mod, "QMessageBox") as message,
    ):
        assert drops[0][0](input_path) is True
        qtcore.QTimer.singleShot.call_args.args[2]()
    message.warning.assert_called_once()
    context.set_current_file.assert_not_called()
