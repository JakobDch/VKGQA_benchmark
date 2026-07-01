"""CHOICE-DSL grammar and parser for ambiguous SPARQL queries.

The LLM agent does not write a finished SPARQL query. It writes an *ambiguous*
query that leaves a hole at every ambiguous spot instead of guessing. Two kinds
of hole exist:

TERM CHOICE (inline, in predicate / term position of a triple)
--------------------------------------------------------------
A single schema element could not be pinned down to one candidate. The agent
lists the candidates and commits to none::

    ?field <opProp: :currentFieldOperator | :hasLicence/:licenceOperator> ?company .

Unicode form ``<...>`` (angle brackets) and the ASCII fallback ``<<...>>`` are
both accepted, so models that cannot reliably emit the Unicode angle brackets
still parse. Each candidate is a verbatim SPARQL term (an IRI/prefixed name or
a property path such as ``:hasLicence/:licenceOperator``).

STRUCTURAL CHOICE (a block over whole graph patterns)
-----------------------------------------------------
It is unclear which subtree a constraint hangs on, so the agent branches over
entire graph patterns::

    CHOICE temporalAttach {
      onWellbore: { ?wb :drilledInField ?field .
                    ?wb <dateProp: :entryDate | :completionDate> ?t . }
      onField:    { ?field :dateOfDiscovery ?t . }
    }

A structural branch body is itself DSL (it may contain further term choices),
so choices nest.

EVERYTHING ELSE
---------------
The rest of the query is ordinary SPARQL (SELECT, the fixed BGP, FILTER, ORDER
BY, LIMIT, ...). It is carried through verbatim. ``<n>`` style numeric
placeholders for an open LIMIT etc. are *not* interpreted here; the agent is
asked to either commit to a value or express the alternatives as a choice.

PARSE RESULT
------------
Parsing yields an :class:`AmbiguousQuery`: a *template* string in which every
choice has been replaced by a unique placeholder token, plus the ordered list
of :class:`ChoicePoint` descriptors. The expander
(:mod:`src.ambiguity.expander`) renders one concrete SPARQL string per element
of the cartesian product of the choice points by substituting the placeholders.

This module is a pure-Python parser. It does not depend on rdflib; the expander
optionally uses rdflib only to sanity-check individual expansions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "AmbiguousQuery",
    "ChoicePoint",
    "Constraint",
    "DSLParseError",
    "parse_ambiguous_query",
]


class DSLParseError(ValueError):
    """Raised when the CHOICE-DSL is malformed and cannot be parsed."""


# A placeholder token embedded in the template string for one choice point.
# The %d is the choice point's index. Chosen to never collide with SPARQL.
_PLACEHOLDER = "\x00CHOICE_{}\x00"
_PLACEHOLDER_RE = re.compile(r"\x00CHOICE_(\d+)\x00")


@dataclass
class StructuralBranch:
    """One named branch of a structural CHOICE block.

    ``pattern`` is the branch body as a template string (placeholders for any
    nested choices substituted), and ``nested`` lists the indices of choice
    points that live inside this branch.
    """

    name: str
    pattern: str
    nested: list[int] = field(default_factory=list)


@dataclass
class ChoicePoint:
    """One ambiguity hole in the query.

    kind == "term":
        ``options`` is the list of candidate SPARQL terms (strings); rendering
        substitutes the chosen term verbatim in place of the placeholder.

    kind == "structural":
        ``branches`` is the list of named branches; rendering substitutes the
        chosen branch's ``pattern`` (which may itself contain placeholders).

    kind == "unspecified":
        NOT an ambiguity — a value the question *implies but never states* (e.g.
        the cutoff in "affordable products", the N in "top products"). It is a
        single placeholder filled with a context-appropriate default the agent
        supplies, so the query stays executable without pretending the value was
        given. ``options == [default_value]`` (exactly one); cardinality is 1, so
        it never multiplies the expansion count. Provenance flags it as
        UNSPECIFIED so a reader sees the value was inserted, not stated.
    """

    index: int
    name: str
    kind: Literal["term", "structural", "unspecified"]
    options: list[str] = field(default_factory=list)  # term choice / [default]
    branches: list[StructuralBranch] = field(default_factory=list)  # structural

    @property
    def option_names(self) -> list[str]:
        """Human-readable label per option (for provenance)."""
        if self.kind == "structural":
            return [b.name for b in self.branches]
        if self.kind == "unspecified":
            return [f"{self.options[0]} (UNSPECIFIED)"]
        return list(self.options)

    @property
    def cardinality(self) -> int:
        if self.kind == "structural":
            return len(self.branches)
        if self.kind == "unspecified":
            # A missing value is filled with one default; it is not a choice and
            # must not blow up the cartesian product.
            return 1
        return len(self.options)


@dataclass
class Constraint:
    """A correlation between two choice points that prunes the expansion.

    ``IRRELEVANT_WHEN``: when choice ``trigger`` takes option ``trigger_value``,
    choice ``target`` no longer affects the result (e.g. with ``aggFunc=COUNT``
    the ``ratingProp`` chosen does not change the answer). The expander then
    pins ``target`` to its canonical first option in those selections, so the
    correlated dimension contributes exactly one expansion instead of N.

    ``target_index`` / ``trigger_index`` are resolved to choice indices at parse
    time; ``trigger_value`` is the option *label* of the trigger choice.
    """

    target: str
    trigger: str
    trigger_value: str
    target_index: int
    trigger_index: int
    trigger_option_index: int


@dataclass
class AmbiguousQuery:
    """Parsed ambiguous query: a template plus its choice points.

    The template is a SPARQL string with one placeholder per choice point. A
    choice point may be *nested* inside a structural branch; such a placeholder
    only appears in the template after its parent branch has been substituted.
    The :attr:`top_level` indices are the choice points reachable from the root
    template (i.e. not inside any branch).

    ``constraints`` are correlations that prune redundant expansions (see
    :class:`Constraint`).
    """

    raw: str
    template: str
    choices: list[ChoicePoint]
    constraints: list[Constraint] = field(default_factory=list)

    @property
    def top_level(self) -> list[int]:
        """Indices of choice points whose placeholder is in the root template."""
        present = {int(m.group(1)) for m in _PLACEHOLDER_RE.finditer(self.template)}
        return sorted(present)

    def choice(self, index: int) -> ChoicePoint:
        return self.choices[index]

    def describe(self) -> str:
        """Compact human-readable summary of the choice structure."""
        lines = [f"AmbiguousQuery with {len(self.choices)} choice point(s):"]
        for cp in self.choices:
            opts = " | ".join(cp.option_names)
            lines.append(f"  [{cp.index}] {cp.name} ({cp.kind}): {opts}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

# Identifier for choice / branch names: letters, digits, underscore.
_NAME = r"[A-Za-z_][A-Za-z0-9_]*"


def parse_ambiguous_query(text: str) -> AmbiguousQuery:
    """Parse a CHOICE-DSL string into an :class:`AmbiguousQuery`.

    Raises :class:`DSLParseError` on malformed input.
    """
    if not text or not text.strip():
        raise DSLParseError("empty query")

    # Pull CONSTRAINT lines out first: they are metadata about correlations, not
    # part of the SPARQL graph pattern, so they must not reach _parse_block (which
    # would otherwise copy them into the template verbatim).
    body, raw_constraints = _extract_constraint_lines(text)

    choices: list[ChoicePoint] = []
    # Normalise the ASCII fallback angle brackets to a single internal form by
    # parsing both; we handle them directly in the scanners below, so no global
    # substitution is needed (that would corrupt SPARQL '<iri>' tokens).
    template = _parse_block(body, choices)

    if not choices:
        # A query with no choice points is allowed (it's just unambiguous), but
        # most callers expect at least one; we still return it so the expander
        # yields a single expansion.
        pass

    _validate(choices)
    constraints = _resolve_constraints(raw_constraints, choices)
    return AmbiguousQuery(
        raw=text, template=template, choices=choices, constraints=constraints
    )


def _parse_block(text: str, choices: list[ChoicePoint]) -> str:
    """Parse a DSL fragment, replacing every choice with a placeholder.

    Returns the fragment as a template string. ``choices`` is appended to
    in document order; nested choices are appended before their enclosing
    structural choice point so that indices are stable.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        # Try structural CHOICE block at this position.
        m = _match_choice_keyword(text, i)
        if m is not None:
            placeholder, next_i = _parse_structural_choice(text, i, choices)
            out.append(placeholder)
            i = next_i
            continue
        # Try term choice <...> / <<...>> at this position.
        term = _match_term_choice(text, i)
        if term is not None:
            inner, next_i = term
            placeholder = _build_term_choice(inner, choices)
            out.append(placeholder)
            i = next_i
            continue
        # Otherwise copy one character verbatim.
        out.append(text[i])
        i += 1
    return "".join(out)


