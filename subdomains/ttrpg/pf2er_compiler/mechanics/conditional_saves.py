"""Compile annotated Monster Core saving throws without activating runtime.

Monster Core prints a creature's ordinary save modifier and conditional
modifiers in one ``Will`` or ``Fort`` scalar.  This module keeps that source
shape intact: the base save, every ordered conditional clause, the authored
clause separator, modifier type and sign, target text, predicate text, and
predicate conjunctions remain distinct.

The compiler accepts only selections and provider rules revalidated through
one explicit :class:`SourceAuthorityAdapter`.  It is deliberately compile-only
and unregistered.  Predicate matching, modifier stacking, save resolution, and
the interpretation of untyped parenthetical values remain typed runtime
deferrals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal, TypeAlias, final

from .contracts import RawSourceMember, RawSourceObject
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
)
from .source_values import (
    MAX_SOURCE_INTEGER,
    MIN_SOURCE_INTEGER,
    parse_decimal_integer,
)


FAMILY_ID = "conditional-saving-throw-modifiers"
MECHANIC_TYPE = "conditional-saving-throw-modifier"
REGISTRY_STATUS = "compile-only"
MONSTER_CORE_SOURCE_ID = "core-mc1"
PLAYER_CORE_SOURCE_ID = "core-pc1"

MAX_SOURCE_TEXT_BYTES = 512
MAX_PREDICATE_TEXT_BYTES = 256
MAX_CONDITIONAL_CLAUSES = 8
MAX_PREDICATE_TERMS = 8

SaveField: TypeAlias = Literal["Fort", "Will"]
ClauseSeparator: TypeAlias = Literal[
    "parenthetical",
    "semicolon",
    "comma",
]
ModifierKind: TypeAlias = Literal["bonus", "penalty"]
ValueSign: TypeAlias = Literal["positive", "negative"]
ModifierType: TypeAlias = Literal["status", "circumstance"]
TargetPreposition: TypeAlias = Literal["to", "on"]
TargetScope: TypeAlias = Literal[
    "current-save",
    "all-saves",
    "saves",
    "all-defenses",
]
ValueRole: TypeAlias = Literal[
    "modifier",
    "unresolved-parenthetical-value",
]
PredicateSeparator: TypeAlias = Literal[
    "",
    ", ",
    " and ",
    " or ",
    ", and ",
    ", or ",
]
RuntimeMechanic: TypeAlias = Literal[
    "conditional-save-predicate-matching",
    "conditional-save-modifier-stacking",
    "conditional-save-check-resolution",
    "untyped-parenthetical-value-interpretation",
    "all-defenses-target-expansion",
]


class ConditionalSaveCompileError(ValueError):
    """An authenticated source field is outside the reviewed grammar."""


_BASE_RE = re.compile(
    r"^(?P<base>[+-][0-9]+)(?P<suffix>.+)$",
    re.ASCII,
)
_CLAUSE_RE = re.compile(
    r"^(?P<value>[+-][0-9]+)"
    r"(?: (?P<modifier_type>status|circumstance))?"
    r"(?: (?P<penalty_label>penalty))?"
    r"(?: (?P<preposition>to|on) "
    r"(?P<target>all saves|saves|all defenses))?"
    r" vs\. (?P<predicate>.+)$",
    re.ASCII,
)
_NEXT_CLAUSE_RE = re.compile(
    r"(?:; |, )(?=[+-][0-9])",
    re.ASCII,
)
_PREDICATE_SEPARATOR_RE = re.compile(
    r"(, or |, and |, | and | or )",
    re.ASCII,
)
_LOCATOR_RE = re.compile(r"^[1-9][0-9]*\.[1-9][0-9]*$", re.ASCII)
_REVIEWED_CLAUSE_FORMS = frozenset(
    {
        ("semicolon", "status", False, "to", "all saves", "modifier"),
        (
            "parenthetical",
            "status",
            False,
            None,
            None,
            "modifier",
        ),
        (
            "parenthetical",
            None,
            False,
            None,
            None,
            "unresolved-parenthetical-value",
        ),
        (
            "semicolon",
            "circumstance",
            False,
            "to",
            "all saves",
            "modifier",
        ),
        ("semicolon", "status", False, "on", "all saves", "modifier"),
        ("semicolon", "status", False, "to", "saves", "modifier"),
        ("comma", "status", False, "to", "all saves", "modifier"),
        ("semicolon", "status", True, "to", "all saves", "modifier"),
        ("semicolon", None, False, "to", "all saves", "modifier"),
        (
            "semicolon",
            "circumstance",
            False,
            "to",
            "all defenses",
            "modifier",
        ),
        ("comma", "status", False, "to", "saves", "modifier"),
    }
)


# The provider inventory is immutable primitive data.  Every public call
# constructs fresh RuleRequirement values so rebinding or mutating an exported
# requirement cannot change the compiler's trust boundary.
_PROVIDER_SPECS = (
    (
        "player-core-bonuses-and-penalties",
        "10.8",
        "85aa354e605232b91a8e8e3afb7ae93e53c7a281977abeb283b0f3fb80d66a27",
    ),
    (
        "player-core-saving-throw",
        "11.9",
        "aa4805197da891e63a9783feeada0be65ceacd4f751544b4dd6d45ba097b5b47",
    ),
    (
        "player-core-affliction-saving-throw",
        "430.4",
        "9dfb48b64be6588d59a030a6d3eeb9614d19a841e8b0392b2ecd297f6aedd044",
    ),
)


def _exact_text(
    value: object,
    label: str,
    *,
    maximum_bytes: int = MAX_SOURCE_TEXT_BYTES,
    _error: type[ConditionalSaveCompileError] = ConditionalSaveCompileError,
) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or "\x00" in value
        or len(value.encode("utf-8")) > maximum_bytes
    ):
        raise _error(
            f"{label} must be bounded, non-empty, trimmed source text"
        )
    return value


def _exact_integer(
    value: object,
    label: str,
    *,
    _minimum: int = MIN_SOURCE_INTEGER,
    _maximum: int = MAX_SOURCE_INTEGER,
    _error: type[ConditionalSaveCompileError] = ConditionalSaveCompileError,
) -> int:
    if (
        type(value) is not int
        or value < _minimum
        or value > _maximum
    ):
        raise _error(
            f"{label} must be a bounded source integer"
        )
    return value


def _fresh_provider_requirements(
    specs: tuple[tuple[str, str, str], ...],
    *,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _source_id: str = PLAYER_CORE_SOURCE_ID,
) -> tuple[RuleRequirement, ...]:
    return tuple(
        _requirement_type(
            rule_id=rule_id,
            source_id=_source_id,
            locator=locator,
            expected_block_sha256=expected_sha256,
            expected_value_sha256=expected_sha256,
            expected_selection_sha256=expected_sha256,
        )
        for rule_id, locator, expected_sha256 in specs
    )


def _same_requirement(
    left: RuleRequirement,
    right: RuleRequirement,
    *,
    canonical_json: Any = canonical_json_bytes,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _serialize: Any = RuleRequirement.as_serialized,
) -> bool:
    if (
        type(left) is not _requirement_type
        or type(right) is not _requirement_type
    ):
        return False
    return canonical_json(
        _serialize(left)
    ) == canonical_json(_serialize(right))


def _uncopyable(label: str) -> TypeError:
    return TypeError(f"{label} cannot be copied or pickled")


@final
@dataclass(frozen=True, slots=True)
class PredicateTerm:
    """One ordered predicate term and its exact preceding conjunction."""

    ordinal: int
    text: str
    separator_before: PredicateSeparator

    def __post_init__(
        self,
        _exact_text_value: Any = _exact_text,
    ) -> None:
        if (
            type(self.ordinal) is not int
            or self.ordinal < 0
            or self.ordinal >= 8
        ):
            raise ConditionalSaveCompileError(
                "PredicateTerm.ordinal is invalid"
            )
        _exact_text_value(
            self.text,
            "PredicateTerm.text",
            maximum_bytes=256,
        )
        if (
            type(self.separator_before) is not str
            or self.separator_before
            not in ("", ", ", " and ", " or ", ", and ", ", or ")
            or (self.ordinal == 0) != (self.separator_before == "")
        ):
            raise ConditionalSaveCompileError(
                "PredicateTerm separator/order is invalid"
            )

    def as_serialized(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "text": self.text,
            "separatorBefore": self.separator_before,
        }

    def __copy__(self) -> PredicateTerm:
        raise _uncopyable("PredicateTerm")

    def __deepcopy__(self, _memo: dict[int, object]) -> PredicateTerm:
        raise _uncopyable("PredicateTerm")

    def __reduce__(self) -> object:
        raise _uncopyable("PredicateTerm")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise _uncopyable("PredicateTerm")


@final
@dataclass(frozen=True, slots=True)
class ConditionalSaveClause:
    """One conditional modifier clause in exact source order."""

    ordinal: int
    separator: ClauseSeparator
    separator_text: str
    closing_text: str
    source_text: str
    signed_value_source: str
    signed_value: int
    value_sign: ValueSign
    modifier_kind: ModifierKind | None
    modifier_type: ModifierType | None
    explicit_penalty_label: bool
    target_preposition: TargetPreposition | None
    target_text: str | None
    target_scope: TargetScope
    predicate_text: str
    predicate_terms: tuple[PredicateTerm, ...]
    value_role: ValueRole

    def __post_init__(
        self,
        _parse_integer: Any = parse_decimal_integer,
        _exact_text_value: Any = _exact_text,
        _exact_integer_value: Any = _exact_integer,
        _predicate_type: type[PredicateTerm] = PredicateTerm,
    ) -> None:
        if (
            type(self.ordinal) is not int
            or self.ordinal < 0
            or self.ordinal >= 8
        ):
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause.ordinal is invalid"
            )
        if (
            type(self.separator) is not str
            or self.separator
            not in ("parenthetical", "semicolon", "comma")
        ):
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause.separator is invalid"
            )
        expected_delimiters = {
            "parenthetical": (" (", ")"),
            "semicolon": ("; ", ""),
            "comma": (", ", ""),
        }[self.separator]
        if (
            type(self.separator_text) is not str
            or type(self.closing_text) is not str
            or (self.separator_text, self.closing_text)
            != expected_delimiters
        ):
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause delimiters are invalid"
            )
        _exact_text_value(
            self.source_text,
            "ConditionalSaveClause.source_text",
        )
        _exact_text_value(
            self.signed_value_source,
            "ConditionalSaveClause.signed_value_source",
        )
        parsed_value = _parse_integer(self.signed_value_source)
        if parsed_value is None or parsed_value != self.signed_value:
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause signed value is inconsistent"
            )
        _exact_integer_value(
            self.signed_value,
            "ConditionalSaveClause.signed_value",
        )
        expected_sign = (
            "negative"
            if self.signed_value_source.startswith("-")
            else "positive"
        )
        if (
            type(self.value_sign) is not str
            or self.value_sign != expected_sign
        ):
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause value sign is inconsistent"
            )
        expected_role = (
            "unresolved-parenthetical-value"
            if (
                self.separator == "parenthetical"
                and self.modifier_type is None
                and self.target_text is None
            )
            else "modifier"
        )
        expected_kind = (
            None
            if expected_role == "unresolved-parenthetical-value"
            else ("penalty" if expected_sign == "negative" else "bonus")
        )
        if (
            (
                self.modifier_kind is not None
                and type(self.modifier_kind) is not str
            )
            or self.modifier_kind != expected_kind
            or type(self.explicit_penalty_label) is not bool
            or (
                self.explicit_penalty_label
                and self.modifier_kind != "penalty"
            )
        ):
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause modifier sign/kind is inconsistent"
            )
        if self.modifier_type is not None and (
            type(self.modifier_type) is not str
            or self.modifier_type not in ("status", "circumstance")
        ):
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause.modifier_type is invalid"
            )
        if (self.target_preposition is None) != (self.target_text is None):
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause target fields are incomplete"
            )
        if self.target_preposition is not None and (
            type(self.target_preposition) is not str
            or self.target_preposition not in ("to", "on")
        ):
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause.target_preposition is invalid"
            )
        expected_scope = {
            None: "current-save",
            "all saves": "all-saves",
            "saves": "saves",
            "all defenses": "all-defenses",
        }.get(self.target_text)
        if (
            expected_scope is None
            or type(self.target_scope) is not str
            or self.target_scope != expected_scope
        ):
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause target scope is inconsistent"
            )
        _exact_text_value(
            self.predicate_text,
            "ConditionalSaveClause.predicate_text",
            maximum_bytes=256,
        )
        if (
            type(self.predicate_terms) is not tuple
            or not self.predicate_terms
            or len(self.predicate_terms) > 8
            or any(
                type(item) is not _predicate_type
                for item in self.predicate_terms
            )
            or tuple(item.ordinal for item in self.predicate_terms)
            != tuple(range(len(self.predicate_terms)))
            or "".join(
                f"{item.separator_before}{item.text}"
                for item in self.predicate_terms
            )
            != self.predicate_text
        ):
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause predicate order is invalid"
        )
        for item in self.predicate_terms:
            _predicate_type.__post_init__(item)
        if (
            type(self.value_role) is not str
            or self.value_role != expected_role
        ):
            raise ConditionalSaveCompileError(
                "ConditionalSaveClause.value_role is inconsistent"
            )

    def as_serialized(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "separator": self.separator,
            "separatorText": self.separator_text,
            "closingText": self.closing_text,
            "sourceText": self.source_text,
            "signedValueSource": self.signed_value_source,
            "signedValue": self.signed_value,
            "valueSign": self.value_sign,
            "modifierKind": self.modifier_kind,
            "modifierType": self.modifier_type,
            "explicitPenaltyLabel": self.explicit_penalty_label,
            "targetPreposition": self.target_preposition,
            "targetText": self.target_text,
            "targetScope": self.target_scope,
            "predicateText": self.predicate_text,
            "predicateTerms": [
                item.as_serialized() for item in self.predicate_terms
            ],
            "valueRole": self.value_role,
        }

    def __copy__(self) -> ConditionalSaveClause:
        raise _uncopyable("ConditionalSaveClause")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> ConditionalSaveClause:
        raise _uncopyable("ConditionalSaveClause")

    def __reduce__(self) -> object:
        raise _uncopyable("ConditionalSaveClause")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise _uncopyable("ConditionalSaveClause")


@final
@dataclass(frozen=True, slots=True)
class ConditionalSaveRuntimeDeferral:
    """One explicit runtime contract still required by this family."""

    deferral_id: str
    mechanic: RuntimeMechanic
    required_contract: str

    def __post_init__(
        self,
        _exact_text_value: Any = _exact_text,
    ) -> None:
        _exact_text_value(
            self.deferral_id,
            "ConditionalSaveRuntimeDeferral.deferral_id",
        )
        if (
            type(self.mechanic) is not str
            or self.mechanic
            not in (
                "conditional-save-predicate-matching",
                "conditional-save-modifier-stacking",
                "conditional-save-check-resolution",
                "untyped-parenthetical-value-interpretation",
                "all-defenses-target-expansion",
            )
        ):
            raise ConditionalSaveCompileError(
                "ConditionalSaveRuntimeDeferral.mechanic is invalid"
            )
        _exact_text_value(
            self.required_contract,
            "ConditionalSaveRuntimeDeferral.required_contract",
        )

    def as_serialized(self) -> dict[str, str]:
        return {
            "id": self.deferral_id,
            "phase": "runtime",
            "mechanic": self.mechanic,
            "requiredContract": self.required_contract,
            "status": "deferred",
            "blocks": "registry-activation",
        }

    def __copy__(self) -> ConditionalSaveRuntimeDeferral:
        raise _uncopyable("ConditionalSaveRuntimeDeferral")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> ConditionalSaveRuntimeDeferral:
        raise _uncopyable("ConditionalSaveRuntimeDeferral")

    def __reduce__(self) -> object:
        raise _uncopyable("ConditionalSaveRuntimeDeferral")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise _uncopyable("ConditionalSaveRuntimeDeferral")


@final
@dataclass(frozen=True, slots=True)
class CompiledConditionalSave:
    """Canonical compile-only projection of one authenticated save field."""

    source_id: str
    locator: str
    section_id: str
    creature_name: str
    field_name: SaveField
    source_text: str
    base_source_text: str
    base_save: int
    clauses: tuple[ConditionalSaveClause, ...]
    consumer: VerifiedSourceSelection = field(repr=False, compare=False)
    provider_rules: tuple[VerifiedRuleReceipt, ...] = field(
        repr=False,
        compare=False,
    )
    runtime_deferrals: tuple[ConditionalSaveRuntimeDeferral, ...]

    def __post_init__(
        self,
        _parse_integer: Any = parse_decimal_integer,
        _exact_text_value: Any = _exact_text,
        _exact_integer_value: Any = _exact_integer,
        _selection_type: type[VerifiedSourceSelection] = (
            VerifiedSourceSelection
        ),
        _rule_type: type[VerifiedRuleReceipt] = VerifiedRuleReceipt,
        _clause_type: type[ConditionalSaveClause] = ConditionalSaveClause,
        _deferral_type: type[ConditionalSaveRuntimeDeferral] = (
            ConditionalSaveRuntimeDeferral
        ),
        _locator_re: re.Pattern[str] = _LOCATOR_RE,
    ) -> None:
        if type(self.source_id) is not str or self.source_id != "core-mc1":
            raise ConditionalSaveCompileError(
                "CompiledConditionalSave.source_id is invalid"
            )
        if (
            type(self.locator) is not str
            or _locator_re.fullmatch(self.locator) is None
            or type(self.section_id) is not str
            or not self.section_id.startswith("core-mc1:")
        ):
            raise ConditionalSaveCompileError(
                "CompiledConditionalSave source address is invalid"
            )
        _exact_text_value(
            self.creature_name,
            "CompiledConditionalSave.creature_name",
        )
        if (
            type(self.field_name) is not str
            or self.field_name not in ("Fort", "Will")
        ):
            raise ConditionalSaveCompileError(
                "CompiledConditionalSave.field_name is invalid"
            )
        _exact_text_value(
            self.source_text,
            "CompiledConditionalSave.source_text",
        )
        _exact_text_value(
            self.base_source_text,
            "CompiledConditionalSave.base_source_text",
        )
        parsed_base = _parse_integer(self.base_source_text)
        if parsed_base is None or parsed_base != self.base_save:
            raise ConditionalSaveCompileError(
                "CompiledConditionalSave base value is inconsistent"
            )
        _exact_integer_value(
            self.base_save,
            "CompiledConditionalSave.base_save",
        )
        if (
            type(self.clauses) is not tuple
            or not self.clauses
            or len(self.clauses) > 8
            or any(
                type(item) is not _clause_type
                for item in self.clauses
            )
            or tuple(item.ordinal for item in self.clauses)
            != tuple(range(len(self.clauses)))
            or (
                self.base_source_text
                + "".join(
                    f"{item.separator_text}{item.source_text}{item.closing_text}"
                    for item in self.clauses
                )
                != self.source_text
            )
        ):
            raise ConditionalSaveCompileError(
                "CompiledConditionalSave clauses are invalid"
        )
        for item in self.clauses:
            _clause_type.__post_init__(item)
        if type(self.consumer) is not _selection_type:
            raise TypeError(
                "CompiledConditionalSave.consumer must be an exact "
                "VerifiedSourceSelection"
            )
        if (
            self.source_id != self.consumer.address.source_id
            or self.locator != self.consumer.address.locator
            or self.section_id != self.consumer.address.section_id
        ):
            raise ConditionalSaveCompileError(
                "CompiledConditionalSave address disagrees with its consumer"
            )
        if (
            type(self.provider_rules) is not tuple
            or len(self.provider_rules) != 3
            or any(
                type(item) is not _rule_type
                for item in self.provider_rules
            )
        ):
            raise TypeError(
                "CompiledConditionalSave.provider_rules are invalid"
            )
        if (
            type(self.runtime_deferrals) is not tuple
            or len(self.runtime_deferrals) < 3
            or any(
                type(item) is not _deferral_type
                for item in self.runtime_deferrals
            )
            or len(
                {
                    item.deferral_id for item in self.runtime_deferrals
                }
            )
            != len(self.runtime_deferrals)
        ):
            raise TypeError(
                "CompiledConditionalSave.runtime_deferrals are invalid"
        )
        for item in self.runtime_deferrals:
            _deferral_type.__post_init__(item)

    def as_serialized(
        self,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        raise TypeError("compiled conditional-save contract is not bound")

    def __copy__(self) -> CompiledConditionalSave:
        raise _uncopyable("CompiledConditionalSave")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> CompiledConditionalSave:
        raise _uncopyable("CompiledConditionalSave")

    def __reduce__(self) -> object:
        raise _uncopyable("CompiledConditionalSave")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise _uncopyable("CompiledConditionalSave")


def _bind_exact_post_init(
    contract_type: type[Any],
    label: str,
) -> None:
    """Freeze exact-class validation outside rebindable module globals."""

    implementation = contract_type.__post_init__

    def exact_post_init(self: object, *args: object, **kwargs: object) -> None:
        if type(self) is not contract_type:
            raise TypeError(f"{label} subclasses are unsupported")
        implementation(self, *args, **kwargs)

    contract_type.__post_init__ = exact_post_init


def _bind_exact_serializer(contract_type: type[Any]) -> None:
    implementation = contract_type.as_serialized
    validator = contract_type.__post_init__

    def exact_as_serialized(
        self: object,
        *args: object,
        **kwargs: object,
    ) -> Any:
        validator(self)
        return implementation(self, *args, **kwargs)

    contract_type.as_serialized = exact_as_serialized


_bind_exact_post_init(PredicateTerm, "PredicateTerm")
_bind_exact_post_init(ConditionalSaveClause, "ConditionalSaveClause")
_bind_exact_post_init(
    ConditionalSaveRuntimeDeferral,
    "ConditionalSaveRuntimeDeferral",
)
_bind_exact_post_init(CompiledConditionalSave, "CompiledConditionalSave")
_bind_exact_serializer(PredicateTerm)
_bind_exact_serializer(ConditionalSaveClause)
_bind_exact_serializer(ConditionalSaveRuntimeDeferral)


def _predicate_terms(
    predicate_text: str,
    *,
    separator_re: re.Pattern[str] = _PREDICATE_SEPARATOR_RE,
    _term_type: type[PredicateTerm] = PredicateTerm,
    _exact_text_value: Any = _exact_text,
    _error: type[ConditionalSaveCompileError] = ConditionalSaveCompileError,
) -> tuple[PredicateTerm, ...]:
    parts = separator_re.split(predicate_text)
    if not parts or len(parts) % 2 == 0:
        raise _error(
            "conditional save predicate conjunctions are malformed"
        )
    result: list[PredicateTerm] = []
    for index in range(0, len(parts), 2):
        text = _exact_text_value(
            parts[index],
            "conditional save predicate term",
            maximum_bytes=256,
        )
        separator = "" if index == 0 else parts[index - 1]
        result.append(
            _term_type(
                ordinal=len(result),
                text=text,
                separator_before=separator,  # type: ignore[arg-type]
            )
        )
    if len(result) > 8:
        raise _error(
            "conditional save predicate has too many terms"
        )
    return tuple(result)


def _split_clause_sources(
    suffix: str,
    *,
    next_clause_re: re.Pattern[str] = _NEXT_CLAUSE_RE,
    _error: type[ConditionalSaveCompileError] = ConditionalSaveCompileError,
) -> tuple[tuple[ClauseSeparator, str, str, str], ...]:
    result: list[tuple[ClauseSeparator, str, str, str]] = []
    remaining = suffix
    while remaining:
        if len(result) >= 8:
            raise _error(
                "conditional save has too many clauses"
            )
        if remaining.startswith(" ("):
            close = remaining.find(")", 2)
            if close < 0 or "(" in remaining[2:close]:
                raise _error(
                    "conditional save parenthetical is malformed"
                )
            body = remaining[2:close]
            result.append(("parenthetical", " (", ")", body))
            remaining = remaining[close + 1 :]
            continue
        if remaining.startswith("; "):
            separator: ClauseSeparator = "semicolon"
            separator_text = "; "
        elif remaining.startswith(", "):
            separator = "comma"
            separator_text = ", "
        else:
            raise _error(
                "conditional save clause separator is not understood"
            )
        remaining = remaining[2:]
        next_match = next_clause_re.search(remaining)
        end = len(remaining) if next_match is None else next_match.start()
        body = remaining[:end]
        if not body:
            raise _error(
                "conditional save clause is empty"
            )
        result.append((separator, separator_text, "", body))
        remaining = remaining[end:]
    if not result:
        raise _error(
            "conditional save has no conditional clause"
        )
    return tuple(result)


def _parse_clause(
    *,
    ordinal: int,
    separator: ClauseSeparator,
    separator_text: str,
    closing_text: str,
    source_text: str,
    clause_re: re.Pattern[str] = _CLAUSE_RE,
    parse_integer: Any = parse_decimal_integer,
    _exact_text_value: Any = _exact_text,
    _predicate_terms_value: Any = _predicate_terms,
    _clause_type: type[ConditionalSaveClause] = ConditionalSaveClause,
    _reviewed_forms: frozenset[tuple[object, ...]] = (
        _REVIEWED_CLAUSE_FORMS
    ),
    _error: type[ConditionalSaveCompileError] = ConditionalSaveCompileError,
) -> ConditionalSaveClause:
    match = clause_re.fullmatch(source_text)
    if match is None:
        raise _error(
            "conditional save clause is not understood"
        )
    signed_source = match.group("value")
    signed_value = parse_integer(signed_source)
    if signed_value is None:
        raise _error(
            "conditional save clause value is not a bounded integer"
        )
    modifier_type = match.group("modifier_type")
    explicit_penalty = match.group("penalty_label") is not None
    value_sign: ValueSign = (
        "negative" if signed_source.startswith("-") else "positive"
    )
    if explicit_penalty and value_sign != "negative":
        raise _error(
            "conditional save penalty label requires a negative value"
        )
    preposition = match.group("preposition")
    target = match.group("target")
    predicate = _exact_text_value(
        match.group("predicate"),
        "conditional save predicate",
        maximum_bytes=256,
    )
    target_scope: TargetScope = {
        None: "current-save",
        "all saves": "all-saves",
        "saves": "saves",
        "all defenses": "all-defenses",
    }[target]
    value_role: ValueRole = (
        "unresolved-parenthetical-value"
        if (
            separator == "parenthetical"
            and modifier_type is None
            and target is None
        )
        else "modifier"
    )
    source_form = (
        separator,
        modifier_type,
        explicit_penalty,
        preposition,
        target,
        value_role,
    )
    if source_form not in _reviewed_forms:
        raise _error(
            "conditional save clause form is outside the reviewed corpus"
        )
    return _clause_type(
        ordinal=ordinal,
        separator=separator,
        separator_text=separator_text,
        closing_text=closing_text,
        source_text=source_text,
        signed_value_source=signed_source,
        signed_value=signed_value,
        value_sign=value_sign,
        modifier_kind=(
            None
            if value_role == "unresolved-parenthetical-value"
            else ("penalty" if value_sign == "negative" else "bonus")
        ),
        modifier_type=modifier_type,  # type: ignore[arg-type]
        explicit_penalty_label=explicit_penalty,
        target_preposition=preposition,  # type: ignore[arg-type]
        target_text=target,
        target_scope=target_scope,
        predicate_text=predicate,
        predicate_terms=_predicate_terms_value(predicate),
        value_role=value_role,
    )


def _parse_conditional_source(
    source_text: str,
    *,
    base_re: re.Pattern[str] = _BASE_RE,
    parse_integer: Any = parse_decimal_integer,
    _exact_text_value: Any = _exact_text,
    _split_clause_sources_value: Any = _split_clause_sources,
    _parse_clause_value: Any = _parse_clause,
    _error: type[ConditionalSaveCompileError] = ConditionalSaveCompileError,
) -> tuple[str, int, tuple[ConditionalSaveClause, ...]]:
    _exact_text_value(source_text, "conditional save source text")
    match = base_re.fullmatch(source_text)
    if match is None:
        raise _error(
            "conditional save source grammar is not understood"
        )
    base_source = match.group("base")
    base_value = parse_integer(base_source)
    if base_value is None:
        raise _error(
            "conditional save base value is not a bounded integer"
        )
    clauses = tuple(
        _parse_clause_value(
            ordinal=ordinal,
            separator=separator,
            separator_text=separator_text,
            closing_text=closing_text,
            source_text=clause_source,
        )
        for ordinal, (
            separator,
            separator_text,
            closing_text,
            clause_source,
        ) in enumerate(
            _split_clause_sources_value(match.group("suffix"))
        )
    )
    return base_source, base_value, clauses


def _validated_consumer_shape(
    selection: VerifiedSourceSelection,
    *,
    _selection_type: type[VerifiedSourceSelection] = (
        VerifiedSourceSelection
    ),
    _member_step_type: type[RawMemberStep] = RawMemberStep,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _exact_text_value: Any = _exact_text,
    _error: type[ConditionalSaveCompileError] = ConditionalSaveCompileError,
) -> tuple[str, SaveField, str]:
    if type(selection) is not _selection_type:
        raise TypeError(
            "conditional save consumer must be a VerifiedSourceSelection"
        )
    address = selection.address
    if (
        address.source_id != "core-mc1"
        or address.span is not None
        or not address.carrier_path
        or type(address.carrier_path[-1]) is not _member_step_type
        or address.carrier_path[-1].raw_key != "^.creature"
        or type(address.selection_path) is not tuple
        or len(address.selection_path) != 1
        or type(address.selection_path[0]) is not _member_step_type
    ):
        raise _error(
            "conditional save consumer is not a direct creature save field"
        )
    step = address.selection_path[0]
    if step.raw_key not in ("Fort", "Will"):
        raise _error(
            "conditional save consumer field must be Fort or Will"
        )
    if (
        type(selection.raw_member) is not _member_type
        or selection.raw_member.key != step.raw_key
        or type(selection.raw_value) is not str
        or type(selection.selected_value) is not str
        or selection.raw_value != selection.selected_value
        or selection.raw_member.value != selection.raw_value
    ):
        raise _error(
            "conditional save consumer selection is inconsistent"
        )
    block = selection.carrier.raw_block
    if type(block) is not _object_type or type(block.members) is not tuple:
        raise _error(
            "conditional save creature carrier is invalid"
        )
    if (
        step.member_ordinal >= len(block.members)
        or block.members[step.member_ordinal] != selection.raw_member
    ):
        raise _error(
            "conditional save member ordinal is inconsistent"
        )
    names = tuple(
        member.value for member in block.members if member.key == "Name"
    )
    fields = tuple(
        member
        for member in block.members
        if member.key == step.raw_key
    )
    if len(names) != 1 or len(fields) != 1:
        raise _error(
            "conditional save creature identity or field is ambiguous"
        )
    creature_name = _exact_text_value(
        names[0],
        "conditional save creature name",
    )
    source_text = _exact_text_value(
        selection.raw_value,
        "conditional save source text",
    )
    return creature_name, step.raw_key, source_text  # type: ignore[return-value]


def _runtime_deferrals(
    clauses: tuple[ConditionalSaveClause, ...],
    *,
    _deferral_type: type[ConditionalSaveRuntimeDeferral] = (
        ConditionalSaveRuntimeDeferral
    ),
) -> tuple[ConditionalSaveRuntimeDeferral, ...]:
    result = [
        _deferral_type(
            deferral_id="predicate-matching",
            mechanic="conditional-save-predicate-matching",
            required_contract=(
                "match each ordered source predicate against the complete "
                "traits, effects, sources, and check context"
            ),
        ),
        _deferral_type(
            deferral_id="modifier-stacking",
            mechanic="conditional-save-modifier-stacking",
            required_contract=(
                "apply circumstance, status, and untyped modifiers using "
                "Player Core stacking and suppression rules"
            ),
        ),
        _deferral_type(
            deferral_id="save-check-resolution",
            mechanic="conditional-save-check-resolution",
            required_contract=(
                "select applicable clauses and resolve the saving throw "
                "without altering the stored base modifier"
            ),
        ),
    ]
    if any(
        item.value_role == "unresolved-parenthetical-value"
        for item in clauses
    ):
        result.append(
            _deferral_type(
                deferral_id="untyped-parenthetical-value",
                mechanic="untyped-parenthetical-value-interpretation",
                required_contract=(
                    "resolve whether an untyped parenthetical signed value is "
                    "a conditional total or a modifier from reviewed rules"
                ),
            )
        )
    if any(item.target_scope == "all-defenses" for item in clauses):
        result.append(
            _deferral_type(
                deferral_id="all-defenses-target",
                mechanic="all-defenses-target-expansion",
                required_contract=(
                    "expand all defenses to its exact save, AC, and DC "
                    "consumers before modifier stacking"
                ),
            )
        )
    return tuple(result)


def _verified_provider_rules(
    authority: SourceAuthorityAdapter,
    consumer: VerifiedSourceSelection,
    providers: tuple[VerifiedRuleReceipt, ...],
    *,
    specs: tuple[tuple[str, str, str], ...],
    validate_rule: Any,
    require_shared_authority: Any,
    _rule_type: type[VerifiedRuleReceipt] = VerifiedRuleReceipt,
    _fresh_requirements: Any = _fresh_provider_requirements,
    _requirements_equal: Any = _same_requirement,
    _error: type[ConditionalSaveCompileError] = ConditionalSaveCompileError,
) -> tuple[VerifiedRuleReceipt, ...]:
    if (
        type(providers) is not tuple
        or len(providers) != len(specs)
        or any(type(item) is not _rule_type for item in providers)
    ):
        raise TypeError(
            "conditional save providers must be one exact ordered tuple"
        )
    expected = _fresh_requirements(specs)
    verified: list[VerifiedRuleReceipt] = []
    for actual, requirement in zip(providers, expected, strict=True):
        rule = validate_rule(authority, actual)
        if (
            rule.rule_id != requirement.rule_id
            or not _requirements_equal(rule.requirement, requirement)
        ):
            raise _error(
                "conditional save provider order or requirement is invalid"
            )
        verified.append(rule)
    result = tuple(verified)
    require_shared_authority(authority, consumer, result)
    return result


def _canonical_compiled(
    authority: SourceAuthorityAdapter,
    consumer: VerifiedSourceSelection,
    providers: tuple[VerifiedRuleReceipt, ...],
    *,
    specs: tuple[tuple[str, str, str], ...],
    validate_selection: Any,
    validate_rule: Any,
    require_shared_authority: Any,
    parse_source: Any,
    _authority_type: type[SourceAuthorityAdapter] = (
        SourceAuthorityAdapter
    ),
    _consumer_shape: Any = _validated_consumer_shape,
    _provider_rules: Any = _verified_provider_rules,
    _compiled_type: type[CompiledConditionalSave] = (
        CompiledConditionalSave
    ),
    _deferrals: Any = _runtime_deferrals,
) -> CompiledConditionalSave:
    if type(authority) is not _authority_type:
        raise TypeError(
            "conditional save compilation requires SourceAuthorityAdapter"
        )
    verified_consumer = validate_selection(authority, consumer)
    creature_name, field_name, source_text = _consumer_shape(
        verified_consumer
    )
    base_source, base_save, clauses = parse_source(source_text)
    verified_providers = _provider_rules(
        authority,
        verified_consumer,
        providers,
        specs=specs,
        validate_rule=validate_rule,
        require_shared_authority=require_shared_authority,
    )
    return _compiled_type(
        source_id=verified_consumer.address.source_id,
        locator=verified_consumer.address.locator,
        section_id=verified_consumer.address.section_id,
        creature_name=creature_name,
        field_name=field_name,
        source_text=source_text,
        base_source_text=base_source,
        base_save=base_save,
        clauses=clauses,
        consumer=verified_consumer,
        provider_rules=verified_providers,
        runtime_deferrals=_deferrals(clauses),
    )


def _rule_payload(
    rule: VerifiedRuleReceipt,
    *,
    _serialize_requirement: Any = RuleRequirement.as_serialized,
    _serialize_receipt: Any = SourceReceipt.as_serialized,
) -> dict[str, Any]:
    return {
        "ruleId": rule.rule_id,
        "requirement": _serialize_requirement(rule.requirement),
        "source": _serialize_receipt(rule.receipt),
    }


def _compiled_payload(
    value: CompiledConditionalSave,
    *,
    _serialize_receipt: Any = SourceReceipt.as_serialized,
    _serialize_clause: Any = ConditionalSaveClause.as_serialized,
    _serialize_rule: Any = _rule_payload,
    _serialize_deferral: Any = (
        ConditionalSaveRuntimeDeferral.as_serialized
    ),
) -> dict[str, Any]:
    return {
        "family": "conditional-saving-throw-modifiers",
        "mechanicType": "conditional-saving-throw-modifier",
        "source": _serialize_receipt(value.consumer.receipt),
        "creatureName": value.creature_name,
        "field": value.field_name,
        "sourceText": value.source_text,
        "baseSave": {
            "sourceText": value.base_source_text,
            "value": value.base_save,
        },
        "conditionalClauses": [
            _serialize_clause(item) for item in value.clauses
        ],
        "providerRules": [
            _serialize_rule(item) for item in value.provider_rules
        ],
        "runtimeDeferrals": [
            _serialize_deferral(item) for item in value.runtime_deferrals
        ],
        "registryStatus": "compile-only",
        "runtimeReady": False,
    }


def _validate_compiled(
    authority: SourceAuthorityAdapter,
    value: CompiledConditionalSave,
    *,
    specs: tuple[tuple[str, str, str], ...],
    validate_selection: Any,
    validate_rule: Any,
    require_shared_authority: Any,
    parse_source: Any,
    canonical_json: Any,
    _authority_type: type[SourceAuthorityAdapter] = (
        SourceAuthorityAdapter
    ),
    _compiled_type: type[CompiledConditionalSave] = (
        CompiledConditionalSave
    ),
    _provider_rules: Any = _verified_provider_rules,
    _canonical_compiled_value: Any = _canonical_compiled,
    _payload: Any = _compiled_payload,
    _error: type[ConditionalSaveCompileError] = ConditionalSaveCompileError,
) -> CompiledConditionalSave:
    if type(authority) is not _authority_type:
        raise TypeError(
            "compiled conditional save requires SourceAuthorityAdapter"
        )
    if type(value) is not _compiled_type:
        raise TypeError(
            "compiled conditional save must be CompiledConditionalSave"
        )
    _compiled_type.__post_init__(value)
    verified_consumer = validate_selection(authority, value.consumer)
    verified_providers = _provider_rules(
        authority,
        verified_consumer,
        value.provider_rules,
        specs=specs,
        validate_rule=validate_rule,
        require_shared_authority=require_shared_authority,
    )
    canonical = _canonical_compiled_value(
        authority,
        verified_consumer,
        verified_providers,
        specs=specs,
        validate_selection=validate_selection,
        validate_rule=validate_rule,
        require_shared_authority=require_shared_authority,
        parse_source=parse_source,
    )
    supplied_payload = _payload(value)
    canonical_payload = _payload(canonical)
    if canonical_json(supplied_payload) != canonical_json(canonical_payload):
        raise _error(
            "compiled conditional save differs from canonical source derivation"
        )
    return value


def _bind_public_api(
    provider_specs: tuple[tuple[str, str, str], ...],
) -> tuple[Any, Any, Any, Any]:
    """Bind trust hooks and reviewed providers outside rebindable globals."""

    validate_selection = SourceAuthorityAdapter.validate_selection
    validate_rule = SourceAuthorityAdapter.validate_rule
    require_shared_authority = SourceAuthorityAdapter.require_shared_authority
    parse_source = _parse_conditional_source
    canonical_json = canonical_json_bytes
    canonical_compiled = _canonical_compiled
    validate_compiled = _validate_compiled
    payload = _compiled_payload
    fresh_requirements = _fresh_provider_requirements

    def conditional_save_provider_requirements(
    ) -> tuple[RuleRequirement, ...]:
        """Return fresh reviewed Player Core provider requirements."""

        return fresh_requirements(provider_specs)

    def compile_conditional_save(
        authority: SourceAuthorityAdapter,
        consumer: VerifiedSourceSelection,
        providers: tuple[VerifiedRuleReceipt, ...],
    ) -> CompiledConditionalSave:
        """Compile one exact authenticated annotated Fort or Will field."""

        result = canonical_compiled(
            authority,
            consumer,
            providers,
            specs=provider_specs,
            validate_selection=validate_selection,
            validate_rule=validate_rule,
            require_shared_authority=require_shared_authority,
            parse_source=parse_source,
        )
        return validate_compiled(
            authority,
            result,
            specs=provider_specs,
            validate_selection=validate_selection,
            validate_rule=validate_rule,
            require_shared_authority=require_shared_authority,
            parse_source=parse_source,
            canonical_json=canonical_json,
        )

    def validate_compiled_conditional_save(
        authority: SourceAuthorityAdapter,
        value: CompiledConditionalSave,
    ) -> CompiledConditionalSave:
        """Revalidate authority and rederive every canonical public field."""

        return validate_compiled(
            authority,
            value,
            specs=provider_specs,
            validate_selection=validate_selection,
            validate_rule=validate_rule,
            require_shared_authority=require_shared_authority,
            parse_source=parse_source,
            canonical_json=canonical_json,
        )

    def compiled_as_serialized(
        value: CompiledConditionalSave,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        validate_compiled_conditional_save(authority, value)
        result = payload(value)
        canonical_json(result)
        return result

    return (
        conditional_save_provider_requirements,
        compile_conditional_save,
        validate_compiled_conditional_save,
        compiled_as_serialized,
    )


(
    conditional_save_provider_requirements,
    compile_conditional_save,
    validate_compiled_conditional_save,
    _compiled_as_serialized,
) = _bind_public_api(_PROVIDER_SPECS)
CompiledConditionalSave.as_serialized = _compiled_as_serialized


__all__ = [
    "CompiledConditionalSave",
    "ConditionalSaveClause",
    "ConditionalSaveCompileError",
    "ConditionalSaveRuntimeDeferral",
    "FAMILY_ID",
    "MAX_CONDITIONAL_CLAUSES",
    "MAX_PREDICATE_TERMS",
    "MAX_PREDICATE_TEXT_BYTES",
    "MAX_SOURCE_TEXT_BYTES",
    "MECHANIC_TYPE",
    "MONSTER_CORE_SOURCE_ID",
    "PLAYER_CORE_SOURCE_ID",
    "PredicateTerm",
    "REGISTRY_STATUS",
    "compile_conditional_save",
    "conditional_save_provider_requirements",
    "validate_compiled_conditional_save",
]
