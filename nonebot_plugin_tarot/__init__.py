from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .ai_service import TarotAIUserError, prepare_ai_request, run_ai_divination
from .command_parser import (
    BONUS_COMMAND_PATTERN,
    DIVINE_COMMAND_PATTERN,
    DIVINE_COMMAND_RE,
    TAROT_COMMAND_PATTERN,
    TAROT_COMMAND_RE,
    parse_bonus_command,
    parse_tarot_command,
)
from .config import (
    AI_CONFIG_MODULE,
    DEFAULT_AI_COST_GOLD,
    DEFAULT_AI_DAILY_LIMIT,
    DEFAULT_AI_MODEL_NAME,
)
from .copywriting import (
    pick_failure_message,
    pick_locked_message,
    pick_pending_message,
)
from .data_source import build_usage_text, get_formation, tarot_manager
from .models import TarotAIDailyUsage
from .render import render_unknown_formation
from .runtime_state import acquire_ai_lock, release_ai_lock

__tarot_version__ = "v1.0.0"
__tarot_usages__ = build_usage_text()


__plugin_meta__ = PluginMetadata(
    name="塔罗牌",
    description="塔罗牌占卜",
    usage=__tarot_usages__,
    extra=PluginExtraData(
        author="k1yuyu",
        version=__tarot_version__,
        menu_type="功能",
        configs=[
            RegisterConfig(
                module=AI_CONFIG_MODULE,
                key="AI_MODEL_NAME",
                value=DEFAULT_AI_MODEL_NAME,
                help="塔罗AI占卜使用的模型名称",
                default_value=DEFAULT_AI_MODEL_NAME,
            ),
            RegisterConfig(
                module=AI_CONFIG_MODULE,
                key="AI_DAILY_LIMIT",
                value=DEFAULT_AI_DAILY_LIMIT,
                help="普通用户每日可用的塔罗AI占卜次数",
                default_value=DEFAULT_AI_DAILY_LIMIT,
                type=int,
            ),
            RegisterConfig(
                module=AI_CONFIG_MODULE,
                key="AI_COST_GOLD",
                value=DEFAULT_AI_COST_GOLD,
                help="普通用户每次使用塔罗AI占卜消耗的金币",
                default_value=DEFAULT_AI_COST_GOLD,
                type=int,
            ),
        ],
        superuser_help="`补魔 <QQ号/@用户> <次数>`",
    ).to_dict(),
)

divine = on_regex(pattern=DIVINE_COMMAND_PATTERN, priority=7, block=True)
tarot = on_regex(pattern=TAROT_COMMAND_PATTERN, priority=7, block=True)
bonus = on_regex(
    pattern=BONUS_COMMAND_PATTERN,
    permission=SUPERUSER,
    priority=7,
    block=True,
)
chain_reply_switch = on_regex(
    pattern=r"^(开启|启用|关闭|禁用)群聊转发(模式)?$",
    permission=SUPERUSER,
    priority=7,
    block=True,
)


async def _send_unknown_formation(query: str) -> None:
    image_bytes = await render_unknown_formation(query)
    await MessageUtils.build_message(image_bytes).finish()


def _build_quoted_message(
    event: MessageEvent,
    message: Message | MessageSegment,
) -> Message:
    return MessageSegment.reply(event.message_id) + message


async def _finish_reply_message(
    matcher: Matcher,
    event: MessageEvent,
    message: str | bytes | Message | MessageSegment,
) -> None:
    if isinstance(message, Message | MessageSegment):
        await matcher.finish(_build_quoted_message(event, message))
        return
    await MessageUtils.build_message(message).finish(reply_to=True)


async def _send_unknown_formation_reply(
    matcher: Matcher,
    event: MessageEvent,
    query: str,
) -> None:
    image_bytes = await render_unknown_formation(query)
    await MessageUtils.build_message(image_bytes).finish(reply_to=True)


async def _dispatch_tarot_command(
    bot: Bot,
    matcher: Matcher,
    event: MessageEvent,
    *,
    command_re,
) -> None:
    parsed_command = parse_tarot_command(event.get_plaintext(), command_re)

    if parsed_command.is_ai:
        if parsed_command.formation_query and not get_formation(
            parsed_command.formation_query
        ):
            await _send_unknown_formation_reply(
                matcher,
                event,
                parsed_command.formation_query,
            )
            return

        try:
            context = await prepare_ai_request(bot, event, parsed_command)
        except TarotAIUserError as exc:
            await _finish_reply_message(matcher, event, str(exc))
            return

        acquired = await acquire_ai_lock(context.platform, context.user_id)
        if not acquired:
            await _finish_reply_message(matcher, event, pick_locked_message())
            return

        try:
            await matcher.send(pick_pending_message())

            try:
                image_bytes = await run_ai_divination(
                    bot,
                    event,
                    parsed_command,
                    context=context,
                )
            except TarotAIUserError as exc:
                if exc.category == "user_input":
                    await _finish_reply_message(matcher, event, str(exc))
                    return
                await _finish_reply_message(
                    matcher,
                    event,
                    pick_failure_message(exc.category),
                )
                return

            await _finish_reply_message(matcher, event, image_bytes)
        finally:
            await release_ai_lock(context.platform, context.user_id)
        return

    if parsed_command.command in {"塔罗牌", "抽塔罗牌"}:
        msg = await tarot_manager.onetime_divine()
        await _finish_reply_message(matcher, event, msg)
        return

    if parsed_command.formation_query and not get_formation(
        parsed_command.formation_query
    ):
        await _send_unknown_formation(parsed_command.formation_query)
        return

    await tarot_manager.divine(bot, matcher, event, parsed_command.formation_query)


@divine.handle()
async def general_divine(bot: Bot, matcher: Matcher, event: MessageEvent):
    await _dispatch_tarot_command(
        bot,
        matcher,
        event,
        command_re=DIVINE_COMMAND_RE,
    )


@tarot.handle()
async def tarot_draw(bot: Bot, matcher: Matcher, event: MessageEvent):
    await _dispatch_tarot_command(
        bot,
        matcher,
        event,
        command_re=TAROT_COMMAND_RE,
    )


@bonus.handle()
async def add_ai_bonus(bot: Bot, event: MessageEvent):
    parsed = parse_bonus_command(event.get_message())
    if parsed is None:
        await bonus.finish("用法：补魔 <QQ号/@用户> <次数>")
        return

    platform = PlatformUtils.get_platform(bot) or "unknown"
    await TarotAIDailyUsage.add_bonus_today(
        user_id=parsed.target_user_id,
        platform=platform,
        count=parsed.count,
    )
    await bonus.finish(
        f"已为 {parsed.target_user_id} 增加今日 AI 占卜次数 {parsed.count} 次。"
    )


@chain_reply_switch.handle()
async def switch_chain_reply(event: GroupMessageEvent):
    arg = event.get_plaintext()

    if arg[:2] in {"开启", "启用"}:
        tarot_manager.switch_chain_reply(True)
        msg = "占卜群聊转发模式已开启~"
    else:
        tarot_manager.switch_chain_reply(False)
        msg = "占卜群聊转发模式已关闭~"

    await chain_reply_switch.finish(msg)
