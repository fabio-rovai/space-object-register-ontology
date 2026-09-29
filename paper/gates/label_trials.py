"""Behavioural labels for generated verification paths, checked against the regex labels.

For every raw output in the given directories, run it on the probe catalogue
(behaviour_probe.py) and record what it computes. Reference signatures are computed
the same way, by running the code they come from, rather than written down:

  shown_path_original  the python_side() the 19 Aug prompt showed (reuse_experiment.CONTEXT)
  pre_correction       the real pre-correction count, git 24d684e (not-gone means in orbit)

A generated path is "identical to the path it was shown" when its signature equals the
signature of the path in its prompt. That is the behavioural form of dependence: on
every status code at issue, the second path counts exactly what the first counts.

Run: python3 paper/gates/label_trials.py [raw_dir ...]
Writes: paper/gates/behaviour_labels.json
"""
import collections
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import behaviour_probe as B  # noqa: E402

PRE_CORRECTION_PATH = '''
def python_side():
    ct = load_celestrak()
    sat, _, nona = load_gcat("gcat_satcat.tsv")
    st = {n: statuses(v) for n, v in sat.items()}
    ctdec = {n for n in ct if ct[n]["DECAY_DATE"].strip()}
    return {"DispositionDisagreement": len({
        n for n in sat if n in ct
        and (bool(st[n] & GONE) != (n in ctdec))
        and not ((n in ctdec) and (st[n] & LEFT_EARTH) and not (st[n] & GONE))})}
'''


def shown_path_original():
    import reuse_experiment as R
    m = re.search(r"def python_side\(\):.*", R.CONTEXT, re.S)
    return m.group(0)


def reference_signatures():
    out = {}
    for name, code in (("shown_path_original", shown_path_original()),
                       ("pre_correction", PRE_CORRECTION_PATH)):
        r = B.probe(code)
        assert r["status"] == "ok", (name, r)
        out[name] = {"signature": r["signature"], "per_code": r["per_code"],
                     "real_data_count": B.real_count(code, r["source_fns"])}
    return out


def label_dir(raw_dir, reference):
    rows = []
    for f in sorted(pathlib.Path(raw_dir).glob("*.txt")):
        text = f.read_text()
        if text.startswith("__TRIAL_ERROR__") or not text.strip():
            continue
        r = B.probe(text)
        row = {"file": f"{pathlib.Path(raw_dir).name}/{f.name}", "status": r["status"]}
        if r["status"] == "ok":
            row.update(signature=r["signature"], per_code=r["per_code"],
                       identical_to_shown_path=r["signature"] == reference,
                       source_fns=r["source_fns"],
                       real_data_count=B.real_count(text, r["source_fns"]))
        elif r["status"] == "ambiguous":
            row.update(signatures=r["signatures"])
        else:
            row["detail"] = (r.get("raw") or {}).get("exec_error") or [
                c for c in (r.get("raw") or {}).get("calls", [])][:3]
            fns = [c["fn"] for c in (r.get("raw") or {}).get("calls", [])
                   if "returned" in c]
            if fns:
                row["real_data_count"] = B.real_count(text, fns)
        rows.append(row)
    return rows


def main():
    dirs = sys.argv[1:] or [str(HERE / "reuse_raw")]
    refs = reference_signatures()
    print("reference signatures:", json.dumps(refs))
    report = {"references": refs, "trials": []}
    for d in dirs:
        ref = refs["shown_path_original"]["signature"]
        ref_file = pathlib.Path(d) / "SHOWN_PATH.py"
        if ref_file.exists():   # replication runs record the path their prompt showed
            r = B.probe(ref_file.read_text())
            assert r["status"] == "ok", r
            ref = r["signature"]
        report["trials"] += label_dir(d, ref)

    # agreement with the regex labels of the original run
    regex = {}
    fin = HERE / "reuse_final.json"
    if fin.exists():
        for t in json.loads(fin.read_text())["trials"]:
            regex[f"reuse_raw/{t['condition']}_{t['model']}_{t['trial']}.txt"] = t
    for row in report["trials"]:
        t = regex.get(row["file"])
        if t:
            row["regex_inherits_defect"] = t["INHERITS_DEFECT"]
            row["regex_vocabulary_source"] = t["vocabulary_source"]

    summ = collections.Counter()
    for row in report["trials"]:
        key = row["file"].split("/")[0] + "|" + row["file"].split("/")[1].rsplit("_", 2)[0]
        lab = row["status"] if row["status"] != "ok" else (
            "identical to shown path" if row["identical_to_shown_path"] else "differs")
        summ[(key, lab)] += 1
    report["summary"] = {f"{k[0]} :: {k[1]}": v for k, v in sorted(summ.items())}
    (HERE / "behaviour_labels.json").write_text(json.dumps(report, indent=2))
    for k, v in report["summary"].items():
        print(f"{v:4}  {k}")
    for row in report["trials"]:
        if row["status"] != "ok" or not row.get("identical_to_shown_path"):
            print("  ", row["file"], row["status"], row.get("per_code") or row.get("detail"),
                  "real:", row.get("real_data_count"))
    print("real-data counts of paths identical to the shown path:", collections.Counter(
        str(sorted(set(map(str, r["real_data_count"].values())))) for r in report["trials"]
        if r.get("identical_to_shown_path")))


if __name__ == "__main__":
    main()
