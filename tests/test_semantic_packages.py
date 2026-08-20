from __future__ import annotations

from copy import deepcopy
import json
import unittest

from subdomains.ttrpg.semantic_packages import (
    AssetRef,
    CapabilityRequirement,
    ProviderCarrierRelationship,
    SemanticEntity,
    SemanticPackage,
    SemanticPackageError,
    SemanticReceipt,
    build_semantic_entity,
    build_semantic_package,
)


def _digest(character: str) -> str:
    return character * 64


def _evidence(character: str = "a") -> dict[str, str]:
    return {
        "evidence_authority_id": "ttrpg:test-semantic-evidence",
        "evidence_record_digest": _digest(character),
        "compiler_digest": _digest("4"),
        "raw_definition_digest": _digest("5"),
        "projection_id": "ttrpg:test-source-free-projector",
        "projection_version": "1.0.0",
        "projection_digest": _digest("6"),
    }


def _entity(
    entity_id: str,
    name: str,
    *,
    kind: str = "ttrpg:creature",
) -> SemanticEntity:
    return build_semantic_entity(
        entity_id=entity_id,
        entity_kind=kind,
        definition={
            "name": name,
            "level": 1,
            "actions": [{"id": "pf2er:strike", "traits": ["attack"]}],
            "abilities": (
                [{"id": "darkvision", "ruleRef": "pf2er:darkvision"}]
                if entity_id == "pf2er:goblin-warrior"
                else []
            ),
        },
        **_evidence(),
        required_capabilities=(
            CapabilityRequirement("gladiator:pf2er-strike", "1.0.0"),
        ),
        asset_refs=(
            AssetRef(f"ttrpg:{name.lower().replace(' ', '-')}-portrait", _digest("b")),
        ),
    )


def _package_with_relationships(
    entities: tuple[SemanticEntity, ...],
    relationships: tuple[ProviderCarrierRelationship, ...],
) -> SemanticPackage:
    return build_semantic_package(
        package_id="ttrpg:pf2er-monster-core",
        version="1.0.0",
        ruleset_id="paizo:pf2er",
        ruleset_digest=_digest("1"),
        book_id="paizo:monster-core",
        book_digest=_digest("2"),
        semantic_generation="ttrpg:monster-core-generation-7",
        semantic_generation_digest=_digest("3"),
        compiler_id="ttrpg:pf2er-creature-compiler",
        compiler_version="1.0.0",
        compiler_digest=_digest("4"),
        entities=entities,
        relationships=relationships,
    )


def _package(*entities: SemanticEntity) -> SemanticPackage:
    return _package_with_relationships(
        entities,
        (
            ProviderCarrierRelationship(
                "ttrpg:darkvision-grant",
                "pf2er:darkvision",
                "pf2er:goblin-warrior",
            ),
        ),
    )


