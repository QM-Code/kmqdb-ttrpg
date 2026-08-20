"""Installed WSGI entry point for the standalone KMQDB TTRPG service.

The first standalone release serves only fully downloaded cache assets.  A
future deployment may construct its own application with
``subdomains.ttrpg.backend.create_application`` and inject an external asset
streaming port without adding a Core dependency to this distribution.
"""

from subdomains.ttrpg.backend import create_application


application = create_application()


__all__ = ["application"]
