"""Generic immutable mechanic-registry construction.

This kernel imports only extension contracts and standard-library support. It
contains no PF2ER family discovery, authority binding, or global composition.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .contracts import (
    AbilityCompilerRegistration,
    ActivityHandlerRegistration,
    CompoundActivityHandlerRegistration,
    BattlegroundAdjudicationNormalizerRegistration,
    ControllerActionRegistration,
    ControllerIntentDescriptorRegistration,
    EventRendererRegistration,
    HostActivityInputEnricherRegistration,
    MechanicFamilyFragment,
    MovementExposureRegistration,
    PendingDecisionHandlerRegistration,
    PostActionResultHookRegistration,
    PostEventHookRegistration,
    PublicStateProjectorRegistration,
    ReactionHandlerRegistration,
    ReactionQueueHandlerRegistration,
    RendererKey,
    SpellEffectHandlerKey,
    SpellEffectHandlerRegistration,
    StateValidatorRegistration,
    TurnStartHookRegistration,
)


class RegistryConfigurationError(ValueError):
    """The explicit family fragment tuple is incomplete or ambiguous."""


@dataclass(frozen=True, slots=True, init=False)
class MechanicRegistry:
    """Read-only tables assembled in the caller's explicit fragment order."""

    families: tuple[MechanicFamilyFragment, ...]
    family_by_id: Mapping[str, MechanicFamilyFragment]
    mechanic_owners: Mapping[str, str]
    ability_compilers: tuple[AbilityCompilerRegistration, ...]
    activity_handlers: Mapping[str, ActivityHandlerRegistration]
    compound_activity_handlers: Mapping[
        str,
        CompoundActivityHandlerRegistration,
    ]
    host_activity_input_enrichers: Mapping[
        str,
        HostActivityInputEnricherRegistration,
    ]
    controller_intent_descriptors: Mapping[
        str,
        ControllerIntentDescriptorRegistration,
    ]
    controller_action_descriptors: Mapping[
        str,
        ControllerActionRegistration,
    ]
    reaction_handlers: Mapping[str, ReactionHandlerRegistration]
    reaction_queue_handlers: Mapping[
        str,
        ReactionQueueHandlerRegistration,
    ]
    post_event_hooks: tuple[PostEventHookRegistration, ...]
    pending_decision_handlers: Mapping[
        str,
        PendingDecisionHandlerRegistration,
    ]
    post_action_result_hooks: tuple[
        PostActionResultHookRegistration,
        ...,
    ]
    turn_start_hooks: tuple[TurnStartHookRegistration, ...]
    movement_exposures: Mapping[str, MovementExposureRegistration]
    battleground_adjudication_normalizers: Mapping[
        str,
        BattlegroundAdjudicationNormalizerRegistration,
    ]
    state_validators: tuple[StateValidatorRegistration, ...]
    spell_effect_handlers: Mapping[
        SpellEffectHandlerKey,
        SpellEffectHandlerRegistration,
    ]
    event_renderers: Mapping[RendererKey, EventRendererRegistration]
    public_state_projectors: tuple[PublicStateProjectorRegistration, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "MechanicRegistry instances must be created with build_registry()"
        )


