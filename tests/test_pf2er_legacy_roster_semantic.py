from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import pf2er_legacy_roster_semantic as roster_semantic
from scripts import build_pf2er_legacy_roster_publication as roster_publication
from subdomains.ttrpg.pf2er_compiler.source_authority_store import (
    SourceAuthorityStore,
)
from subdomains.ttrpg.pf2er_compiler.source import source_creature_description
from subdomains.ttrpg.pf2er_compiler import source as pf2er_source
from subdomains.ttrpg.pf2er_compiler import errors as pf2er_errors
from subdomains.ttrpg.pf2er_compiler.mechanics.contracts import RawSourceObject
from subdomains.ttrpg.pf2er_semantic import (
    PF2ER_MONSTER_CORE_ONE_BOOK_ID,
    build_pf2er_semantic_compiler_set,
)
from subdomains.ttrpg.semantic_evidence import SemanticEvidenceStore
from subdomains.ttrpg.semantic_assets import SemanticAssetArtifact
from subdomains.ttrpg.semantic_packages import (
    AssetRef,
    SemanticPackage,
    public_definition_acquisition_paths,
)


TTRPG_ROOT = Path(__file__).resolve().parents[1]
CACHE_DB = Path(
    os.environ.get(
        "KMQDB_TTRPG_TEST_CACHE_DB",
        TTRPG_ROOT / "cache" / "cache.db",
    )
).expanduser()
PRESENTATION_CACHE_DB = Path(
    os.environ.get(
        "KMQDB_TTRPG_TEST_PRESENTATION_CACHE_DB",
        TTRPG_ROOT / "cache" / "presentation-cache.db",
    )
).expanduser()
PORTRAIT_ROOT = Path(
    os.environ.get(
        "KMQDB_TTRPG_TEST_PORTRAIT_ROOT",
        TTRPG_ROOT / "cache" / "legacy-roster-portraits",
    )
).expanduser()
LIBRARY_ASSET_ROOT = Path(
    os.environ.get(
        "KMQDB_TTRPG_TEST_LIBRARY_ASSET_ROOT",
        TTRPG_ROOT / "cache" / "library-source-assets",
    )
).expanduser()
PRIOR_PUBLICATION_ROOT = Path(
    os.environ.get(
        "KMQDB_TTRPG_TEST_PRIOR_PUBLICATION_ROOT",
        TTRPG_ROOT / "work" / "legacy-roster-baseline-publication",
    )
).expanduser()
EXPECTED_PACKAGE_DIGEST = (
    "5bcd84c073831e8bb94236445dc43720e9aa5adf6089047a7ee780efd5133f85"
)


