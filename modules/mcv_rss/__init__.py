import re
from datetime import datetime

import orjson
from bs4 import BeautifulSoup
from google_play_scraper import app as google_play_scraper

from core.builtins.bot import Bot
from core.builtins.message.chain import MessageChain
from core.builtins.message.internal import I18NContext, FormattedTime
from core.component import module
from core.config.core import CoreConfig
from core.constants import Secret
from core.logger import Logger
from core.scheduler import IntervalTrigger
from core.utils.http import get_url
from core.utils.storedata import get_stored_list, update_stored_list
from core.utils.web_render import web_render, SourceOptions

SNAPSHOT_PATTERN = re.compile(r"^(?P<major>[\d.]+)-snapshot-?(?P<patch>\d+)$")
OLD_SNAPSHOT_PATTERN = re.compile(r"^(1\d)|(2[0-5])[w|W]\d{2}[A-Fa-f]$")
PRERELEASE_PATTERN = re.compile(r"^(?P<major>[\d.]+)-pre-?(?P<patch>\d+)$")
RELEASE_CANDIDATE_PATTERN = re.compile(r"^(?P<major>[\d.]+)-rc-?(?P<patch>\d+)$")
RELEASE_PATTERN = re.compile(r"^\d{1,2}\.\d+(\.\d+)?$")

CHANGELOG_URL_PREFIX = "https://www.minecraft.net/en-us/article/minecraft"

BETA_PREVIEW_SECTION_URL = "https://feedback.minecraft.net/hc/en-us/sections/360001185332-Beta-and-Preview-Information-and-Changelogs"
DEV_UPDATE_TARGET_KEYS = {"je": "mcv_rss_dev", "be": "mcbv_rss_dev"}
DEV_UPDATE_DEFAULTS = {"je": True, "be": False}


def dev_updates_enabled(session, edition: str) -> bool:
    target_union_info = getattr(session, "target_union_info", None)
    if target_union_info is None:
        session_info = getattr(session, "session_info", None)
        target_union_info = getattr(session_info, "target_union_info", None)
    target_data = getattr(target_union_info, "target_data", {}) if target_union_info else {}
    return bool(target_data.get(DEV_UPDATE_TARGET_KEYS[edition], DEV_UPDATE_DEFAULTS[edition]))


def filter_dev_sessions(session_list, edition: str):
    return [session for session in session_list if dev_updates_enabled(session, edition)]


async def post_dev_update(module_name: str, message: MessageChain, edition: str):
    sessions = await Bot.get_enabled_this_module(module_name)
    await Bot.post_message(module_name, message=message, session_list=filter_dev_sessions(sessions, edition))


async def get_bedrock_preview_version() -> str:
    html = await get_url(BETA_PREVIEW_SECTION_URL, attempt=1, logging_err_resp=False)
    soup = BeautifulSoup(html, "html.parser")
    for article in soup.find_all("a"):
        title = article.get_text(" ", strip=True)
        match = re.match(r"^Minecraft Beta & Preview - (?P<version>[\d./]+)$", title)
        if match:
            return match.group("version")
    return ""


def get_changelog_url(version: str) -> str | None:
    """Generate changelog url of the given minecraft version id"""
    if m := re.match(SNAPSHOT_PATTERN, version):
        return f"{CHANGELOG_URL_PREFIX}-{m.group('major').replace('.', '-')}-snapshot-{m.group('patch')}"
    if m := re.match(PRERELEASE_PATTERN, version):
        return f"{CHANGELOG_URL_PREFIX}-{m.group('major').replace('.', '-')}-pre-release-{m.group('patch')}"
    if m := re.match(RELEASE_CANDIDATE_PATTERN, version):
        return f"{CHANGELOG_URL_PREFIX}-{m.group('major').replace('.', '-')}-release-candidate-{m.group('patch')}"
    if re.match(RELEASE_PATTERN, version):
        return f"{CHANGELOG_URL_PREFIX}-java-edition-{version.replace('.', '-')}"
    if re.match(OLD_SNAPSHOT_PATTERN, version):
        return f"{CHANGELOG_URL_PREFIX}-snapshot-{version}"
    return None