def _create_registry(
    *,
    families: tuple[MechanicFamilyFragment, ...],
    family_by_id: Mapping[str, MechanicFamilyFragment],
    mechanic_owners: Mapping[str, str],
    ability_compilers: tuple[AbilityCompilerRegistration, ...],
    activity_handlers: Mapping[str, ActivityHandlerRegistration],
    compound_activity_handlers: Mapping[
        str,
        CompoundActivityHandlerRegistration,
    ],
    host_activity_input_enrichers: Mapping[
        str,
        HostActivityInputEnricherRegistration,
    ],
    controller_intent_descriptors: Mapping[
        str,
        ControllerIntentDescriptorRegistration,
    ],
    controller_action_descriptors: Mapping[
        str,
        ControllerActionRegistration,
    ],
    reaction_handlers: Mapping[str, ReactionHandlerRegistration],
    reaction_queue_handlers: Mapping[
        str,
        ReactionQueueHandlerRegistration,
    ],
    post_event_hooks: tuple[PostEventHookRegistration, ...],
    pending_decision_handlers: Mapping[
        str,
        PendingDecisionHandlerRegistration,
    ],
    post_action_result_hooks: tuple[
        PostActionResultHookRegistration,
        ...,
    ],
    turn_start_hooks: tuple[TurnStartHookRegistration, ...],
    movement_exposures: Mapping[str, MovementExposureRegistration],
    battleground_adjudication_normalizers: Mapping[
        str,
        BattlegroundAdjudicationNormalizerRegistration,
    ],
    state_validators: tuple[StateValidatorRegistration, ...],
    spell_effect_handlers: Mapping[
        SpellEffectHandlerKey,
        SpellEffectHandlerRegistration,
    ],
    event_renderers: Mapping[RendererKey, EventRendererRegistration],
    public_state_projectors: tuple[PublicStateProjectorRegistration, ...],
) -> MechanicRegistry:
    """Create one registry after build_registry has validated every table."""

    registry = object.__new__(MechanicRegistry)
    object.__setattr__(registry, "families", tuple(families))
    object.__setattr__(
        registry,
        "family_by_id",
        MappingProxyType(dict(family_by_id)),
    )
    object.__setattr__(
        registry,
        "mechanic_owners",
        MappingProxyType(dict(mechanic_owners)),
    )
    object.__setattr__(
        registry,
        "ability_compilers",
        tuple(ability_compilers),
    )
    object.__setattr__(
        registry,
        "activity_handlers",
        MappingProxyType(dict(activity_handlers)),
    )
    object.__setattr__(
        registry,
        "compound_activity_handlers",
        MappingProxyType(dict(compound_activity_handlers)),
    )
    object.__setattr__(
        registry,
        "host_activity_input_enrichers",
        MappingProxyType(dict(host_activity_input_enrichers)),
    )
    object.__setattr__(
        registry,
        "controller_intent_descriptors",
        MappingProxyType(dict(controller_intent_descriptors)),
    )
    object.__setattr__(
        registry,
        "controller_action_descriptors",
        MappingProxyType(dict(controller_action_descriptors)),
    )
    object.__setattr__(
        registry,
        "reaction_handlers",
        MappingProxyType(dict(reaction_handlers)),
    )
    object.__setattr__(
        registry,
        "reaction_queue_handlers",
        MappingProxyType(dict(reaction_queue_handlers)),
    )
    object.__setattr__(
        registry,
        "post_event_hooks",
        tuple(post_event_hooks),
    )
    object.__setattr__(
        registry,
        "pending_decision_handlers",
        MappingProxyType(dict(pending_decision_handlers)),
    )
    object.__setattr__(
        registry,
        "post_action_result_hooks",
        tuple(post_action_result_hooks),
    )
    object.__setattr__(
        registry,
        "turn_start_hooks",
        tuple(turn_start_hooks),
    )
    object.__setattr__(
        registry,
        "movement_exposures",
        MappingProxyType(dict(movement_exposures)),
    )
    object.__setattr__(
        registry,
        "battleground_adjudication_normalizers",
        MappingProxyType(dict(battleground_adjudication_normalizers)),
    )
    object.__setattr__(
        registry,
        "state_validators",
        tuple(state_validators),
    )
    object.__setattr__(
        registry,
        "spell_effect_handlers",
        MappingProxyType(dict(spell_effect_handlers)),
    )
    object.__setattr__(
        registry,
        "event_renderers",
        MappingProxyType(dict(event_renderers)),
    )
    object.__setattr__(
        registry,
        "public_state_projectors",
        tuple(public_state_projectors),
    )
    return registry


def _add_unique(
    values: dict,
    key: object,
    value: object,
    *,
    label: str,
) -> None:
    if key in values:
        raise RegistryConfigurationError(f"duplicate {label}: {key!r}")
    values[key] = value


def _require_owned_mechanic(
    fragment: MechanicFamilyFragment,
    mechanic_type: str,
    *,
    registration_kind: str,
) -> None:
    if mechanic_type not in fragment.mechanic_types:
        raise RegistryConfigurationError(
            f"family {fragment.family_id!r} {registration_kind} references "
            f"unowned mechanic type: {mechanic_type!r}"
        )


def _require_registration(
    value: object,
    expected_type: type,
    *,
    family_id: str,
    registration_kind: str,
) -> None:
    if not isinstance(value, expected_type):
        raise RegistryConfigurationError(
            f"family {family_id!r} has invalid {registration_kind}: "
            f"{type(value).__name__}"
        )

