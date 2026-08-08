"""代理地址归一化。

容器运行时将指向本机回环地址的代理主机映射为 Docker Host 别名，同时保留认证
信息、端口和 URL 其他组成部分。
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit


LOCAL_PROXY_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def resolve_proxy_url(proxy_url: str, identifier: str = "", placeholder: str = ".xxx") -> str:
    """Replace a local proxy host with the Docker host alias when configured.
    Also replaces identifier placeholder (e.g. .xxx or {id}) with the account identifier.
    """
    value = str(proxy_url or "").strip()
    if not value:
        return value

    # Replace identifier placeholder for per-account unique proxy
    if identifier:
        ph = str(placeholder or ".xxx").strip() or ".xxx"
        if ph in value:
            value = value.replace(ph, f".{identifier}")
        elif "{id}" in value.lower():
            value = value.replace("{id}", identifier)
        elif ".xxx" in value:
            value = value.replace(".xxx", f".{identifier}")

    docker_host = str(os.environ.get("GROK_DOCKER_PROXY_HOST", "") or "").strip()
    if not docker_host:
        return value

    has_scheme = "://" in value
    parsed = urlsplit(value if has_scheme else f"http://{value}")
    if (parsed.hostname or "").lower() not in LOCAL_PROXY_HOSTS:
        return value

    auth = parsed.netloc.rsplit("@", 1)[0] + "@" if "@" in parsed.netloc else ""
    port = f":{parsed.port}" if parsed.port else ""
    resolved = urlunsplit(
        (parsed.scheme, f"{auth}{docker_host}{port}", parsed.path, parsed.query, parsed.fragment)
    )
    return resolved if has_scheme else resolved.split("://", 1)[1]
