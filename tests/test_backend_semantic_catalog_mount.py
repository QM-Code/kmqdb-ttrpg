from __future__ import annotations

import json
import unittest
from unittest import mock

from subdomains.ttrpg import backend


def _request(path: str) -> tuple[str, dict[str, str], bytes]:
    response: dict[str, object] = {}

    def start_response(status, headers, _exc_info=None):
        response["status"] = status
        response["headers"] = dict(headers)

    chunks = backend.application(
        {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": path,
            "QUERY_STRING": "catalogDigest=" + "a" * 64,
            "wsgi.input": None,
        },
        start_response,
    )
    return (
        str(response["status"]),
        dict(response["headers"]),
        b"".join(chunks),
    )


class SemanticCatalogMountTests(unittest.TestCase):
    def test_catalog_v1_is_delegated_without_ttrpg_route_interpretation(self):
        seen: list[tuple[str, str]] = []

        def catalog_application(environ, start_response):
            seen.append((environ["PATH_INFO"], environ["QUERY_STRING"]))
            body = b'{"catalog":"exact"}'
            start_response(
                "200 OK",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        with mock.patch.object(
            backend.semantic_service,
            "application",
            catalog_application,
        ):
            status, _headers, body = _request(
                "/.api/catalog/v1/envelope"
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(body), {"catalog": "exact"})
        self.assertEqual(
            seen,
            [
                (
                    "/.api/catalog/v1/envelope",
                    "catalogDigest=" + "a" * 64,
                )
            ],
        )

    def test_unconfigured_catalog_fails_closed_without_affecting_other_routes(self):
        def unavailable(_environ, _start_response):
            raise backend.semantic_service.SemanticServiceConfigurationError(
                "not configured"
            )

        with mock.patch.object(
            backend.semantic_service,
            "application",
            unavailable,
        ):
            status, headers, body = _request(
                "/.api/catalog/v1/envelope"
            )
        self.assertEqual(status, "503 Service Unavailable")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(
            json.loads(body),
            {"error": "semantic catalog service is unavailable"},
        )


if __name__ == "__main__":
    unittest.main()
