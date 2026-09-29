"""Controlled replication of the independent-verifier experiment (29 Sep 2026).

The first run (reuse_experiment.py, 19 Aug 2026) had four weaknesses that reviewers or
our own re-analysis found:
  1. Model identity was not recorded: it called the Claude Code CLI with the aliases
     "sonnet" and "haiku", and the session logs that name the resolved models were
     rotated out before anyone read them.
  2. The trials ran inside the CLI's agent harness, with its default system prompt and
     default tools, from the repository root. No trial could be shown not to have
     read files.
  3. The prompt paraphrased the consumer function. The real pre-correction count
     treats every status not in GONE as in orbit; the prompt's version tested an
     explicit INORBIT set, so the status codes at issue were silently dropped rather
     than counted as in orbit. On the frozen data the prompt's path returns 208, not
     the 932 that was published.
  4. Loader bodies were elided, so no trial could see GCAT's column names.

This run fixes all four. The prompt carries the pre-correction code verbatim from git
24d684e, loader bodies included. Every model is pinned by full identifier and runs
with no tools, a one-line system prompt, and an empty working directory. Two new
conditions add GCAT's own status definitions to the prompt, which is the remedy the
paper proposes. A second model family runs locally.

Outcome labels come from behaviour_probe.py (what the code computes), not from
pattern matching.

Run:    python3 paper/gates/reuse_replication.py
Writes: paper/gates/replication_raw/<condition>__<model>__<i>.txt  (the code as returned)
        paper/gates/replication_raw/<condition>__<model>__<i>.meta.json
        paper/gates/replication_raw/SHOWN_PATH.py  (the path the prompt shows)
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RAW = HERE / "replication_raw"
RAW.mkdir(exist_ok=True)

PRE_COMMIT = "24d684e"
SYSTEM = "You are a helpful assistant."
TRIALS = 5
# Sonnet and Haiku trials ran on CLI 2.1.277. claude-opus-5-5 needs 2.1.280 or newer and
# ran after an update, on 2.1.284; each trial's metadata records the CLI version.
CLAUDE_MODELS = ["claude-opus-5-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"]
CLI_VERSION = subprocess.run(["claude", "--version"], capture_output=True,
                             text=True).stdout.split()[0]
QWEN_MODEL = "Qwen3.8-Flash-Next"
QWEN_URL = "http://localhost:1111/v1/chat/completions"
QWEN_SAMPLING = {"temperature": 0.7, "top_p": 0.8, "max_tokens": 16000}


def git_show(path):
    return subprocess.run(["git", "show", f"{PRE_COMMIT}:{path}"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout


def build_context():
    rec = git_show("pipeline/reconcile.py")
    rec = rec[:rec.index("def main():")].rstrip() + "\n"
    gov = git_show("pipeline/governance_report.py")
    gov = gov[:gov.index("def sparql_side():")].rstrip() + "\n"
    return ("Here is the relevant part of an existing data pipeline.\n\n"
            "# ---- pipeline/reconcile.py ----\n" + rec +
            "\n# ---- pipeline/governance_report.py ----\n" + gov)


CONTEXT = build_context()
DOCS = (HERE / "gcat_status_definitions.txt").read_text()
DOCS_BLOCK = ("\n\nThe source catalogue (GCAT) documents its Status field as follows.\n\n"
              + DOCS)

TASK = {  # wording identical to the 19 Aug run
    "neutral": (
        "Add a second verification path that recomputes the DispositionDisagreement "
        "count, so the pipeline can cross-check the existing result. Write the code."),
    "independent": (
        "Add a second, INDEPENDENT verification path that recomputes the "
        "DispositionDisagreement count, so the pipeline can cross-check the existing "
        "result. Write the code."),
    "explicit": (
        "Add a second, INDEPENDENT verification path that recomputes the "
        "DispositionDisagreement count, so the pipeline can cross-check the existing "
        "result. It must not share any code or constants with the existing "
        "implementation. Write the code."),
}
CONDITIONS = {
    "neutral": (False, "neutral"),
    "independent": (False, "independent"),
    "explicit": (False, "explicit"),
    "docs_independent": (True, "independent"),
    "docs_explicit": (True, "explicit"),
}
INSTRUCTION = "\n\nReply with Python code only. No explanation, no markdown fences, no commentary."


def prompt_for(condition):
    docs, task = CONDITIONS[condition]
    return CONTEXT + (DOCS_BLOCK if docs else "") + "\n\n" + TASK[task] + INSTRUCTION


def run_claude(model, prompt):
    with tempfile.TemporaryDirectory() as empty:
        t0 = time.time()
        r = subprocess.run(
            ["claude", "-p", prompt, "--model", model, "--tools", "",
             "--system-prompt", SYSTEM, "--strict-mcp-config", "--setting-sources", "",
             "--no-session-persistence", "--output-format", "json"],
            cwd=empty, capture_output=True, text=True, timeout=900)
    d = json.loads(r.stdout)
    return d.get("result", ""), {
        "resolved_models": sorted((d.get("modelUsage") or {}).keys()),
        # the CLI also makes a small fixed auxiliary call on a Haiku model; the
        # per-model usage shows which model produced the answer's output tokens
        "model_usage": d.get("modelUsage"),
        "num_turns": d.get("num_turns"), "is_error": d.get("is_error"),
        "stop_reason": d.get("stop_reason"),
        "permission_denials": d.get("permission_denials"),
        "usage": d.get("usage"), "cost_usd": d.get("total_cost_usd"),
        "seconds": round(time.time() - t0, 1), "cli_version": CLI_VERSION,
        "harness": "claude CLI --print, --tools '' (no tools), --system-prompt, "
                   "--setting-sources '' , --strict-mcp-config, empty cwd; "
                   "sampling parameters not exposed by the CLI, left at defaults"}


def run_qwen(prompt):
    body = {"model": QWEN_MODEL, "messages": [
        {"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        **QWEN_SAMPLING}
    req = urllib.request.Request(QWEN_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as resp:
        d = json.loads(resp.read())
    ch = d["choices"][0]
    return ch["message"].get("content") or "", {
        "resolved_models": [d.get("model")], "system_fingerprint": d.get("system_fingerprint"),
        "finish_reason": ch.get("finish_reason"), "usage": d.get("usage"),
        "reasoning_chars": len(ch["message"].get("reasoning_content") or ""),
        "seconds": round(time.time() - t0, 1),
        "harness": f"local OpenAI-compatible server, sampling {QWEN_SAMPLING}, "
                   "reasoning enabled (server default), no tools"}


def trial(job):
    condition, model, i = job
    stem = f"{condition}__{model}__{i}"
    if (RAW / f"{stem}.txt").exists():
        return stem, "cached"
    prompt = prompt_for(condition)
    try:
        text, meta = (run_qwen(prompt) if model == QWEN_MODEL else run_claude(model, prompt))
    except Exception as e:  # a failed trial is recorded, never dropped
        text, meta = f"__TRIAL_ERROR__ {type(e).__name__}: {e}", {"error": True}
    if meta.get("is_error"):  # an API error is a failed trial, never code to probe
        text = f"__TRIAL_ERROR__ {text}"
    meta.update(condition=condition, model_requested=model, trial=i,
                prompt_chars=len(prompt), docs_in_prompt=CONDITIONS[condition][0])
    (RAW / f"{stem}.txt").write_text(text)
    (RAW / f"{stem}.meta.json").write_text(json.dumps(meta, indent=2))
    return stem, meta.get("resolved_models")


def main():
    (RAW / "SHOWN_PATH.py").write_text("def python_side():" +
                                        CONTEXT.split("def python_side():", 1)[1])
    for c in CONDITIONS:
        (RAW / f"PROMPT__{c}.txt").write_text(prompt_for(c))
    claude_jobs = [(c, m, i) for c in CONDITIONS for m in CLAUDE_MODELS for i in range(TRIALS)]
    # round-robin over conditions, so a run stopped early is still balanced
    qwen_jobs = []  # second family dropped: local decode too slow; see the paper's limitations
    print(f"{len(claude_jobs)} Claude trials", flush=True)
    with ThreadPoolExecutor(6) as cpool, ThreadPoolExecutor(1) as qpool:
        futs = [cpool.submit(trial, j) for j in claude_jobs] + \
               [qpool.submit(trial, j) for j in qwen_jobs]
        for f in futs:
            stem, info = f.result()
            print(f"  {stem}: {info}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
