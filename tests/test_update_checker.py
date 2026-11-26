# coding: utf-8
"""update_checker：本文件只补充 test_update_manager.py 未覆盖的测试点。

- _is_packaged 的三种判定（frozen / _MEIPASS / nuitka_version）
- 一些额外边界（不重复 test_update_manager.py 已有内容）
"""

import sys

from desktop_calendar.infrastructure.network.update_checker import (
    _is_packaged,
)


# ===================== _is_packaged =====================
class TestIsPackaged:
    def test_not_packaged(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.delattr(sys, "nuitka_version", raising=False)
        assert _is_packaged() is False

    def test_pyinstaller_frozen(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.delattr(sys, "nuitka_version", raising=False)
        assert _is_packaged() is True

    def test_pyinstaller_meipass(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEI123", raising=False)
        monkeypatch.delattr(sys, "nuitka_version", raising=False)
        assert _is_packaged() is True

    def test_nuitka(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(sys, "nuitka_version", "1.0", raising=False)
        assert _is_packaged() is True


# ===================== 清单镜像与回退 =====================
class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.headers = {}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _run_checker(urls, monkeypatch, urlopen_fake):
    """直接跑 run()，把 emitted 结果收集到列表（直连，避免等事件循环）。"""
    from PyQt6.QtCore import Qt

    from desktop_calendar.infrastructure.network import update_checker as uc

    if urlopen_fake is not None:
        monkeypatch.setattr(uc, "urlopen", urlopen_fake)
    checker = uc.UpdateChecker(urls, None)
    results: list[dict] = []
    checker.checked.connect(results.append, Qt.ConnectionType.DirectConnection)
    checker.run()
    return checker, results


class TestManifestUrls:
    def test_primary_first_then_mirrors(self):
        from desktop_calendar.infrastructure.network import update_checker as uc

        urls = uc.manifest_urls()
        assert urls[0] == uc.UPDATE_MANIFEST_URL
        assert len(urls) == 1 + len(uc.UPDATE_MANIFEST_MIRROR_PREFIXES)
        assert len(set(urls)) == len(urls)
        assert all(u.startswith("https://") for u in urls)

    def test_default_manifest_points_at_current_repo(self):
        """仓库改过一次名（MyCalendar → Calendar），地址写错会让所有镜像一起 404。"""
        from desktop_calendar.infrastructure.network import update_checker as uc

        assert uc.UPDATE_MANIFEST_URL == (
            "https://github.com/limvict/Calendar/releases/latest/download/version.json"
        )
        assert "MyCalendar" not in uc.UPDATE_MANIFEST_URL
        assert "https://mirror.ghproxy.com/" not in uc.UPDATE_MANIFEST_MIRROR_PREFIXES
        for prefix in uc.UPDATE_MANIFEST_MIRROR_PREFIXES:
            assert prefix.startswith("https://") and prefix.endswith("/")

    def test_holiday_sources_have_no_dead_mirror(self):
        from desktop_calendar.infrastructure.network.qt_holiday_source import HolidayNetWorker

        assert all("mirror.ghproxy.com" not in url for url in HolidayNetWorker.CDN_LIST)

    def test_non_https_dropped(self):
        from desktop_calendar.infrastructure.network import update_checker as uc

        assert uc.manifest_urls("http://example.com/v.json") == ()


class TestCheckerFallback:
    def test_second_url_used_when_first_fails(self, monkeypatch):
        manifest = (
            b'{"version": "9.9.9", "download_url": "https://x/s.exe", "sha256": "'
            + b"a" * 64
            + b'"}'
        )

        def fake_urlopen(req, timeout=None):
            if "one.example" in req.full_url:
                raise TimeoutError("blocked")
            return _FakeResponse(manifest)

        checker, results = _run_checker(
            ["https://one.example/version.json", "https://two.example/version.json"],
            monkeypatch,
            fake_urlopen,
        )
        try:
            assert len(results) == 1
            result = results[0]
            assert result["error"] is None
            assert result["has_update"] is True
            assert result["manifest_url"] == "https://two.example/version.json"
            assert result["info"]["version"] == "9.9.9"
        finally:
            checker.deleteLater()

    def test_all_urls_failed_reports_each_host(self, monkeypatch):
        def fake_urlopen(req, timeout=None):
            raise OSError("refused")

        checker, results = _run_checker(
            ["https://one.example/v.json", "https://two.example/v.json"], monkeypatch, fake_urlopen
        )
        try:
            error = results[0]["error"]
            assert error.startswith("全部 2 个清单地址均不可用")
            assert "one.example" in error and "two.example" in error
            assert results[0]["has_update"] is False
        finally:
            checker.deleteLater()

    def test_invalid_json_falls_through_to_next_mirror(self, monkeypatch):
        good = (
            b'{"version": "9.9.9", "download_url": "https://x/s.exe", "sha256": "'
            + b"a" * 64
            + b'"}'
        )

        def fake_urlopen(req, timeout=None):
            if "bad.example" in req.full_url:
                return _FakeResponse(b"<html>proxy error</html>")
            return _FakeResponse(good)

        checker, results = _run_checker(
            ["https://bad.example/v.json", "https://good.example/v.json"], monkeypatch, fake_urlopen
        )
        try:
            assert results[0]["error"] is None
            assert results[0]["manifest_url"] == "https://good.example/v.json"
        finally:
            checker.deleteLater()

    def test_no_usable_url_reports_error(self, monkeypatch):
        checker, results = _run_checker(["http://insecure.example/v.json"], monkeypatch, None)
        try:
            assert "没有可用的更新清单地址" in results[0]["error"]
            assert checker.urls == ()
        finally:
            checker.deleteLater()

    def test_timeout_is_short(self):
        """并发后单地址超时不宜过长，否则网络差时要等太久才给结论。"""
        from desktop_calendar.infrastructure.network import update_checker as uc

        assert uc.CHECK_TIMEOUT <= 8

    def test_failure_message_keeps_configured_order(self, monkeypatch):
        def fake_urlopen(req, timeout=None):
            raise OSError("refused")

        checker, results = _run_checker(
            ["https://a.example/v.json", "https://b.example/v.json"], monkeypatch, fake_urlopen
        )
        try:
            error = results[0]["error"]
            assert error.index("a.example") < error.index("b.example")
        finally:
            checker.deleteLater()


class TestCheckerConcurrency:
    def test_slow_url_does_not_block_fast_mirror(self, monkeypatch):
        """主站握手卡住时，镜像返回就应该立刻出结果（不串行等待）。"""
        import threading
        import time

        good = (
            b'{"version": "9.9.9", "download_url": "https://x/s.exe", "sha256": "'
            + b"a" * 64
            + b'"}'
        )
        # 慢地址只有在“快地址已开始请求”后才会释放；串行实现会一直等到超时
        fast_started = threading.Event()

        def fake_urlopen(req, timeout=None):
            if "slow.example" in req.full_url:
                fast_started.wait(3.0)
                raise TimeoutError("handshake timed out")
            fast_started.set()
            return _FakeResponse(good)

        started = time.monotonic()
        checker, results = _run_checker(
            ["https://slow.example/v.json", "https://fast.example/v.json"],
            monkeypatch,
            fake_urlopen,
        )
        elapsed = time.monotonic() - started
        try:
            assert results[0]["error"] is None
            assert results[0]["manifest_url"] == "https://fast.example/v.json"
            assert elapsed < 2.0, f"并发拉取应快速返回，实际 {elapsed:.2f}s"
        finally:
            checker.deleteLater()


# ===================== 清单字段正则校验 =====================
class TestManifestProblems:
    def _valid(self, **over):
        info = {
            "version": "3.1.2",
            "download_url": "https://github.com/owner/repo/releases/download/v3.1.2/setup.exe",
            "sha256": "a" * 64,
        }
        info.update(over)
        return info

    def test_valid(self):
        from desktop_calendar.infrastructure.network.update_checker import manifest_problems

        assert manifest_problems(self._valid()) == []
        assert manifest_problems(self._valid(release_notes="修复若干问题")) == []

    def test_not_a_dict(self):
        from desktop_calendar.infrastructure.network.update_checker import manifest_problems

        assert manifest_problems([]) != []

    def test_version_format(self):
        from desktop_calendar.infrastructure.network.update_checker import manifest_problems

        for bad in ("1.2", "v1.2.3", "1.2.3-beta", ""):
            problems = manifest_problems(self._valid(version=bad))
            assert any("X.Y.Z" in p for p in problems), bad

    def test_sha256_format(self):
        from desktop_calendar.infrastructure.network.update_checker import manifest_problems

        for bad in ("abc", "g" * 64, 64 * "a" + "b"):
            problems = manifest_problems(self._valid(sha256=bad))
            assert any("sha256" in p for p in problems), bad

    def test_download_url_must_be_https_without_spaces(self):
        from desktop_calendar.infrastructure.network.update_checker import manifest_problems

        for bad in ("http://x/a.exe", "https://x/a b.exe", "https:///a.exe", 'https://x/a".exe'):
            problems = manifest_problems(self._valid(download_url=bad))
            assert problems, bad

    def test_bad_mirror_rejected(self):
        from desktop_calendar.infrastructure.network.update_checker import manifest_problems

        problems = manifest_problems(
            self._valid(download_url_mirrors=["https://ok/x.exe", "http://bad/x.exe"])
        )
        assert any("download_url_mirrors[1]" in p for p in problems)

    def test_release_notes_type(self):
        from desktop_calendar.infrastructure.network.update_checker import manifest_problems

        problems = manifest_problems(self._valid(release_notes=123))
        assert any("release_notes" in p for p in problems)

    def test_pure_no_mutation(self):
        from desktop_calendar.infrastructure.network.update_checker import manifest_problems

        info = self._valid(download_url_mirrors=["https://m/x.exe", "http://bad/x.exe"])
        before = {k: (list(v) if isinstance(v, list) else v) for k, v in info.items()}
        manifest_problems(info)
        assert info == before