class PF2ERLegacyRosterTargetTests(unittest.TestCase):
    def test_exact_91_entity_census_is_unique_and_excludes_reviewed_lanes(self) -> None:
        targets = roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
        self.assertEqual(len(targets), 91)
        self.assertEqual(len({target.entity_id for target in targets}), 91)
        self.assertEqual(
            len({target.legacy_source_address for target in targets}),
            91,
        )
        self.assertTrue(
            all(
                target.legacy_source_address.startswith("core-mc1:")
                for target in targets
            )
        )
        self.assertTrue(
            {"pf2er:hadrosaurid", "pf2er:viper", "pf2er:xulgath-warrior"}
            .isdisjoint(target.entity_id for target in targets)
        )

    def test_only_three_private_locator_reconnections_are_declared(self) -> None:
        corrected = {
            target.legacy_source_address: (
                f"core-mc1:{target.current_locator}"
            )
            for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
            if target.legacy_locator != target.current_locator
        }
        self.assertEqual(
            corrected,
            {
                "core-mc1:312.2": "core-mc1:312.4",
                "core-mc1:312.4": "core-mc1:312.6",
                "core-mc1:313.5": "core-mc1:313.6",
            },
        )

    def test_portable_spellcasting_projection_is_source_free_and_capability_bound(
        self,
    ) -> None:
        target = next(
            item
            for item in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
            if item.entity_id == "pf2er:gnome-bard"
        )
        profile_id, spell_ids = roster_semantic._EXECUTABLE_SPELLCASTING_TARGETS[
            target.entity_id
        ]
        execution = {
            "executable": True,
            "status": "active",
            "runtimeSupported": True,
            "runtimeDependencies": [],
        }
        raw_plan = {
            "schema": 1,
            "kind": "pf2er-creature-spellcasting-plan",
            "runtimeActivation": {
                "status": "active",
                "executableSpellIds": list(spell_ids),
            },
            "casting": {
                "id": "spellcasting:occult",
                "mode": "spontaneous",
                "tradition": "occult",
                "dc": 17,
                "attack": 7,
                "slots": [],
                "cantrips": {"rank": 1, "spellIds": list(spell_ids)},
            },
            "spells": [
                {
                    "id": spell_id,
                    "name": spell_id.replace("-", " ").title(),
                    "rank": 1,
                    "kind": "cantrip",
                    "actionCost": 2,
                    "rawActionCost": "two",
                    "actionVariants": [2],
                    "traits": [],
                    "traditions": ["occult"],
                    "compiledEffect": {
                        "duration": {
                            "rounds": 1,
                            "source": "1 round",
                        }
                    },
                    "execution": execution,
                }
                for spell_id in spell_ids
            ],
        }

        projected = roster_semantic._project_executable_spellcasting(
            raw_plan,
            target,
        )

        self.assertEqual(projected["schema"], 2)
        self.assertEqual(projected["runtimeProfileId"], profile_id)
        self.assertEqual(
            projected["runtimeActivation"]["executableSpellIds"],
            list(spell_ids),
        )
        self.assertEqual(public_definition_acquisition_paths(projected), ())
        self.assertNotIn(
            '"source":',
            json.dumps(projected, sort_keys=True, separators=(",", ":")),
        )
        self.assertEqual(
            projected["spells"][0]["compiledEffect"]["duration"],
            {"rounds": 1, "sourceUnit": "1 round"},
        )
        self.assertEqual(
            roster_semantic._EXECUTABLE_SPELLCASTING_CAPABILITIES[
                target.entity_id
            ],
            (
                roster_semantic.PF2ER_LEGACY_ROSTER_SUMMON_INSTRUMENT_CAPABILITY,
            ),
        )

    def test_generic_description_remains_ambiguous_article_fail_closed(self) -> None:
        description = RawSourceObject.from_pairs(
            [
                ("Family One", RawSourceObject.from_pairs([("~.p", "one")])),
                ("Family Two", RawSourceObject.from_pairs([("~.p", "two")])),
            ]
        )
        block = RawSourceObject.from_pairs([("Description", description)])
        with self.assertRaisesRegex(
            pf2er_errors.EngineInputError,
            "must contain exactly one article",
        ):
            pf2er_source._creature_description_text(block, "Creature")


