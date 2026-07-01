"""Execution feedback for the ambiguity agent's self-correction loop.

The ambiguity agent emits an ambiguous CHOICE-DSL query, then needs to *see what
its expansions actually do* before committing — exactly like the multi-step
SQL/SPARQL agents that run a candidate and revise it. This module turns a
CHOICE-DSL string into a compact, agent-readable execution summary: it parses,
expands, runs every expansion against Ontop, and reports per-interpretation
status / row counts / errors plus any parse error.

It is deliberately read-only and side-effect-free apart from the SPARQL reads,
and reuses the deterministic :mod:`src.ambiguity.expander` so the numbers the
agent sees are exactly the numbers the final report will show. The agent decides
what (if anything) to fix; this module never edits the query.
"""

from __future__ import annotations

import json

from src.ambiguity.dsl import DSLParseError, parse_ambiguous_query
from src.ambiguity.expander import answer_set, execute_all, expand

__all__ = ["evaluate_ambiguous_query", "format_feedback"]

# Keep the feedback compact: a few sample answer rows per interpretation is
# enough for the agent to judge plausibility without flooding the context.
_MAX_SAMPLE_ROWS = 3
_MAX_INTERPRETATIONS_SHOWN = 40


async def evaluate_ambiguous_query(
    dsl_query: str, *, max_concurrency: int = 4
) -> dict:
    """Parse, expand, and execute a CHOICE-DSL query; return a result summary.

    Returns a dict with either ``{"parse_error": ...}`` (the DSL did not parse)
    or the executed breakdown: number of expansions, how many succeeded/failed,
    the union answer-set size, and a per-interpretation list (provenance, status,
    row count, error, a few sample rows). This is the payload the agent sees
    between iterations of its self-correction loop.
    """
    try:
        aq = parse_ambiguous_query(dsl_query)
    except DSLParseError as exc:
        return {"parse_error": str(exc)}

    expansions = expand(aq)
    run = await execute_all(aq, expansions, max_concurrency=max_concurrency)
    ans = answer_set(run)

    interpretations = []
    for exp in run.expansions:
        prov = exp.query.provenance
        sample = []
        if exp.success and exp.bindings:
            for b in exp.bindings[:_MAX_SAMPLE_ROWS]:
                sample.append(
                    {
                        k: (v or {}).get("value", "")
                        for k, v in b.items()
                        if k != "_source_endpoint"
                    }
                )
        interpretations.append(
            {
                "provenance": prov,
                "success": exp.success,
                "row_count": exp.row_count,
                "error_type": exp.error_type,
                "error_message": (exp.error_message or "")[:300] or None,
                "sample": sample,
                "endpoints": exp.queried_endpoints,
            }
        )

    return {
        "parse_error": None,
        "n_choice_points": len(aq.choices),
        "n_constraints": len(aq.constraints),
        "n_expansions": len(expansions),
        "n_successful": ans.n_successful,
        "n_failed": ans.n_failed,
        "answer_union_size": ans.union_size,
        "answer_columns": ans.columns,
        "interpretations": interpretations,
    }


def format_feedback(summary: dict) -> str:
    """Render an execution summary as a compact string for the agent prompt."""
    if summary.get("parse_error"):
        return (
            "Your CHOICE-DSL did not PARSE — it was not executed:\n"
            f"  {summary['parse_error']}\n"
            "Fix the syntax and re-emit the query."
        )

    lines = [
        f"Executed {summary['n_expansions']} expansion(s) from "
        f"{summary['n_choice_points']} choice point(s), "
        f"{summary['n_constraints']} constraint(s): "
        f"{summary['n_successful']} ok, {summary['n_failed']} failed. "
        f"Union of admissible answers: {summary['answer_union_size']} tuple(s) "
        f"over columns {summary['answer_columns']}.",
        "",
        "Per interpretation:",
    ]
    shown = summary["interpretations"][:_MAX_INTERPRETATIONS_SHOWN]
    for i, it in enumerate(shown):
        prov = ", ".join(f"{k}={v}" for k, v in it["provenance"].items()) or "(no choices)"
        if it["success"]:
            tag = f"{it['row_count']} rows"
            if it["row_count"] == 0:
                tag += "  <- EMPTY: valid query, no matches (check filters/vocabulary)"
        else:
            tag = f"FAILED [{it['error_type']}]: {it['error_message']}"
        lines.append(f"  [{i}] {prov} -> {tag}")
        if it["success"] and it["sample"]:
            lines.append(f"        sample: {json.dumps(it['sample'], ensure_ascii=False)}")
    if len(summary["interpretations"]) > len(shown):
        lines.append(f"  ... ({len(summary['interpretations']) - len(shown)} more)")

    lines += [
        "",
        "Review this. If every interpretation you intended runs and returns "
        "plausible answers, you are done — keep the query as is. If some "
        "expansions FAILED or are unexpectedly EMPTY due to a defect (wrong "
        "datatype in a FILTER, missing GROUP BY, wrong property direction, a "
        "typo), fix the ambiguous query and try again. Do NOT drop a genuine "
        "interpretation just because it returns few rows — only fix actual "
        "defects.",
    ]
    return "\n".join(lines)
