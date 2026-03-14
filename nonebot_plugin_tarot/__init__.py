import re

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from .data_source import build_usage_text, tarot_manager

__tarot_version__ = "v0.4.0.post4"
__tarot_usages__ = build_usage_text()

TAROT_COMMAND_PATTERN = r"^(?P<cmd>塔罗牌|抽塔罗牌)(?:\s+(?P<arg>.+?))?\s*$"
DIVINE_COMMAND_PATTERN = (
    r"^(?P<cmd>占卜|塔罗牌阵|抽塔罗牌阵)(?:\s+(?P<arg>.+?))?\s*$"
)

TAROT_COMMAND_RE = re.compile(TAROT_COMMAND_PATTERN)
DIVINE_COMMAND_RE = re.compile(DIVINE_COMMAND_PATTERN)


__plugin_meta__ = PluginMetadata(
    name="塔罗牌",
    description="塔罗牌！魔法占卜🔮",
    usage=__tarot_usages__,
    extra={
        "author": "KafCoppelia <k740677208@gmail.com>",
        "version": __tarot_version__,
        "menu_type": "功能",
    },
)

divine = on_regex(pattern=DIVINE_COMMAND_PATTERN, priority=7, block=True)
tarot = on_regex(pattern=TAROT_COMMAND_PATTERN, priority=7, block=True)
chain_reply_switch = on_regex(
    pattern=r"^(开启|启用|关闭|禁用)群聊转发(模式)?$",
    permission=SUPERUSER,
    priority=7,
    block=True,
)


def _extract_arg(text: str, command_re: re.Pattern[str]) -> str:
    matched = command_re.fullmatch(text.strip())
    if matched is None:
        return ""

    arg = matched.group("arg")
    return arg.strip() if arg else ""


@divine.handle()
async def general_divine(bot: Bot, matcher: Matcher, event: MessageEvent):
    arg = _extract_arg(event.get_plaintext(), DIVINE_COMMAND_RE)

    await tarot_manager.divine(bot, matcher, event, formation_query=arg or None)


@tarot.handle()
async def _(matcher: Matcher, event: MessageEvent):
    msg = await tarot_manager.onetime_divine()
    await matcher.finish(msg)


@chain_reply_switch.handle()
async def _(event: GroupMessageEvent):
    arg: str = event.get_plaintext()

    if arg[:2] == "开启" or arg[:2] == "启用":
        tarot_manager.switch_chain_reply(True)
        msg = "占卜群聊转发模式已开启~"
    else:
        tarot_manager.switch_chain_reply(False)
        msg = "占卜群聊转发模式已关闭~"

    await chain_reply_switch.finish(msg)