@unittest.skipUnless(
    CACHE_DB.is_file()
    and (
        (
            PRESENTATION_CACHE_DB.is_file()
            and PORTRAIT_ROOT.is_dir()
            and LIBRARY_ASSET_ROOT.is_dir()
        )
        or (
            PRIOR_PUBLICATION_ROOT.is_dir()
            and (PRIOR_PUBLICATION_ROOT / "bundle").is_dir()
        )
    ),
    "live publication inputs unavailable; set KMQDB_TTRPG_TEST_CACHE_DB, "
    "KMQDB_TTRPG_TEST_PRESENTATION_CACHE_DB, "
    "KMQDB_TTRPG_TEST_PORTRAIT_ROOT, and "
    "KMQDB_TTRPG_TEST_LIBRARY_ASSET_ROOT, or set "
    "KMQDB_TTRPG_TEST_PRIOR_PUBLICATION_ROOT",
)
class PF2ERLegacyRosterPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = SourceAuthorityStore.from_path(CACHE_DB)
        cls.authority = cls.store.adapter_for(
            ("core-gmc", "core-mc1", "core-pc1")
        )
        cls.compiler = build_pf2er_semantic_compiler_set(
            book_ids=(PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
        )
        cls.evidence = SemanticEvidenceStore()
        if (
            PRESENTATION_CACHE_DB.is_file()
            and PORTRAIT_ROOT.is_dir()
            and LIBRARY_ASSET_ROOT.is_dir()
        ):
            (
                cls.portrait_refs,
                cls.portrait_artifacts,
                cls.portrait_manifest,
            ) = roster_publication._portrait_inventory(PORTRAIT_ROOT)
            presentation_targets = [
                (target.entity_id, target.name, target.current_locator)
                for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
            ]
            presentation_targets.extend(
                (
                    entity_id,
                    roster_publication.REVIEWED_PORTRAIT_NAMES[entity_id],
                    locator,
                )
                for entity_id, locator in sorted(
                    roster_publication.REVIEWED_SOURCE_LOCATORS.items()
                )
            )
            (
                cls.source_presentations,
                cls.source_presentation_artifacts,
                cls.source_presentation_audit,
            ) = roster_publication.build_roster_source_presentations(
                cache_path=PRESENTATION_CACHE_DB,
                targets=presentation_targets,
                library_asset_root=LIBRARY_ASSET_ROOT,
            )
        else:
            package_path = (
                PRIOR_PUBLICATION_ROOT
                / "bundle"
                / "semantic-packages"
                / (
                    roster_semantic.PF2ER_LEGACY_ROSTER_PRIOR_PACKAGE_DIGEST
                    + ".json"
                )
            )
            prior_body = package_path.read_bytes()
            prior_package = SemanticPackage.from_dict(
                json.loads(prior_body.decode("utf-8"))
            )
            if prior_package.canonical_json() != prior_body:
                raise AssertionError("prior legacy package is not canonical")
            (
                cls.portrait_refs,
                cls.source_presentations,
            ) = roster_semantic.legacy_roster_presentation_bindings(
                prior_package
            )
            prior_packages = tuple(
                SemanticPackage.from_dict(
                    json.loads(path.read_text(encoding="utf-8"))
                )
                for path in sorted(package_path.parent.glob("*.json"))
            )
            for entity_id in roster_publication.REVIEWED_PORTRAIT_NAMES:
                reviewed_entity = next(
                    package.entity(entity_id)
                    for package in prior_packages
                    if any(
                        entity.entity_id == entity_id
                        for entity in package.entities
                    )
                )
                presentation = reviewed_entity.definition["presentation"]
                references = {
                    reference.asset_id: reference
                    for reference in reviewed_entity.asset_refs
                }
                cls.portrait_refs[entity_id] = (
                    references[presentation["iconAssetId"]],
                    references[presentation["viewerAssetId"]],
                )
            cls.portrait_manifest = json.loads(
                (PRIOR_PUBLICATION_ROOT / "portrait-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            cls.source_presentation_audit = json.loads(
                (
                    PRIOR_PUBLICATION_ROOT / "source-presentation-audit.json"
                ).read_text(encoding="utf-8")
            )
            asset_root = PRIOR_PUBLICATION_ROOT / "bundle" / "semantic-assets"
            asset_index = json.loads(
                (asset_root / "index.json").read_text(encoding="utf-8")
            )
            artifacts = tuple(
                SemanticAssetArtifact(
                    AssetRef.from_dict(row["assetRef"]),
                    row["mediaType"],
                    (asset_root / "blobs" / row["sha256"]).read_bytes(),
                    row["size"],
                    row["sha256"],
                )
                for row in asset_index["assets"]
            )
            portrait_ref_set = {
                reference
                for references in cls.portrait_refs.values()
                for reference in references
            }
            cls.portrait_artifacts = tuple(
                artifact
                for artifact in artifacts
                if artifact.asset_ref in portrait_ref_set
            )
            cls.source_presentation_artifacts = tuple(
                artifact
                for artifact in artifacts
                if artifact.asset_ref not in portrait_ref_set
            )
        cls.package = roster_semantic.build_legacy_roster_semantic_package(
            authority=cls.authority,
            compiler_set=cls.compiler,
            evidence_store=cls.evidence,
            portrait_asset_refs={
                target.entity_id: cls.portrait_refs[target.entity_id]
                for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
            },
            source_presentations={
                target.entity_id: cls.source_presentations[target.entity_id]
                for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
            },
        )

    def test_package_is_exact_deterministic_and_round_trips(self) -> None:
        self.assertEqual(self.store.digest, roster_semantic.PF2ER_LEGACY_ROSTER_AUTHORITY_DIGEST)
        self.assertEqual(self.package.package_digest, EXPECTED_PACKAGE_DIGEST)
        self.assertEqual(len(self.package.entities), 91)
        parsed = SemanticPackage.from_dict(self.package.to_dict())
        self.assertEqual(parsed.canonical_json(), self.package.canonical_json())
        self.assertEqual(parsed.package_digest, EXPECTED_PACKAGE_DIGEST)

    def test_all_definitions_are_source_free_with_exact_executable_scope(self) -> None:
        for entity in self.package.entities:
            with self.subTest(entity=entity.entity_id):
                definition = entity.definition
                self.assertEqual(definition["id"], entity.entity_id)
                self.assertEqual(definition["kind"], "pf2er-creature")
                self.assertEqual(definition["inventory"], [])
                self.assertEqual(definition["abilities"], [])
                self.assertIs(type(definition["description"]), str)
                self.assertTrue(definition["description"])
                self.assertIs(type(definition["level"]), int)
                self.assertIs(type(definition["size"]), str)
                self.assertIs(type(definition["traits"]), list)
                self.assertIs(type(definition["languages"]), list)
                self.assertEqual(
                    set(definition["attributes"]),
                    {
                        "strength",
                        "dexterity",
                        "constitution",
                        "intelligence",
                        "wisdom",
                        "charisma",
                    },
                )
                self.assertEqual(
                    set(definition["perception"]),
                    {"modifier", "senses"},
                )
                self.assertIs(type(definition["skills"]), list)
                self.assertTrue(definition["speeds"])
                self.assertTrue(
                    all(
                        type(value) is int and value > 0
                        for value in definition["speeds"].values()
                    )
                )
                self.assertTrue(
                    {
                        "armorClass",
                        "fortitude",
                        "reflex",
                        "will",
                        "maximumHitPoints",
                    }.issubset(definition["defenses"])
                )
                expected_blockers = (
                    [roster_semantic.PF2ER_LEGACY_ROSTER_RUNTIME_BLOCKER]
                    if entity.entity_id == "pf2er:plague-zombie"
                    else []
                )
                self.assertEqual(definition["runtimeBlockers"], expected_blockers)
                self.assertEqual(definition["unsupportedMechanics"], [])
                self.assertTrue(definition["strikes"])
                self.assertEqual(definition["abilities"], [])
                self.assertTrue(
                    all(
                        strike["damage"]["riderEffects"] == []
                        and strike["followUps"] == []
                        and strike["attackSource"] == {"kind": "natural"}
                        for strike in definition["strikes"]
                    )
                )
                self.assertEqual(public_definition_acquisition_paths(definition), ())
                self.assertNotIn(
                    '"source":',
                    json.dumps(
                        definition,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
                selected_spellcasting = (
                    roster_semantic._EXECUTABLE_SPELLCASTING_TARGETS.get(
                        entity.entity_id
                    )
                )
                expected_capabilities = (
                    roster_semantic._EXECUTABLE_SPELLCASTING_CAPABILITIES.get(
                        entity.entity_id,
                        (),
                    )
                )
                self.assertEqual(
                    entity.required_capabilities,
                    expected_capabilities,
                )
                if selected_spellcasting is None:
                    self.assertNotIn("spellcastingCompilation", definition)
                else:
                    runtime_profile_id, spell_ids = selected_spellcasting
                    plan = definition["spellcastingCompilation"]
                    self.assertEqual(plan["schema"], 2)
                    self.assertEqual(plan["runtimeProfileId"], runtime_profile_id)
                    self.assertEqual(plan["supportState"], "executable")
                    self.assertEqual(
                        tuple(plan["runtimeActivation"]["executableSpellIds"]),
                        spell_ids,
                    )
                    self.assertEqual(
                        tuple(spell["id"] for spell in plan["spells"]),
                        spell_ids,
                    )
                presentation = definition["presentation"]
                self.assertEqual(
                    presentation["iconAssetId"],
                    roster_semantic.pf2er_roster_portrait_asset_id(
                        entity.entity_id, "x128"
                    ),
                )
                self.assertEqual(
                    presentation["viewerAssetId"],
                    roster_semantic.pf2er_roster_portrait_asset_id(
                        entity.entity_id, "x512"
                    ),
                )
                source_view = presentation["sourceNodeView"]
                self.assertEqual(source_view["schema"], 1)
                asset_ids = {item.asset_id for item in entity.asset_refs}
                self.assertIn(source_view["packetAssetId"], asset_ids)
                self.assertIn(source_view["closureManifestAssetId"], asset_ids)
                self.assertLess(len(entity.asset_refs), 100)
                self.assertEqual(
                    definition["publication"]["presentationAsset"],
                    "published",
                )
                self.assertEqual(
                    definition["publication"]["executableDefinition"],
                    (
                        "blocked-pending-plague-zombie-runtime"
                        if expected_blockers
                        else (
                            "baseline-strikes-and-reviewed-spellcasting"
                            if selected_spellcasting is not None
                            else "baseline-strikes"
                        )
                    ),
                )

    def test_portrait_inventory_is_exact_complete_and_bounded(self) -> None:
        self.assertEqual(len(self.portrait_refs), 94)
        self.assertEqual(len(self.portrait_artifacts), 188)
        self.assertEqual(
            sum(artifact.size for artifact in self.portrait_artifacts),
            7156182,
        )
        self.assertEqual(
            self.portrait_manifest["tiers"],
            {"thumbnail": "x128", "viewer": "x512"},
        )
        self.assertEqual(
            roster_publication.canonical_digest(
                self.portrait_manifest,
                "legacy roster portrait source manifest",
            ),
            roster_publication.ROSTER_PORTRAIT_MANIFEST_DIGEST,
        )
        self.assertEqual(
            len({artifact.asset_ref for artifact in self.portrait_artifacts}),
            188,
        )

    def test_source_node_view_preserves_complete_war_chanter_presentation(self) -> None:
        import json

        publication = self.source_presentations["pf2er:goblin-war-chanter"]
        artifacts = {
            artifact.asset_ref: artifact
            for artifact in self.source_presentation_artifacts
        }
        packet = json.loads(
            artifacts[publication.packet_ref].asset_bytes.decode("utf-8")
        )
        content = packet["content"]["section"]["content"]
        for exact_source_field in (
            '"Items"',
            '"Melee"',
            '"Ranged"',
            '"Spellcasting"',
            '"!.Goblin Scuttle"',
            '"!.Goblin Song"',
        ):
            self.assertIn(exact_source_field, content)
        closure = json.loads(
            artifacts[publication.closure_manifest_ref].asset_bytes.decode("utf-8")
        )
        self.assertEqual(closure["unavailableMediaReferences"], [])
        self.assertEqual(
            [item["role"] for item in closure["presentation"]["scripts"]],
            ["renderer-interface", "sealed-renderer-bundle"],
        )
        references = {item["reference"] for item in closure["mediaBindings"]}
        self.assertIn(
            "core/mc1/creatures/x128/Goblin War Chanter", references
        )
        self.assertIn(
            "core/mc1/creatures/x256/Goblin War Chanter", references
        )
        self.assertIn("core/pc1/actions/Single Action", references)
        self.assertIn("core/pc1/actions/Reaction", references)
        self.assertEqual(self.source_presentation_audit["targetCount"], 94)
        self.assertEqual(
            self.source_presentation_audit["unavailableMediaReferences"], []
        )

    def test_generic_description_handles_one_broader_family_heading(self) -> None:
        description = source_creature_description(
            self.authority,
            "core-mc1",
            "248.1",
        )
        self.assertEqual(len(description), 654)
        self.assertEqual(
            hashlib.sha256(description.encode("utf-8")).hexdigest(),
            "1582171927f7e4472a26832e7ed05192397fe7e3e146f4d03fc02f37d7c61849",
        )

    def test_missing_portrait_reference_fails_closed(self) -> None:
        refs = {
            target.entity_id: self.portrait_refs[target.entity_id]
            for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
        }
        refs.pop("pf2er:arbiter")
        with self.assertRaisesRegex(
            roster_semantic.PF2ERLegacyRosterSemanticError,
            "portrait reference census changed",
        ):
            roster_semantic.build_legacy_roster_semantic_package(
                authority=self.authority,
                compiler_set=self.compiler,
                evidence_store=SemanticEvidenceStore(),
                portrait_asset_refs=refs,
                source_presentations={
                    target.entity_id: self.source_presentations[target.entity_id]
                    for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
                },
            )

    def test_private_evidence_reconnects_every_target_without_public_leakage(self) -> None:
        for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS:
            entity = self.package.entity(target.entity_id)
            record = self.evidence.record(
                entity.receipt.evidence_record_digest
            )
            acquisition = record.acquisition_receipt
            self.assertEqual(
                acquisition["legacySourceAddress"],
                target.legacy_source_address,
            )
            self.assertEqual(
                acquisition["currentSelection"]["address"]["locator"],
                target.current_locator,
            )
            self.assertNotIn(
                target.legacy_source_address,
                entity.receipt.to_dict().values(),
            )
        self.assertEqual(len(self.evidence.snapshot().records), 91)

    def test_authority_and_compiler_drift_fail_before_publication(self) -> None:
        with patch.object(
            roster_semantic,
            "PF2ER_LEGACY_ROSTER_AUTHORITY_DIGEST",
            "0" * 64,
        ):
            with self.assertRaisesRegex(
                roster_semantic.PF2ERLegacyRosterSemanticError,
                "source authority drifted",
            ):
                roster_semantic.build_legacy_roster_semantic_package(
                    authority=self.authority,
                    compiler_set=self.compiler,
                    evidence_store=SemanticEvidenceStore(),
                    portrait_asset_refs={
                        target.entity_id: self.portrait_refs[target.entity_id]
                        for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
                    },
                    source_presentations={
                        target.entity_id: self.source_presentations[target.entity_id]
                        for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
                    },
                )

        wrong = build_pf2er_semantic_compiler_set()
        with self.assertRaisesRegex(
            roster_semantic.PF2ERLegacyRosterSemanticError,
            "compiler selection drifted",
        ):
            roster_semantic.build_legacy_roster_semantic_package(
                authority=self.authority,
                compiler_set=wrong,
                evidence_store=SemanticEvidenceStore(),
                portrait_asset_refs={
                    target.entity_id: self.portrait_refs[target.entity_id]
                    for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
                },
                source_presentations={
                    target.entity_id: self.source_presentations[target.entity_id]
                    for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
                },
            )


if __name__ == "__main__":
    unittest.main()
