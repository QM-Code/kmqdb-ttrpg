from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import os
import subprocess
import sys
import textwrap
import unittest


TTRPG_ROOT = Path(__file__).resolve().parents[1]
COMPILER_ROOT = TTRPG_ROOT / "subdomains" / "ttrpg" / "pf2er_compiler"
COMPILER_PACKAGE = "subdomains.ttrpg.pf2er_compiler"
COMPILER_PROVIDER_MODULES = frozenset({"subdomains.ttrpg.source_content"})
ISOLATED_TARGET_MODULES = frozenset(
    {
        *COMPILER_PROVIDER_MODULES,
        "subdomains.ttrpg.item_catalog",
    }
)

EXPECTED_PATHS = frozenset(
    {
        "__init__.py",
        "battlemap.py",
        "durability.py",
        "equipment.py",
        "errors.py",
        "geometry.py",
        "illumination.py",
        "map_data.py",
        "mechanics/__init__.py",
        "mechanics/action_costs.py",
        "mechanics/afflictions.py",
        "mechanics/all_around_vision.py",
        "mechanics/amoeba_abilities.py",
        "mechanics/animated_construct_armor.py",
        "mechanics/annotated_stats.py",
        "mechanics/battle_cry.py",
        "mechanics/buck.py",
        "mechanics/cats_luck.py",
        "mechanics/change_shape.py",
        "mechanics/conditional_damage.py",
        "mechanics/conditional_saves.py",
        "mechanics/conditions.py",
        "mechanics/contracts.py",
        "mechanics/damage_defenses.py",
        "mechanics/damage_immunities.py",
        "mechanics/diseases.py",
        "mechanics/draconic_sequences.py",
        "mechanics/engulf.py",
        "mechanics/equipment_bindings.py",
        "mechanics/ferocity.py",
        "mechanics/flash_beetle.py",
        "mechanics/forced_movement.py",
        "mechanics/frightful_presence.py",
        "mechanics/fungus_leshy.py",
        "mechanics/gaze.py",
        "mechanics/generic_auras.py",
        "mechanics/ghoul.py",
        "mechanics/giant_ant.py",
        "mechanics/gnome_bard.py",
        "mechanics/goblin_song.py",
        "mechanics/grabbed_strike_activities.py",
        "mechanics/grapples.py",
        "mechanics/heal_spell.py",
        "mechanics/healing_affinities.py",
        "mechanics/healing_potion.py",
        "mechanics/innate_spell_usage.py",
        "mechanics/kobold_tactics.py",
        "mechanics/movement_speeds.py",
        "mechanics/persistent_damage.py",
        "mechanics/persistent_damage_foundation.py",
        "mechanics/plague_zombie_abilities.py",
        "mechanics/poisons.py",
        "mechanics/prepared_spellcasting.py",
        "mechanics/reactive_strike.py",
        "mechanics/regeneration.py",
        "mechanics/registry.py",
        "mechanics/river_drake.py",
        "mechanics/runic_weapon.py",
        "mechanics/runtime_registry.py",
        "mechanics/scarecrow.py",
        "mechanics/scuttle.py",
        "mechanics/shared_feast.py",
        "mechanics/shield_block.py",
        "mechanics/size_space_reach.py",
        "mechanics/slink.py",
        "mechanics/source_authority.py",
        "mechanics/source_values.py",
        "mechanics/special_senses.py",
        "mechanics/spontaneous_spellcasting.py",
        "mechanics/stench.py",
        "mechanics/stride_strike.py",
        "mechanics/strike_save_control.py",
        "mechanics/strike_sources.py",
        "mechanics/swallow_whole.py",
        "mechanics/telepathy.py",
        "mechanics/trample.py",
        "mechanics/triggered_creature_reactions.py",
        "mechanics/vision_senses.py",
        "mechanics/warg.py",
        "mechanics/zombie_brute.py",
        "mechanics/zombie_rot.py",
        "ranged_cover.py",
        "source.py",
        "source_authority_store.py",
        "source_compilation_plan.py",
        "source_nodes.py",
    }
)


def _module_identity(relative: str) -> tuple[str, str]:
    path = Path(relative).with_suffix("")
    parts = list(path.parts)
    if parts[-1] == "__init__":
        parts.pop()
        module = COMPILER_PACKAGE + (f".{'.'.join(parts)}" if parts else "")
        return module, module
    module = f"{COMPILER_PACKAGE}.{'.'.join(parts)}"
    return module, module.rpartition(".")[0]


