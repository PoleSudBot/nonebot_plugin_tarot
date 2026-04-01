import re

from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.permission import SUPERUSER

from zhenxun.models.user_console import UserConsole
from zhenxun.services import chat
from zhenxun.services.log import logger
from zhenxun.services.llm import LLMException
from zhenxun.services.llm.config.generation import (
    CoreConfig,
    LLMGenerationConfig,
    ReasoningConfig,
    ReasoningEffort,
)
from zhenxun.services.llm.types import LLMErrorCode
from zhenxun.utils.enum import GoldHandle
from zhenxun.utils.exception import InsufficientGold
from zhenxun.utils.platform import PlatformUtils

from .config import get_ai_cost_gold, get_ai_model_name, get_ai_daily_limit
from .data_source import get_default_ai_formation, get_formation, tarot_manager
from .models import TarotAIDailyUsage
from .prompt_loader import build_system_prompt, build_user_prompt
from .render import render_ai_result
from .types import (
    ParsedTarotCommand,
    TarotAIFailureCategory,
    TarotAIRequestContext,
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_CODE_BLOCK_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*|\s*```\s*$")
_PLUGIN_SOURCE = "nonebot_plugin_tarot"


class TarotAIUserError(Exception):
    def __init__(
        self,
        message: str,
        category: TarotAIFailureCategory = "user_input",
    ):
        self.message = message
        self.category = category
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


def _build_generation_config() -> LLMGenerationConfig:
    return LLMGenerationConfig(
        core=CoreConfig(),
        reasoning=ReasoningConfig(
            effort=ReasoningEffort.HIGH,
            show_thoughts=False,
        ),
    )


def _clean_ai_text(text: str) -> str:
    cleaned = _THINK_RE.sub("", text or "").strip()
    if cleaned.startswith("```"):
        cleaned = _CODE_BLOCK_RE.sub("", cleaned).strip()
    return cleaned.strip()


def _log_ai_error(
    level: str,
    message: str,
    *,
    context: TarotAIRequestContext,
    exc: Exception,
) -> None:
    log_func = getattr(logger, level)
    log_func(
        message,
        "塔罗AI",
        session=context.user_id,
        platform=context.platform,
        e=exc,
    )


def _wrap_internal_error(
    message: str,
    *,
    context: TarotAIRequestContext,
    exc: Exception,
) -> TarotAIUserError:
    _log_ai_error("error", message, context=context, exc=exc)
    return TarotAIUserError("AI占卜暂时不可用，请稍后再试。", category="internal")


def _wrap_upstream_error(
    *,
    context: TarotAIRequestContext,
    exc: LLMException,
) -> TarotAIUserError:
    category: TarotAIFailureCategory = (
        "filtered" if exc.code == LLMErrorCode.CONTENT_FILTERED else "upstream"
    )
    _log_ai_error("warning", "塔罗AI调用失败", context=context, exc=exc)
    return TarotAIUserError("AI占卜暂时不可用，请稍后再试。", category=category)


async def prepare_ai_request(
    bot: Bot,
    event: MessageEvent,
    parsed_command: ParsedTarotCommand,
) -> TarotAIRequestContext:
    question = (parsed_command.question or "").strip()
    if not question:
        raise TarotAIUserError("AI占卜需要在【】里提供问题。")

    formation = (
        get_formation(parsed_command.formation_query)
        if parsed_command.formation_query
        else get_default_ai_formation()
    )
    if formation is None:
        raise TarotAIUserError("未找到指定牌阵。")

    user_id = event.get_user_id()
    platform = PlatformUtils.get_platform(bot) or "unknown"
    is_superuser = await SUPERUSER(bot, event)
    cost_gold = get_ai_cost_gold()

    if not is_superuser:
        remaining_count = await TarotAIDailyUsage.get_remaining_count(
            user_id=user_id,
            platform=platform,
            daily_limit=get_ai_daily_limit(),
        )
        if remaining_count <= 0:
            raise TarotAIUserError("今天的AI占卜次数已经用完了。")

        if cost_gold > 0:
            user = await UserConsole.get_user(user_id, platform)
            if user.gold < cost_gold:
                raise TarotAIUserError(f"金币不足，AI占卜需要{cost_gold}金币。")

    return TarotAIRequestContext(
        question=question,
        formation=formation,
        user_id=user_id,
        platform=platform,
        is_superuser=is_superuser,
        cost_gold=cost_gold,
    )


async def run_ai_divination(
    bot: Bot,
    event: MessageEvent,
    parsed_command: ParsedTarotCommand,
    context: TarotAIRequestContext | None = None,
) -> bytes:
    context = context or await prepare_ai_request(bot, event, parsed_command)

    try:
        reading = await tarot_manager.draw_ai_reading(context.formation)
        system_prompt = build_system_prompt(reading.formation_prompt)
        user_prompt = build_user_prompt(
            parsed_command.command,
            context.question,
            reading,
        )
    except TarotAIUserError:
        raise
    except Exception as exc:
        raise _wrap_internal_error(
            "塔罗AI预处理失败",
            context=context,
            exc=exc,
        ) from exc

    try:
        response = await chat(
            user_prompt,
            model=get_ai_model_name(),
            instruction=system_prompt,
            config=_build_generation_config(),
            timeout=90,
        )
    except LLMException as exc:
        raise _wrap_upstream_error(context=context, exc=exc) from exc

    interpretation = _clean_ai_text(response.text)
    if not interpretation:
        logger.warning(
            "塔罗AI返回空解读",
            "塔罗AI",
            session=context.user_id,
            platform=context.platform,
        )
        raise TarotAIUserError("AI占卜暂时不可用，请稍后再试。", "upstream")

    try:
        image_bytes = await render_ai_result(
            parsed_command.command,
            context.question,
            reading,
            interpretation,
        )
    except Exception as exc:
        raise _wrap_internal_error(
            "塔罗AI结果渲染失败",
            context=context,
            exc=exc,
        ) from exc

    if not context.is_superuser:
        if context.cost_gold > 0:
            try:
                await UserConsole.reduce_gold(
                    context.user_id,
                    context.cost_gold,
                    GoldHandle.PLUGIN,
                    _PLUGIN_SOURCE,
                    context.platform,
                )
            except InsufficientGold as exc:
                raise TarotAIUserError(
                    f"金币不足，AI占卜需要{context.cost_gold}金币。"
                ) from exc
            except Exception as exc:
                raise _wrap_internal_error(
                    "塔罗AI扣除金币失败",
                    context=context,
                    exc=exc,
                ) from exc
        try:
            await TarotAIDailyUsage.consume_today(context.user_id, context.platform)
        except Exception as exc:
            raise _wrap_internal_error(
                "塔罗AI计次失败",
                context=context,
                exc=exc,
            ) from exc

    return image_bytes
