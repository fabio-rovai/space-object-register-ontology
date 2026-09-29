# paper/gates

Every figure in the paper is produced by a script here. Inputs are the frozen files in
`data/` (not committed; checksums in the paper, Appendix D).

| Claim | Script | Output |
|---|---|---|
| Three gates on defective and corrected code | `evaluate_gates.py` | `RESULTS.md`, `results.json` |
| Full-history disposition count (220) | `history_check.py` | `history_results.json` |
| Second reading from GCAT's derived catalogue (219) | `currentcat_crosscheck.py` | `currentcat_results.json` |
| Object ledger 932 -> 261 -> 220 | `count_ledger.py` | `count_ledger.json` |
| Names both gate paths share | `shared_ancestor_audit.py` | stdout |
| Behavioural probe for generated code | `behaviour_probe.py` | library |
| Preliminary model run (19 Aug), relabelled by behaviour | `label_trials.py` | `behaviour_labels.json` |
| Controlled replication (29 Sep) | `reuse_replication.py`, `label_replication.py` | `replication_raw/`, `replication_labels.json` |

Superseded, kept for the record: `reuse_experiment.py` and `reclassify.py` (preliminary
run and its regex labels), `reuse_results.json`, `reuse_final.json`, `reuse_raw/`.

`history_check.py` and `currentcat_crosscheck.py` also need `data/gcat_ecat_20260928.tsv`
and `data/gcat_currentcat_20260928.tsv`, retrieved 29 Sep 2026 from
`planet4589.org/space/gcat/tsv/cat/ecat.tsv` and `.../tsv/derived/currentcat.tsv`.