def _outside_imports(relative: str) -> tuple[str, ...]:
    path = COMPILER_ROOT / relative
    _module, package = _module_identity(relative)
    tree = ast.parse(path.read_bytes(), filename=str(path))
    failures: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = tuple(alias.name for alias in node.names)
            level = 0
        elif isinstance(node, ast.ImportFrom):
            names = ((node.module or ""),)
            level = node.level
        else:
            continue
        for name in names:
            if level:
                resolved = importlib.util.resolve_name(
                    "." * level + name,
                    package,
                )
                if resolved in COMPILER_PROVIDER_MODULES:
                    continue
                if not (
                    resolved == COMPILER_PACKAGE
                    or resolved.startswith(COMPILER_PACKAGE + ".")
                ):
                    failures.append(resolved)
                continue
            root = name.partition(".")[0]
            if name.startswith(COMPILER_PACKAGE + "."):
                continue
            if name in COMPILER_PROVIDER_MODULES:
                continue
            if root not in sys.stdlib_module_names:
                failures.append(name)
    return tuple(sorted(set(failures)))


class Pf2erCompilerSeparationTests(unittest.TestCase):
    def test_exact_compiler_source_closure_and_namespace(self) -> None:
        actual = {
            path.relative_to(COMPILER_ROOT).as_posix()
            for path in COMPILER_ROOT.rglob("*.py")
        }
        self.assertEqual(actual, EXPECTED_PATHS)
        self.assertEqual(len(actual), 86)
        self.assertFalse((TTRPG_ROOT / "subdomains" / "__init__.py").exists())
        self.assertFalse(
            (TTRPG_ROOT / "subdomains" / "ttrpg" / "__init__.py").exists()
        )
        item_catalog_path = (
            TTRPG_ROOT / "subdomains" / "ttrpg" / "item_catalog.py"
        )
        self.assertTrue(item_catalog_path.is_file())
        item_tree = ast.parse(
            item_catalog_path.read_bytes(),
            filename=str(item_catalog_path),
        )
        item_imports = {
            alias.name
            for node in ast.walk(item_tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name.partition(".")[0] not in sys.stdlib_module_names
        }
        item_imports.update(
            node.module or ""
            for node in ast.walk(item_tree)
            if isinstance(node, ast.ImportFrom)
            and (
                node.level
                or (node.module or "").partition(".")[0]
                not in sys.stdlib_module_names
            )
        )
        self.assertEqual(item_imports, set())

    def test_every_import_stays_inside_compiler_or_stdlib(self) -> None:
        failures = {
            relative: imports
            for relative in sorted(EXPECTED_PATHS)
            if (imports := _outside_imports(relative))
        }
        self.assertEqual(failures, {})

    def test_every_module_imports_in_isolation_without_sibling_packages(
        self,
    ) -> None:
        modules = tuple(
            sorted(_module_identity(relative)[0] for relative in EXPECTED_PATHS)
        )
        probe = textwrap.dedent(
            f"""
            import importlib
            import importlib.abc
            from pathlib import Path
            import sys

            ROOT = Path({str(TTRPG_ROOT)!r}).resolve()
            COMPILER_ROOT = (ROOT / "subdomains" / "ttrpg" / "pf2er_compiler").resolve()
            PACKAGE = {COMPILER_PACKAGE!r}
            PROVIDER_MODULES = {ISOLATED_TARGET_MODULES!r}
            MODULES = {modules!r}

            class BlockSiblingTtrpgPackages(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if (
                        fullname.startswith("subdomains.ttrpg.")
                        and fullname != PACKAGE
                        and not fullname.startswith(PACKAGE + ".")
                        and fullname not in PROVIDER_MODULES
                    ):
                        raise ModuleNotFoundError(
                            "non-compiler TTRPG dependency blocked: " + fullname
                        )
                    return None

            sys.path.insert(0, str(ROOT))
            sys.meta_path.insert(0, BlockSiblingTtrpgPackages())
            for module_name in MODULES:
                module = importlib.import_module(module_name)
                module_path = Path(module.__file__).resolve()
                if not module_path.is_relative_to(COMPILER_ROOT):
                    raise SystemExit(
                        f"compiler module escaped target repository: {{module_name}}={{module_path}}"
                    )

            importlib.import_module("subdomains.ttrpg.item_catalog")
            for module_name in PROVIDER_MODULES:
                module_path = Path(sys.modules[module_name].__file__).resolve()
                expected = (ROOT / Path(*module_name.split("."))).with_suffix(".py")
                if module_path != expected:
                    raise SystemExit(
                        f"provider dependency escaped target repository: {{module_name}}={{module_path}}"
                    )

            escaped = sorted(
                name
                for name in sys.modules
                if name.startswith("subdomains.ttrpg.")
                and name != PACKAGE
                and not name.startswith(PACKAGE + ".")
                and name not in PROVIDER_MODULES
            )
            if escaped:
                raise SystemExit("sibling TTRPG modules loaded: " + repr(escaped))
            """
        )
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [sys.executable, "-I", "-c", probe],
            cwd=TTRPG_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
