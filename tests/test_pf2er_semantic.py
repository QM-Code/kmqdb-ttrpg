from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from subdomains.ttrpg import pf2er_semantic
from subdomains.ttrpg.pf2er_compiler.mechanics import battle_cry
from subdomains.ttrpg.pf2er_compiler.mechanics.contracts import (
    RawSourceArray,
    RawSourceObject,
)
from subdomains.ttrpg.pf2er_compiler.mechanics.source_authority import (
    AuthoritySnapshot,
    authority_manifest_digest,
    text_sha256,
)
from subdomains.ttrpg.pf2er_compiler.source_authority_store import (
    SourceAuthorityStore,
)
from subdomains.ttrpg.semantic_compiler import SemanticCompilerSet
from subdomains.ttrpg.semantic_evidence import (
    SemanticEvidenceStore,
    canonical_digest,
)
from subdomains.ttrpg.semantic_package_builder import (
    SemanticPackageBuilderError,
    SourceCreatureTarget,
)
from subdomains.ttrpg.semantic_packages import (
    AssetRef,
    public_definition_acquisition_paths,
)


TTRPG_ROOT = Path(__file__).resolve().parents[1]
CACHE_DB = Path(
    os.environ.get(
        "KMQDB_TTRPG_TEST_CACHE_DB",
        TTRPG_ROOT / "cache" / "cache.db",
    )
).expanduser()
XULGATH_ICON_DIGEST = (
    "aa81ad330e38bf2f04521ce524ab07cc06add632bd9447edee529cb8a0a400f9"
)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(character: str) -> str:
    return character * 64


def _battle_cry_block() -> RawSourceObject:
    return RawSourceObject(
        (
            (
                "!.Battle Cry",
                RawSourceObject(
                    (
                        ("Action", "single"),
                        ("Traits", RawSourceArray(battle_cry.TRAITS)),
                        ("Description", battle_cry.DESCRIPTION),
                    )
                ),
            ),
        )
    )


def _compile_battle_cry(compiler_set: SemanticCompilerSet) -> dict:
    return compiler_set.compile_abilities(
        _battle_cry_block(),
        creature_name=battle_cry.CREATURE_NAME,
        source_id=battle_cry.SOURCE_ID,
        locator=battle_cry.LOCATOR,
    )[0]


def _authority():
    source_id = "core-mc1"
    source_payload = _json({"id": source_id, "name": "Monster Core"})
    content = _json({"privateRawSource": "TTRPG only"})
    section_id = "core-mc1:creatures"
    section_payload = _json(
        {"id": section_id, "source_id": source_id, "content": content}
    )
    source_toc = _json(
        [
            {
                "label": "Orc Commander",
                "locator": battle_cry.LOCATOR,
                "section_id": section_id,
                "content_path": [],
                "children": [],
            }
        ]
    )
    body = {
        "schema": 1,
        "ruleset": "pf2er",
        "sources": [
            {
                "id": source_id,
                "payloadSha256": text_sha256(source_payload),
                "tocSha256": text_sha256(source_toc),
            }
        ],
        "sections": [
            {
                "id": section_id,
                "sourceId": source_id,
                "payloadSha256": text_sha256(section_payload),
                "contentSha256": text_sha256(content),
            }
        ],
    }
    snapshot = AuthoritySnapshot.from_rows(
        {**body, "digest": authority_manifest_digest(body)},
        source_payloads={source_id: source_payload},
        source_tocs={source_id: source_toc},
        section_payloads={section_id: section_payload},
        section_source_ids={section_id: source_id},
    )
    return snapshot.adapter((source_id,))


