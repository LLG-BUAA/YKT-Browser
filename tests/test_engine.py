import queue
import unittest
from unittest.mock import patch

from engine import EngineStatus, PageType, YuketangEngine, normalize_engine_options


class FakeRoot:
    def __init__(self, name, url="", selectors=None, evaluate_results=None):
        self.name = name
        self.url = url or name
        self.selectors = set(selectors or [])
        self.evaluate_results = evaluate_results or {}

    def query_selector(self, selector):
        if selector in self.selectors:
            return object()
        return None

    def evaluate(self, script):
        if "ykt_has_video" in script:
            return self.evaluate_results.get("has_video", False)
        if "ykt_has_next_button" in script:
            return self.evaluate_results.get("has_next_button", False)
        if "ykt_click_next_button" in script:
            return self.evaluate_results.get("click_next", {"clicked": False})
        if "ykt_next_button_diagnostics" in script:
            return self.evaluate_results.get("diagnostics", [])
        if "ykt_discover_next_urls" in script:
            return self.evaluate_results.get("next_url_discovery", [])
        if "ykt_page_snapshot" in script:
            return self.evaluate_results.get("page_snapshot", {"url": self.url})
        raise AssertionError(f"Unexpected script: {script[:80]}")


class FakePage:
    def __init__(self, frames, url="https://example.com/course"):
        self.frames = frames
        self.main_frame = frames[0] if frames else None
        self.url = url
        self.wait_calls = []
        self.next_url = url + "/next"
        self.default_timeout = None
        self.closed = False

    def wait_for_load_state(self, state, timeout=0):
        self.wait_calls.append((state, timeout))

    def set_default_timeout(self, timeout):
        self.default_timeout = timeout

    def is_closed(self):
        return self.closed

    def simulate_next_unit_change(self):
        self.url = self.next_url
        if self.main_frame is not None:
            self.main_frame.url = self.url

    def goto(self, url, wait_until="domcontentloaded", timeout=0):
        self.url = url
        if self.main_frame is not None:
            self.main_frame.url = url
        self.wait_calls.append((f"goto:{wait_until}", timeout))


class FakeContext:
    def __init__(self, pages):
        self.pages = pages


