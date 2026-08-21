from __future__ import annotations

from pathlib import Path
import re
import unittest


SERVICE_PATH = Path(__file__).resolve().parents[1] / "kmqdbttrpg.service.example"

EXPECTED_TTRPG_ENVIRONMENT = {
    "KMQDB_TTRPG_AUTH_DB": "/var/lib/kmqdb/ttrpg/ttrpg-auth.db",
    "KMQDB_TTRPG_CACHE_DB": (
        "/var/lib/kmqdb/ttrpg/cache/cache.db"
    ),
    "KMQDB_TTRPG_ITEM_CATALOG_DB": (
        "/var/lib/kmqdb/ttrpg/cache/item-catalog.db"
    ),
    "KMQDB_TTRPG_SEMANTIC_REPOSITORY": (
        "/var/lib/kmqdb/ttrpg/semantic-repositories/"
        "84e19dfa52236397ca7e837795908b11b72fe08d3b34ddabde2fda13bbabf6de"
    ),
    "KMQDB_TTRPG_SSO_ISSUER": "https://kmqdb.com",
    "KMQDB_TTRPG_SSO_REDIRECT_URI": (
        "https://ttrpg.kmqdb.com/.api/auth/sso/callback"
    ),
}

FORBIDDEN_GAME_ENVIRONMENT = {
    "KMQDB_TTRPG_ENCOUNTERS_DB",
    "KMQDB_TTRPG_GLADIATOR_CONNECTION_DB",
    "KMQDB_TTRPG_GLADIATOR_DB",
    "KMQDB_TTRPG_OBSERVER_ENABLED",
}

GAME_ENVIRONMENT_PATTERN = re.compile(
    r"(?:GLADIATOR|ENCOUNTER|OBSERVER|RULES_BUNDLE|STATIC_ROOT|WORLD_DB)"
)


def _environment() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in SERVICE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("Environment="):
            continue
        assignment = line.removeprefix("Environment=")
        name, separator, value = assignment.partition("=")
        if not separator or not name or name in result:
            raise AssertionError(f"invalid Environment directive: {line!r}")
        result[name] = value
    return result


class TtrpgServiceSeparationTests(unittest.TestCase):
    def test_unit_keeps_exact_ttrpg_delivery_and_semantic_state(self):
        environment = _environment()
        self.assertEqual(
            {name: environment.get(name) for name in EXPECTED_TTRPG_ENVIRONMENT},
            EXPECTED_TTRPG_ENVIRONMENT,
        )

    def test_unit_owns_no_gladiator_or_encounter_state(self):
        environment = _environment()
        self.assertTrue(FORBIDDEN_GAME_ENVIRONMENT.isdisjoint(environment))
        self.assertEqual(
            [name for name in environment if GAME_ENVIRONMENT_PATTERN.search(name)],
            [],
        )

    def test_unit_still_starts_the_ttrpg_host(self):
        source = SERVICE_PATH.read_text(encoding="utf-8")
        self.assertIn("Description=KMQDB TTRPG web app\n", source)
        self.assertIn("StateDirectory=kmqdb/ttrpg\n", source)
        self.assertIn("RequiresMountsFor=/var/lib/kmqdb/ttrpg\n", source)
        self.assertIn("EnvironmentFile=/etc/kmqdb/ttrpg.env\n", source)
        self.assertIn(
            "127.0.0.1:8012 kmqdb_ttrpg_wsgi:application\n",
            source,
        )
        self.assertNotIn("kmqdb_core_gladiator_wsgi", source)


if __name__ == "__main__":
    unittest.main()
