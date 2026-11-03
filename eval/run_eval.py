"""Evaluate BrandProof on the labelled NovaTech claim set.

    python eval/run_eval.py                 # rules-only baseline (needs no key, no database)
    LLM_API_KEY=... python eval/run_eval.py --gemini   # rules-only vs rules + Gemini, side by side

Each claim is audited on its own. A claim counts as *flagged* when any finding is not "Supported".
Labels: correct | wrong_fact | unsupported_claim | exaggeration  (anything but "correct" should be flagged).

Honest limits, repeated in the report:
- The easy claims were written next to the rules, so rules-only scores on them are optimistic.
  The claims marked ``hard`` are paraphrases and claims the rules were not designed for; they show
  the real gap Gemini is meant to close.
- "Rewrite verified" only means the rewrite re-audits clean under the rules. Whether a person
  *accepts* a rewrite is a human judgement and cannot be measured offline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from app.audit import run_rules_audit  # noqa: E402
from app.corrections import build_rewrite  # noqa: E402

EXPECTED_CATEGORIES = {
    "wrong_fact": {"Factual accuracy", "Claim support"},
    "unsupported_claim": {"Claim support", "Policy compliance", "Policy"},
    "exaggeration": {"Policy compliance", "Tone", "Policy"},
}


def load_context():
    data = json.loads((ROOT / "context.json").read_text())
    facts = [NS(active=True, **item) for item in data["facts"]]
    policies = [NS(active=True, **item) for item in data["policies"]]
    terms = [NS(active=True, **item) for item in data["terminology"]]
    return facts, policies, terms


def ratio(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else numerator / denominator


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def audit_claim(text: str, facts, policies, terms, use_gemini: bool):
    drafts = run_rules_audit(text, facts, policies, terms)
    findings = [(draft.category, draft.verification_status, "rules") for draft in drafts]
    ai_findings = []
    if use_gemini:
        from app.ai import AIProviderError, call_gemini

        try:
            ai_findings = call_gemini(text, facts, policies)
        except AIProviderError as exc:
            return findings, [], str(exc)
        findings += [(item.category, item.verification_status, "ai") for item in ai_findings]
    return findings, ai_findings, ""


def evaluate(claims, facts, policies, terms, use_gemini: bool):
    rows = []
    errors = 0
    for claim in claims:
        findings, ai_findings, error = audit_claim(claim["text"], facts, policies, terms, use_gemini)
        errors += bool(error)
        open_findings = [item for item in findings if item[1] != "Supported"]
        rows.append({**claim, "flagged": bool(open_findings), "categories": sorted({item[0] for item in open_findings}), "error": error, "ai_findings": [item.model_dump() for item in ai_findings] if ai_findings else []})
        if use_gemini:
            time.sleep(0.4)
    return rows, errors


def metrics(rows):
    bad = [row for row in rows if row["label"] != "correct"]
    good = [row for row in rows if row["label"] == "correct"]
    tp = sum(row["flagged"] for row in bad)
    fn = len(bad) - tp
    fp = sum(row["flagged"] for row in good)
    tn = len(good) - fp
    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    f1 = None if precision is None or recall is None or precision + recall == 0 else 2 * precision * recall / (precision + recall)
    right_type = sum(1 for row in bad if row["flagged"] and set(row["categories"]) & EXPECTED_CATEGORIES[row["label"]])
    return {"n": len(rows), "tp": tp, "fn": fn, "fp": fp, "tn": tn, "precision": precision, "recall": recall, "false_positive_rate": ratio(fp, fp + tn), "f1": f1, "category_agreement": ratio(right_type, tp)}


def rewrite_stats(rows, facts, policies, terms):
    flagged = [row for row in rows if row["flagged"] and row["label"] != "correct"]
    changed = verified = 0
    for row in flagged:
        result = build_rewrite(row["text"], facts, policies, terms, [])
        if result["changes"]:
            changed += 1
            verified += result["verification"]["passed"]
    return {"flagged_bad_claims": len(flagged), "rewrite_proposed": changed, "rewrite_verified_clean": verified, "verified_rate": ratio(verified, changed), "coverage": ratio(changed, len(flagged))}


def fmt_block(title: str, m: dict) -> list[str]:
    return [f"| {title} | {m['n']} | {pct(m['precision'])} | {pct(m['recall'])} | {pct(m['false_positive_rate'])} | {pct(m['f1'])} | {pct(m['category_agreement'])} | {m['tp']}/{m['fn']}/{m['fp']}/{m['tn']} |"]


def report(mode: str, rows, facts, policies, terms) -> list[str]:
    easy, hard = [row for row in rows if not row["hard"]], [row for row in rows if row["hard"]]
    lines = [f"### {mode}", "", "| Subset | Claims | Precision | Recall | False-positive rate | F1 | Category agreement | TP/FN/FP/TN |", "|---|---|---|---|---|---|---|---|"]
    lines += fmt_block("All", metrics(rows))
    lines += fmt_block("Easy (rules-style)", metrics(easy))
    lines += fmt_block("Hard (paraphrase / out-of-rules)", metrics([row for row in rows if row["hard"] or row["label"] == "correct"]))
    rw = rewrite_stats(rows, facts, policies, terms)
    lines += ["", f"Rewrite check (rules-only rewrite engine): {rw['rewrite_proposed']}/{rw['flagged_bad_claims']} flagged bad claims received a proposed fix ({pct(rw['coverage'])}); {rw['rewrite_verified_clean']}/{rw['rewrite_proposed']} of those re-audit clean ({pct(rw['verified_rate'])}). This is an automatic proxy, not human acceptance.", ""]
    per_label: dict[str, list[int]] = {}
    for row in rows:
        per_label.setdefault(row["label"], [0, 0])
        per_label[row["label"]][0] += row["flagged"]
        per_label[row["label"]][1] += 1
    lines.append("Flagged per label: " + ", ".join(f"{label} {a}/{b}" for label, (a, b) in per_label.items()))
    missed = [row for row in rows if row["label"] != "correct" and not row["flagged"]]
    wrong = [row for row in rows if row["label"] == "correct" and row["flagged"]]
    if wrong:
        lines += ["", "False positives:"] + [f"- {row['id']} \"{row['text']}\" -> {', '.join(row['categories'])}" for row in wrong]
    if missed:
        lines += ["", f"Missed ({len(missed)}):"] + [f"- {row['id']} [{row['label']}{', hard' if row['hard'] else ''}] \"{row['text']}\"" for row in missed]
    return lines + [""]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gemini", action="store_true", help="also run rules + Gemini (needs LLM_API_KEY)")
    parser.add_argument("--out", default=str(ROOT / "results.md"), help="where to write the markdown report")
    args = parser.parse_args()

    facts, policies, terms = load_context()
    claims = json.loads((ROOT / "claims.json").read_text())["claims"]
    out = ["# BrandProof evaluation results", "", f"Claim set: {len(claims)} labelled NovaTech claims ({sum(c['hard'] for c in claims)} hard). Run on {time.strftime('%Y-%m-%d')}.", ""]

    rule_rows, _ = evaluate(claims, facts, policies, terms, use_gemini=False)
    out += report("Rules-only", rule_rows, facts, policies, terms)

    if args.gemini:
        key = os.environ.get("LLM_API_KEY", "")
        if not key:
            print("--gemini needs LLM_API_KEY in the environment", file=sys.stderr)
            return 2
        from app.config import settings

        settings.llm_api_key, settings.llm_provider = key, "gemini"
        if os.environ.get("LLM_MODEL"):
            settings.llm_model = os.environ["LLM_MODEL"]
        gem_rows, errors = evaluate(claims, facts, policies, terms, use_gemini=True)
        out += report(f"Rules + Gemini ({settings.llm_model})", gem_rows, facts, policies, terms)
        if errors:
            out += [f"Note: {errors} claim(s) hit a provider error and were scored with rules only.", ""]
        before, after = metrics(rule_rows), metrics(gem_rows)
        out += ["### Change from adding Gemini", "", f"- Recall: {pct(before['recall'])} -> {pct(after['recall'])}", f"- False-positive rate: {pct(before['false_positive_rate'])} -> {pct(after['false_positive_rate'])}", f"- Precision: {pct(before['precision'])} -> {pct(after['precision'])}", ""]
    else:
        out += ["_Gemini comparison not run: pass --gemini with LLM_API_KEY set to add it._", ""]

    text = "\n".join(out)
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