async def get_article(version):
    link = get_changelog_url(version)
    try:
        if link:
            html = await web_render.source(SourceOptions(url=str(link)))

            soup = BeautifulSoup(html, "html.parser")

            title = soup.find("h1")
            if title and title.text == "404":
                return "", ""
            if title:
                return link, title.text
    except Exception:
        if CoreConfig.debug:
            Logger.exception()
    return "", ""


startup_mute = [True, True]

mcv_rss = module(
    "mcv-rss",
    developers=["OasisAkari", "Dianliang233"],
    # recommend_modules=["mcv_jira_rss"],
    desc="{I18N:mcv_rss.help.mcv-rss.desc}",
    alias=["mcv_rss", "mcvrss"],
    doc=True,
    rss=True,
)


@mcv_rss.command(
    "dev <edition> <action> {{I18N:mcv_rss.help.dev}}",
    required_admin=True,
    available_without_enable=True,
)
async def _(msg: Bot.MessageSession, edition: str, action: str):
    edition = edition.lower()
    action = action.lower()
    if edition not in DEV_UPDATE_TARGET_KEYS:
        await msg.finish(I18NContext("mcv_rss.message.dev.invalid-edition"))
    if action not in {"on", "off", "status"}:
        await msg.finish(I18NContext("mcv_rss.message.dev.invalid-action"))
    enabled = dev_updates_enabled(msg, edition)
    if action == "status":
        await msg.finish(I18NContext("mcv_rss.message.dev.status", edition=edition.upper(), enabled="开启" if enabled else "关闭"))
    new_value = action == "on"
    await msg.session_info.target_union_info.edit_target_data(DEV_UPDATE_TARGET_KEYS[edition], new_value)
    await msg.finish(I18NContext("mcv_rss.message.dev.updated", edition=edition.upper(), enabled="开启" if new_value else "关闭"))


mcbv_rss = module(
    "mcbv-rss",
    developers=["OasisAkari"],
    desc="{I18N:mcv_rss.help.mcbv-rss.desc}",
    alias=["mcbv_rss", "mcbvrss"],
    doc=True,
    rss=True,
)

# for future use

# mcv_jira_rss = module(
#     "mcv_jira_rss",
#     developers=["OasisAkari", "Dianliang233"],
#     recommend_modules=["mcv_rss"],
#     desc="{I18N:mcv_rss.help.mcv-jira-rss.desc}",
#     alias="mcvjirarss",
#     doc=True,
#     rss=True,
# )
#
#
# @mcv_jira_rss.hook()
# async def _(fetch: Bot, ctx: Bot.ModuleHookContext):
#     await fetch.post_message("mcv_jira_rss", **ctx.args)


