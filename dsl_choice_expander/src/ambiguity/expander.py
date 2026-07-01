"""Deterministic expander for ambiguous CHOICE-DSL queries.

Three stages, mirroring the design:

1. :func:`expand` — unfold the AND-OR tree into the set of unambiguous, concrete
   SPARQL queries. Every choice point contributes a dimension; the result is the
   cartesian product of all (top-level and nested) choices. Each expansion
   carries *provenance*: which option was chosen at each choice point.

2. :func:`execute_all` — run every expansion against the Ontop endpoint(s),
   reusing the existing :func:`src.tools.sparql_tools.execute_sparql_async`
   (endpoint routing from PREFIX declarations, validation, retries). Validation
   is *by execution*: syntactically broken or type-inconsistent expansions
   surface here as errors and are marked, not repaired.

3. :func:`answer_set` — assemble the set of admissible answers: the union of
   result tuples across all *successful* expansions, plus a per-interpretation
   breakdown so one can see which interpretation yields which answers.

Endpoint context (slot / SSH tunnel / USE_SLOT_CONTAINERS) is the caller's
responsibility — the expander is endpoint-agnostic and only calls the existing
execution function, which resolves endpoints from the query's prefixes.
"""

from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass, field

from src.ambiguity.dsl import (
    _PLACEHOLDER,
    _PLACEHOLDER_RE,
    AmbiguousQuery,
    ChoicePoint,
)

__all__ = [
    "ExpandedQuery",
    "ExecutedExpansion",
    "ExpansionRun",
    "AdmissibleAnswers",
    "expand",
    "execute_all",
    "answer_set",
]


@dataclass
class ExpandedQuery:
    """One unambiguous SPARQL query produced from the ambiguous query.

    ``provenance`` maps each choice point name to the option label that was
    selected to produce this expansion. ``selection`` is the same keyed by
    choice index (stable across duplicate names).
    """

    sparql: str
    provenance: dict[str, str]
    selection: dict[int, int]  # choice index -> option index

    def provenance_str(self) -> str:
        return ", ".join(f"{k}={v}" for k, v in self.provenance.items()) or "(no choices)"


@dataclass
class ExecutedExpansion:
    """Result of running one :class:`ExpandedQuery` against the endpoint(s)."""

    query: ExpandedQuery
    success: bool
    bindings: list[dict] = field(default_factory=list)  # SPARQL-JSON bindings
    row_count: int = 0
    queried_endpoints: list[str] = field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class ExpansionRun:
    """All executed expansions for one ambiguous query."""

    ambiguous: AmbiguousQuery
    expansions: list[ExecutedExpansion]

    @property
    def successful(self) -> list[ExecutedExpansion]:
        return [e for e in self.expansions if e.success]

    @property
    def failed(self) -> list[ExecutedExpansion]:
        return [e for e in self.expansions if not e.success]


@dataclass
class AdmissibleAnswers:
    """The set of admissible answers across all interpretations.

    ``columns`` is the projected variable order taken from the first successful
    expansion. ``union`` is the set of distinct answer tuples (as tuples of
    strings, one per projected variable) over all successful expansions.
    ``by_interpretation`` lists, per successful expansion, its provenance and
    the answer tuples it produced.
    """

    columns: list[str]
    union: set[tuple[str, ...]]
    by_interpretation: list[dict]
    n_expansions: int
    n_successful: int
    n_failed: int

    @property
    def union_size(self) -> int:
        return len(self.union)


# --------------------------------------------------------------------------- #
# Stage 1: expand
# --------------------------------------------------------------------------- #


def _render(aq: AmbiguousQuery, selection: dict[int, int]) -> str:
    """Render the template with the given per-choice option selection.

    Substitution is iterated to a fixpoint because structural branches may
    themselves contain placeholders for nested choices. Only placeholders whose
    choice index is present in ``selection`` are substituted; by construction a
    complete selection covers every choice that can become visible.
    """
    text = aq.template
    # Iterate until no known placeholder remains (nested choices get revealed as
    # their parent branch is substituted in).
    for _ in range(len(aq.choices) + 1):
        def _sub(m: "re.Match") -> str:  # noqa: F821 - re.Match via _PLACEHOLDER_RE
            idx = int(m.group(1))
            cp = aq.choices[idx]
            opt = selection[idx]
            if cp.kind == "term":
                return cp.options[opt]
            if cp.kind == "unspecified":
                # Single default value; opt is always 0 (cardinality 1).
                return cp.options[0]
            return cp.branches[opt].pattern

        new_text = _PLACEHOLDER_RE.sub(_sub, text)
        if new_text == text:
            break
        text = new_text
    return text


