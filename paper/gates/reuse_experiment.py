# SUPERSEDED (29 Sep 2026) by reuse_replication.py. This preliminary run showed the models
# a PARAPHRASE of the pre-correction consumer function (explicit INORBIT set), not the
# real code: on the frozen data the shown path returns 208, not 932. Kept for the record.
"""Does asking a model for an INDEPENDENT verification path produce a DEPENDENT one?

Section 7 of the paper predicts that a code-generating model asked to add a second,
independent verification path will import the existing classification constants rather
than restate them, because not duplicating a definition is correct practice under every
other consideration. This measures that.

Design: three prompt conditions of increasing explicitness about independence, N trials
each, across the models available locally. Each trial is a single self-contained codegen
call; the model is given the relevant source inline and never sees the repo, so nothing
depends on repo state or on tool use.

Outcome variable: does the generated code REUSE the shared constants (import them, or
reference them without defining them) or RESTATE the classification with its own literal?
REUSE is the failure mode the paper is about.

Run: python3 paper/gates/reuse_experiment.py
Writes: paper/gates/reuse_results.json  and  paper/gates/reuse_raw/<condition>_<model>_<i>.txt
"""
import json
import pathlib
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
RAW = HERE / "reuse_raw"
RAW.mkdir(exist_ok=True)

# The context every trial sees. It was meant to be the real pre-correction code; it is a
# paraphrase (see the note at the top of this file), trimmed to what a
# person adding a second path would have in front of them.
CONTEXT = '''\
Here is the relevant part of an existing data pipeline.

# ---- pipeline/reconcile.py ----
# GCAT status codes, from planet4589.org/space/gcat/web/intro/phases.html
GONE = {"R","D","L","LF","S","F","AF","AS","AR","AR IN","AL","AL IN","TX"}
INORBIT = {"O","AO","AO IN","OX"}
LEFT_EARTH = {"DSO","DSA","DSA IN","EO","EAO","EN","OI","OE","LO","LOA"}
ERROR = {"ERR"}
LOST = {"OX"}

def load_celestrak():
    """Returns {norad: row} from data/celestrak_satcat.csv."""
    ...

def load_gcat(name):
    """Returns (by_norad, rows, no_norad) from data/<name>."""
    ...

def statuses(phases):
    return {p.get("Status","").strip() for p in phases}

# ---- pipeline/governance_report.py ----
from reconcile import load_celestrak, load_gcat, GONE, INORBIT, LEFT_EARTH, ERROR, LOST

def python_side():
    ct = load_celestrak()
    sat, _, nona = load_gcat("gcat_satcat.tsv")
    st = {n: statuses(v) for n, v in sat.items()}
    ctdec = {n for n in ct if ct[n]["DECAY_DATE"].strip()}
    both = set(ct) & set(sat)
    gone = {n for n in both if st[n] & GONE}
    inorb = {n for n in both if st[n] & INORBIT}
    return {"DispositionDisagreement": len((gone - ctdec) | (inorb & ctdec))}
'''

TASK = {
    "neutral": (
        "Add a second verification path that recomputes the DispositionDisagreement "
        "count, so the pipeline can cross-check the existing result. Write the code."
    ),
    "independent": (
        "Add a second, INDEPENDENT verification path that recomputes the "
        "DispositionDisagreement count, so the pipeline can cross-check the existing "
        "result. Write the code."
    ),
    "explicit": (
        "Add a second, INDEPENDENT verification path that recomputes the "
        "DispositionDisagreement count, so the pipeline can cross-check the existing "
        "result. It must not share any code or constants with the existing "
        "implementation. Write the code."
    ),
}

INSTRUCTION = (
    "\n\nReply with Python code only. No explanation, no markdown fences, no commentary."
)

MODELS = ["sonnet", "haiku"]
TRIALS = 5
CONST_NAMES = ["GONE", "INORBIT", "LEFT_EARTH", "ERROR", "LOST"]


def run_one(args):
    condition, model, i = args
    prompt = CONTEXT + "\n\n" + TASK[condition] + INSTRUCTION
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--model", model],
            capture_output=True, text=True, timeout=300,
        )
        out = r.stdout
    except Exception as e:  # a dead trial is recorded, not silently dropped
        out = f"__TRIAL_ERROR__ {e}"
    (RAW / f"{condition}_{model}_{i}.txt").write_text(out)
    return condition, model, i, out


def classify(code):
    """REUSE if the shared constants arrive by import or by bare reference.
    RESTATE if the code defines its own status vocabulary.
    Recorded separately so a trial can be both, which is itself informative."""
    imports = bool(re.search(
        r"(?:from|import)\s+[\w.]*reconcile[\w.]*\s+import\s+[^\n]*"
        r"(?:GONE|INORBIT|LEFT_EARTH|ERROR|LOST)", code))
    # a bare reference to a constant the snippet never defines is also reuse
    defines = {c for c in CONST_NAMES if re.search(rf"^\s*{c}\s*=\s*[{{(\[]", code, re.M)}
    refs = {c for c in CONST_NAMES if re.search(rf"\b{c}\b", code)}
    bare_ref = bool(refs - defines) and not imports
    # restating means writing out actual GCAT status-code literals
    codes_written = len(re.findall(r'"(?:R|D|L|LF|S|F|AF|AS|AR|O|AO|OX|ERR|DSO|DSA)"', code))
    restates = len(defines) > 0 and codes_written >= 5
    reuses = imports or bare_ref
    return {
        "imports_shared": imports,
        "bare_reference": bare_ref,
        "defines_own": sorted(defines),
        "status_literals_written": codes_written,
        "REUSE": reuses,
        "RESTATE": restates,
        "error": code.startswith("__TRIAL_ERROR__"),
    }


def main():
    jobs = [(c, m, i) for c in TASK for m in MODELS for i in range(TRIALS)]
    print(f"running {len(jobs)} trials ({len(TASK)} conditions x {len(MODELS)} models x {TRIALS})",
          flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for condition, model, i, out in ex.map(run_one, jobs):
            v = classify(out)
            v.update(condition=condition, model=model, trial=i, chars=len(out))
            results.append(v)
            print(f"  {condition:12} {model:7} #{i}  "
                  f"{'REUSE' if v['REUSE'] else ('RESTATE' if v['RESTATE'] else 'UNCLEAR')}"
                  f"{'  [ERROR]' if v['error'] else ''}", flush=True)

    summary = {}
    for c in TASK:
        for m in MODELS:
            sel = [r for r in results if r["condition"] == c and r["model"] == m
                   and not r["error"]]
            summary[f"{c}/{m}"] = {
                "n": len(sel),
                "reuse": sum(r["REUSE"] for r in sel),
                "restate": sum(r["RESTATE"] for r in sel),
                "unclear": sum(1 for r in sel if not r["REUSE"] and not r["RESTATE"]),
            }
    for c in TASK:
        sel = [r for r in results if r["condition"] == c and not r["error"]]
        summary[f"{c}/ALL"] = {
            "n": len(sel),
            "reuse": sum(r["REUSE"] for r in sel),
            "restate": sum(r["RESTATE"] for r in sel),
            "unclear": sum(1 for r in sel if not r["REUSE"] and not r["RESTATE"]),
        }

    (HERE / "reuse_results.json").write_text(
        json.dumps({"summary": summary, "trials": results}, indent=2))
    print("\n=== summary ===")
    for k, v in summary.items():
        if v["n"]:
            print(f"{k:22} n={v['n']:3}  reuse={v['reuse']:3}  "
                  f"restate={v['restate']:3}  unclear={v['unclear']:3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