@mcv_rss.schedule(IntervalTrigger(seconds=60))
async def _():
    global startup_mute
    url = "https://piston-meta.mojang.com/mc/game/version_manifest.json"
    try:
        verlist = await get_stored_list(Bot.Info.client_name, "mcv_rss")
        file = orjson.loads(await get_url(url, attempt=1, logging_err_resp=False))
        latest = file.get("latest", {})
        release = latest.get("release", "")
        snapshot = latest.get("snapshot", "")
        time_release = 0
        time_snapshot = 0
        for v in file.get("versions", []):
            if v.get("id") == release:
                time_release = datetime.fromisoformat(v.get("releaseTime", "")).timestamp()
            if v.get("id") == snapshot:
                time_snapshot = datetime.fromisoformat(v.get("releaseTime", "")).timestamp()

        if release not in verlist:
            Logger.info(f"Huh, we found {release}.")

            if not startup_mute[0]:
                await Bot.post_message(
                    "mcv-rss",
                    message=MessageChain.assign(
                        [
                            I18NContext(
                                "mcv_rss.message.mcv-rss.release",
                                version=release,
                                record_time=FormattedTime(time_release, simple=True),
                                posted_time=FormattedTime(datetime.now().timestamp(), simple=True),
                            ),
                        ]
                    ),
                )
            verlist.append(release)
            await update_stored_list(Bot.Info.client_name, "mcv_rss", verlist)
            article = await get_article(release)
            if article[0] != "":
                get_stored_news_title = await get_stored_list(Bot.Info.client_name, "mcnews")
                if article[1] not in get_stored_news_title:
                    if not startup_mute[0]:
                        await Bot.post_message(
                            "minecraft-news",
                            message=MessageChain.assign(
                                [
                                    I18NContext(
                                        "minecraft_news.message.update_log",
                                        version=release,
                                        article=article[0],
                                    )
                                ]
                            ),
                        )
                    get_stored_news_title.append(article[1])
                    await update_stored_list(Bot.Info.client_name, "mcnews", get_stored_news_title)
        if snapshot not in verlist:
            Logger.info(f"Huh, we found {snapshot}.")
            if not startup_mute[0]:
                await post_dev_update(
                    "mcv-rss",
                    MessageChain.assign(
                        [
                            I18NContext(
                                "mcv_rss.message.mcv-rss.snapshot",
                                version=file["latest"]["snapshot"],
                                record_time=FormattedTime(time_snapshot, simple=True),
                                posted_time=FormattedTime(datetime.now().timestamp(), simple=True),
                            ),
                        ]
                    ),
                    "je",
                )
            verlist.append(snapshot)
            await update_stored_list(Bot.Info.client_name, "mcv_rss", verlist)
            article = await get_article(snapshot)
            if article[0] != "":
                get_stored_news_title = await get_stored_list(Bot.Info.client_name, "mcnews")
                if article[1] not in get_stored_news_title:
                    if not startup_mute[0]:
                        await post_dev_update(
                            "minecraft-news",
                            MessageChain.assign(
                                [
                                    I18NContext(
                                        "minecraft_news.message.update_log",
                                        version=snapshot,
                                        article=article[0],
                                    )
                                ]
                            ),
                            "je",
                        )
                    get_stored_news_title.append(article[1])
                    await update_stored_list(Bot.Info.client_name, "mcnews", get_stored_news_title)
        startup_mute[0] = False
    except Exception:
        if CoreConfig.debug:
            Logger.exception()


@mcbv_rss.schedule(IntervalTrigger(seconds=180))
async def _():
    global startup_mute
    if Secret.ip_country == "China" or not Secret.ip_country:
        return  # 中国大陆无法访问Google Play商店
    try:
        verlist = await get_stored_list(Bot.Info.client_name, "mcbv_rss")
        version = google_play_scraper("com.mojang.minecraftpe")["version"]
        preview_version = await get_bedrock_preview_version()
        if preview_version and preview_version not in verlist:
            Logger.info(f"Huh, we found Bedrock Preview {preview_version}.")
            if not startup_mute[1]:
                await post_dev_update(
                    "mcbv-rss",
                    MessageChain.assign([I18NContext("mcv_rss.message.mcbv-rss.preview", version=preview_version)]),
                    "be",
                )
            verlist.append(preview_version)
            await update_stored_list(Bot.Info.client_name, "mcbv_rss", verlist)

        if version not in verlist:
            Logger.info(f"Huh, we found Bedrock {version}.")
            if not startup_mute[1]:
                await Bot.post_message(
                    "mcbv-rss",
                    message=MessageChain.assign([I18NContext("mcv_rss.message.mcbv-rss", version=version)]),
                )
                verlist.append(version)
            await update_stored_list(Bot.Info.client_name, "mcbv_rss", verlist)
        startup_mute[1] = False
    except Exception:
        if CoreConfig.debug:
            Logger.exception()
