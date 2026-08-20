from __future__ import annotations

from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from subdomains.ttrpg import item_catalog


BUILDER_PATH = REPOSITORY_ROOT / "scripts" / "build_item_catalog.py"
BUILDER_SPEC = importlib.util.spec_from_file_location(
    "kmqdb_ttrpg_item_catalog_builder_test",
    BUILDER_PATH,
)
assert BUILDER_SPEC is not None and BUILDER_SPEC.loader is not None
builder = importlib.util.module_from_spec(BUILDER_SPEC)
sys.modules[BUILDER_SPEC.name] = builder
BUILDER_SPEC.loader.exec_module(builder)

CONFIGURED_TEST_CACHE = str(
    os.environ.get("KMQDB_TTRPG_TEST_CACHE_DB") or ""
).strip()
TEST_SOURCE_CACHE = (
    Path(CONFIGURED_TEST_CACHE).expanduser()
    if CONFIGURED_TEST_CACHE
    else builder.DEFAULT_SOURCE_CACHE
)


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
COMPILER = {"id": "test-item-catalog", "version": 1}
CURRENT_MIGRATION_SOURCE_NAMES = (
    "+1 <i>striking warhammer</i>",
    "arrows",
    "bolts",
    "bullets",
    "chain mail",
    "crossbow",
    "cytillesh toolkit (see sidebar on page 84)",
    "dagger",
    "dogslicer",
    "greataxe",
    "greatclub",
    "half plate",
    "heavy crossbow",
    "hide armor",
    "horsechopper",
    "javelin",
    "lance",
    "leather armor",
    "longsword",
    "musical instrument (handheld)",
    "orc knuckle dagger",
    "scimitar",
    "shoddy breastplate",
    "shortbow",
    "shortsword",
    "sling",
    "spear",
    "staff",
    "steel shield (hardness 5, hp 20, bt 10)",
    "sterling artisan’s toolkit",
    "studded leather armor",
    "torch",
    "warhammer",
)


def sample_definition() -> dict:
    return {
        "schema": 1,
        "kind": "pf2er-item-definition",
        "rulesetId": "pf2er",
        "definitionId": "core-pc1:item:test-sword",
        "itemId": "core-pc1:item:test-sword",
        "itemKind": "weapon",
        "name": "Test sword",
        "configuration": {
            "itemId": "core-pc1:item:test-sword",
            "quality": None,
            "modifiers": [],
        },
        "mechanics": {"kind": "weapon"},
        "sourceReceipts": [],
        "support": {
            "identity": {"status": "ready", "blockers": []},
            "price": {"status": "ready", "blockers": []},
            "durability": {
                "status": "blocked",
                "blockers": ["durability-profile-uncompiled"],
            },
        },
        "price": {
            "amountCp": 100,
            "currency": "cp",
            "sourceText": "1 gp",
            "unitQuantity": 1,
        },
    }


def artifact_values() -> dict:
    definition = sample_definition()
    return {
        "compiler": COMPILER,
        "source_generation": DIGEST_A,
        "source_authority_digest": DIGEST_B,
        "source_snapshot_digest": DIGEST_C,
        "definitions": [definition],
        "aliases": [
            {
                "sourceName": "test sword",
                "status": "canonical",
                "definitionDigest": item_catalog.json_digest(
                    definition
                ),
            },
            {
                "sourceName": "almost a sword",
                "status": "deferred",
                "blocker": {
                    "kind": "near-miss-not-bound",
                    "message": "not an exact canonical row",
                },
            },
        ],
        "generated_at": "2026-07-29T00:00:00+00:00",
    }


