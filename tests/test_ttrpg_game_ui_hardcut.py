from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest

from subdomains.ttrpg import backend

TTRPG_ROOT = Path(backend.__file__).resolve().parent
APP_JS = TTRPG_ROOT / "@static" / "app.js"
APP_CSS = TTRPG_ROOT / "@static" / "app.css"


def _render_route(path: str) -> dict[str, str]:
    harness = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const path = process.argv[2];
const app = {
  classList: {add() {}, remove() {}},
  innerHTML: "",
};
const document = {
  title: "",
  getElementById() { return app; },
  addEventListener() {},
};
const window = {
  KMQDB_SUBDOMAIN_BOOTSTRAP: {path},
  location: {origin: "https://ttrpg.kmqdb.com", pathname: path},
  history: {pushState() {}, replaceState() {}},
  localStorage: {getItem() { return null; }, setItem() {}},
  addEventListener() {},
};
vm.runInNewContext(source, {document, window, URL, URLSearchParams}, {
  filename: process.argv[1],
});
process.stdout.write(JSON.stringify({html: app.innerHTML, title: document.title}));
'''
    completed = subprocess.run(
        ["node", "-e", harness, str(APP_JS), path],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


class TtrpgGameUiHardcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.javascript = APP_JS.read_text(encoding="utf-8")
        cls.stylesheet = APP_CSS.read_text(encoding="utf-8")

    def test_navigation_and_routes_are_catalog_only(self) -> None:
        match = re.search(
            r"const navCategories = (?P<categories>\[[^;]+\]);",
            self.javascript,
        )
        self.assertIsNotNone(match)
        self.assertEqual(
            json.loads(match.group("categories")),
            ["sources", "rules", "data", "tools"],
        )
        for forbidden in (
            "/stable",
            "/stables",
            "/encounters",
            "My stable",
            "Encounters",
            "isEncounterRoute",
            "isGladiatorStableRoute",
            "renderEncounter",
            "renderGladiator",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.javascript)

    def test_removed_game_routes_are_plain_not_found(self) -> None:
        for path in (
            "/pf2er/stable/",
            "/pf2er/stables/example/",
            "/pf2er/encounters/",
            "/pf2er/encounters/example/",
            "/pf2er/gladiator/",
        ):
            with self.subTest(path=path):
                rendered = _render_route(path)
                self.assertEqual(rendered["title"], "Not Found - TTRPG")
                self.assertIn("Not Found", rendered["html"])

    def test_game_assets_and_api_calls_are_absent(self) -> None:
        for forbidden in (
            "/.static/encounter-observer",
            "KMQDBEncounterObserver",
            "encounterObserver",
            "/.api/gladiator",
            "/.api/engine",
            "/.api/encounter",
            "/.api/observer",
            "/.api/stable",
            "/.api/inventory",
            "/.api/world",
            "/.api/controller",
            "game-static",
            "gladiatorJsonRequest",
            "data-gladiator",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.javascript)

    def test_catalog_source_and_rules_calls_remain(self) -> None:
        for required in (
            'ttrpgApiUrl("bookshelf")',
            'ttrpgApiUrl("rules/source-node"',
            "ttrpgApiUrl(`sources/${encodeURIComponent(String(sourceId || \"\"))}/publication`)",
            "ttrpgApiUrl(`sources/${encodeURIComponent(String(sourceId || \"\"))}/node`",
            '"/.static/rules-menu.json"',
            '"/.static/rules-targets.json"',
            "renderPublicationOverview",
            "renderRulesetShell",
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.javascript)

    def test_game_presentation_styles_are_absent(self) -> None:
        for forbidden in (
            ".gladiator-",
            ".is-gladiator",
            ".is-encounter",
            "encounter-observer",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.stylesheet)


if __name__ == "__main__":
    unittest.main()
