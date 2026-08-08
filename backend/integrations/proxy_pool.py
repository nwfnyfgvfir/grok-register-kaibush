"""代理池管理。

存储代理列表（JSON 文件 data/proxy_pool.json），支持：
- 添加代理（多行文本）
- 批量探测延迟（可配置 delay，支持 http/socks5 + 用户名密码）
- 批量删除失败代理
- 从池中按 round-robin / random / lowest_latency 挑选代理

集成：registration.engine.get_proxies 优先使用池内代理，否则回退到 config.proxy。
"""

from __future__ import annotations

import json
import os
import random
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

from backend.shared.paths import DATA_ROOT

PROXY_POOL_FILE = DATA_ROOT / "proxy_pool.json"


_rr_lock = threading.Lock()
_rr_index = 0


def _pool_path() -> Path:
    return PROXY_POOL_FILE


def load_pool() -> List[Dict[str, Any]]:
    """加载代理池。"""
    path = _pool_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            proxies = data.get("proxies", [])
            if isinstance(proxies, list):
                return [p for p in proxies if isinstance(p, dict) and p.get("url")]
        except Exception:
            pass
    return []


def save_pool(proxies: List[Dict[str, Any]]) -> None:
    """保存代理池。"""
    path = _pool_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"proxies": proxies}, f, ensure_ascii=False, indent=2)


def _detect_protocol(url: str) -> str:
    """从 URL 检测协议。"""
    scheme = (urlparse(url).scheme or "http").lower()
    if scheme in ("socks5", "socks5h"):
        return "socks5"
    if scheme == "socks4":
        return "socks4"
    if scheme == "https":
        return "https"
    return "http"


