from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "infrastructure" / "aws" / "ttrpg-server.yaml"
NGINX = ROOT / "infrastructure" / "aws" / "ttrpg.kmqdb.com.nginx"
BOOTSTRAP_NGINX = (
    ROOT / "infrastructure" / "aws" / "ttrpg.kmqdb.com.bootstrap.nginx"
)
HARDENING = ROOT / "infrastructure" / "aws" / "kmqdbttrpg-hardening.conf"
SERVICE = ROOT / "kmqdbttrpg.service.example"
README = ROOT / "infrastructure" / "aws" / "README.md"


class TtrpgServerTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_exact_identity_eip_and_deferred_dns_are_declared(self) -> None:
        self.assertIn("Default: ttrpg.kmqdb.com", self.template)
        self.assertIn("Default: eipalloc-52e89067", self.template)
        self.assertIn("Default: 52.207.82.158", self.template)
        self.assertIn("Default: 'false'", self.template)
        self.assertIn("PublishDnsRecord: !Equals", self.template)
        self.assertRegex(
            self.template,
            re.compile(
                r"TtrpgDnsRecord:\n\s+Type: AWS::Route53::RecordSet\n"
                r"\s+Condition: PublishDnsRecord"
            ),
        )

    def test_network_is_public_only_on_http_https_and_bounded_ssh(self) -> None:
        self.assertRegex(
            self.template,
            re.compile(
                r"Description: Operator SSH\n\s+IpProtocol: tcp\n"
                r"\s+FromPort: 22\n\s+ToPort: 22\n\s+CidrIp: !Ref OperatorCidr"
            ),
        )
        self.assertNotIn(
            "FromPort: 22\n          ToPort: 22\n          CidrIp: 0.0.0.0/0",
            self.template,
        )
        self.assertIn("FromPort: 80", self.template)
        self.assertIn("FromPort: 443", self.template)

    def test_retained_encrypted_state_uses_shared_backups(self) -> None:
        volume = self.template.split("  TtrpgDataVolume:", 1)[1].split(
            "  TtrpgInstance:", 1
        )[0]
        instance = self.template.split("  TtrpgInstance:", 1)[1]
        self.assertIn("DeletionPolicy: Retain", volume)
        self.assertIn("UpdateReplacePolicy: Retain", volume)
        self.assertIn("Encrypted: true", volume)
        self.assertIn("- Key: BackupEnabled\n          Value: 'true'", volume)
        self.assertNotIn("- Key: BackupEnabled", instance)
        self.assertIn("DisableApiTermination: true", instance)
        self.assertIn("HttpTokens: required", instance)

    def test_bootstrap_has_no_aws_credentials_or_application_source(self) -> None:
        self.assertIn("/var/lib/kmqdb/ttrpg", self.template)
        self.assertIn("proxy_pass http://127.0.0.1:8012", self.template)
        for forbidden in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "KMQDB_S3_BUCKET",
            "pip install kmqdb-ttrpg",
        ):
            self.assertNotIn(forbidden, self.template)

    def test_service_uses_persistent_ttrpg_state_only(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn(
            "KMQDB_TTRPG_CACHE_DB=/var/lib/kmqdb/ttrpg/cache/cache.db",
            source,
        )
        self.assertIn(
            "KMQDB_TTRPG_ITEM_CATALOG_DB=/var/lib/kmqdb/ttrpg/cache/item-catalog.db",
            source,
        )
        self.assertIn(
            "84e19dfa52236397ca7e837795908b11b72fe08d3b34ddabde2fda13bbabf6de",
            source,
        )
        self.assertIn("127.0.0.1:8012 kmqdb_ttrpg_wsgi:application", source)
        for forbidden in ("AWS_", "KMQDB_S3", "GLADIATOR", "ENCOUNTER"):
            self.assertNotIn(forbidden, source)

    def test_hardening_limits_writes_to_ttrpg_state(self) -> None:
        source = HARDENING.read_text(encoding="utf-8")
        self.assertIn("UMask=0077", source)
        self.assertIn("ProtectSystem=strict", source)
        self.assertIn("NoNewPrivileges=true", source)
        self.assertIn("CapabilityBoundingSet=\n", source)
        self.assertIn("ReadWritePaths=/var/lib/kmqdb/ttrpg", source)

    def test_tls_proxy_rejects_unknown_hosts_and_uses_loopback(self) -> None:
        source = NGINX.read_text(encoding="utf-8")
        self.assertEqual(source.count("server_name ttrpg.kmqdb.com;"), 2)
        self.assertIn("listen 80 default_server;", source)
        self.assertIn("listen 443 ssl default_server;", source)
        self.assertIn("ssl_reject_handshake on;", source)
        self.assertIn("return 301 https://$host$request_uri;", source)
        self.assertIn("proxy_pass http://127.0.0.1:8012;", source)

        bootstrap = BOOTSTRAP_NGINX.read_text(encoding="utf-8")
        self.assertIn("listen 80 default_server;", bootstrap)
        self.assertIn("server_name _;", bootstrap)
        self.assertIn("return 444;", bootstrap)
        self.assertIn("server_name ttrpg.kmqdb.com;", bootstrap)
        self.assertIn("proxy_pass http://127.0.0.1:8012;", bootstrap)

    def test_deployment_documentation_pins_the_exact_bundle(self) -> None:
        source = README.read_text(encoding="utf-8")
        for digest in (
            "2a5ed3eee81bbdb3ab2587fb60c4fa7613eb6c5688292a70883244019496fc58",
            "7fa658b9a1e4a1148942040b318c758ebf2c49bccf27f91577ecb56e007f6e99",
            "8de4b6d9ec51f71a981c8e2dd6789cad19c0ce21e1456c9ecd6e6227ef765828",
            "abb170fb8fe73a45ca165a63706f66d85aa0b71c4cc4e5a6c8be7ac25359fffd",
            "4847f712ccf7c5f3297a7b7e21bf4e2406bb160b050c4db754d93c8f5d78394e",
            "84e19dfa52236397ca7e837795908b11b72fe08d3b34ddabde2fda13bbabf6de",
            "43f2552a2378b44869fe8827aa19e69512e3245a219104438692385b0ee119d1",
            "c1453022f490d2459a11819d83ad1d586e9ff65a12ac3e705ffebd46d3685dcf",
            "b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992",
            "ec400d38950de4dfd418cff8328b2c8faed0edb0d517d3394e457c317908ca4d",
            "d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c",
        ):
            self.assertIn(digest, source)


if __name__ == "__main__":
    unittest.main()