def _match_choice_keyword(text: str, i: int) -> re.Match | None:
    """Match ``CHOICE <name> {`` starting at position ``i`` (word-boundary)."""
    if not text.startswith("CHOICE", i):
        return None
    # Ensure 'CHOICE' is a standalone keyword (preceded by start/space/brace).
    if i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_"):
        return None
    return re.compile(rf"CHOICE\s+({_NAME})\s*\{{").match(text, i)


def _parse_structural_choice(
    text: str, start: int, choices: list[ChoicePoint]
) -> tuple[str, int]:
    """Parse a ``CHOICE name { ... }`` block beginning at ``start``.

    Returns ``(placeholder, index_after_block)``.
    """
    header = _match_choice_keyword(text, start)
    assert header is not None
    name = header.group(1)
    body_start = header.end()  # position just after the opening '{'
    body, after = _read_balanced_braces(text, body_start - 1)  # include the '{'
    branches = _parse_branches(name, body, choices)
    cp_index = len(choices)
    cp = ChoicePoint(
        index=cp_index, name=name, kind="structural", branches=branches
    )
    choices.append(cp)
    return _PLACEHOLDER.format(cp_index), after


def _parse_branches(
    choice_name: str, body: str, choices: list[ChoicePoint]
) -> list[StructuralBranch]:
    """Parse ``opt1: { ... } opt2: { ... }`` inside a structural CHOICE body."""
    branches: list[StructuralBranch] = []
    i = 0
    n = len(body)
    while i < n:
        # Skip whitespace and separators.
        while i < n and body[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        m = re.compile(rf"({_NAME})\s*:\s*\{{").match(body, i)
        if m is None:
            # Allow trailing whitespace/garbage only if nothing left meaningful.
            remainder = body[i:].strip()
            if remainder:
                raise DSLParseError(
                    f"CHOICE '{choice_name}': expected 'name: {{ ... }}' branch, "
                    f"got: {remainder[:60]!r}"
                )
            break
        branch_name = m.group(1)
        brace_pos = m.end() - 1  # the '{'
        branch_body, after = _read_balanced_braces(body, brace_pos)
        before = len(choices)
        pattern = _parse_block(branch_body, choices)
        nested = list(range(before, len(choices)))
        branches.append(
            StructuralBranch(name=branch_name, pattern=pattern, nested=nested)
        )
        i = after
    if not branches:
        raise DSLParseError(f"CHOICE '{choice_name}' has no branches")
    return branches


def _read_balanced_braces(text: str, open_pos: int) -> tuple[str, int]:
    """Given ``text[open_pos] == '{'``, return ``(inner, index_after_close)``.

    Brace counting is naive but adequate: the DSL bodies are SPARQL graph
    patterns whose braces are balanced. String literals containing stray braces
    are not expected in these schema-grounded queries; if that ever changes we
    can add literal-awareness here.
    """
    if open_pos >= len(text) or text[open_pos] != "{":
        raise DSLParseError("expected '{'")
    depth = 0
    i = open_pos
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[open_pos + 1 : i], i + 1
        i += 1
    raise DSLParseError("unbalanced '{' — missing closing '}'")


# Term choice: <name: a | b | ...> (Unicode angle) or <<name: a | b>> (ASCII).
# We accept the literal '<' / '>' and the Unicode angle brackets U+27E8/U+27E9.
_OPEN_ANGLE = "⟨"   # ⟨
_CLOSE_ANGLE = "⟩"  # ⟩


# A single-angle token <name: ...> is treated as a term choice ONLY when its
# content has the choice shape "ident: ... | ..." — i.e. an identifier, a colon,
# AND at least one pipe separating multiple candidates. Requiring the pipe makes
# it impossible to confuse with any SPARQL IRI (<http://...>, <urn:x:y>), which
# never contain ' | '. A genuine single-candidate "choice" is not ambiguous and
# need not be expressed as a choice anyway.
_CHOICE_HEAD_RE = re.compile(rf"\s*{_NAME}\s*:\s*[^|]*\|")


def _match_term_choice(text: str, i: int) -> tuple[str, int] | None:
    """Detect a term choice starting at ``i``; return ``(inner, after)``.

    Accepted opening/closing pairs, in order of robustness:
      * ``<< ... >>``    ASCII double-angle (preferred — unambiguous)
      * ``⟨ ... ⟩``      Unicode mathematical angle brackets U+27E8 / U+27E9
      * ``< ... >``      single-angle, ONLY when the body has the choice shape
                         ``name: ...`` (so it cannot be a SPARQL IRI ``<http://…>``)

    The single-angle form is supported because LLMs frequently emit it despite
    instructions; restricting it to the ``name:`` shape keeps IRIs safe.
    """
    # ASCII double-angle (check before single '<').
    if text.startswith("<<", i):
        close = text.find(">>", i + 2)
        if close == -1:
            raise DSLParseError("unbalanced '<<' — missing '>>'")
        return text[i + 2 : close], close + 2
    # Unicode angle brackets.
    if text[i] == _OPEN_ANGLE:
        close = text.find(_CLOSE_ANGLE, i + 1)
        if close == -1:
            raise DSLParseError("unbalanced '⟨' — missing '⟩'")
        return text[i + 1 : close], close + 1
    # Single-angle, choice-shaped only.
    if text[i] == "<":
        close = text.find(">", i + 1)
        if close == -1:
            return None  # not a choice; let it pass through verbatim
        inner = text[i + 1 : close]
        if _CHOICE_HEAD_RE.match(inner):
            return inner, close + 1
        return None
    return None


# A missing-value placeholder: ``<<MISSING: name=default>>``. The value the
# question implies but never states; filled with the agent-supplied default.
_MISSING_RE = re.compile(rf"\s*MISSING\s*:\s*({_NAME})\s*=\s*(.+?)\s*$", re.DOTALL)


def _build_missing(inner: str, choices: list[ChoicePoint]) -> str:
    """Parse ``MISSING: name=default`` -> single 'unspecified' placeholder."""
    m = _MISSING_RE.match(inner)
    if m is None:
        raise DSLParseError(
            "missing-value placeholder must be '<<MISSING: name=default>>', "
            f"got: {inner.strip()[:60]!r}"
        )
    name, default = m.group(1), m.group(2).strip()
    if not default:
        raise DSLParseError(f"MISSING '{name}' has no default value")
    cp_index = len(choices)
    choices.append(
        ChoicePoint(index=cp_index, name=name, kind="unspecified", options=[default])
    )
    return _PLACEHOLDER.format(cp_index)


def _build_term_choice(inner: str, choices: list[ChoicePoint]) -> str:
    """Parse a ``<< >>`` body: either ``MISSING: name=default`` or a term
    choice ``name: a | b | c`` -> placeholder."""
    # A missing-value placeholder is distinguished by the MISSING keyword; it is
    # not a choice and renders to a single default value.
    if re.match(r"\s*MISSING\s*:", inner):
        return _build_missing(inner, choices)
    m = re.match(rf"\s*({_NAME})\s*:\s*(.*)$", inner, re.DOTALL)
    if m is None:
        raise DSLParseError(
            f"term choice must be '<name: a | b | ...>', got: {inner.strip()[:60]!r}"
        )
    name = m.group(1)
    opts_raw = m.group(2)
    options = [o.strip() for o in opts_raw.split("|")]
    options = [o for o in options if o]
    if len(options) < 1:
        raise DSLParseError(f"term choice '{name}' has no candidates")
    cp_index = len(choices)
    choices.append(
        ChoicePoint(index=cp_index, name=name, kind="term", options=options)
    )
    return _PLACEHOLDER.format(cp_index)


# A constraint line: CONSTRAINT <target> IRRELEVANT_WHEN <trigger> = <value>
# The value may be a bare identifier (branch/option label) or a quoted/term-like
# token; we capture the rest of the line and strip it.
_CONSTRAINT_RE = re.compile(
    rf"^\s*CONSTRAINT\s+({_NAME})\s+IRRELEVANT_WHEN\s+({_NAME})\s*=\s*(.+?)\s*$"
)


def _extract_constraint_lines(text: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Split CONSTRAINT lines out of the DSL text.

    Returns ``(body_without_constraint_lines, [(target, trigger, value), ...])``.
    A line whose first keyword is ``CONSTRAINT`` but does not match the expected
    shape is a hard parse error (so a malformed constraint is reported back to
    the agent rather than silently ignored).
    """
    body_lines: list[str] = []
    raw: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("CONSTRAINT"):
            m = _CONSTRAINT_RE.match(line)
            if m is None:
                raise DSLParseError(
                    "constraint must be 'CONSTRAINT <target> IRRELEVANT_WHEN "
                    f"<trigger> = <value>', got: {stripped[:80]!r}"
                )
            raw.append((m.group(1), m.group(2), m.group(3).strip()))
        else:
            body_lines.append(line)
    return "\n".join(body_lines), raw


def _resolve_constraints(
    raw: list[tuple[str, str, str]], choices: list[ChoicePoint]
) -> list[Constraint]:
    """Resolve constraint names to choice indices, validating every reference.

    Unknown target/trigger names or an unknown trigger value raise
    :class:`DSLParseError` — the pipeline feeds that message back to the agent so
    it can correct the constraint, rather than silently dropping the pruning.
    """
    if not raw:
        return []
    by_name: dict[str, list[ChoicePoint]] = {}
    for cp in choices:
        by_name.setdefault(cp.name, []).append(cp)

    def _unique(name: str, role: str) -> ChoicePoint:
        hits = by_name.get(name)
        if not hits:
            raise DSLParseError(
                f"constraint references unknown {role} choice {name!r}; "
                f"known choices: {sorted(by_name)}"
            )
        if len(hits) > 1:
            raise DSLParseError(
                f"constraint {role} {name!r} is ambiguous (appears "
                f"{len(hits)} times); give correlated choices distinct names"
            )
        return hits[0]

    out: list[Constraint] = []
    for target, trigger, value in raw:
        tgt = _unique(target, "target")
        trg = _unique(trigger, "trigger")
        if value not in trg.option_names:
            raise DSLParseError(
                f"constraint trigger value {value!r} is not an option of "
                f"choice {trigger!r}; options: {trg.option_names}"
            )
        out.append(
            Constraint(
                target=target,
                trigger=trigger,
                trigger_value=value,
                target_index=tgt.index,
                trigger_index=trg.index,
                trigger_option_index=trg.option_names.index(value),
            )
        )
    return out


def _validate(choices: list[ChoicePoint]) -> None:
    """Light consistency checks on the parsed choice points."""
    seen: dict[str, int] = {}
    for cp in choices:
        if cp.kind == "term" and not cp.options:
            raise DSLParseError(f"term choice '{cp.name}' has no options")
        if cp.kind == "structural" and not cp.branches:
            raise DSLParseError(f"structural choice '{cp.name}' has no branches")
        if cp.kind == "unspecified" and len(cp.options) != 1:
            raise DSLParseError(
                f"unspecified value '{cp.name}' must have exactly one default"
            )
        # Duplicate names are allowed (different spots), but warn-free here.
        seen[cp.name] = seen.get(cp.name, 0) + 1