class ItemCatalogArtifactTests(unittest.TestCase):
    def test_current_item_presentation_round_trips_by_item_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "item-catalog.db"
            values = artifact_values()
            definition = values["definitions"][0]
            definition["presentation"] = {
                "name": "Test sword",
                "source": {
                    "sourceId": "core-pc1",
                    "locator": "286.9",
                },
            }
            definition["source"] = deepcopy(
                definition["presentation"]["source"]
            )
            values["aliases"][0]["definitionDigest"] = (
                item_catalog.json_digest(definition)
            )
            item_catalog.replace_item_catalog(path, **values)

            catalog = item_catalog.load_item_catalog(path)
            self.assertEqual(
                catalog.item_presentation(
                    "core-pc1:item:test-sword"
                ),
                {
                    "name": "Test sword",
                    "sourceName": "Test sword",
                    "source": {
                        "sourceId": "core-pc1",
                        "locator": "286.9",
                    },
                },
            )

    def test_atomic_artifact_round_trip_and_deferred_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache" / "item-catalog.db"
            manifest = item_catalog.replace_item_catalog(
                path,
                **artifact_values(),
            )
            catalog = item_catalog.load_item_catalog(path)

            self.assertEqual(
                catalog.manifest["catalogDigest"],
                manifest["catalogDigest"],
            )
            self.assertEqual(
                catalog.resolve("  TEST   SWORD  ")["price"]["amountCp"],
                100,
            )
            with self.assertRaises(
                item_catalog.ItemCatalogDeferred
            ) as deferred:
                catalog.resolve("almost a sword")
            self.assertEqual(
                deferred.exception.reason_kind,
                "near-miss-not-bound",
            )
            with self.assertRaises(item_catalog.ItemCatalogMiss):
                catalog.resolve("invented caller sword")
            with sqlite3.connect(path) as connection:
                self.assertEqual(
                    connection.execute(
                        "PRAGMA integrity_check"
                    ).fetchone()[0],
                    "ok",
                )
                self.assertEqual(
                    connection.execute(
                        "PRAGMA user_version"
                    ).fetchone()[0],
                    item_catalog.CATALOG_SCHEMA_VERSION,
                )

    def test_payload_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "item-catalog.db"
            item_catalog.replace_item_catalog(
                path,
                **artifact_values(),
            )
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE definitions SET payload = '{}'"
                )
                connection.commit()
            with self.assertRaises(
                item_catalog.ItemCatalogUnavailable
            ):
                item_catalog.load_item_catalog(path)

    def test_failed_replacement_preserves_prior_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "item-catalog.db"
            first = item_catalog.replace_item_catalog(
                path,
                **artifact_values(),
            )
            invalid = artifact_values()
            invalid["aliases"] = [
                {
                    "sourceName": "test sword",
                    "status": "canonical",
                    "definitionDigest": "f" * 64,
                }
            ]
            with self.assertRaises(
                item_catalog.ItemCatalogUnavailable
            ):
                item_catalog.replace_item_catalog(path, **invalid)
            current = item_catalog.load_item_catalog(path)
            self.assertEqual(
                current.manifest["catalogDigest"],
                first["catalogDigest"],
            )


