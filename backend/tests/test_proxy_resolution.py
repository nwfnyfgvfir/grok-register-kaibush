import unittest
from unittest import mock

from backend.integrations.proxy import resolve_proxy_url


class DockerProxyResolutionTests(unittest.TestCase):
    def test_localhost_proxy_maps_to_docker_host(self):
        with mock.patch.dict(
            "os.environ", {"GROK_DOCKER_PROXY_HOST": "host.docker.internal"}, clear=False
        ):
            self.assertEqual(
                resolve_proxy_url("http://127.0.0.1:7897"),
                "http://host.docker.internal:7897",
            )

    def test_credentials_are_preserved(self):
        with mock.patch.dict(
            "os.environ", {"GROK_DOCKER_PROXY_HOST": "host.docker.internal"}, clear=False
        ):
            self.assertEqual(
                resolve_proxy_url("socks5://user:pass@localhost:7897"),
                "socks5://user:pass@host.docker.internal:7897",
            )

    def test_regular_proxy_is_unchanged(self):
        with mock.patch.dict(
            "os.environ", {"GROK_DOCKER_PROXY_HOST": "host.docker.internal"}, clear=False
        ):
            self.assertEqual(
                resolve_proxy_url("http://proxy.example.com:7897"),
                "http://proxy.example.com:7897",
            )

    def test_identifier_placeholder_is_replaced(self):
        with mock.patch.dict(
            "os.environ", {"GROK_DOCKER_PROXY_HOST": "host.docker.internal"}, clear=False
        ):
            self.assertEqual(
                resolve_proxy_url(
                    "http://Default.xxx:pass@127.0.0.1:2260",
                    identifier="A",
                ),
                "http://Default.A:pass@host.docker.internal:2260",
            )

    def test_identifier_placeholder_without_docker(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                resolve_proxy_url(
                    "http://Default.xxx:pass@127.0.0.1:2260",
                    identifier="B",
                ),
                "http://Default.B:pass@127.0.0.1:2260",
            )

    def test_custom_placeholder(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                resolve_proxy_url(
                    "http://Default.xxxx:pass@127.0.0.1:2260",
                    identifier="C",
                    placeholder=".xxxx",
                ),
                "http://Default.C:pass@127.0.0.1:2260",
            )

    def test_realtime_identifier_for_connectivity(self):
        """Connectivity probe now uses a realtime sticky id, not fixed 'probe'."""
        with mock.patch.dict("os.environ", {}, clear=True):
            ident = "a1b2c3d4e5f60718"
            self.assertEqual(
                resolve_proxy_url(
                    "http://Default.xxx:pass@127.0.0.1:2260",
                    identifier=ident,
                    placeholder=".xxx",
                ),
                f"http://Default.{ident}:pass@127.0.0.1:2260",
            )

    def test_xxxx_fallback_when_placeholder_is_xxx(self):
        """URL uses .xxxx but config placeholder is default .xxx — still replace."""
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                resolve_proxy_url(
                    "http://Default.xxxx:pass@01.proxy.koyeb.app:17728",
                    identifier="abc123",
                    placeholder=".xxx",
                ),
                "http://Default.abc123:pass@01.proxy.koyeb.app:17728",
            )


if __name__ == "__main__":
    unittest.main()
