# ORCA Input Generator Pro — Test Suite

327 tests across 7 files. All run headlessly — no Qt installation, no display
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

# Set explicit main app path (real-context integration tier)
CI_MAIN_APP_SRC=/path/to/python_molecular_editor/moleditpy/src \
  python -m pytest tests/test_plugin_integration.py tests/test_api.py -v
```

---

## Test files

| File | Tests | Area |
|---|---|---|
| `test_keyword_builder.py` | 78 | Route/keyword building, `parse_route()`, `get_constraints_text()` |
| `test_parse_route_extended.py` | 68 | Advanced route parsing: SCF convergence, NumFreq, RIJCOSX, NBO, solvation, TDDFT, 3c |
| `test_constants.py` | 59 | Data-quality checks on `ALL_ORCA_METHODS` and `ALL_ORCA_BASIS_SETS` |
| `test_api.py` | 45 | `plugin_api_checker.py` infrastructure + API contract against main app |
| `test_main_dialog.py` | 29 | `consolidate_orca_blocks()`, duplicate merging, MaxIter deduplication |
| `test_plugin_integration.py` | 25 | `PluginContext` contract — stub mode (always) + real-context mode (optional) |
| `test_metadata.py` | 23 | Plugin constants, `get_default_settings()`, `initialize()` with `MagicMock` context |

---

## Test files — detailed

### `test_constants.py` — Data quality for constants.py (59 tests)

`constants.py` is pure data (no Qt, no RDKit), loaded directly.

| Class | What is tested |
|---|---|
| `TestAllOrcaMethods` | List type; non-empty; no duplicates; no whitespace padding; known entries present (B3LYP, CCSD(T), …) |
| `TestAllOrcaBasisSets` | Same checks + spelling of key basis sets (def2-SVP, def2-TZVP, cc-pVDZ) |
| `TestGetInferredCategory` | Representative methods for every category including Multireference and Double Hybrid |

---

### `test_keyword_builder.py` — OrcaKeywordBuilderDialog logic (78 tests)

PyQt6 and RDKit are stubbed. Classes used as base classes (`QDialog`, `QWidget`,
`QScrollArea`) are real inheritable stubs — not `MagicMock()` instances.

| Class | What is tested |
|---|---|
| `TestGetInferredCategory` | DFT / HF / post-HF / semi-empirical / compound method categorisation |
| `TestUpdatePreview` | Job-type → route keyword mapping; basis set included/excluded per method |
| `TestParseRoute` | Round-trip: keyword string → widget state (method, basis, job type, nproc, maxcore) |
| `TestGetConstraintsText` | Constraint block generation (freeze, fix distance/angle/dihedral); scan block |

---

### `test_parse_route_extended.py` — Extended parse_route() coverage (68 tests)

Extends `test_keyword_builder.py` with branches not covered there.

| Tokens / branches tested |
|---|
| SCF convergence: `SloppySCF` … `ExtremeSCF` |
| `NumFreq`, `Raman` |
| `RIJCOSX`, `RI`, `Def2/J`, `Def2/JK` auxiliary basis tokens |
| `NBO` |
| Dispersion: `D3BJ`, `D3Zero`, `D4`, `D2`, `NL` |
| `CPCM(solvent)`, `SMD`, `CPC(Water)` solvation |
| `Opt + Freq` combo (both orderings), `COpt`, `CalcFC` |
| `Gradient`, `Hessian` job types |
| `%tddft` block: `NRoots`, `IRoot`, `Triplets`, `TDA` |
| `%geom MaxIter 256` |
| Empty / whitespace route (no-op) |
| `get_extra_blocks_text()`: Triplets, TDA, IRoot combinations |
| `update_preview()`: NumFreq, Opt+Freq+TightOpt, 3c methods without basis |

---

### `test_main_dialog.py` — consolidate_orca_blocks() logic (29 tests)

Methods called unbound with `self=None` — `OrcaSetupDialogPro.__init__` is never invoked.

| Scenario | Behaviour verified |
|---|---|
| Basic round-trip (no blocks) | Content unchanged |
| Duplicate `%` blocks | Merged into one |
| `MaxIter` in `%geom` / `%scf` | Deduplicated, last wins |
| `NRoots` / `IRoot` in `%tddft` | Deduplicated, last wins |
| Redundant bare `Opt` | Removed when `TightOpt`/`VeryTightOpt`/`LooseOpt` present |
| Duplicate `!` tokens | Removed |
| `%pal` / `%maxcore` | Preserved unchanged |
| Post-coord blocks | Stay after coordinate block |
| Pre+post same block | Merged into pre-coord zone |
| One-liner `%block … end` | Handled correctly |
| No coordinate block | No crash |

---

### `test_metadata.py` — Plugin constants and initialize() contract (23 tests)

| Class | What is tested |
|---|---|
| `TestPluginMetadata` | `PLUGIN_NAME`, `PLUGIN_VERSION` (semver X.Y.Z), `PLUGIN_AUTHOR`, `PLUGIN_DESCRIPTION`, `PLUGIN_SUPPORTED_MOLEDITPY_VERSION` — all present and non-empty |
| `TestDefaultSettings` | `get_default_settings()` shape: `nproc` (int > 0), `maxcore` (int > 0), `route` (str), `coord_format`; two calls return independent dicts |
| `TestInitialize` | `add_export_action` called once with str label + callable; save/load/reset handlers registered; save returns None before dialog opened, dict after; load updates settings; reset restores defaults; multiple initialize calls don't crash |

---

### `test_plugin_integration.py` — PluginContext contract (25 tests)

Two execution modes:

**Stub mode** (always runs, including CI): `StubPluginContext` mirrors the real
`PluginContext` API used by `initialize()`.

**Real-context mode** (runs when `python_molecular_editor` is present locally or
via `CI_MAIN_APP_SRC`): exercises `initialize()` against the actual `PluginContext`.

| Class | Tests | What is verified |
|---|---|---|
| `TestInitializeContract` | 6 | 1 export action registered; label is non-empty str; callback callable; 1 save/load/reset handler each |
| `TestPersistenceHandlers` | 10 | Save returns None before dialog opened, current_settings dict after; load updates nproc/maxcore; load ignores non-dict/empty; load sets dialog flag; load strips charge/mult keys; reset restores defaults and clears flag; roundtrip save→reset→load |
| `TestWithRealPluginContext` | 3 | `initialize(real_ctx)` doesn't raise; real ctx is `PluginContext` instance; all used methods exist on real class |
| `TestMarkModifiedCallback` | 3 | `initialize()` stores context; `_mark_modified` closure calls `context.mark_project_modified()`; no crash when context is None |

---

### `test_api.py` — API checker infrastructure + integration (45 tests)

Tests `plugin_api_checker.py` itself using **synthetic code and temp directories** — no
main app required for the unit tests. All test classes except `TestAPIChecker` run
unconditionally.

| Class | Tests | What is tested |
|---|---|---|
| `TestIssue` | 4 | `Issue` str format (`[try]` tag), `key()` 4-tuple, `in_try` excluded from key |
| `TestMergeAllowlists` | 5 | `mw`/`manager`/`context` set unions; empty merge; single dict preserved |
| `TestLoadSiteAllowlist` | 6 | List form, dict form, manager form, context form; missing file → `{}`; invalid JSON → `{}` |
| `TestPluginFileChecker` | 21 | Unknown MW attr flagged; known attr OK; private/Qt-inherited skipped; `hasattr` not flagged; try-block `in_try` flag; `get_main_window()` alias tracked; `self.main_window` alias tracked; MW/manager allowlist suppression; unknown/known manager attr; unknown/known context attr; context check off by default; plugin-specific attrs (`add_export_action`, `mark_project_modified`) OK; syntax error; dedup |
| `TestAppAPIExtractor` | 8 | Extracts MW methods, properties, class attrs, manager attr, manager members, context members from synthetic app tree; scans `self.host.X` assignments |
| `TestAPIChecker` | 1 | Scans all plugin source files against the real MainWindow/PluginContext API (skipped unless main app present) |

---

## Integration test strategy

```
Stub mode (always runs)
  StubPluginContext mirrors the real API.
  No main app required. Catches interface mismatches immediately.

Real-context mode (runs when main app is available)
  Uses the actual PluginContext from python_molecular_editor.
  Catches drift invisible to the stub.
```

Real-context mode activates when repos are siblings:

```
<parent>/
    moleditpy_orca_input_generator_pro/   ← this plugin
    python_molecular_editor/              ← main app
```

### CI

| Job | Python | Main app | Tests |
|---|---|---|---|
| `test` | 3.11, 3.12, 3.13 | Not cloned | Full suite; `TestWithRealPluginContext` + `TestAPIChecker` skipped |
| `test-integration` | 3.11 | Cloned `--depth 1` | `test_plugin_integration.py` + `test_api.py` including real-context tier |

---

## Mocking strategy

| Module | Approach |
|---|---|
| `constants.py` | Loaded directly — no stubs (pure data) |
| `keyword_builder.py` | Qt/RDKit stubbed; `QDialog` etc. as real inheritable stub classes (not `MagicMock()`) |
| `main_dialog.py` | Qt stubbed; methods called unbound — `__init__` never runs |
| `__init__.py` | `QMessageBox` stubbed as `MagicMock`; `MagicMock` context passed to `initialize()` |
| `plugin_api_checker.py` | No stubs — pure stdlib (`ast`, `json`, `pathlib`) |
