"""Compile lossless annotated Core MC1 HP and AC source fields.

The Monster Core stat block grammar stores ordinary HP and AC as decimal
strings.  A bounded minority append source-significant annotations such as
shield-raised alternatives, object Hardness, conditional defenses, healing
abilities, and bespoke named abilities.  Those annotations are not flavor
text: flattening them to one integer would silently discard rules.

This module preserves the exact field, base-number span, annotation span, and
ordered duplicate-preserving fragments.  It classifies only a small reviewed
set of common shapes and emits typed runtime deferrals.  Nothing here is
registered or executable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Literal, Mapping, TypeAlias, final

from .contracts import RawSourceMember, RawSourceObject
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    TextSpan,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    VerifiedSourceSelection,
)


FAMILY_ID = "annotated-stats"
MECHANIC_TYPE = "annotated-stat"
MONSTER_CORE_SOURCE_ID = "core-mc1"
MAX_STAT_VALUE = 10_000
MAX_STAT_SOURCE_BYTES = 1_024
MAX_ANNOTATION_FRAGMENTS = 32

StatField: TypeAlias = Literal["HP", "AC"]
RuntimeDeferralKind: TypeAlias = Literal[
    "shield",
    "conditional",
    "threshold",
    "recovery",
    "other",
]

_FIELDS = ("HP", "AC")
_LOCATOR_RE = re.compile(r"^[0-9]+\.[0-9]+$", re.ASCII)
_PLAIN_DECIMAL_RE = re.compile(r"^[1-9][0-9]*$", re.ASCII)
_HP_ANNOTATED_RE = re.compile(
    r"^(?P<prefix>body )?(?P<base>[1-9][0-9]*)(?P<suffix>.+)$",
    re.ASCII,
)
_AC_ANNOTATED_RE = re.compile(
    r"^(?P<base>[1-9][0-9]*)(?P<suffix>.+)$",
    re.ASCII,
)
_SHIELD_RE = re.compile(
    r"^\((?P<alternate>[1-9][0-9]*) with "
    r"(?P<shield>(?:trash )?shield) raised\)$",
    re.ASCII,
)
_BROKEN_RE = re.compile(
    r"^\((?P<alternate>[1-9][0-9]*) when broken\)$",
    re.ASCII,
)
_HARDNESS_RE = re.compile(
    r"^Hardness (?P<amount>[1-9][0-9]*)$",
    re.ASCII,
)
_FAST_HEALING_RE = re.compile(
    r"^(?:fast healing (?P<amount>[1-9][0-9]*)"
    r"(?: \((?P<qualifier>[^()]+)\))?"
    r"|\(fast healing (?P<parenthetical_amount>[1-9][0-9]*)\))$",
    re.ASCII,
)
_REGENERATION_RE = re.compile(
    r"^regeneration (?P<amount>[1-9][0-9]*) "
    r"\(deactivated by (?P<deactivation>[^();]+)"
    r"(?:; page 360)?\)$",
    re.ASCII,
)
_VOID_HEALING_RE = re.compile(
    r"^void healing(?: \(page 360\))?$",
    re.ASCII,
)
_CONDITIONAL_ALTERNATE_RE = re.compile(
    r"^\((?P<alternate>[1-9][0-9]*) "
    r"(?:against|with) [^()]+\)$",
    re.ASCII,
)
_STATUS_CONDITION_RE = re.compile(
    r"^\+(?P<bonus>[1-9][0-9]*) status vs\. .+$",
    re.ASCII,
)

_PROVIDER_SPECS = (
    (
        "gmc-creature-armor-class",
        "core-gmc",
        "117.3",
        "9e83b76954080785b30b3f4c8913d2a1816316a362ad685c4ef5bd21a7621aac",
    ),
    (
        "gmc-creature-hit-points",
        "core-gmc",
        "118.3",
        "2a343f719cdd6721aae586a5879d6c334be9c38b44b8eb1fa3a87408e02fa7cf",
    ),
    (
        "gmc-regeneration-and-healing",
        "core-gmc",
        "118.5",
        "a3878d35c7423c6ae7225f623f26e1ee5f5c87b9096925d4e89930a5cf7e5f49",
    ),
    (
        "pc1-bonuses-and-penalties",
        "core-pc1",
        "10.8",
        "85aa354e605232b91a8e8e3afb7ae93e53c7a281977abeb283b0f3fb80d66a27",
    ),
    (
        "pc1-fast-healing-and-regeneration",
        "core-pc1",
        "410.4",
        "506aded94143e23549e0af1b931249735e88e680c59e962e464d60f67ab8089d",
    ),
    (
        "pc1-items-and-hit-points",
        "core-pc1",
        "410.5",
        "0cfb1d8dd814b3d7a0bda179bdff8d01d9e9c02e99e629bcd8342e0a39778d54",
    ),
    (
        "pc1-raise-a-shield",
        "core-pc1",
        "419.9",
        "a671f3223b918b5a30ff712c0a446e8e511638c9929cb87fd8e0d484ae7871bb",
    ),
    (
        "pc1-broken-condition",
        "core-pc1",
        "442.7",
        "32135329b72076529f012eb51fc3f9f6c4cb0b13597016ebcdf9cf0a61f104bf",
    ),
)

_DEFERRAL_SPECS = (
    (
        "shield",
        (
            "gmc-creature-armor-class",
            "pc1-bonuses-and-penalties",
            "pc1-raise-a-shield",
        ),
    ),
    (
        "conditional",
        (
            "gmc-creature-armor-class",
            "gmc-creature-hit-points",
            "pc1-bonuses-and-penalties",
        ),
    ),
    (
        "threshold",
        (
            "gmc-creature-armor-class",
            "gmc-creature-hit-points",
            "pc1-items-and-hit-points",
            "pc1-broken-condition",
        ),
    ),
    (
        "recovery",
        (
            "gmc-creature-hit-points",
            "gmc-regeneration-and-healing",
            "pc1-fast-healing-and-regeneration",
        ),
    ),
    (
        "other",
        (
            "gmc-creature-armor-class",
            "gmc-creature-hit-points",
        ),
    ),
)


class AnnotatedStatCompileError(ValueError):
    """An annotated HP or AC source field is not canonical."""


def _requirement_from_spec(
    spec: tuple[str, str, str, str],
) -> RuleRequirement:
    rule_id, source_id, locator, block_sha256 = spec
    return RuleRequirement(
        rule_id=rule_id,
        source_id=source_id,
        locator=locator,
        expected_block_sha256=block_sha256,
    )


ANNOTATED_STAT_RULE_REQUIREMENTS = MappingProxyType(
    {
        spec[0]: _requirement_from_spec(spec)
        for spec in _PROVIDER_SPECS
    }
)


@final
@dataclass(frozen=True, slots=True)
class RuntimeStatDeferral:
    """One exact runtime concern retained by an annotated stat."""

    kind: RuntimeDeferralKind
    provider_rule_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        raise TypeError("RuntimeStatDeferral contract is not bound")

    def as_serialized(self) -> dict[str, Any]:
        raise TypeError("RuntimeStatDeferral contract is not bound")


def _bind_deferral_contract():
    deferral_type = RuntimeStatDeferral
    error_type = AnnotatedStatCompileError
    canonical_specs = tuple(
        (kind, tuple(provider_rule_ids))
        for kind, provider_rule_ids in _DEFERRAL_SPECS
    )

    def validate(value: RuntimeStatDeferral) -> None:
        if (
            type(value) is not deferral_type
            or type(value.kind) is not str
            or type(value.provider_rule_ids) is not tuple
            or any(
                type(rule_id) is not str
                for rule_id in value.provider_rule_ids
            )
            or (value.kind, value.provider_rule_ids)
            not in canonical_specs
        ):
            raise TypeError(
                "RuntimeStatDeferral must match one exact canonical pair"
            )

    def serialize(value: RuntimeStatDeferral) -> dict[str, Any]:
        validate(value)
        return {
            "kind": value.kind,
            "providerRuleIds": list(value.provider_rule_ids),
            "status": "deferred",
            "blocks": "runtime-activation",
        }

    def build(
        kinds: tuple[str, ...],
    ) -> tuple[RuntimeStatDeferral, ...]:
        if (
            type(kinds) is not tuple
            or any(type(kind) is not str for kind in kinds)
            or len(frozenset(kinds)) != len(kinds)
        ):
            raise error_type(
                "annotated-stat deferral kinds are not exact"
            )
        by_kind = dict(canonical_specs)
        if any(kind not in by_kind for kind in kinds):
            raise error_type(
                "annotated-stat deferral kind is unknown"
            )
        return tuple(
            deferral_type(kind, by_kind[kind])
            for kind, _providers in canonical_specs
            if kind in kinds
        )

    return validate, serialize, build


(
    _validate_runtime_deferral,
    _serialize_runtime_deferral,
    _build_runtime_deferrals,
) = _bind_deferral_contract()
RuntimeStatDeferral.__post_init__ = _validate_runtime_deferral
RuntimeStatDeferral.as_serialized = _serialize_runtime_deferral


@final
@dataclass(frozen=True, slots=True, init=False)
class CompiledAnnotatedStat:
    """Opaque authority-backed lossless annotated-stat projection."""

    _authority: SourceAuthorityAdapter = field(repr=False)
    _consumer_receipt: SourceReceipt = field(repr=False)
    _projection: Mapping[str, Any] = field(repr=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "CompiledAnnotatedStat can only be constructed by "
            "compile_annotated_stat"
        )

    def __copy__(self) -> None:
        raise TypeError("CompiledAnnotatedStat cannot be copied")

    def __deepcopy__(self, _memo: object) -> None:
        raise TypeError("CompiledAnnotatedStat cannot be copied")

    def __reduce__(self) -> None:
        raise TypeError("CompiledAnnotatedStat cannot be pickled")

    def __reduce_ex__(self, _protocol: object) -> None:
        raise TypeError("CompiledAnnotatedStat cannot be pickled")

    @property
    def field_name(self) -> StatField:
        raise TypeError("CompiledAnnotatedStat contract is not bound")

    @property
    def base_value(self) -> int:
        raise TypeError("CompiledAnnotatedStat contract is not bound")

    @property
    def source_text(self) -> str:
        raise TypeError("CompiledAnnotatedStat contract is not bound")

    @property
    def source_receipt(self) -> SourceReceipt:
        raise TypeError("CompiledAnnotatedStat contract is not bound")

    @property
    def provider_rules(self) -> tuple[VerifiedRuleReceipt, ...]:
        raise TypeError("CompiledAnnotatedStat contract is not bound")

    @property
    def deferrals(self) -> tuple[RuntimeStatDeferral, ...]:
        raise TypeError("CompiledAnnotatedStat contract is not bound")

    def as_serialized(self) -> dict[str, Any]:
        raise TypeError("CompiledAnnotatedStat contract is not bound")


def _closed_json_transform(
    value: Any,
    *,
    freeze: bool,
    label: str,
    error_type: type[Exception] = AnnotatedStatCompileError,
    mapping_proxy_type: Any = MappingProxyType,
) -> Any:
    active: set[int] = set()
    node_count = 0
    maximum_depth = 40
    maximum_nodes = 8_192
    maximum_items = 2_048
    maximum_text_bytes = 4_096

    def visit(item: Any, depth: int) -> Any:
        nonlocal node_count
        node_count += 1
        if node_count > maximum_nodes:
            raise error_type(
                f"{label} exceeds its node bound"
            )
        if depth > maximum_depth:
            raise error_type(
                f"{label} exceeds its depth bound"
            )
        if item is None or type(item) in {bool, int}:
            return item
        if type(item) is str:
            if len(item.encode("utf-8")) > maximum_text_bytes:
                raise error_type(
                    f"{label} text exceeds its byte bound"
                )
            return item

        mapping_type = dict if freeze else mapping_proxy_type
        if type(item) is mapping_type:
            if len(item) > maximum_items:
                raise error_type(
                    f"{label} mapping exceeds its item bound"
                )
            identity = id(item)
            if identity in active:
                raise error_type(
                    f"{label} contains a cycle"
                )
            active.add(identity)
            try:
                copied: dict[str, Any] = {}
                for key, nested in item.items():
                    if type(key) is not str:
                        raise error_type(
                            f"{label} contains a non-string key"
                        )
                    if len(key.encode("utf-8")) > maximum_text_bytes:
                        raise error_type(
                            f"{label} key exceeds its byte bound"
                        )
                    copied[key] = visit(nested, depth + 1)
            finally:
                active.remove(identity)
            return mapping_proxy_type(copied) if freeze else copied

        sequence_type = list if freeze else tuple
        if type(item) is sequence_type:
            if len(item) > maximum_items:
                raise error_type(
                    f"{label} sequence exceeds its item bound"
                )
            identity = id(item)
            if identity in active:
                raise error_type(
                    f"{label} contains a cycle"
                )
            active.add(identity)
            try:
                copied_items = [
                    visit(nested, depth + 1)
                    for nested in item
                ]
            finally:
                active.remove(identity)
            return tuple(copied_items) if freeze else copied_items

        raise error_type(
            f"{label} is not closed JSON"
        )

    return visit(value, 0)


def _consumer_root(
    selection: VerifiedSourceSelection,
    *,
    source_id: str,
    fields: tuple[str, str],
    locator_re: re.Pattern[str],
    selection_type: type[VerifiedSourceSelection],
    carrier_type: type[VerifiedSourceCarrier],
    object_type: type[RawSourceObject],
    member_type: type[RawSourceMember],
    step_type: type[RawMemberStep],
    error_type: type[Exception],
) -> tuple[VerifiedSourceCarrier, RawSourceObject, str, str, str]:
    if type(selection) is not selection_type:
        raise TypeError(
            "annotated-stat consumer must be a verified selection"
        )
    address = selection.address
    carrier = selection.carrier
    path = address.selection_path
    if (
        type(carrier) is not carrier_type
        or carrier.source_id != source_id
        or type(carrier.locator) is not str
        or locator_re.fullmatch(carrier.locator) is None
        or address.span is not None
        or type(path) is not tuple
        or len(path) != 1
        or type(path[0]) is not step_type
        or path[0].raw_key not in fields
        or not address.carrier_path
        or type(address.carrier_path[-1]) is not step_type
        or address.carrier_path[-1].raw_key != "^.creature"
        or type(carrier.raw_block) is not object_type
        or type(selection.raw_member) is not member_type
        or selection.raw_member.key != path[0].raw_key
        or type(selection.raw_member.value) is not str
        or type(selection.raw_value) is not str
        or type(selection.selected_value) is not str
        or selection.raw_value != selection.raw_member.value
        or selection.selected_value != selection.raw_value
    ):
        raise error_type(
            "consumer must select one exact Core MC1 HP or AC member"
        )
    matches = tuple(
        (ordinal, member)
        for ordinal, member in enumerate(carrier.raw_block.members)
        if member.key == path[0].raw_key
    )
    names = tuple(
        member.value
        for member in carrier.raw_block.members
        if member.key == "Name"
    )
    if (
        len(matches) != 1
        or matches[0][0] != path[0].member_ordinal
        or matches[0][1] is not selection.raw_member
        or len(names) != 1
        or type(names[0]) is not str
        or not names[0]
        or names[0] != names[0].strip()
    ):
        raise error_type(
            "annotated-stat creature field is ambiguous"
        )
    return (
        carrier,
        carrier.raw_block,
        path[0].raw_key,
        selection.raw_value,
        names[0],
    )


def _fragment_spans(
    source_text: str,
    suffix_start: int,
    *,
    maximum_fragments: int,
    error_type: type[Exception],
) -> tuple[tuple[int, int, str, str], ...]:
    result: list[tuple[int, int, str, str]] = []
    cursor = suffix_start
    while cursor < len(source_text):
        if len(result) >= maximum_fragments:
            raise error_type(
                "annotation exceeds its fragment bound"
            )
        start = cursor
        if source_text.startswith(", ", cursor):
            separator = ", "
        elif source_text.startswith("; ", cursor):
            separator = "; "
        elif source_text.startswith(" ", cursor):
            separator = " "
        else:
            raise error_type(
                "annotation separator is not canonical"
            )
        text_start = cursor + len(separator)
        cursor = text_start
        depth = 0
        while cursor < len(source_text):
            character = source_text[cursor]
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth < 0:
                    raise error_type(
                        "annotation parentheses are unbalanced"
                    )
            if (
                depth == 0
                and (
                    source_text.startswith(", ", cursor)
                    or source_text.startswith("; ", cursor)
                )
            ):
                break
            cursor += 1
        if depth != 0:
            raise error_type(
                "annotation parentheses are unbalanced"
            )
        text = source_text[text_start:cursor]
        if not text or text != text.strip():
            raise error_type(
                "annotation fragment text is not canonical"
            )
        result.append((start, cursor, separator, text))
    if not result:
        raise error_type(
            "annotated stat has no annotation fragments"
        )
    return tuple(result)


def _semantic_markers(
    field_name: str,
    text: str,
    *,
    maximum_value: int,
    shield_re: re.Pattern[str],
    broken_re: re.Pattern[str],
    hardness_re: re.Pattern[str],
    fast_healing_re: re.Pattern[str],
    regeneration_re: re.Pattern[str],
    void_healing_re: re.Pattern[str],
    conditional_alternate_re: re.Pattern[str],
    status_condition_re: re.Pattern[str],
    error_type: type[Exception],
) -> tuple[dict[str, Any], ...]:
    result: dict[str, dict[str, Any]] = {}

    def bounded_number(source: str, label: str) -> int:
        value = int(source)
        if not 1 <= value <= maximum_value:
            raise error_type(
                f"{label} exceeds its finite bound"
            )
        return value

    shield = shield_re.fullmatch(text) if field_name == "AC" else None
    if shield is not None:
        result["shield"] = {
            "kind": "shield",
            "alternateValue": bounded_number(
                shield.group("alternate"),
                "annotated shield AC",
            ),
            "shieldSourceText": shield.group("shield"),
        }
        result["conditional"] = {"kind": "conditional"}

    broken = broken_re.fullmatch(text) if field_name == "AC" else None
    if broken is not None:
        result["conditional"] = {
            "kind": "conditional",
            "alternateValue": bounded_number(
                broken.group("alternate"),
                "annotated broken AC",
            ),
        }
        result["threshold"] = {
            "kind": "threshold",
            "thresholdSourceText": "broken",
        }

    hardness = hardness_re.fullmatch(text) if field_name == "HP" else None
    if hardness is not None:
        result["threshold"] = {
            "kind": "threshold",
            "hardness": bounded_number(
                hardness.group("amount"),
                "annotated Hardness",
            ),
        }

    fast_healing = (
        fast_healing_re.fullmatch(text)
        if field_name == "HP"
        else None
    )
    if fast_healing is not None:
        amount = (
            fast_healing.group("amount")
            or fast_healing.group("parenthetical_amount")
        )
        result["recovery"] = {
            "kind": "recovery",
            "mode": "fast-healing",
            "amount": bounded_number(
                amount,
                "annotated fast healing",
            ),
        }
        qualifier = fast_healing.group("qualifier")
        if (
            qualifier is not None
            and not qualifier.startswith("page ")
        ):
            result["conditional"] = {
                "kind": "conditional",
                "conditionSourceText": qualifier,
            }

    regeneration = (
        regeneration_re.fullmatch(text)
        if field_name == "HP"
        else None
    )
    if regeneration is not None:
        result["recovery"] = {
            "kind": "recovery",
            "mode": "regeneration",
            "amount": bounded_number(
                regeneration.group("amount"),
                "annotated regeneration",
            ),
        }
        result["conditional"] = {
            "kind": "conditional",
            "conditionSourceText": (
                "deactivated by "
                + regeneration.group("deactivation")
            ),
        }

    if field_name == "HP" and void_healing_re.fullmatch(text):
        result["recovery"] = {
            "kind": "recovery",
            "mode": "void-healing",
        }

    if field_name == "AC":
        conditional_alternate = conditional_alternate_re.fullmatch(text)
        if conditional_alternate is not None:
            alternate_value = bounded_number(
                conditional_alternate.group("alternate"),
                "annotated conditional AC",
            )
            if shield is None and broken is None:
                result["conditional"] = {
                    "kind": "conditional",
                    "alternateValue": alternate_value,
                }
        status_condition = status_condition_re.fullmatch(text)
        if status_condition is not None:
            result["conditional"] = {
                "kind": "conditional",
                "statusBonus": bounded_number(
                    status_condition.group("bonus"),
                    "annotated conditional AC status bonus",
                ),
            }
        if text == "construct armor":
            result["threshold"] = {
                "kind": "threshold",
                "thresholdSourceText": "construct armor",
            }
        if text.endswith(" after Shed Armor"):
            result["conditional"] = {"kind": "conditional"}

    if not result:
        result["other"] = {"kind": "other"}
    order = ("shield", "conditional", "threshold", "recovery", "other")
    return tuple(result[kind] for kind in order if kind in result)


def _parse_source(
    field_name: str,
    source_text: str,
    *,
    fields: tuple[str, str],
    plain_decimal_re: re.Pattern[str],
    hp_annotated_re: re.Pattern[str],
    ac_annotated_re: re.Pattern[str],
    maximum_value: int,
    maximum_source_bytes: int,
    maximum_fragments: int,
    fragment_parser: Any,
    error_type: type[Exception],
) -> dict[str, Any] | None:
    if (
        type(field_name) is not str
        or field_name not in fields
        or type(source_text) is not str
        or not source_text
        or source_text != source_text.strip()
        or len(source_text.encode("utf-8")) > maximum_source_bytes
    ):
        raise error_type(
            "annotated-stat source scalar is invalid"
        )
    if plain_decimal_re.fullmatch(source_text):
        value = int(source_text)
        if value > maximum_value:
            raise error_type(
                "plain stat value exceeds its bound"
            )
        return None
    match = (
        hp_annotated_re.fullmatch(source_text)
        if field_name == "HP"
        else ac_annotated_re.fullmatch(source_text)
    )
    if match is None:
        raise error_type(
            "annotated-stat source grammar is not reviewed"
        )
    prefix = match.groupdict().get("prefix") or ""
    base_text = match.group("base")
    suffix = match.group("suffix")
    base_value = int(base_text)
    if (
        type(base_value) is not int
        or not 1 <= base_value <= maximum_value
    ):
        raise error_type(
            "annotated-stat base value exceeds its bound"
        )
    base_start = len(prefix)
    base_end = base_start + len(base_text)
    fragments = fragment_parser(
        source_text,
        base_end,
        maximum_fragments=maximum_fragments,
        error_type=error_type,
    )
    return {
        "prefix": prefix,
        "baseText": base_text,
        "baseValue": base_value,
        "baseStart": base_start,
        "baseEnd": base_end,
        "suffix": suffix,
        "fragments": fragments,
    }


def _contract_fingerprint(
    provider_specs: tuple[tuple[str, str, str, str], ...],
    deferral_specs: tuple[tuple[str, tuple[str, ...]], ...],
    fields: tuple[str, str],
    *,
    json_dumps: Any = json.dumps,
    sha256: Any = hashlib.sha256,
) -> str:
    payload = {
        "schema": 1,
        "providers": provider_specs,
        "deferrals": deferral_specs,
        "fields": fields,
        "grammar": "lossless-hp-ac-v1",
    }
    encoded = json_dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _bind_reviewed_contract():
    family_id = str(FAMILY_ID)
    mechanic_type = str(MECHANIC_TYPE)
    source_id = str(MONSTER_CORE_SOURCE_ID)
    fields = tuple(_FIELDS)
    maximum_value = int(MAX_STAT_VALUE)
    maximum_source_bytes = int(MAX_STAT_SOURCE_BYTES)
    maximum_fragments = int(MAX_ANNOTATION_FRAGMENTS)
    locator_re = re.compile(_LOCATOR_RE.pattern, re.ASCII)
    plain_decimal_re = re.compile(_PLAIN_DECIMAL_RE.pattern, re.ASCII)
    hp_annotated_re = re.compile(_HP_ANNOTATED_RE.pattern, re.ASCII)
    ac_annotated_re = re.compile(_AC_ANNOTATED_RE.pattern, re.ASCII)
    shield_re = re.compile(_SHIELD_RE.pattern, re.ASCII)
    broken_re = re.compile(_BROKEN_RE.pattern, re.ASCII)
    hardness_re = re.compile(_HARDNESS_RE.pattern, re.ASCII)
    fast_healing_re = re.compile(_FAST_HEALING_RE.pattern, re.ASCII)
    regeneration_re = re.compile(_REGENERATION_RE.pattern, re.ASCII)
    void_healing_re = re.compile(_VOID_HEALING_RE.pattern, re.ASCII)
    conditional_alternate_re = re.compile(
        _CONDITIONAL_ALTERNATE_RE.pattern,
        re.ASCII,
    )
    status_condition_re = re.compile(
        _STATUS_CONDITION_RE.pattern,
        re.ASCII,
    )
    provider_specs = tuple(tuple(spec) for spec in _PROVIDER_SPECS)
    deferral_specs = tuple(
        (kind, tuple(provider_ids))
        for kind, provider_ids in _DEFERRAL_SPECS
    )
    fingerprint_function = _contract_fingerprint
    fingerprint = fingerprint_function(
        provider_specs,
        deferral_specs,
        fields,
    )

    adapter_type = SourceAuthorityAdapter
    receipt_type = SourceReceipt
    selection_type = VerifiedSourceSelection
    carrier_type = VerifiedSourceCarrier
    provider_type = VerifiedRuleReceipt
    requirement_type = RuleRequirement
    compiled_type = CompiledAnnotatedStat
    error_type = AnnotatedStatCompileError
    mapping_proxy_type = MappingProxyType
    text_span_type = TextSpan
    object_type = RawSourceObject
    member_type = RawSourceMember
    step_type = RawMemberStep
    consumer_root = _consumer_root
    fragment_parser = _fragment_spans
    parse_source = _parse_source
    markers_for = _semantic_markers
    build_deferrals = _build_runtime_deferrals
    closed_json_transform = _closed_json_transform
    json_dumps = json.dumps

    def require_contract() -> None:
        if (
            family_id != "annotated-stats"
            or mechanic_type != "annotated-stat"
            or source_id != "core-mc1"
            or fields != ("HP", "AC")
            or maximum_value != 10_000
            or maximum_source_bytes != 1_024
            or maximum_fragments != 32
            or type(provider_specs) is not tuple
            or len(provider_specs) != 8
            or any(
                type(spec) is not tuple
                or len(spec) != 4
                or any(type(item) is not str for item in spec)
                for spec in provider_specs
            )
            or tuple(spec[0] for spec in provider_specs) != (
                "gmc-creature-armor-class",
                "gmc-creature-hit-points",
                "gmc-regeneration-and-healing",
                "pc1-bonuses-and-penalties",
                "pc1-fast-healing-and-regeneration",
                "pc1-items-and-hit-points",
                "pc1-raise-a-shield",
                "pc1-broken-condition",
            )
            or type(deferral_specs) is not tuple
            or len(deferral_specs) != 5
            or fingerprint_function(
                provider_specs,
                deferral_specs,
                fields,
            )
            != fingerprint
        ):
            raise error_type(
                "annotated-stat reviewed contract disagrees"
            )

    def build_requirements() -> tuple[RuleRequirement, ...]:
        require_contract()
        return tuple(
            requirement_type(
                rule_id=rule_id,
                source_id=source_id,
                locator=locator,
                expected_block_sha256=block_sha256,
            )
            for rule_id, source_id, locator, block_sha256
            in provider_specs
        )

    def freeze_json(value: dict[str, Any]) -> Mapping[str, Any]:
        frozen = closed_json_transform(
            value,
            freeze=True,
            label="annotated-stat derived projection",
            error_type=error_type,
            mapping_proxy_type=mapping_proxy_type,
        )
        if type(frozen) is not mapping_proxy_type:
            raise error_type(
                "annotated-stat projection root is invalid"
            )
        return frozen

    def thaw_json(value: Any) -> dict[str, Any]:
        thawed = closed_json_transform(
            value,
            freeze=False,
            label="annotated-stat stored projection",
            error_type=error_type,
            mapping_proxy_type=mapping_proxy_type,
        )
        if type(thawed) is not dict:
            raise error_type(
                "annotated-stat projection root is invalid"
            )
        return thawed

    def projection_bytes(value: dict[str, Any]) -> bytes:
        try:
            return json_dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as failure:
            raise error_type(
                "annotated-stat projection is not canonical JSON"
            ) from failure

    def select_span(
        authority: SourceAuthorityAdapter,
        source: VerifiedSourceSelection,
        start: int,
        end: int,
    ) -> VerifiedSourceSelection:
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(source.raw_value)
        ):
            raise error_type(
                "annotated-stat source span is invalid"
            )
        selection = source.carrier.select(
            source.address.selection_path,
            span=text_span_type(start, end),
        )
        authority.validate_selection(selection)
        if type(selection) is not selection_type:
            raise error_type(
                "annotated-stat span did not verify"
            )
        return selection

    def derive(
        authority: SourceAuthorityAdapter,
        consumer_receipt: SourceReceipt,
    ) -> tuple[
        VerifiedSourceSelection,
        tuple[VerifiedRuleReceipt, ...],
        tuple[RuntimeStatDeferral, ...],
        dict[str, Any],
    ] | None:
        require_contract()
        if type(authority) is not adapter_type:
            raise TypeError(
                "compile_annotated_stat requires an exact "
                "SourceAuthorityAdapter"
            )
        if type(consumer_receipt) is not receipt_type:
            raise TypeError(
                "compile_annotated_stat requires an exact SourceReceipt"
            )
        source = authority.validate_selection(
            authority.reload(consumer_receipt)
        )
        _carrier, _block, field_name, source_text, creature_name = (
            consumer_root(
                source,
                source_id=source_id,
                fields=fields,
                locator_re=locator_re,
                selection_type=selection_type,
                carrier_type=carrier_type,
                object_type=object_type,
                member_type=member_type,
                step_type=step_type,
                error_type=error_type,
            )
        )
        parsed = parse_source(
            field_name,
            source_text,
            fields=fields,
            plain_decimal_re=plain_decimal_re,
            hp_annotated_re=hp_annotated_re,
            ac_annotated_re=ac_annotated_re,
            maximum_value=maximum_value,
            maximum_source_bytes=maximum_source_bytes,
            maximum_fragments=maximum_fragments,
            fragment_parser=fragment_parser,
            error_type=error_type,
        )
        if parsed is None:
            return None

        requirements = build_requirements()
        providers = tuple(
            authority.validate_rule(
                authority.resolve_rule(requirement)
            )
            for requirement in requirements
        )
        authority.require_shared_authority(source, providers)
        for provider, requirement, spec in zip(
            providers,
            requirements,
            provider_specs,
            strict=True,
        ):
            if (
                type(provider) is not provider_type
                or provider.rule_id != spec[0]
                or type(provider.requirement) is not requirement_type
                or provider.requirement != requirement
                or provider.receipt != provider.selection.receipt
                or provider.receipt.authority_digest
                != source.receipt.authority_digest
                or provider.selection.address.source_id != spec[1]
                or provider.selection.address.locator != spec[2]
                or provider.receipt.block_sha256 != spec[3]
            ):
                raise error_type(
                    "annotated-stat provider proof disagrees"
                )

        base_selection = select_span(
            authority,
            source,
            parsed["baseStart"],
            parsed["baseEnd"],
        )
        suffix_selection = select_span(
            authority,
            source,
            parsed["baseEnd"],
            len(source_text),
        )
        prefix_selection = (
            select_span(
                authority,
                source,
                0,
                parsed["baseStart"],
            )
            if parsed["prefix"]
            else None
        )

        fragment_projections = []
        deferral_kinds: set[str] = set()
        if parsed["prefix"]:
            deferral_kinds.add("other")
        for ordinal, (
            start,
            end,
            separator,
            text,
        ) in enumerate(parsed["fragments"]):
            selection = select_span(
                authority,
                source,
                start,
                end,
            )
            semantics = markers_for(
                field_name,
                text,
                maximum_value=maximum_value,
                shield_re=shield_re,
                broken_re=broken_re,
                hardness_re=hardness_re,
                fast_healing_re=fast_healing_re,
                regeneration_re=regeneration_re,
                void_healing_re=void_healing_re,
                conditional_alternate_re=conditional_alternate_re,
                status_condition_re=status_condition_re,
                error_type=error_type,
            )
            deferral_kinds.update(
                item["kind"] for item in semantics
            )
            fragment_projections.append(
                {
                    "ordinal": ordinal,
                    "separator": separator,
                    "text": text,
                    "sourceText": source_text[start:end],
                    "source": selection.receipt.as_serialized(),
                    "semantics": list(semantics),
                }
            )
        deferrals = build_deferrals(tuple(deferral_kinds))
        provider_projection = {
            provider.rule_id: provider.as_serialized()
            for provider in providers
        }
        projection = {
            "schema": 1,
            "family": family_id,
            "mechanicType": mechanic_type,
            "sourceId": source_id,
            "locator": source.address.locator,
            "creatureName": creature_name,
            "field": field_name,
            "base": {
                "value": parsed["baseValue"],
                "sourceText": parsed["baseText"],
                "source": base_selection.receipt.as_serialized(),
            },
            "sourceText": source_text,
            "source": source.receipt.as_serialized(),
            "annotation": {
                "prefixText": parsed["prefix"],
                "prefixSource": (
                    prefix_selection.receipt.as_serialized()
                    if prefix_selection is not None
                    else None
                ),
                "suffixText": parsed["suffix"],
                "suffixSource": (
                    suffix_selection.receipt.as_serialized()
                ),
                "fragments": fragment_projections,
            },
            "providerRules": provider_projection,
            "runtime": {
                "status": "deferred",
                "deferrals": [
                    deferral.as_serialized()
                    for deferral in deferrals
                ],
            },
            "contractProof": {
                "schema": 1,
                "sha256": fingerprint,
                "providerCount": len(provider_specs),
                "deferralKindCount": len(deferral_specs),
            },
        }
        return source, providers, deferrals, projection

    def validate_compiled(
        value: object,
    ) -> tuple[
        VerifiedSourceSelection,
        tuple[VerifiedRuleReceipt, ...],
        tuple[RuntimeStatDeferral, ...],
        dict[str, Any],
    ]:
        if type(value) is not compiled_type:
            raise TypeError(
                "annotated-stat projection requires an exact "
                "CompiledAnnotatedStat"
            )
        try:
            authority = value._authority
            consumer_receipt = value._consumer_receipt
            stored_projection = value._projection
        except AttributeError as failure:
            raise error_type(
                "compiled annotated-stat capability is incomplete"
            ) from failure
        if (
            type(authority) is not adapter_type
            or type(consumer_receipt) is not receipt_type
        ):
            raise error_type(
                "compiled annotated-stat capability is forged"
            )
        derived = derive(authority, consumer_receipt)
        if derived is None:
            raise error_type(
                "compiled annotated-stat source is no longer annotated"
            )
        expected = derived[-1]
        actual = thaw_json(stored_projection)
        if projection_bytes(actual) != projection_bytes(expected):
            raise error_type(
                "compiled annotated-stat projection is stale"
            )
        return derived

    def compile_annotated_stat(
        authority: object,
        consumer_receipt: object,
        /,
    ) -> CompiledAnnotatedStat | None:
        """Compile one exact annotated HP or AC field, or ``None`` if plain."""

        derived = derive(authority, consumer_receipt)
        if derived is None:
            return None
        source = derived[0]
        projection = derived[-1]
        result = object.__new__(compiled_type)
        object.__setattr__(result, "_authority", authority)
        object.__setattr__(
            result,
            "_consumer_receipt",
            source.receipt,
        )
        object.__setattr__(
            result,
            "_projection",
            freeze_json(projection),
        )
        return result

    def compiled_field(value: CompiledAnnotatedStat) -> str:
        return validate_compiled(value)[-1]["field"]

    def compiled_base(value: CompiledAnnotatedStat) -> int:
        return validate_compiled(value)[-1]["base"]["value"]

    def compiled_source_text(value: CompiledAnnotatedStat) -> str:
        return validate_compiled(value)[-1]["sourceText"]

    def compiled_source_receipt(
        value: CompiledAnnotatedStat,
    ) -> SourceReceipt:
        return validate_compiled(value)[0].receipt

    def compiled_providers(
        value: CompiledAnnotatedStat,
    ) -> tuple[VerifiedRuleReceipt, ...]:
        return validate_compiled(value)[1]

    def compiled_deferrals(
        value: CompiledAnnotatedStat,
    ) -> tuple[RuntimeStatDeferral, ...]:
        return validate_compiled(value)[2]

    def compiled_projection(
        value: CompiledAnnotatedStat,
    ) -> dict[str, Any]:
        return validate_compiled(value)[-1]

    return (
        compile_annotated_stat,
        compiled_field,
        compiled_base,
        compiled_source_text,
        compiled_source_receipt,
        compiled_providers,
        compiled_deferrals,
        compiled_projection,
    )


(
    compile_annotated_stat,
    _compiled_field,
    _compiled_base,
    _compiled_source_text,
    _compiled_source_receipt,
    _compiled_providers,
    _compiled_deferrals,
    _compiled_projection,
) = _bind_reviewed_contract()
CompiledAnnotatedStat.field_name = property(_compiled_field)
CompiledAnnotatedStat.base_value = property(_compiled_base)
CompiledAnnotatedStat.source_text = property(_compiled_source_text)
CompiledAnnotatedStat.source_receipt = property(_compiled_source_receipt)
CompiledAnnotatedStat.provider_rules = property(_compiled_providers)
CompiledAnnotatedStat.deferrals = property(_compiled_deferrals)
CompiledAnnotatedStat.as_serialized = _compiled_projection


__all__ = [
    "ANNOTATED_STAT_RULE_REQUIREMENTS",
    "AnnotatedStatCompileError",
    "CompiledAnnotatedStat",
    "FAMILY_ID",
    "MAX_ANNOTATION_FRAGMENTS",
    "MAX_STAT_SOURCE_BYTES",
    "MAX_STAT_VALUE",
    "MECHANIC_TYPE",
    "RuntimeStatDeferral",
    "compile_annotated_stat",
]
