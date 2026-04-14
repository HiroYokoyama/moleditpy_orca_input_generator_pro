# Tests — ORCA Input Generator Pro

## Running locally

```bash
# From the repo root
python -m pytest tests/ -v
```

No Qt installation or display is required. All Qt/RDKit dependencies are
stubbed at the Python level so tests run headlessly in CI and locally.

## Test files

| File | What it covers |
|------|---------------|
| `test_metadata.py` | `PLUGIN_NAME`, `PLUGIN_VERSION`, `get_default_settings()`, `initialize()` registration contract |
| `test_keyword_builder.py` | `get_inferred_category()`, `update_preview()` route/keyword building, `parse_route()` round-trips, `get_constraints_text()` |
| `test_plugin_integration.py` | Stub-context contract tests + optional real `PluginContext` integration |

## Integration tests (real PluginContext)

`test_plugin_integration.py` auto-detects the main app at:

```
../python_molecular_editor/moleditpy/src
```

(relative to the repo root — i.e. both repos checked out as siblings).

When found, `TestWithRealPluginContext` runs using the actual `PluginContext`
class to verify API compatibility. When not found, those tests are skipped.

You can also set `CI_MAIN_APP_SRC` to an explicit path:

```bash
CI_MAIN_APP_SRC=/path/to/python_molecular_editor/moleditpy/src \
  python -m pytest tests/test_plugin_integration.py -v
```