class SemanticPackageTests(unittest.TestCase):
    def test_relationship_endpoints_and_unique_provider_claims_are_closed(
        self,
    ) -> None:
        provider = _entity(
            "pf2er:slink", "Slink", kind="ttrpg:creature-ability"
        )
        carrier = _entity("pf2er:viper", "Viper")
        rogue = _entity("pf2er:rogue-viper", "Rogue Viper")
        relationship = ProviderCarrierRelationship(
            "ttrpg:viper-slink", "pf2er:slink", "pf2er:viper"
        )
        cases = (
            ((provider,), relationship, "carrier must be an exact creature"),
            (
                (carrier,),
                ProviderCarrierRelationship(
                    "ttrpg:viper-missing",
                    "pf2er.rule:missing",
                    "pf2er:viper",
                ),
                "carrier-local semantic rule provider",
            ),
            (
                (provider, carrier),
                relationship,
                "declared exactly once",
            ),
        )
        for entities, relation, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(SemanticPackageError, message):
                    _package_with_relationships(entities, (relation,))

        provider_claim = {
            "entityId": "pf2er:slink",
            "kind": "creature-ability",
        }
        carrier = build_semantic_entity(
            entity_id="pf2er:viper",
            entity_kind="ttrpg:creature",
            definition={"name": "Viper", "abilities": [provider_claim]},
            **_evidence(),
        )
        rogue = build_semantic_entity(
            entity_id="pf2er:rogue-viper",
            entity_kind="ttrpg:creature",
            definition={"name": "Rogue", "abilities": [provider_claim]},
            **_evidence("c"),
        )
        with self.assertRaisesRegex(SemanticPackageError, "only its relationship carrier"):
            _package_with_relationships(
                (provider, carrier, rogue), (relationship,)
            )

    def test_existing_carrier_local_rule_provider_remains_valid(self) -> None:
        package = _package(_entity("pf2er:goblin-warrior", "Goblin"))
        self.assertEqual(
            package.relationships[0].provider_entity_id,
            "pf2er:darkvision",
        )

    def test_digest_bound_contracts_cannot_be_constructed_directly(self) -> None:
        for contract in (SemanticReceipt, SemanticEntity, SemanticPackage):
            with self.subTest(contract=contract.__name__):
                with self.assertRaisesRegex(TypeError, "created through their builders"):
                    contract()  # type: ignore[call-arg]

    def test_package_is_deterministic_and_round_trips_canonically(self) -> None:
        goblin = _entity("pf2er:goblin-warrior", "Goblin")
        leopard = _entity("pf2er:leopard", "Leopard")

        first = _package(goblin, leopard)
        second = _package(leopard, goblin)
        loaded = SemanticPackage.from_dict(json.loads(first.canonical_json()))

        self.assertEqual(first.package_digest, second.package_digest)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(loaded.canonical_json(), first.canonical_json())
        self.assertRegex(first.package_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(
            [item["entityId"] for item in first.to_dict()["entities"]],
            ["pf2er:goblin-warrior", "pf2er:leopard"],
        )

    def test_lookup_returns_only_the_selected_namespaced_entity(self) -> None:
        goblin = _entity("pf2er:goblin-warrior", "Goblin")
        leopard = _entity("pf2er:leopard", "Leopard")
        package = _package(goblin, leopard)

        selected = package.entity("pf2er:leopard")
        self.assertEqual(selected.definition["name"], "Leopard")
        with self.assertRaises(KeyError):
            package.entity("pf2er:wolf")
        with self.assertRaisesRegex(SemanticPackageError, "namespaced ID"):
            package.entity("Leopard")

    def test_rejects_duplicate_entity_ids_and_relationships(self) -> None:
        goblin = _entity("pf2er:goblin-warrior", "Goblin")
        duplicate = _entity("pf2er:goblin-warrior", "Other Goblin")
        with self.assertRaisesRegex(SemanticPackageError, "duplicate entity IDs"):
            _package(goblin, duplicate)

        relationship = ProviderCarrierRelationship(
            "ttrpg:darkvision-grant", "pf2er:darkvision", "pf2er:goblin-warrior"
        )
        with self.assertRaisesRegex(SemanticPackageError, "contains duplicates"):
            build_semantic_package(
                package_id="ttrpg:pf2er-monster-core",
                version="1.0.0",
                ruleset_id="paizo:pf2er",
                ruleset_digest=_digest("1"),
                book_id="paizo:monster-core",
                book_digest=_digest("2"),
                semantic_generation="ttrpg:monster-core-generation-7",
                semantic_generation_digest=_digest("3"),
                compiler_id="ttrpg:pf2er-creature-compiler",
                compiler_version="1.0.0",
                compiler_digest=_digest("4"),
                entities=(goblin,),
                relationships=(relationship, relationship),
            )

    def test_malformed_and_non_json_definitions_fail_closed(self) -> None:
        with self.assertRaisesRegex(SemanticPackageError, "namespaced ID"):
            _entity("Goblin Warrior", "Goblin")
        with self.assertRaisesRegex(SemanticPackageError, "strict JSON-compatible"):
            build_semantic_entity(
                entity_id="pf2er:goblin-warrior",
                entity_kind="ttrpg:creature",
                definition={"traits": ("goblin",)},  # type: ignore[dict-item]
                **_evidence(),
            )
        with self.assertRaisesRegex(SemanticPackageError, "non-finite"):
            build_semantic_entity(
                entity_id="pf2er:goblin-warrior",
                entity_kind="ttrpg:creature",
                definition={"level": float("nan")},
                **_evidence(),
            )

    def test_definition_receipt_and_package_tampering_is_rejected(self) -> None:
        packet = _package(_entity("pf2er:goblin-warrior", "Goblin")).to_dict()

        changed_definition = deepcopy(packet)
        changed_definition["entities"][0]["definition"]["level"] = 2
        with self.assertRaisesRegex(SemanticPackageError, "definition digest mismatch"):
            SemanticPackage.from_dict(changed_definition)

        changed_provenance = deepcopy(packet)
        changed_provenance["entities"][0]["receipt"][
            "evidenceRecordDigest"
        ] = _digest("9")
        with self.assertRaisesRegex(
            SemanticPackageError, "semantic receipt digest mismatch"
        ):
            SemanticPackage.from_dict(changed_provenance)

        changed_metadata = deepcopy(packet)
        changed_metadata["compilerDigest"] = _digest("5")
        with self.assertRaisesRegex(
            SemanticPackageError,
            "compiler digest disagrees with its package",
        ):
            SemanticPackage.from_dict(changed_metadata)

        malformed = deepcopy(packet)
        malformed["unexpected"] = True
        with self.assertRaisesRegex(SemanticPackageError, "must have exactly"):
            SemanticPackage.from_dict(malformed)

    def test_entity_receipt_chain_is_sealed_into_the_package(self) -> None:
        goblin = _entity("pf2er:goblin-warrior", "Goblin")
        package = _package(goblin)
        receipt = package.entity(goblin.entity_id).receipt

        self.assertEqual(
            receipt.projected_definition_digest, goblin.definition_digest
        )
        self.assertRegex(receipt.evidence_record_digest, r"^[0-9a-f]{64}$")
        self.assertRegex(receipt.semantic_receipt_digest, r"^[0-9a-f]{64}$")
        packet = package.to_dict()
        serialized = packet["entities"][0]["receipt"]
        self.assertEqual(
            serialized["semanticReceiptDigest"], receipt.semantic_receipt_digest
        )

        alternate = build_semantic_entity(
            entity_id=goblin.entity_id,
            entity_kind=goblin.entity_kind,
            definition=goblin.definition,
            **_evidence("b"),
            required_capabilities=goblin.required_capabilities,
            asset_refs=goblin.asset_refs,
        )
        self.assertEqual(alternate.definition_digest, goblin.definition_digest)
        self.assertNotEqual(
            alternate.receipt.semantic_receipt_digest,
            goblin.receipt.semantic_receipt_digest,
        )
        self.assertNotEqual(_package(alternate).package_digest, package.package_digest)


if __name__ == "__main__":
    unittest.main()