@unittest.skipUnless(
    TEST_SOURCE_CACHE.is_file(),
    "live TTRPG source cache is unavailable; set "
    "KMQDB_TTRPG_TEST_CACHE_DB",
)
class LiveItemCatalogBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.values = builder.compile_catalog_values(
            TEST_SOURCE_CACHE
        )
        cls.temporary = tempfile.TemporaryDirectory()
        cls.path = (
            Path(cls.temporary.name) / "item-catalog.db"
        )
        item_catalog.replace_item_catalog(
            cls.path,
            compiler=cls.values["compiler"],
            source_generation=cls.values["source_generation"],
            source_authority_digest=cls.values[
                "source_authority_digest"
            ],
            source_snapshot_digest=cls.values[
                "source_snapshot_digest"
            ],
            definitions=cls.values["definitions"],
            aliases=cls.values["aliases"],
            generated_at="2026-07-29T00:00:00+00:00",
        )
        cls.catalog = item_catalog.load_item_catalog(cls.path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_closed_binding_registry_has_exact_census(self) -> None:
        self.assertEqual(
            self.values["census"],
            {
                "definitions": 73,
                "aliases": 78,
                "canonicalAliases": 73,
                "deferredAliases": 5,
                "priceSupport": {"ready": 73},
                "durabilitySupport": {
                    "blocked": 57,
                    "not-applicable": 8,
                    "ready": 8,
                },
                "healingPotionVariants": 5,
            },
        )

    def test_every_current_migration_name_resolves(self) -> None:
        for source_name in CURRENT_MIGRATION_SOURCE_NAMES:
            with self.subTest(source_name=source_name):
                definition = self.catalog.resolve(source_name)
                self.assertEqual(
                    definition["support"]["identity"]["status"],
                    "ready",
                )

    def test_ordinary_shoddy_gear_ammunition_and_shield_prices(self) -> None:
        self.assertEqual(
            self.catalog.resolve("warhammer")["price"]["amountCp"],
            100,
        )
        self.assertEqual(
            self.catalog.resolve("shoddy breastplate")["price"][
                "amountCp"
            ],
            400,
        )
        self.assertEqual(
            self.catalog.resolve("sterling artisan’s toolkit")[
                "price"
            ]["amountCp"],
            5000,
        )
        arrows = self.catalog.resolve("arrows")
        self.assertEqual(arrows["price"]["amountCp"], 10)
        self.assertEqual(arrows["price"]["unitQuantity"], 10)
        shield = self.catalog.resolve(
            "steel shield (hardness 5, hp 20, bt 10)"
        )
        self.assertEqual(shield["price"]["amountCp"], 200)
        self.assertEqual(
            shield["mechanics"]["durability"],
            {
                "hardness": 5,
                "maximumHitPoints": 20,
                "brokenThreshold": 10,
                "rule": {
                    "sourceId": "core-pc1",
                    "locator": "274.1",
                },
            },
        )
        self.assertEqual(
            shield["support"]["durability"]["status"],
            "ready",
        )
        self.assertEqual(
            self.catalog.resolve("longsword")["mechanics"][
                "durability"
            ],
            {
                "material": "thin iron or steel",
                "hardness": 5,
                "maximumHitPoints": 20,
                "brokenThreshold": 10,
                "exampleBasis": "sword",
                "rule": {
                    "sourceId": "core-gmc",
                    "locator": "252.2",
                },
            },
        )
        self.assertEqual(
            self.catalog.resolve("leather armor")[
                "mechanics"
            ]["durability"]["maximumHitPoints"],
            16,
        )
        shoddy_breastplate = self.catalog.resolve(
            "shoddy breastplate"
        )
        self.assertEqual(
            (
                shoddy_breastplate["mechanics"]["durability"][
                    "hardness"
                ],
                shoddy_breastplate["mechanics"]["durability"][
                    "maximumHitPoints"
                ],
                shoddy_breastplate["mechanics"]["durability"][
                    "brokenThreshold"
                ],
            ),
            (9, 18, 9),
        )
        self.assertEqual(
            shoddy_breastplate["mechanics"]["durability"][
                "qualityAdjustment"
            ]["rule"],
            {
                "sourceId": "core-pc1",
                "locator": "270.2",
            },
        )
        self.assertEqual(
            self.catalog.resolve("invisibility potion")["price"][
                "amountCp"
            ],
            2000,
        )
        self.assertEqual(
            self.catalog.resolve("spider venom")["price"]["amountCp"],
            2500,
        )

    def test_magic_price_composes_exact_runes_and_durability_stays_gated(
        self,
    ) -> None:
        magic = self.catalog.resolve(
            "+1 <i>striking warhammer</i>"
        )
        self.assertEqual(
            magic["price"]["amountCp"],
            10100,
        )
        self.assertEqual(
            [
                adjustment["amountCp"]
                for adjustment in magic["price"]["adjustments"]
            ],
            [3500, 6500],
        )
        self.assertEqual(
            magic["mechanics"]["level"],
            4,
        )
        self.assertEqual(
            magic["support"]["price"]["status"],
            "ready",
        )
        ordinary = self.catalog.resolve("warhammer")
        self.assertEqual(
            ordinary["support"]["durability"],
            {
                "status": "blocked",
                "blockers": ["durability-profile-uncompiled"],
            },
        )

    def test_all_healing_potion_variants_are_exact_consumables(
        self,
    ) -> None:
        expected = {
            "Minor": (1, 400, 1, 0),
            "Lesser": (3, 1200, 2, 5),
            "Moderate": (6, 5000, 3, 10),
            "Greater": (12, 40000, 6, 20),
            "Major": (18, 500000, 8, 30),
        }
        for variant, (
            level,
            price_cp,
            die_count,
            modifier,
        ) in expected.items():
            with self.subTest(variant=variant):
                definition = self.catalog.resolve(
                    f"Healing Potion ({variant})"
                )
                mechanics = definition["mechanics"]
                self.assertEqual(
                    definition["itemId"],
                    "core-gmc:item:healing-potion-"
                    + variant.lower(),
                )
                self.assertEqual(
                    definition["price"]["amountCp"],
                    price_cp,
                )
                self.assertEqual(mechanics["level"], level)
                self.assertEqual(mechanics["kind"], "consumable")
                self.assertEqual(
                    mechanics["consumableKind"],
                    "healing-potion",
                )
                self.assertTrue(mechanics["consumedOnUse"])
                self.assertEqual(
                    {
                        key: mechanics["activation"][key]
                        for key in (
                            "actionCost",
                            "target",
                            "traits",
                        )
                    },
                    {
                        "actionCost": 1,
                        "target": "self",
                        "traits": ["manipulate"],
                    },
                )
                self.assertEqual(
                    mechanics["activation"]["effect"][
                        "healing"
                    ],
                    {
                        "dice": {
                            "count": die_count,
                            "sides": 8,
                        },
                        "modifier": modifier,
                    },
                )
                self.assertEqual(
                    definition["support"]["durability"]["status"],
                    "not-applicable",
                )

    def test_five_reviewed_near_misses_fail_closed(self) -> None:
        deferred = {
            "defiled religious symbol of pharasma",
            "frying pan",
            "religious symbol",
            "religious symbol of ydersius",
            "tengu feather fan (worth 0 gp)",
        }
        for source_name in deferred:
            with self.subTest(source_name=source_name):
                with self.assertRaises(
                    item_catalog.ItemCatalogDeferred
                ):
                    self.catalog.resolve(source_name)


if __name__ == "__main__":
    unittest.main()
