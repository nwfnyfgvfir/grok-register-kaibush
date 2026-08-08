# -*- coding: utf-8 -*-
"""CF/代理失败判定与槽位重试语义测试。"""

from __future__ import annotations

import unittest

from backend.registration import engine
from backend.registration import signup_flow


class ProxyOrCfFailureTests(unittest.TestCase):
    def test_detects_cloudflare_messages(self):
        self.assertTrue(engine.is_proxy_or_cf_failure(Exception("Cloudflare 拦截 HTTP 403")))
        self.assertTrue(engine.is_proxy_or_cf_failure(Exception("Just a moment...")))
        self.assertTrue(engine.is_proxy_or_cf_failure(Exception("checking your browser")))
        self.assertTrue(engine.is_proxy_or_cf_failure(Exception("请更换当前 proxy 后重试")))

    def test_detects_proxy_tunnel_errors(self):
        self.assertTrue(engine.is_proxy_or_cf_failure(Exception("ERR_PROXY_CONNECTION_FAILED")))
        self.assertTrue(engine.is_proxy_or_cf_failure(Exception("tunnel connection failed")))
        self.assertTrue(engine.is_proxy_or_cf_failure(Exception("代理不可用，出站探测失败")))

    def test_excludes_non_proxy_failures(self):
        self.assertFalse(
            engine.is_proxy_or_cf_failure(engine.EmailDomainRejected("a@b.com", "域名拒绝"))
        )
        self.assertFalse(
            engine.is_proxy_or_cf_failure(signup_flow.AccountAlreadyRegistered("已注册"))
        )
        self.assertFalse(
            engine.is_proxy_or_cf_failure(engine.RegistrationRiskDenied("风控"))
        )
        self.assertFalse(engine.is_proxy_or_cf_failure(engine.AccountRetryNeeded("卡住")))
        self.assertFalse(engine.is_proxy_or_cf_failure(Exception("未收到验证码")))
        self.assertFalse(engine.is_proxy_or_cf_failure(Exception("[CPA] 换 token 失败")))
        self.assertFalse(engine.is_proxy_or_cf_failure(Exception("未获取到 sso cookie")))

    def test_max_proxy_slot_retries_positive(self):
        self.assertGreaterEqual(engine.MAX_PROXY_SLOT_RETRIES, 1)


if __name__ == "__main__":
    unittest.main()