class PF2ERSemanticCompositionTests(unittest.TestCase):
    def test_raw_source_adapter_selects_one_exact_book_and_fails_closed(self) -> None:
        both_selected = (
            "core-gmc",
            "core-pc1",
            "core-mc1",
            "core-mc2",
        )
        mc1 = pf2er_semantic.build_pf2er_creature_compiler_set_for_source(
            source_id="core-mc1",
            selected_source_ids=both_selected,
        )
        mc2 = pf2er_semantic.build_pf2er_creature_compiler_set_for_source(
            source_id="core-mc2",
            selected_source_ids=both_selected,
        )

        self.assertIn("battle-cry", mc1.registry.family_by_id)
        self.assertNotIn("conditions", mc1.registry.family_by_id)
        self.assertIn("conditions", mc2.registry.family_by_id)
        self.assertNotIn("battle-cry", mc2.registry.family_by_id)
        self.assertNotEqual(mc1.digest, mc2.digest)

        with self.assertRaisesRegex(
            pf2er_semantic.PF2ERSemanticCompositionError,
            "not selected",
        ):
            pf2er_semantic.build_pf2er_creature_compiler_set_for_source(
                source_id="core-mc2",
                selected_source_ids=("core-gmc", "core-pc1", "core-mc1"),
            )
        with self.assertRaisesRegex(
            pf2er_semantic.PF2ERSemanticCompositionError,
            "unsupported PF2ER creature compiler source",
        ):
            pf2er_semantic.build_pf2er_creature_compiler_set_for_source(
                source_id="how-pc1",
                selected_source_ids=("core-gmc", "core-pc1", "how-pc1"),
            )
        with self.assertRaisesRegex(
            pf2er_semantic.PF2ERSemanticCompositionError,
            "omit foundation",
        ):
            pf2er_semantic.build_pf2er_creature_compiler_set_for_source(
                source_id="core-mc1",
                selected_source_ids=("core-pc1", "core-mc1"),
            )

    def test_book_selection_is_exact_deterministic_and_coexistent(self) -> None:
        mc1 = pf2er_semantic.build_pf2er_semantic_compiler_set(
            book_ids=(pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
        )
        mc2 = pf2er_semantic.build_pf2er_semantic_compiler_set(
            book_ids=(pf2er_semantic.PF2ER_MONSTER_CORE_TWO_BOOK_ID,)
        )

        self.assertTrue(_compile_battle_cry(mc1)["supported"])
        self.assertFalse(_compile_battle_cry(mc2)["supported"])
        self.assertTrue(_compile_battle_cry(mc1)["supported"])
        self.assertIn("battle-cry", mc1.registry.family_by_id)
        self.assertNotIn("battle-cry", mc2.registry.family_by_id)
        self.assertNotIn("conditions", mc1.registry.family_by_id)
        self.assertIn("conditions", mc2.registry.family_by_id)
        self.assertIn("grapples", mc1.registry.family_by_id)
        self.assertIn("grapples", mc2.registry.family_by_id)

        first = pf2er_semantic.build_pf2er_semantic_compiler_set(
            book_ids=(
                pf2er_semantic.PF2ER_MONSTER_CORE_TWO_BOOK_ID,
                pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
            )
        )
        second = pf2er_semantic.build_pf2er_semantic_compiler_set(
            book_ids=(
                pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
                pf2er_semantic.PF2ER_MONSTER_CORE_TWO_BOOK_ID,
            )
        )
        self.assertEqual(first.canonical_manifest(), second.canonical_manifest())
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(
            first.digest,
            hashlib.sha256(first.canonical_manifest().encode()).hexdigest(),
        )

    def test_explicit_table_is_the_full_current_compiler_fragment_census(self) -> None:
        expected_family_ids = {
            "conditional-damage",
            "ferocity",
            "stride-strike",
            "gaze",
            "goblin-scuttle",
            "grapples",
            "reactive-strike",
            "conditions",
            "afflictions",
            "goblin-song",
            "battle-cry",
            "fungus-leshy-spores",
            "river-drake-caustic-mucus",
            "river-drake-draconic-frenzy",
            "river-drake-speed-surge",
            "grabbed-strike-activities",
            "kobold-construct-trap",
            "tail-lash",
            "biting-snakes",
            "giant-crab-scuttle",
            "cats-luck",
            "giant-amoeba-envelop",
            "shield-block",
            "animated-construct-armor",
            "gnome-bard",
            "warg",
            "giant-ant",
            "flash-beetle",
            "scarecrow",
            "stench",
            "ghoul",
            "plague-zombie-abilities",
            "damaging-strike-save-control",
            "zombie-rot",
        }
        family_ids = [
            fragment.family_id
            for fragment in pf2er_semantic.PF2ER_ALL_COMPILER_FRAGMENTS
        ]
        self.assertEqual(len(family_ids), len(set(family_ids)))
        self.assertEqual(set(family_ids), expected_family_ids)
        self.assertTrue(
            all(
                fragment.ability_compilers
                for fragment in pf2er_semantic.PF2ER_ALL_COMPILER_FRAGMENTS
            )
        )

        path = Path(pf2er_semantic.__file__).resolve()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse(
            [
                name
                for name in imported
                if "registry" in name
                or "gladiator" in name
                or "backend" in name
            ],
            imported,
        )
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("FAMILY_FRAGMENTS", text)
        self.assertNotIn("REGISTRY", text)
        self.assertNotIn("ABILITY_COMPILERS", text)

    def test_invalid_or_unselected_books_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            pf2er_semantic.PF2ERSemanticCompositionError,
            "unsupported PF2ER book",
        ):
            pf2er_semantic.build_pf2er_semantic_compiler_set(
                book_ids=("paizo:unselected-adventure",)
            )
        with self.assertRaisesRegex(
            pf2er_semantic.PF2ERSemanticCompositionError,
            "duplicates",
        ):
            pf2er_semantic.build_pf2er_semantic_compiler_set(
                book_ids=(
                    pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
                    pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
                )
            )

        mc2 = pf2er_semantic.build_pf2er_semantic_compiler_set(
            book_ids=(pf2er_semantic.PF2ER_MONSTER_CORE_TWO_BOOK_ID,)
        )
        with self.assertRaisesRegex(
            SemanticPackageBuilderError,
            "not selected by the compiler set",
        ):
            pf2er_semantic.build_pf2er_creature_semantic_package(
                authority=_authority(),
                compiler_set=mc2,
                book_id=pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
                ruleset_digest=_digest("1"),
                book_digest=_digest("2"),
                semantic_generation="ttrpg:monster-core-one-generation-1",
                evidence_store=SemanticEvidenceStore(),
                creatures=(
                    SourceCreatureTarget(
                        "pf2er:orc-commander",
                        "core-mc1",
                        battle_cry.LOCATOR,
                    ),
                ),
            )

    def test_authenticated_package_builder_handoff_uses_selected_book(self) -> None:
        authority = _authority()
        compiler_set = pf2er_semantic.build_pf2er_semantic_compiler_set(
            book_ids=(pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
        )
        target = SourceCreatureTarget(
            "pf2er:orc-commander",
            "core-mc1",
            battle_cry.LOCATOR,
        )

        with patch.object(
            SemanticCompilerSet,
            "compile_source_creature",
            autospec=True,
            return_value={
                "schema": 1,
                "id": "core-mc1:259.3",
                "name": "Orc Commander",
                "level": 2,
                "space": {
                    "widthSquares": 1,
                    "heightSquares": 1,
                    "defaultReachFeet": 5,
                },
                "defenses": {"maximumHitPoints": 30},
                "inventory": [],
                "strikes": [],
                "abilities": [],
            },
        ) as compile_creature:
            package = pf2er_semantic.build_pf2er_creature_semantic_package(
                authority=authority,
                compiler_set=compiler_set,
                book_id=pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
                ruleset_digest=_digest("1"),
                book_digest=_digest("2"),
                semantic_generation="ttrpg:monster-core-one-generation-1",
                evidence_store=SemanticEvidenceStore(),
                creatures=(target,),
            )

        self.assertEqual(
            package.package_id,
            pf2er_semantic.PF2ER_MONSTER_CORE_ONE_PACKAGE_ID,
        )
        self.assertEqual(package.ruleset_id, pf2er_semantic.PF2ER_RULESET_ID)
        self.assertEqual(
            package.book_id,
            pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
        )
        self.assertEqual(package.compiler_digest, compiler_set.digest)
        self.assertNotEqual(
            package.semantic_generation_digest, authority.snapshot.digest
        )
        self.assertEqual(
            package.entity("pf2er:orc-commander").definition["id"],
            "pf2er:orc-commander",
        )
        self.assertEqual(
            package.entity("pf2er:orc-commander").definition["schema"],
            2,
        )
        self.assertEqual(
            package.entity("pf2er:orc-commander").definition["kind"],
            "pf2er-creature",
        )
        compile_creature.assert_called_once_with(
            compiler_set,
            authority,
            "core-mc1",
            battle_cry.LOCATOR,
        )

    def test_pf2er_projector_rejects_untranslated_compiler_evidence(self) -> None:
        authority = _authority()
        compiler_set = pf2er_semantic.build_pf2er_semantic_compiler_set(
            book_ids=(pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
        )
        evidence_store = SemanticEvidenceStore()
        with patch.object(
            SemanticCompilerSet,
            "compile_source_creature",
            autospec=True,
            return_value={
                "schema": 1,
                "id": "core-mc1:259.3",
                "name": "Orc Commander",
                "source": {
                    "sourceId": "core-mc1",
                    "locator": "259.3",
                    "sectionId": "core-mc1:orc",
                    "contentPath": ["Orc", "Orc Commander"],
                },
                "icon": "core/mc1/creatures/x128/Orc Commander",
                "level": 2,
                "space": {
                    "widthSquares": 1,
                    "heightSquares": 1,
                    "defaultReachFeet": 5,
                },
                "defenses": {"maximumHitPoints": 30},
                "inventory": [],
                "strikes": [],
                "abilities": [],
            },
        ):
            with self.assertRaisesRegex(
                SemanticPackageBuilderError,
                "icon lacks a reviewed opaque asset binding",
            ):
                pf2er_semantic.build_pf2er_creature_semantic_package(
                    authority=authority,
                    compiler_set=compiler_set,
                    book_id=pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
                    ruleset_digest=_digest("1"),
                    book_digest=_digest("2"),
                    semantic_generation="ttrpg:monster-core-one-generation-1",
                    creatures=(
                        SourceCreatureTarget(
                            "pf2er:orc-commander",
                            "core-mc1",
                            battle_cry.LOCATOR,
                        ),
                    ),
                    evidence_store=evidence_store,
                )
        self.assertEqual(evidence_store.inventory_projection()["records"], [])

    def test_xulgath_binding_is_explicit_while_stench_capability_is_reusable(self) -> None:
        authority = _authority()
        compiler_set = pf2er_semantic.build_pf2er_semantic_compiler_set(
            book_ids=(pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
        )
        common = {
            "authority": authority,
            "compiler_set": compiler_set,
            "book_id": pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
            "ruleset_digest": _digest("1"),
            "book_digest": _digest("2"),
            "semantic_generation": "ttrpg:xulgath-semantic-generation-1",
            "evidence_store": SemanticEvidenceStore(),
        }
        xulgath_without_capability = SourceCreatureTarget(
            pf2er_semantic.PF2ER_XULGATH_WARRIOR_ENTITY_ID,
            "core-mc1",
            "352.3",
        )
        with self.assertRaisesRegex(
            pf2er_semantic.PF2ERSemanticCompositionError,
            "requires exactly the reviewed Stench lifecycle capability",
        ):
            pf2er_semantic.build_pf2er_creature_semantic_package(
                **common,
                creatures=(xulgath_without_capability,),
                relationships=(
                    pf2er_semantic.PF2ER_XULGATH_STENCH_RELATIONSHIP,
                ),
            )

        xulgath = SourceCreatureTarget(
            pf2er_semantic.PF2ER_XULGATH_WARRIOR_ENTITY_ID,
            "core-mc1",
            "352.3",
            required_capabilities=(
                pf2er_semantic.PF2ER_STENCH_LIFECYCLE_CAPABILITY,
            ),
        )
        with self.assertRaisesRegex(
            pf2er_semantic.PF2ERSemanticCompositionError,
            "requires exactly the reviewed Stench provider/carrier relationship",
        ):
            pf2er_semantic.build_pf2er_creature_semantic_package(
                **common,
                creatures=(xulgath,),
            )

        non_xulgath = SourceCreatureTarget(
            "pf2er:orc-commander",
            "core-mc1",
            battle_cry.LOCATOR,
            required_capabilities=(
                pf2er_semantic.PF2ER_STENCH_LIFECYCLE_CAPABILITY,
            ),
        )
        with patch.object(
            SemanticCompilerSet,
            "compile_source_creature",
            autospec=True,
            return_value={
                "schema": 1,
                "id": "core-mc1:259.3",
                "name": "Orc Commander",
                "level": 2,
                "space": {
                    "widthSquares": 1,
                    "heightSquares": 1,
                    "defaultReachFeet": 5,
                },
                "defenses": {"maximumHitPoints": 30},
                "inventory": [],
                "strikes": [],
                "abilities": [],
            },
        ):
            package = pf2er_semantic.build_pf2er_creature_semantic_package(
                **common,
                creatures=(non_xulgath,),
            )
        self.assertEqual(
            package.entity("pf2er:orc-commander").required_capabilities,
            (pf2er_semantic.PF2ER_STENCH_LIFECYCLE_CAPABILITY,),
        )
        self.assertEqual(package.relationships, ())


@unittest.skipUnless(
    CACHE_DB.is_file(),
    "live TTRPG source cache is unavailable; set KMQDB_TTRPG_TEST_CACHE_DB",
)
class PF2ERXulgathSemanticProjectionTests(unittest.TestCase):
    def test_live_xulgath_projection_is_source_free_and_evidence_linked(self) -> None:
        authority = SourceAuthorityStore.from_path(CACHE_DB).adapter_for(
            ("core-gmc", "core-mc1", "core-pc1")
        )
        compiler_set = pf2er_semantic.build_pf2er_semantic_compiler_set(
            book_ids=(pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
        )
        raw_definition = compiler_set.compile_source_creature(
            authority,
            "core-mc1",
            "352.3",
        )
        self.assertIn("source", raw_definition)
        self.assertIn("statCompilation", raw_definition)
        self.assertIn("sourceText", raw_definition["inventory"][0])

        evidence_store = SemanticEvidenceStore()
        target = SourceCreatureTarget(
            pf2er_semantic.PF2ER_XULGATH_WARRIOR_ENTITY_ID,
            "core-mc1",
            "352.3",
            required_capabilities=(
                pf2er_semantic.PF2ER_STENCH_LIFECYCLE_CAPABILITY,
            ),
            asset_refs=(
                AssetRef(
                    pf2er_semantic.PF2ER_XULGATH_WARRIOR_ICON_ASSET_ID,
                    XULGATH_ICON_DIGEST,
                ),
            ),
        )
        with patch.object(
            SemanticCompilerSet,
            "compile_source_creature",
            autospec=True,
            return_value=raw_definition,
        ):
            package = pf2er_semantic.build_pf2er_creature_semantic_package(
                authority=authority,
                compiler_set=compiler_set,
                book_id=pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
                ruleset_digest=_digest("3"),
                book_digest=_digest("4"),
                semantic_generation="ttrpg:xulgath-semantic-generation-1",
                creatures=(target,),
                evidence_store=evidence_store,
                relationships=(
                    pf2er_semantic.PF2ER_XULGATH_STENCH_RELATIONSHIP,
                ),
            )

        entity = package.entity(
            pf2er_semantic.PF2ER_XULGATH_WARRIOR_ENTITY_ID
        )
        definition = entity.definition
        self.assertEqual(definition["schema"], 2)
        self.assertEqual(definition["kind"], "pf2er-creature")
        self.assertEqual(
            definition["inventory"],
            [
                {"itemEntityId": "pf2er:item.club", "quantity": 1},
                {"itemEntityId": "pf2er:item.javelin", "quantity": 3},
            ],
        )
        self.assertEqual(
            definition["presentation"],
            {
                "iconAssetId": (
                    pf2er_semantic.PF2ER_XULGATH_WARRIOR_ICON_ASSET_ID
                )
            },
        )
        self.assertEqual(
            [item.to_dict() for item in entity.asset_refs],
            [
                {
                    "assetId": (
                        pf2er_semantic.PF2ER_XULGATH_WARRIOR_ICON_ASSET_ID
                    ),
                    "assetDigest": XULGATH_ICON_DIGEST,
                }
            ],
        )
        self.assertEqual(
            [item.to_dict() for item in entity.required_capabilities],
            [
                {
                    "capabilityId": "gladiator:pf2er-stench-lifecycle",
                    "contractVersion": "1.0.0",
                }
            ],
        )
        self.assertEqual(
            [item.to_dict() for item in package.relationships],
            [
                {
                    "relationshipId": "ttrpg:xulgath-warrior-stench-carrier",
                    "providerEntityId": "pf2er.rule:xulgath-warrior-stench",
                    "carrierEntityId": "pf2er:xulgath-warrior",
                }
            ],
        )

        attacks = {
            strike["id"]: strike["attackSource"]
            for strike in definition["strikes"]
        }
        self.assertEqual(
            attacks,
            {
                "strike:club:melee": {
                    "kind": "item",
                    "itemEntityId": "pf2er:item.club",
                },
                "strike:club:ranged": {
                    "kind": "item",
                    "itemEntityId": "pf2er:item.club",
                },
                "strike:javelin:ranged": {
                    "kind": "item",
                    "itemEntityId": "pf2er:item.javelin",
                },
                "strike:jaws:melee": {"kind": "natural"},
                "strike:claw:melee": {"kind": "natural"},
            },
        )
        used_rule_refs: set[str] = set()

        def collect_rule_refs(value: object) -> None:
            if type(value) is dict:
                rule_ref = value.get("ruleRef")
                if type(rule_ref) is str:
                    used_rule_refs.add(rule_ref)
                role_refs = value.get("ruleRefs")
                if type(role_refs) is dict:
                    used_rule_refs.update(role_refs.values())
                for child in value.values():
                    collect_rule_refs(child)
            elif type(value) is list:
                for child in value:
                    collect_rule_refs(child)

        collect_rule_refs(definition)
        self.assertEqual(
            used_rule_refs,
            set(definition["references"]["rules"]),
        )
        self.assertEqual(
            definition["references"]["items"],
            ["pf2er:item.club", "pf2er:item.javelin"],
        )
        self.assertEqual(public_definition_acquisition_paths(definition), ())
        self.assertNotIn("source", definition)
        self.assertNotIn("statCompilation", definition)
        self.assertNotIn("icon", definition)
        public_json = _json(definition)
        for acquisition_key in (
            "contentPath",
            "locator",
            "sectionId",
            "sourceAddressSha256",
            "sourceDeferredDependencies",
            "sourceId",
            "sourceOccurrenceId",
            "sourceSpan",
            "sourceText",
            "sourceToken",
        ):
            with self.subTest(acquisition_key=acquisition_key):
                self.assertNotIn(f'"{acquisition_key}"', public_json)

        evidence_inventory = evidence_store.inventory_projection()["records"]
        self.assertEqual(len(evidence_inventory), 1)
        evidence = evidence_store.record(evidence_inventory[0]).to_dict()
        self.assertEqual(
            evidence["rawDefinitionDigest"],
            canonical_digest(raw_definition, "raw compiler definition"),
        )
        self.assertEqual(
            evidence["projectedDefinitionDigest"],
            entity.definition_digest,
        )
        self.assertEqual(
            evidence["compilerReceipt"]["projection"],
            {
                "schema": 1,
                "packageId": pf2er_semantic.PF2ER_MONSTER_CORE_ONE_PACKAGE_ID,
                "packageVersion": "1.0.0",
                "projectionId": pf2er_semantic.PF2ER_CREATURE_PROJECTION_ID,
                "projectionVersion": "2.0.0",
                "definitionSchema": 2,
            },
        )
        private_receipt_json = _json(evidence["acquisitionReceipt"])
        self.assertIn("core-mc1", private_receipt_json)
        self.assertIn("352.3", private_receipt_json)


if __name__ == "__main__":
    unittest.main()