class YuketangEngineTests(unittest.TestCase):
    def test_normalize_engine_options_filters_unknown_keys(self):
        options = normalize_engine_options(
            {"click_strategies": ["locator", "unknown", "direct_nav"], "wait_for_captcha": False}
        )
        self.assertEqual(options["click_strategies"], ["locator", "direct_nav"])
        self.assertFalse(options["wait_for_captcha"])

    def test_normalize_engine_options_defaults_to_combo_only(self):
        options = normalize_engine_options()
        self.assertEqual(options["click_strategies"], ["combo"])
        self.assertTrue(options["wait_for_captcha"])

    def test_detect_page_type_finds_video_inside_child_frame(self):
        main_root = FakeRoot("main", url="https://example.com/course")
        video_root = FakeRoot(
            "video-frame",
            url="https://example.com/frame/video",
            evaluate_results={"has_video": True},
        )

        engine = YuketangEngine(queue.Queue())
        engine.page = FakePage([main_root, video_root])

        with patch("engine.time.sleep", return_value=None):
            self.assertEqual(engine._detect_page_type(), PageType.VIDEO)

    def test_has_known_content_recognizes_next_button_in_child_frame(self):
        main_root = FakeRoot("main", url="https://example.com/course")
        nav_root = FakeRoot(
            "nav-frame",
            url="https://example.com/frame/nav",
            evaluate_results={"has_next_button": True},
        )

        engine = YuketangEngine(queue.Queue())
        engine.page = FakePage([main_root, nav_root])

        self.assertTrue(engine._has_known_content())

    def test_click_next_uses_child_frame_when_main_document_has_no_button(self):
        main_root = FakeRoot("main", url="https://example.com/course")
        nav_root = FakeRoot(
            "nav-frame",
            url="https://example.com/frame/nav",
            evaluate_results={
                "click_next": {
                    "clicked": True,
                    "text": "下一单元",
                    "className": "btn-next ml20 pointer",
                    "visible": True,
                    "tagName": "SPAN",
                    "score": 17,
                }
            },
        )

        engine = YuketangEngine(queue.Queue())
        engine.page = FakePage([main_root, nav_root])
        engine._sleep = lambda seconds: True

        engine._click_next()

        self.assertEqual(engine.stats["units"], 1)
        self.assertEqual(
            engine.page.wait_calls,
            [("domcontentloaded", 15000)],
        )

    def test_click_next_can_fall_back_to_direct_navigation(self):
        main_root = FakeRoot(
            "main",
            url="https://example.com/pro/lms/course/section/video/1",
            evaluate_results={
                "next_url_discovery": [
                    {
                        "url": "https://example.com/pro/lms/course/section/video/2",
                        "source": "attr:href",
                        "score": 30,
                    }
                ]
            },
        )

        engine = YuketangEngine(
            queue.Queue(),
            options={"click_strategies": ["direct_nav"], "wait_for_captcha": False},
        )
        engine.page = FakePage([main_root], url=main_root.url)
        engine._sleep = lambda seconds: True

        engine._click_next()

        self.assertEqual(engine.stats["units"], 1)
        self.assertEqual(engine.page.url, "https://example.com/pro/lms/course/section/video/2")

    def test_combo_strategy_can_succeed_with_second_follow_up_click(self):
        main_root = FakeRoot("main", url="https://example.com/course")
        engine = YuketangEngine(
            queue.Queue(),
            options={"click_strategies": ["combo"], "wait_for_captcha": False},
        )
        engine.page = FakePage([main_root], url=main_root.url)
        engine._sleep = lambda seconds: True

        locator_calls = {"count": 0}

        def fake_locator(root):
            locator_calls["count"] += 1
            return {
                "root": "主文档",
                "strategy": "右上角文字",
                "detail": {"selector": "div.fr span.btn-next span.f14"},
            }

        def fake_js(root):
            return {
                "root": "主文档",
                "strategy": "JS事件 / btn-next",
                "detail": {"className": "btn-next"},
            }

        wait_results = iter(
            [
                (False, {"url": "https://example.com/course"}),
                (False, {"url": "https://example.com/course"}),
                (True, {"url": "https://example.com/course/next"}),
            ]
        )

        engine._click_next_via_locator = fake_locator
        engine._click_next_in_root = fake_js
        engine._wait_for_next_unit_change = lambda previous_snapshot, timeout_seconds=0: next(wait_results)

        clicked, latest_snapshot = engine._click_next_via_combo({"url": "https://example.com/course"})

        self.assertIsNotNone(clicked)
        self.assertIn("预热复点", clicked["strategy"])
        self.assertIn("右上角文字", clicked["strategy"])
        self.assertEqual(latest_snapshot["url"], "https://example.com/course/next")

    def test_single_locator_strategy_can_succeed_on_follow_up_click(self):
        main_root = FakeRoot("main", url="https://example.com/course")
        engine = YuketangEngine(
            queue.Queue(),
            options={"click_strategies": ["locator"], "wait_for_captcha": False},
        )
        engine.page = FakePage([main_root], url=main_root.url)
        engine._sleep = lambda seconds: True

        locator_calls = {"count": 0}

        def fake_locator(root):
            locator_calls["count"] += 1
            return {
                "root": "主文档",
                "strategy": "右上角文字",
                "detail": {"selector": "div.fr span.btn-next span.f14"},
            }

        wait_results = iter(
            [
                (False, {"url": "https://example.com/course"}),
                (True, {"url": "https://example.com/course/next"}),
            ]
        )

        engine._click_next_via_locator = fake_locator
        engine._wait_for_next_unit_change = lambda previous_snapshot, timeout_seconds=0: next(wait_results)
        clicked, latest_snapshot, changed = engine._attempt_click_method_with_follow_up(
            engine._click_next_via_locator,
            main_root,
            {"url": "https://example.com/course"},
        )

        self.assertTrue(changed)
        self.assertEqual(locator_calls["count"], 2)
        self.assertIn("复点", clicked["strategy"])
        self.assertEqual(latest_snapshot["url"], "https://example.com/course/next")

    def test_wait_for_content_resets_waiting_login_status(self):
        main_root = FakeRoot("main", url="https://example.com/course")
        engine = YuketangEngine(queue.Queue())
        engine.page = FakePage([main_root], url="https://example.com/course")
        engine.status = EngineStatus.WAITING_LOGIN

        engine._has_known_content = lambda: True
        with patch("engine.time.sleep", return_value=None):
            self.assertTrue(engine._wait_for_content())

        self.assertEqual(engine.status.value, "运行中")

    def test_sync_active_page_prefers_course_tab_with_content(self):
        login_root = FakeRoot(
            "login",
            url="https://example.com/login",
            selectors={"text=登录"},
        )
        content_root = FakeRoot(
            "content",
            url="https://example.com/course",
            evaluate_results={"has_next_button": True},
        )
        login_page = FakePage([login_root], url=login_root.url)
        content_page = FakePage([content_root], url=content_root.url)

        engine = YuketangEngine(queue.Queue())
        engine.target_url = "https://example.com/course"
        engine.page = login_page
        engine.context = FakeContext([login_page, content_page])

        active_page = engine._sync_active_page(prefer_content=True)

        self.assertIs(active_page, content_page)
        self.assertIs(engine.page, content_page)
        self.assertEqual(content_page.default_timeout, 15000)

    def test_wait_for_content_does_not_mark_waiting_login_on_non_login_page(self):
        main_root = FakeRoot("main", url="https://example.com/course")
        engine = YuketangEngine(queue.Queue())
        engine.page = FakePage([main_root], url="https://example.com/course")
        engine.status = EngineStatus.RUNNING

        known_content_results = iter([False, False, True])
        engine._sync_active_page = lambda prefer_content=False, log_reason=None: engine.page
        engine._any_page_has_captcha = lambda: False
        engine._page_looks_like_login = lambda page: False
        engine._has_known_content = lambda page=None: next(known_content_results)

        with patch("engine.time.sleep", return_value=None):
            self.assertTrue(engine._wait_for_content())

        self.assertEqual(engine.status, EngineStatus.RUNNING)


if __name__ == "__main__":
    unittest.main()
