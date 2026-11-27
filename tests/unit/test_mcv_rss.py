"""Unit tests for Minecraft development-version push settings."""

from types import SimpleNamespace

from core.tester import Tester, func_case
from modules.mcv_rss import dev_updates_enabled, filter_dev_sessions


def _session(target_data=None):
    return SimpleNamespace(target_union_info=SimpleNamespace(target_data=target_data or {}))


def _message_session(target_data=None):
    return SimpleNamespace(session_info=_session(target_data))


async def _test_defaults_and_overrides():
    return (
        dev_updates_enabled(_session(), "je")
        and not dev_updates_enabled(_session(), "be")
        and not dev_updates_enabled(_session({"mcv_rss_dev": False}), "je")
        and dev_updates_enabled(_session({"mcbv_rss_dev": True}), "be")
        and not dev_updates_enabled(_message_session({"mcv_rss_dev": False}), "je")
    )


async def _test_filtering():
    sessions = [_session(), _session({"mcv_rss_dev": False}), _session({"mcbv_rss_dev": True})]
    return filter_dev_sessions(sessions, "je") == [sessions[0], sessions[2]] and filter_dev_sessions(sessions, "be") == [
        sessions[2]
    ]


@func_case
async def test_mcv_rss_dev_push_settings(tester: Tester):
    await tester.test(_test_defaults_and_overrides, "开发版本推送默认值与群组覆盖测试")
    await tester.test(_test_filtering, "开发版本推送场景过滤测试")
    return tester
