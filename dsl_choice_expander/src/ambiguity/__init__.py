"""Ambiguity-emitting Text-to-SPARQL.

This package implements the two deterministic halves of the ambiguity pipeline:

  * :mod:`src.ambiguity.dsl` parses the CHOICE-DSL that the LLM agent emits
    (an ambiguous query that leaves a hole at every ambiguous spot instead of
    guessing) into an AND-OR tree.
  * :mod:`src.ambiguity.expander` unfolds that tree into the set of unambiguous,
    valid SPARQL queries, executes each against the Ontop endpoint, and returns
    the union of admissible answers.

The division of labour is the whole point: the uncertain part (language ->
schema) is the LLM's job and it makes its uncertainty explicit as choice nodes;
the structural part (producing valid queries and running them) is deterministic
and guaranteed correct, so it needs no LLM.
"""

from src.ambiguity.dsl import (
    AmbiguousQuery,
    ChoicePoint,
    DSLParseError,
    parse_ambiguous_query,
)
from src.ambiguity.expander import (
    AdmissibleAnswers,
    ExecutedExpansion,
    ExpandedQuery,
    ExpansionRun,
    answer_set,
    execute_all,
    expand,
)
from src.ambiguity.feedback import evaluate_ambiguous_query, format_feedback

__all__ = [
    # dsl
    "AmbiguousQuery",
    "ChoicePoint",
    "DSLParseError",
    "parse_ambiguous_query",
    # expander
    "ExpandedQuery",
    "ExecutedExpansion",
    "ExpansionRun",
    "AdmissibleAnswers",
    "expand",
    "execute_all",
    "answer_set",
    # feedback
    "evaluate_ambiguous_query",
    "format_feedback",
]
