from __future__ import annotations

import ast
import hashlib
import inspect
import json
import unittest
from unittest.mock import patch

from subdomains.ttrpg import semantic_compiler
from subdomains.ttrpg.pf2er_compiler import source
from subdomains.ttrpg.pf2er_compiler.mechanics import battle_cry, ferocity, registry
from subdomains.ttrpg.pf2er_compiler.mechanics.contracts import (
    MechanicFamilyFragment,
    RawSourceArray,
    RawSourceObject,
)


def _identity() -> semantic_compiler.SemanticCompilerIdentity:
    return semantic_compiler.SemanticCompilerIdentity(
        compiler_id="ttrpg:pf2er-semantic-compiler",
        compiler_version="1.0.0",
        ruleset_id="paizo:pf2er",
        packages=(
            semantic_compiler.SemanticCompilerPackage(
                package_id="ttrpg:pf2er-monster-core-one",
                version="1.0.0",
                book_ids=("paizo:monster-core-one",),
            ),
            semantic_compiler.SemanticCompilerPackage(
                package_id="ttrpg:pf2er-player-core-one",
                version="1.0.0",
                book_ids=("paizo:player-core-one",),
            ),
        ),
    )


def _set(*fragments):
    return semantic_compiler.build_semantic_compiler_set(
        identity=_identity(),
        fragments=tuple(fragments),
    )


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


def _compile_battle_cry(
    compiler_set: semantic_compiler.SemanticCompilerSet,
) -> dict:
    abilities = compiler_set.compile_abilities(
        _battle_cry_block(),
        creature_name=battle_cry.CREATURE_NAME,
        source_id=battle_cry.SOURCE_ID,
        locator=battle_cry.LOCATOR,
    )
    return abilities[0]


class SemanticCompilerSelectionTests(unittest.TestCase):
    def test_manifest_is_deterministic_digest_bound_and_callable_free(self) -> None:
        first = _set(battle_cry.FRAGMENT, ferocity.FRAGMENT)
        second = _set(battle_cry.FRAGMENT, ferocity.FRAGMENT)

        self.assertEqual(first.canonical_manifest(), second.canonical_manifest())
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(
            first.digest,
            hashlib.sha256(first.canonical_manifest().encode("utf-8")).hexdigest(),
        )
        packet = json.loads(first.canonical_manifest())
        self.assertEqual(packet["identity"]["rulesetId"], "paizo:pf2er")
        self.assertEqual(
            [item["packageId"] for item in packet["identity"]["packages"]],
            [
                "ttrpg:pf2er-monster-core-one",
                "ttrpg:pf2er-player-core-one",
            ],
        )
        self.assertNotIn("compile_battle_cry", first.canonical_manifest())
        self.assertNotIn("callable", first.canonical_manifest().casefold())
        self.assertEqual(first.registry.activity_handlers, {})
        self.assertEqual(first.registry.reaction_handlers, {})
        self.assertEqual(first.registry.post_event_hooks, ())

        mutable_copy = first.manifest
        mutable_copy["schema"] = 99
        self.assertEqual(first.manifest["schema"], 1)

    def test_selected_battle_cry_compiles_and_omitted_set_defers(self) -> None:
        selected = _set(battle_cry.FRAGMENT)
        omitted = _set(ferocity.FRAGMENT)

        compiled = _compile_battle_cry(selected)
        deferred = _compile_battle_cry(omitted)

        self.assertTrue(compiled["supported"])
        self.assertEqual(
            compiled["mechanic"]["type"],
            battle_cry.MECHANIC_TYPE,
        )
        self.assertFalse(deferred["supported"])
        self.assertNotIn("mechanic", deferred)

        self.assertTrue(_compile_battle_cry(selected)["supported"])
        self.assertFalse(_compile_battle_cry(omitted)["supported"])

    def test_selected_path_never_reads_global_registry_aliases(self) -> None:
        selected = _set(battle_cry.FRAGMENT)

        class ExplodingCompilers:
            def __iter__(self):
                raise AssertionError("global ABILITY_COMPILERS was read")

        with patch.object(registry, "ABILITY_COMPILERS", ExplodingCompilers()):
            self.assertTrue(_compile_battle_cry(selected)["supported"])

        selected_entrypoint = ast.parse(
            inspect.getsource(source.compile_source_creature_with_registry)
        )
        forbidden = {
            node.attr
            for node in ast.walk(selected_entrypoint)
            if isinstance(node, ast.Attribute)
            and node.attr in {"REGISTRY", "ABILITY_COMPILERS"}
        }
        self.assertEqual(forbidden, set())

    def test_source_creature_entrypoint_passes_the_selected_registry(self) -> None:
        selected = _set(battle_cry.FRAGMENT)
        authority = object()
        with patch.object(
            source,
            "compile_source_creature_with_registry",
            return_value={"name": "Orc Commander"},
        ) as compile_creature:
            result = selected.compile_source_creature(
                authority,  # type: ignore[arg-type]
                battle_cry.SOURCE_ID,
                battle_cry.LOCATOR,
            )

        self.assertEqual(result, {"name": "Orc Commander"})
        compile_creature.assert_called_once_with(
            authority,
            battle_cry.SOURCE_ID,
            battle_cry.LOCATOR,
            registry=selected.registry,
        )

    def test_rejects_implicit_or_noncompiler_composition(self) -> None:
        with self.assertRaisesRegex(
            semantic_compiler.SemanticCompilerError,
            "non-empty tuple",
        ):
            semantic_compiler.build_semantic_compiler_set(
                identity=_identity(),
                fragments=(),
            )
        with self.assertRaisesRegex(
            semantic_compiler.SemanticCompilerError,
            "no ability compilers",
        ):
            _set(
                MechanicFamilyFragment(
                    family_id="runtime-only",
                    post_event_hooks=(),
                )
            )


if __name__ == "__main__":
    unittest.main()
