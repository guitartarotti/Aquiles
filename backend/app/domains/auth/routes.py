"""HTTP adapter exposed by the authentication domain."""

from __future__ import annotations

from flask import Flask

from ...auth import register_auth


def register_auth_routes(app: Flask, *, expose_login: bool = True) -> None:
    register_auth(app, expose_login=expose_login)