def build_registry(
    fragments: tuple[MechanicFamilyFragment, ...],
) -> MechanicRegistry:
    """Build one immutable registry from an explicit ordered fragment tuple."""

    if not isinstance(fragments, tuple):
        raise RegistryConfigurationError(
            "mechanics registry requires an explicit family fragment tuple"
        )
    ordered_fragments = fragments
    if not ordered_fragments:
        raise RegistryConfigurationError(
            "mechanics registry requires at least one family fragment"
        )

    family_by_id: dict[str, MechanicFamilyFragment] = {}
    mechanic_owners: dict[str, str] = {}
    for fragment in ordered_fragments:
        if not isinstance(fragment, MechanicFamilyFragment):
            raise RegistryConfigurationError(
                "mechanics registry fragments must be "
                "MechanicFamilyFragment values"
            )
        if not any(
            (
                fragment.ability_compilers,
                fragment.activity_handlers,
                fragment.compound_activity_handlers,
                fragment.host_activity_input_enrichers,
                fragment.controller_intent_descriptors,
                fragment.controller_actions,
                fragment.reaction_handlers,
                fragment.reaction_queue_handlers,
                fragment.post_event_hooks,
                fragment.pending_decision_handlers,
                fragment.post_action_result_hooks,
                fragment.turn_start_hooks,
                fragment.movement_exposures,
                fragment.event_renderers,
                fragment.spell_effect_handlers,
                fragment.public_state_projectors,
            )
        ):
            raise RegistryConfigurationError(
                f"family fragment has no registrations: {fragment.family_id!r}"
            )
        _add_unique(
            family_by_id,
            fragment.family_id,
            fragment,
            label="family id",
        )
        for mechanic_type in fragment.mechanic_types:
            _add_unique(
                mechanic_owners,
                mechanic_type,
                fragment.family_id,
                label="mechanic type",
            )

    ability_compilers: list[AbilityCompilerRegistration] = []
    compiler_by_id: dict[str, AbilityCompilerRegistration] = {}
    activity_handlers: dict[str, ActivityHandlerRegistration] = {}
    compound_activity_handlers: dict[
        str,
        CompoundActivityHandlerRegistration,
    ] = {}
    host_activity_input_enrichers: dict[
        str,
        HostActivityInputEnricherRegistration,
    ] = {}
    controller_intent_descriptors: dict[
        str,
        ControllerIntentDescriptorRegistration,
    ] = {}
    controller_action_descriptors: dict[
        str,
        ControllerActionRegistration,
    ] = {}
    controller_action_by_id: dict[str, ControllerActionRegistration] = {}
    reaction_handlers: dict[str, ReactionHandlerRegistration] = {}
    runtime_handler_kinds: dict[str, str] = {}
    reaction_queue_handlers: dict[
        str,
        ReactionQueueHandlerRegistration,
    ] = {}
    post_event_hooks: list[PostEventHookRegistration] = []
    post_event_hook_by_id: dict[str, PostEventHookRegistration] = {}
    pending_decision_handlers: dict[
        str,
        PendingDecisionHandlerRegistration,
    ] = {}
    post_action_result_hooks: list[
        PostActionResultHookRegistration,
    ] = []
    post_action_result_hook_by_id: dict[
        str,
        PostActionResultHookRegistration,
    ] = {}
    turn_start_hooks: list[TurnStartHookRegistration] = []
    turn_start_hook_by_id: dict[str, TurnStartHookRegistration] = {}
    movement_exposures: dict[str, MovementExposureRegistration] = {}
    battleground_adjudication_normalizers: dict[
        str,
        BattlegroundAdjudicationNormalizerRegistration,
    ] = {}
    state_validators: list[StateValidatorRegistration] = []
    state_validator_by_id: dict[str, StateValidatorRegistration] = {}
    spell_effect_handlers: dict[
        SpellEffectHandlerKey,
        SpellEffectHandlerRegistration,
    ] = {}
    event_renderers: dict[RendererKey, EventRendererRegistration] = {}
    public_state_projectors: list[PublicStateProjectorRegistration] = []
    public_state_projector_by_id: dict[
        str,
        PublicStateProjectorRegistration,
    ] = {}

    for fragment in ordered_fragments:
        referenced_mechanics: set[str] = set()
        for registration in fragment.ability_compilers:
            _require_registration(
                registration,
                AbilityCompilerRegistration,
                family_id=fragment.family_id,
                registration_kind="ability compiler",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="ability compiler",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                compiler_by_id,
                registration.compiler_id,
                registration,
                label="compiler id",
            )
            ability_compilers.append(registration)

        for registration in fragment.activity_handlers:
            _require_registration(
                registration,
                ActivityHandlerRegistration,
                family_id=fragment.family_id,
                registration_kind="activity handler",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="activity handler",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                activity_handlers,
                registration.mechanic_type,
                registration,
                label="activity handler key",
            )
            _add_unique(
                runtime_handler_kinds,
                registration.mechanic_type,
                "activity",
                label="runtime handler mechanic type",
            )

        for registration in fragment.compound_activity_handlers:
            _require_registration(
                registration,
                CompoundActivityHandlerRegistration,
                family_id=fragment.family_id,
                registration_kind="compound activity handler",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="compound activity handler",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                compound_activity_handlers,
                registration.mechanic_type,
                registration,
                label="compound activity handler key",
            )
            _add_unique(
                runtime_handler_kinds,
                registration.mechanic_type,
                "compound-activity",
                label="runtime handler mechanic type",
            )

        for registration in fragment.host_activity_input_enrichers:
            _require_registration(
                registration,
                HostActivityInputEnricherRegistration,
                family_id=fragment.family_id,
                registration_kind="host activity input enricher",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="host activity input enricher",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                host_activity_input_enrichers,
                registration.mechanic_type,
                registration,
                label="host activity input enricher key",
            )

        for registration in fragment.controller_intent_descriptors:
            _require_registration(
                registration,
                ControllerIntentDescriptorRegistration,
                family_id=fragment.family_id,
                registration_kind="controller intent descriptor",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="controller intent descriptor",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                controller_intent_descriptors,
                registration.mechanic_type,
                registration,
                label="controller intent descriptor key",
            )

        for registration in fragment.controller_actions:
            _require_registration(
                registration,
                ControllerActionRegistration,
                family_id=fragment.family_id,
                registration_kind="controller action",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="controller action",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                controller_action_descriptors,
                registration.action_type,
                registration,
                label="controller action type",
            )
            _add_unique(
                controller_action_by_id,
                registration.descriptor.action_id,
                registration,
                label="controller action ID",
            )

        for registration in fragment.reaction_handlers:
            _require_registration(
                registration,
                ReactionHandlerRegistration,
                family_id=fragment.family_id,
                registration_kind="reaction handler",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="reaction handler",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                reaction_handlers,
                registration.mechanic_type,
                registration,
                label="reaction handler key",
            )
            _add_unique(
                runtime_handler_kinds,
                registration.mechanic_type,
                "reaction",
                label="runtime handler mechanic type",
            )

        for registration in fragment.reaction_queue_handlers:
            _require_registration(
                registration,
                ReactionQueueHandlerRegistration,
                family_id=fragment.family_id,
                registration_kind="reaction queue handler",
            )
            _add_unique(
                reaction_queue_handlers,
                registration.queue_kind,
                registration,
                label="reaction queue handler key",
            )

        for registration in fragment.post_event_hooks:
            _require_registration(
                registration,
                PostEventHookRegistration,
                family_id=fragment.family_id,
                registration_kind="post-event hook",
            )
            _add_unique(
                post_event_hook_by_id,
                registration.hook_id,
                registration,
                label="post-event hook id",
            )
            post_event_hooks.append(registration)

        for registration in fragment.pending_decision_handlers:
            _require_registration(
                registration,
                PendingDecisionHandlerRegistration,
                family_id=fragment.family_id,
                registration_kind="pending decision handler",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="pending decision handler",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                pending_decision_handlers,
                registration.decision_type,
                registration,
                label="pending decision type",
            )

        for registration in fragment.post_action_result_hooks:
            _require_registration(
                registration,
                PostActionResultHookRegistration,
                family_id=fragment.family_id,
                registration_kind="post-action result hook",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="post-action result hook",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                post_action_result_hook_by_id,
                registration.hook_id,
                registration,
                label="post-action result hook id",
            )
            post_action_result_hooks.append(registration)

        for registration in fragment.turn_start_hooks:
            _require_registration(
                registration,
                TurnStartHookRegistration,
                family_id=fragment.family_id,
                registration_kind="turn-start hook",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="turn-start hook",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                turn_start_hook_by_id,
                registration.hook_id,
                registration,
                label="turn-start hook id",
            )
            turn_start_hooks.append(registration)

        for registration in fragment.movement_exposures:
            _require_registration(
                registration,
                MovementExposureRegistration,
                family_id=fragment.family_id,
                registration_kind="movement exposure",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="movement exposure",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                movement_exposures,
                registration.exposure_id,
                registration,
                label="movement exposure id",
            )

        for registration in fragment.battleground_adjudication_normalizers:
            _require_registration(
                registration,
                BattlegroundAdjudicationNormalizerRegistration,
                family_id=fragment.family_id,
                registration_kind="battleground adjudication normalizer",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="battleground adjudication normalizer",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                battleground_adjudication_normalizers,
                registration.adjudication_key,
                registration,
                label="battleground adjudication key",
            )

        for registration in fragment.state_validators:
            _require_registration(
                registration,
                StateValidatorRegistration,
                family_id=fragment.family_id,
                registration_kind="state validator",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="state validator",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                state_validator_by_id,
                registration.validator_id,
                registration,
                label="state validator id",
            )
            state_validators.append(registration)

        for registration in fragment.spell_effect_handlers:
            _require_registration(
                registration,
                SpellEffectHandlerRegistration,
                family_id=fragment.family_id,
                registration_kind="spell effect handler",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="spell effect handler",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                spell_effect_handlers,
                registration.key,
                registration,
                label="spell effect handler key",
            )

        for registration in fragment.event_renderers:
            _require_registration(
                registration,
                EventRendererRegistration,
                family_id=fragment.family_id,
                registration_kind="event renderer",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="event renderer",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                event_renderers,
                registration.key,
                registration,
                label="event renderer key",
            )

        for registration in fragment.public_state_projectors:
            _require_registration(
                registration,
                PublicStateProjectorRegistration,
                family_id=fragment.family_id,
                registration_kind="public state projector",
            )
            _require_owned_mechanic(
                fragment,
                registration.mechanic_type,
                registration_kind="public state projector",
            )
            referenced_mechanics.add(registration.mechanic_type)
            _add_unique(
                public_state_projector_by_id,
                registration.projector_id,
                registration,
                label="public state projector id",
            )
            public_state_projectors.append(registration)

        unregistered_mechanics = sorted(
            set(fragment.mechanic_types) - referenced_mechanics
        )
        if unregistered_mechanics:
            raise RegistryConfigurationError(
                f"family {fragment.family_id!r} has unregistered mechanic "
                f"types: {', '.join(repr(item) for item in unregistered_mechanics)}"
            )

    for mechanic_type in host_activity_input_enrichers:
        if (
            mechanic_type not in activity_handlers
            and mechanic_type not in compound_activity_handlers
        ):
            raise RegistryConfigurationError(
                "host activity input enricher lacks an activity handler: "
                f"{mechanic_type!r}"
            )
    for mechanic_type in controller_intent_descriptors:
        if (
            mechanic_type not in activity_handlers
            and mechanic_type not in compound_activity_handlers
        ):
            raise RegistryConfigurationError(
                "controller intent descriptor lacks an activity handler: "
                f"{mechanic_type!r}"
            )
        if mechanic_type not in host_activity_input_enrichers:
            raise RegistryConfigurationError(
                "controller intent descriptor lacks a host activity input "
                f"enricher: {mechanic_type!r}"
            )

    return _create_registry(
        families=ordered_fragments,
        family_by_id=family_by_id,
        mechanic_owners=mechanic_owners,
        ability_compilers=tuple(ability_compilers),
        activity_handlers=activity_handlers,
        compound_activity_handlers=compound_activity_handlers,
        host_activity_input_enrichers=host_activity_input_enrichers,
        controller_intent_descriptors=controller_intent_descriptors,
        controller_action_descriptors=controller_action_descriptors,
        reaction_handlers=reaction_handlers,
        reaction_queue_handlers=reaction_queue_handlers,
        post_event_hooks=tuple(post_event_hooks),
        pending_decision_handlers=pending_decision_handlers,
        post_action_result_hooks=tuple(post_action_result_hooks),
        turn_start_hooks=tuple(
            sorted(
                turn_start_hooks,
                key=lambda item: (item.ordinal, item.hook_id),
            )
        ),
        movement_exposures=movement_exposures,
        battleground_adjudication_normalizers=(
            battleground_adjudication_normalizers
        ),
        state_validators=tuple(
            sorted(
                state_validators,
                key=lambda item: item.validator_id,
            )
        ),
        spell_effect_handlers=spell_effect_handlers,
        event_renderers=event_renderers,
        public_state_projectors=tuple(
            sorted(
                public_state_projectors,
                key=lambda item: item.projector_id,
            )
        ),
    )



__all__ = [
    "MechanicRegistry",
    "RegistryConfigurationError",
    "build_registry",
]
