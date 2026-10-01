"""Explicit deployment configuration; local development stays local by default."""
from dataclasses import dataclass
import os
import re


@dataclass(frozen=True)
class Settings:
    production: bool = False
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]", "testserver")

    @classmethod
    def from_env(cls):
        production = os.environ.get("ZIPFIT_ENV", "local") == "production"
        configured = os.environ.get("ZIPFIT_ALLOWED_HOSTS", "")
        platform_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
        hosts = [h.strip().lower() for h in (configured + "," + platform_host).split(",") if h.strip()]
        for host in hosts:
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
                raise ValueError("ZIPFIT_ALLOWED_HOSTS must contain exact hostnames, without schemes, ports or wildcards")
        if production and not hosts:
            raise ValueError("A production hostname is required: set ZIPFIT_ALLOWED_HOSTS")
        base = ("localhost", "127.0.0.1") if production else cls.allowed_hosts
        return cls(production=production, allowed_hosts=tuple(dict.fromkeys([*base, *hosts])))