def _apply_constraints(aq: AmbiguousQuery, selection: dict[int, int]) -> dict[int, int]:
    """Pin constraint-targeted choices to their canonical option when inactive.

    For each ``IRRELEVANT_WHEN`` constraint whose trigger holds in ``selection``,
    the target choice does not affect the result, so we pin it to option 0. Many
    raw combinations then collapse to the same pinned selection — the caller
    deduplicates, so the correlated dimension contributes one expansion, not N.
    """
    if not aq.constraints:
        return selection
    pinned = dict(selection)
    for c in aq.constraints:
        if selection.get(c.trigger_index) == c.trigger_option_index:
            pinned[c.target_index] = 0
    return pinned


def _iter_selections(aq: AmbiguousQuery):
    """Yield every complete, *consistent* selection over the choice points.

    A selection assigns an option index to every choice point. Nested choices
    that live inside an unchosen structural branch are irrelevant for that
    expansion, but assigning them a value anyway is harmless (their placeholder
    never appears once the parent branch is fixed). We therefore take the full
    cartesian product over all choices, then drop selections that render to the
    same SPARQL string (which collapses the irrelevant nested dimensions).

    Correlation constraints (:class:`Constraint`) further pin a target choice to
    its canonical option whenever its trigger holds, so redundant combinations
    (e.g. ``COUNT`` × every rating property) collapse before rendering. We
    deduplicate the pinned selections here so each surviving selection is yielded
    once.
    """
    indices = [cp.index for cp in aq.choices]
    ranges = [range(aq.choices[i].cardinality) for i in indices]
    seen: set[tuple[tuple[int, int], ...]] = set()
    for combo in itertools.product(*ranges):
        selection = dict(zip(indices, combo, strict=True))
        selection = _apply_constraints(aq, selection)
        key = tuple(sorted(selection.items()))
        if key in seen:
            continue
        seen.add(key)
        yield selection


def expand(aq: AmbiguousQuery) -> list[ExpandedQuery]:
    """Unfold the ambiguous query into distinct unambiguous SPARQL queries."""
    seen: set[str] = set()
    out: list[ExpandedQuery] = []
    for selection in _iter_selections(aq):
        sparql = _render(aq, selection)
        if sparql in seen:
            # Collapses dimensions of nested choices that are not visible in
            # this particular structural branch.
            continue
        seen.add(sparql)
        visible = _visible_indices(aq, selection)
        provenance = {
            aq.choices[i].name: aq.choices[i].option_names[selection[i]]
            for i in visible
        }
        # Restrict the recorded selection to the choices actually visible in
        # this expansion (so provenance is meaningful, not noisy).
        sel = {i: selection[i] for i in visible}
        out.append(ExpandedQuery(sparql=sparql, provenance=provenance, selection=sel))
    return out


def _parent_map(aq: AmbiguousQuery) -> dict[int, tuple[int, int]]:
    """nested choice index -> (parent structural index, parent branch index)."""
    parent: dict[int, tuple[int, int]] = {}
    for cp in aq.choices:
        if cp.kind == "structural":
            for b_idx, branch in enumerate(cp.branches):
                for nested in branch.nested:
                    parent[nested] = (cp.index, b_idx)
    return parent


def _visible_indices(aq: AmbiguousQuery, selection: dict[int, int]) -> list[int]:
    """Choice indices that actually influence this expansion.

    A choice is visible iff every ancestor structural branch on its path was the
    chosen one. Top-level choices (no parent) are always visible. Returns indices
    in document order so provenance reads top-to-bottom.
    """
    parent = _parent_map(aq)

    def visible(idx: int) -> bool:
        cur = idx
        while cur in parent:
            p_idx, b_idx = parent[cur]
            if selection.get(p_idx) != b_idx:
                return False
            cur = p_idx
        return True

    return [cp.index for cp in aq.choices if visible(cp.index)]


