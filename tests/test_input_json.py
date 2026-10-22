"""Exercise the actual main-app atomic JSON writer with synthetic input text."""

import ast
import json
import logging
import os
import stat
import tempfile
from pathlib import Path

import pytest


def project_writer():
    source = (
        Path(__file__).parents[2]
        / "python_molecular_editor"
        / "moleditpy"
        / "src"
        / "moleditpy"
        / "ui"
        / "io_logic.py"
    )
    if not source.is_file():
        pytest.skip("Main-app source is not checked out beside the plugin")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    method = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_write_project_json"
        ),
        None,
    )
    if method is None:
        pytest.skip("Main-app revision has no standalone atomic JSON writer")
    # Execute the production method without importing its VTK/Qt UI modules.
    method.decorator_list = []
    namespace = {
        "os": os,
        "stat": stat,
        "tempfile": tempfile,
        "json": json,
        "logging": logging,
        "Any": object,
    }
    exec(
        compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"),
        namespace,
    )
    return namespace["_write_project_json"]


def test_project_json_preserves_input_text_and_other_data(tmp_path):
    write = project_writer()
    path = tmp_path / "synthetic.pmeprj"
    text = (
        '# 日本語 😀 "quoted" \\path\\file\t\n%custom <tag>\n\0\n--Link1--\n$new_job\n'
    )
    payload = {
        "2d_structure": {"atoms": [{"id": 1}], "bonds": []},
        "plugins": {
            "other-plugin": {"untouched": [1, True, None, {"text": "元のデータ"}]},
            "input-generator": {"nproc": 4, "input_text": text},
        },
    }
    write(str(path), payload)
    restored = json.loads(path.read_text(encoding="utf-8"))
    assert restored == payload
    assert isinstance(restored["plugins"]["input-generator"]["input_text"], str)
    assert restored["plugins"]["input-generator"]["input_text"] == text
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("bad_value", [object(), "\ud800"])
def test_serialization_failure_keeps_existing_project_intact(tmp_path, bad_value):
    write = project_writer()
    path = tmp_path / "synthetic.pmeprj"
    original = b'{"sentinel": "existing project stays intact"}'
    path.write_bytes(original)
    with pytest.raises((TypeError, UnicodeError)):
        write(str(path), {"plugins": {"input-generator": {"input_text": bad_value}}})
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))