def normalize_proxy_url(raw: str) -> str:
    """规范化代理 URL：补 scheme、去空白。"""
    value = str(raw or "").strip()
    if not value or value.startswith("#"):
        return ""
    if "://" not in value:
        value = f"http://{value}"
    parsed = urlparse(value)
    scheme = (parsed.scheme or "http").lower()
    if scheme not in ("http", "https", "socks5", "socks5h", "socks4"):
        return ""
    if not parsed.hostname:
        return ""
    return urlunparse(
        (
            scheme,
            parsed.netloc,
            parsed.path or "",
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def mask_proxy_url(url: str) -> str:
    """脱敏展示：隐藏密码。"""
    value = str(url or "").strip()
    if not value or "@" not in value:
        return value
    try:
        parsed = urlparse(value)
        if not parsed.password:
            return value
        user = parsed.username or ""
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        auth = f"{user}:***" if user else "***"
        return f"{parsed.scheme}://{auth}@{host}{port}{parsed.path or ''}"
    except Exception:
        return value


def public_proxy(item: Dict[str, Any]) -> Dict[str, Any]:
    """API 响应用的公开字段（URL 脱敏）。"""
    return {
        "id": item.get("id"),
        "url": item.get("url"),
        "display_url": mask_proxy_url(str(item.get("url") or "")),
        "protocol": item.get("protocol") or _detect_protocol(str(item.get("url") or "")),
        "latency_ms": item.get("latency_ms"),
        "status": item.get("status") or "unknown",
        "last_checked": item.get("last_checked"),
        "fail_count": int(item.get("fail_count") or 0),
        "exit_ip": item.get("exit_ip") or "",
    }


def add_proxies(lines: List[str] | str) -> Dict[str, int]:
    """添加多行代理地址。返回 added / skipped / invalid。"""
    if isinstance(lines, str):
        raw_lines = lines.splitlines()
    else:
        raw_lines = list(lines or [])

    existing = load_pool()
    existing_urls = {str(p.get("url") or "").strip() for p in existing}
    added = 0
    skipped = 0
    invalid = 0

    for line in raw_lines:
        url = normalize_proxy_url(line)
        if not url:
            if str(line or "").strip() and not str(line).strip().startswith("#"):
                invalid += 1
            continue
        if url in existing_urls:
            skipped += 1
            continue
        existing.append(
            {
                "id": secrets.token_hex(8),
                "url": url,
                "protocol": _detect_protocol(url),
                "latency_ms": None,
                "status": "unknown",
                "last_checked": None,
                "fail_count": 0,
                "exit_ip": "",
            }
        )
        existing_urls.add(url)
        added += 1

    if added:
        save_pool(existing)
    return {"added": added, "skipped": skipped, "invalid": invalid, "total": len(existing)}


def list_proxies() -> List[Dict[str, Any]]:
    """列出所有代理（原始数据）。"""
    return load_pool()


def delete_proxies(ids: List[str]) -> int:
    """删除指定 ids 的代理。"""
    id_set = {str(i) for i in (ids or []) if str(i)}
    if not id_set:
        return 0
    existing = load_pool()
    before = len(existing)
    remaining = [p for p in existing if str(p.get("id") or "") not in id_set]
    save_pool(remaining)
    return before - len(remaining)


def delete_failed_proxies(min_fail_count: int = 1) -> int:
    """删除 status=failed 或 fail_count >= N 的代理。"""
    existing = load_pool()
    before = len(existing)
    remaining = [
        p
        for p in existing
        if not (
            str(p.get("status") or "") == "failed"
            or int(p.get("fail_count") or 0) >= max(1, int(min_fail_count or 1))
        )
    ]
    save_pool(remaining)
    return before - len(remaining)


def _probe_one(proxy_url: str, timeout: float = 10.0) -> Dict[str, Any]:
    """探测单个代理：TCP + Cloudflare trace 出站。"""
    from backend.integrations.network_checks import _tcp_open, _trace_exit_ip

    parsed = urlparse(proxy_url)
    host = parsed.hostname or ""
    if not host:
        return {"ok": False, "latency_ms": None, "detail": "无效主机", "exit_ip": ""}

    default_port = 1080 if (parsed.scheme or "").startswith("socks") else 80
    port = parsed.port or default_port

    start = time.time()
    if not _tcp_open(host, port, timeout=min(timeout, 3.0)):
        return {
            "ok": False,
            "latency_ms": int((time.time() - start) * 1000),
            "detail": f"无法连接 {host}:{port}",
            "exit_ip": "",
        }

    try:
        from curl_cffi import requests as curl_requests

        def _http_get(url: str, **kwargs):
            kwargs.setdefault("timeout", timeout)
            kwargs.setdefault("verify", False)
            return curl_requests.get(url, **kwargs)

        exit_ip = _trace_exit_ip(
            _http_get,
            {"http": proxy_url, "https": proxy_url},
        )
        latency = int((time.time() - start) * 1000)
        if exit_ip:
            return {
                "ok": True,
                "latency_ms": latency,
                "detail": f"可用，出口IP {exit_ip}",
                "exit_ip": exit_ip,
            }
        return {
            "ok": True,
            "latency_ms": latency,
            "detail": "可用（未解析到出口IP）",
            "exit_ip": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": int((time.time() - start) * 1000),
            "detail": f"出站探测失败: {exc}",
            "exit_ip": "",
        }


def probe_proxies(
    ids: Optional[List[str]] = None,
    delay_ms: int = 200,
    skip_heavy_failures: bool = True,
) -> Dict[str, Any]:
    """批量探测延迟，更新 latency/status/fail_count。"""
    existing = load_pool()
    if not existing:
        return {"updated": 0, "ok": 0, "failed": 0, "skipped": 0, "items": []}

    id_set = {str(i) for i in (ids or []) if str(i)} if ids else None
    updated = 0
    ok_count = 0
    fail_count = 0
    skipped = 0
    results: List[Dict[str, Any]] = []

    for p in existing:
        if id_set is not None and str(p.get("id") or "") not in id_set:
            continue

        if (
            skip_heavy_failures
            and str(p.get("status") or "") == "failed"
            and int(p.get("fail_count") or 0) >= 5
        ):
            skipped += 1
            continue

        url = str(p.get("url") or "").strip()
        if not url:
            skipped += 1
            continue

        result = _probe_one(url)
        p["last_checked"] = int(time.time())
        p["latency_ms"] = result.get("latency_ms")
        p["exit_ip"] = result.get("exit_ip") or ""
        p["protocol"] = p.get("protocol") or _detect_protocol(url)

        if result.get("ok"):
            p["status"] = "ok"
            p["fail_count"] = 0
            ok_count += 1
        else:
            p["status"] = "failed"
            p["fail_count"] = int(p.get("fail_count") or 0) + 1
            fail_count += 1

        updated += 1
        results.append(
            {
                **public_proxy(p),
                "detail": result.get("detail") or "",
            }
        )

        if delay_ms > 0:
            time.sleep(max(0, delay_ms) / 1000.0)

    if updated:
        save_pool(existing)

    return {
        "updated": updated,
        "ok": ok_count,
        "failed": fail_count,
        "skipped": skipped,
        "items": results,
    }


def _usable_proxies(proxies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """优先返回 status=ok；若无则返回非 failed；再不行返回全部。"""
    ok_list = [p for p in proxies if str(p.get("status") or "") == "ok"]
    if ok_list:
        return ok_list
    non_failed = [p for p in proxies if str(p.get("status") or "") != "failed"]
    if non_failed:
        return non_failed
    return list(proxies)


def pick_proxy(strategy: str = "round_robin") -> Optional[Dict[str, Any]]:
    """从池中挑选一个代理条目（原始 dict）。"""
    global _rr_index
    proxies = load_pool()
    if not proxies:
        return None

    mode = str(strategy or "round_robin").strip().lower()
    candidates = _usable_proxies(proxies)
    if not candidates:
        return None

    if mode == "random":
        return random.choice(candidates)

    if mode == "lowest_latency":
        measured = [
            p
            for p in candidates
            if p.get("latency_ms") is not None and str(p.get("status") or "") == "ok"
        ]
        if measured:
            return min(measured, key=lambda p: int(p.get("latency_ms") or 10**9))
        return candidates[0]

    # round_robin
    with _rr_lock:
        idx = _rr_index % len(candidates)
        _rr_index = (idx + 1) % (10**9)
        return candidates[idx]


def reset_round_robin() -> None:
    """测试用：重置轮询计数。"""
    global _rr_index
    with _rr_lock:
        _rr_index = 0