# --------------------------------------------------------------------------- #
# Stage 2: execute
# --------------------------------------------------------------------------- #


async def execute_all(
    aq: AmbiguousQuery,
    expansions: list[ExpandedQuery] | None = None,
    *,
    max_concurrency: int = 4,
) -> ExpansionRun:
    """Execute every expansion against its endpoint(s).

    Reuses ``execute_sparql_async`` so endpoint routing, query validation, and
    retry/backoff behave exactly like the main pipeline. The caller must have
    established the endpoint context (slot_context / USE_SLOT_CONTAINERS / SSH
    tunnel) before awaiting this.
    """
    # Imported lazily so importing this module never requires the heavy
    # execution stack (httpx clients, config side effects) until it is used.
    from src.tools.sparql_tools import execute_sparql_async

    if expansions is None:
        expansions = expand(aq)

    sem = asyncio.Semaphore(max_concurrency)

    async def _run(eq: ExpandedQuery) -> ExecutedExpansion:
        async with sem:
            res = await execute_sparql_async(eq.sparql)
        success = bool(res.get("success"))
        bindings = res.get("results", {}).get("bindings", []) if success else []
        error_type = None
        error_message = None
        if not success:
            error_type = res.get("error_type")
            errs = res.get("errors")
            if errs:
                error_type = error_type or errs[0].get("error_type")
                error_message = errs[0].get("error_message")
            error_message = error_message or res.get("error_message")
        return ExecutedExpansion(
            query=eq,
            success=success,
            bindings=bindings,
            row_count=len(bindings),
            queried_endpoints=res.get("queried_endpoints", []),
            error_type=error_type,
            error_message=error_message,
        )

    results = await asyncio.gather(*(_run(eq) for eq in expansions))
    return ExpansionRun(ambiguous=aq, expansions=list(results))


# --------------------------------------------------------------------------- #
# Stage 3: answer set
# --------------------------------------------------------------------------- #


def _projected_vars(bindings: list[dict]) -> list[str]:
    """Projected variable names from SPARQL-JSON bindings (stable order)."""
    order: list[str] = []
    for b in bindings:
        for k in b:
            if k == "_source_endpoint":
                continue
            if k not in order:
                order.append(k)
    return order


def _tuples(bindings: list[dict], columns: list[str]) -> set[tuple[str, ...]]:
    """Convert bindings to a set of value tuples over ``columns``.

    Unbound variables become the empty string. The ``_source_endpoint`` tag is
    ignored. This is order-independent set semantics, the same notion of
    answer-set equality used by the tiered tuple metrics.
    """
    out: set[tuple[str, ...]] = set()
    for b in bindings:
        row = tuple(
            (b.get(c, {}) or {}).get("value", "") for c in columns
        )
        out.add(row)
    return out


def answer_set(run: ExpansionRun) -> AdmissibleAnswers:
    """Assemble the admissible-answer set from an executed run."""
    successful = run.successful

    # Column order from the first successful expansion that returned rows;
    # fall back to the first successful expansion's projection even if empty.
    columns: list[str] = []
    for e in successful:
        cols = _projected_vars(e.bindings)
        if cols:
            columns = cols
            break
    if not columns and successful:
        columns = _projected_vars(successful[0].bindings)

    union: set[tuple[str, ...]] = set()
    by_interpretation: list[dict] = []
    for e in successful:
        tuples = _tuples(e.bindings, columns) if columns else set()
        union |= tuples
        by_interpretation.append(
            {
                "provenance": e.query.provenance,
                "sparql": e.query.sparql,
                "row_count": e.row_count,
                "tuple_count": len(tuples),
                "endpoints": e.queried_endpoints,
            }
        )

    return AdmissibleAnswers(
        columns=columns,
        union=union,
        by_interpretation=by_interpretation,
        n_expansions=len(run.expansions),
        n_successful=len(successful),
        n_failed=len(run.failed),
    )
