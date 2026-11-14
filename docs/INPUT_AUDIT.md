# Input generation audit — 2026-10-24

Scope: production Python modules, keyword/catalog data, generation, input
recovery, Cartesian/internal coordinates, charge/spin checks, constraints,
resource and checkpoint handling, presets/project persistence, save/submit and
window lifecycle. Review combines source reading and documentation comparison
with targeted regressions and the complete repository test suite.

## Shared fixes

- Export host Angstrom coordinates in the length units selected by the job.
  Gaussian radian Z-matrices convert angular values as well.
- Keep ghost labels in the custom-symbol property used by writers and electron
  counting; imported ghosts must not become real atoms after Refresh.
- Refuse nonfinite coordinate data and fall back from undefined linear Z-matrix
  reference planes rather than writing NaN values.
- Validate the spin range as well as electron/spin parity. This is a necessary
  electron-count check, not a prediction of the ground-state multiplicity.
- Recover existing methods/bases without injecting the builder's default basis.
- Preserve full imported/edited source and optional JSON input_text behavior.

## ORCA fixes

- Emit the initial Hessian setting as `%geom Calc_Hess true`; support existing
  stored CalcFC/CalcHess control state without adding invalid simple keywords.
- Emit NumFreq independently of parent-dialog visibility and avoid adding Freq
  simultaneously. Reset the MaxIter checkbox when parsing a replacement route.
- Correct the short water-solvation option to CPCM(Water); restrict ALPB to xTB
  selections. Uppercase 3C names do not receive an extra orbital basis.
- MD templates initialize velocities and the thermostat before one Run command.
- Fragment templates use Definition and terminated GhostFrags lists after
  coordinates. Compound templates use Read_Geom(1); outside New_Step, and disable
  unrelated top-level route/coordinates.
- Block consolidation respects nested coordinates and block terminators carrying
  comments, instead of extracting Compound geometry as top-level geometry.

## Primary sources

- [ORCA 6.1 coordinates and units](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/coordinates.html)
- [ORCA 6.1 geometry optimization](https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/optimizations.html)
- [ORCA 6.1 basis sets and ECP slots](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/basisset.html)
- [ORCA 6.1 solvation](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/solvationmodels.html)
- [ORCA 6.1 MD commands](https://www.faccts.de/docs/orca/6.1/manual/contents/moleculardynamics/moldyn.html)
- [ORCA 6.1 counterpoise](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/counterpoise.html)
- [ORCA 6.1 Compound](https://www.faccts.de/docs/orca/6.1/manual/contents/workflowsautomatization/compound.html)

## Limits

Neither the licensed Gaussian executable nor an ORCA executable was run in this
workspace. Passing these checks validates the generator behavior covered, not
every engine-version/method/basis/ECP combination. Complex syntax outside the
recovered controls remains authoritative source text; explicitly refreshing can
discard unsupported instructions. Examples/templates require user-specific
geometry, active-space, basis/ECP and resource choices.

No private input, host settings or calculation data are used as fixtures.

## Validation result

- Full local suite: 1015 passed, with real PySide6/RDKit installed.
- Ruff E4/E7/E9/F/I checks and changed-file formatting pass; Python 3.9 syntax parsing passes. Broader workspace lint rules retain pre-existing logging/broad-catch style findings.
- Integration-grid template uses ! DefGrid2; CABS selection lists complementary auxiliary bases rather than correlation-fitting bases.

## Keyword audit, 2026-11-14 (4.1.6)

Every method, basis set and simple keyword the builder can write was compared
with the ORCA 6.1 manual. ORCA itself was not run.

- Pople sets take a comma between the heavy-atom and hydrogen parts:
  `6-31G(d,p)`, `6-311++G(2df,2pd)`. The 34 names without it are corrected.
- `M06-2X`, `M06-L`, `LC-wPBE` and `DLPNO-EOM-CCSD` become the ORCA keywords
  `M062X`, `M06L`, `LC-PBE` and `bt-PNO-EOM-CCSD`.
- Not in the manual, and removed from the lists: `M06-HF`, `MN12-L`, `wPBE`,
  `wPBEh`, `B97M-rV`, `SSB-D`, `PTPSS-D3`, `SF-EOM-CCSD`, `PM6`,
  the solvent `HMPA`, `Grid4`-`Grid6`, `NoGrid`, `NoAux`,
  the `Hessian` and `NumHess` job types, and the `SOMO` and `OptRot` boxes.
  (`ma-def2-QZVP` was mistakenly removed here and restored in 4.1.9.)
- Written as blocks, because ORCA has no such simple keyword: polarizability
  and Raman (`%elprop Polar true`), hyperpolarizability (`%elprop Hyperpol
  true`), the g-tensor (`%eprnmr GTensor true`), zero-field splitting
  (`%eprnmr DTensor ssandso`) and hydrogen-only optimization (`Opt` with
  `%geom optimizehydrogens true`). 4.1.8 writes `OptH` again: ORCA accepts
  it although the 6.1 manual documents only `L-OptH`.
- A route from an older version loads into the corrected form. A removed
  keyword that has no replacement stays in the route as typed.

4.1.7: ALPB has no Cyclohexane, CCl4 or Pyridine (manual Table 2.56). With
ALPB selected those solvents are greyed out and a selected one moves to Water;
a loaded `ALPB(CCl4)` stays in the route as typed.

4.1.9: `ma-def2-QZVP` is restored to `ALL_ORCA_BASIS_SETS` (exists in ORCA).
The standalone `COSX` checkbox is removed.

## Final keyword check, 2026-11-14 (4.2.0)

Every keyword removed in 4.1.6 was run through ORCA 6.1.1 (Linux), one
water input each. ORCA's own output decided: an unknown keyword stops with
`UNRECOGNIZED OR DUPLICATED KEYWORD(S) IN SIMPLE INPUT LINE`.

- Rejected, so the removal stands: `M06-HF`, `MN12-L`, `wPBE`, `wPBEh`,
  `B97M-rV`, `SSB-D`, `PTPSS-D3`, `SF-EOM-CCSD`, `PM6`, `LC-wPBE`, `M06-2X`,
  `M06-L`, `DLPNO-EOM-CCSD`, the comma-less Pople names, `Grid4`-`Grid6`,
  `NoGrid`, `NoAux`, `Hessian`, `NumHess`, `Raman`, `Polarizability`,
  `Hyperpol`, `EPR`, `ZFS`, `SOMO`, `OptRot`, `RI-J`, `EPRNMR`, `AutoTRAH`,
  the standalone `COSX`, `CPCM(HMPA)` and `ALPB` with CCl4, Cyclohexane or
  Pyridine.
- Accepted: `OptH`, `ma-def2-QZVP`, `M062X`, `M06L`, `LC-PBE`, the Pople
  names with the comma, `TRAH`, `NoCOSX`, `%elprop` and `%eprnmr` as the
  builder writes them, `%geom optimizehydrogens true`, and `L-OptH`.
- 4.2.0 adds `L-OptH` (hydrogen-only optimization with the L-BFGS
  optimizer) to the search catalog. It has no control of its own and is
  written to the route as typed.
- Not covered: only ORCA 6.1.1 was run; older versions may accept some of
  the rejected names.
