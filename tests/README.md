# ORCA Input Generator Pro — Test Suite

278 tests across 6 files. All run headlessly — no Qt installation, no display
server required. Qt and RDKit dependencies are stubbed at module level.

---

## Running the tests

```bash
# Full suite
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=orca_input_generator_pro --cov-report=term-missing

# Single file
python -m pytest tests/test_keyword_builder.py -v

# Single test
python -m pytest tests/ -k "test_update_preview_basic"

# Set explicit main app path (integration tier 2)
CI_MAIN_APP_SRC=/path/to/python_molecular_editor/moleditpy/src \
  python -m pytest tests/test_plugin_integration.py -v
```

---

## Test files

| File | Tests | Area |
|---|---|---|
| `test_constants.py` | 59 | Data-quality checks on ALL\_ORCA\_METHODS and ALL\_ORCA\_BASIS\_SETS |
| `test_keyword_builder.py` | 78 | Route/keyword building, `parse_route()`, `get_constraints_text()` |
| `test_parse_route_extended.py` | 68 | Advanced route parsing: SCF, NumFreq, RIJCOSX, NBO, solvation, TDDFT, 3c |
| `test_main_dialog.py` | 29 | `consolidate_orca_blocks()`, duplicate merging, MaxIter deduplication |
| `test_metadata.py` | ~22 | Plugin constants, `initialize()` registration contract |
| `test_plugin_integration.py` | 22 | PluginContext contract (stub + optional real) |

---

## Test files — detailed

### `test_constants.py` — Data-quality checks (59 tests)

Exhaustive validation of the `ALL_ORCA_METHODS` and `ALL_ORCA_BASIS_SETS`
constant tables used to populate the keyword dropdowns.

- No duplicate entries in either list
- No leading/trailing whitespace in any entry
- All entries are non-empty strings
- No `None` values
- Correct total counts match expected values

These tests catch typos and copy-paste errors introduced when adding new
methods or basis sets.

---

### `test_keyword_builder.py` — Route/keyword building (78 tests)

Tests the core keyword-builder logic:

| Area | What is tested |
|---|---|
| `get_inferred_category()` | Correct category assignment for DFT, HF, MP2, CCSD, semi-empirical methods |
| `update_preview()` | Route line construction from method + basis + charge + multiplicity + optional keywords |
| `parse_route()` | Round-trip: `update_preview()` output → `parse_route()` → back to same components |
| `get_constraints_text()` | Cartesian / distance / angle / dihedral constraint formatting |

---

### `test_parse_route_extended.py` — Advanced route parsing (68 tests)

Covers specialised ORCA input patterns:

| Category | What is tested |
|---|---|
| SCF convergence | `TightSCF`, `VeryTightSCF`, `LooseConv` flags parsed and preserved |
| Numerical frequencies | `NumFreq` / `NumHess` keywords; `Raman` flag |
| RIJCOSX / RI | Auxiliary basis set keyword handling |
| NBO | `NBO` block detection and round-trip |
| Dispersion | `D3BJ`, `D3`, `D4` dispersion correction keywords |
| Solvation | `CPCM(Solvent)`, `SMD(Solvent)` implicit solvent models |
| TDDFT | `TDDFT` block with `NRoots`, `TDA` options |
| 3c methods | `r2SCAN-3c`, `PBEh-3c`, `B97-3c` composite methods |

---

### `test_main_dialog.py` — Block consolidation (29 tests)

Tests `consolidate_orca_blocks()`, which merges duplicate `%scf`, `%pal`,
`%maxcore`, and other ORCA input blocks:

- Duplicate blocks of the same type are merged (not repeated)
- `MaxIter` values: highest value wins when duplicates conflict
- Empty input returns empty output
- Whitespace-only blocks are discarded

---

### `test_metadata.py` — Plugin constants and initialization

| Area | What is tested |
|---|---|
| Constants | `PLUGIN_NAME`, `PLUGIN_VERSION`, `PLUGIN_AUTHOR`, `PLUGIN_DESCRIPTION` present and non-empty |
| `initialize()` | Registers a menu action; registers save/load/reset handlers; `context.add_menu_action` called with correct path |
| `get_default_settings()` | Returns a dict; all expected keys present; default values are correct types |

---

### `test_plugin_integration.py` — PluginContext contract (22 tests)

Two-tier integration tests — see [Integration Test Strategy](#integration-test-strategy).

| Class | What is tested |
|---|---|
| `TestInitializeRegistrations` | `initialize(context)` registers menu action + save/load/reset handlers |
| `TestSaveLoadState` | Save → load round-trip preserves all settings keys |
| `TestDocumentReset` | Reset clears plugin state without raising |
| `TestWithRealPluginContext` *(skipped unless main app present)* | `initialize()` works with real `PluginContext`; stub matches real API surface |

---

## Integration Test Strategy

### Two-tier approach

```
Tier 1 — Stub mode (always runs)
  StubPluginContext mirrors the PluginContext API.
  No main app required. Catches interface mismatches immediately.

Tier 2 — Real-context mode (runs when main app is a sibling repo)
  Uses the actual PluginContext from python_molecular_editor.
  Catches subtle incompatibilities invisible from the stub.
```

### Local development

Real-context tests activate when repos are siblings:

```
<parent>/
    moleditpy_orca_input_generator_pro/  ← this plugin
    python_molecular_editor/             ← main app
```

### CI

| Job | Main app | Tests run |
|---|---|---|
| `test` (3.11, 3.12, 3.13) | No | Full suite; `TestWithRealPluginContext` skipped |
| `test-integration` (3.11) | Cloned `--depth 1` | Full suite including `TestWithRealPluginContext` |
