import random

from .types import TarotAIFailureCategory

AI_PENDING_MESSAGES: tuple[str, ...] = (
    "✧ 共鸣中.. ✧",
    "✧ 演算中.. ✧",
)

AI_FAILURE_MESSAGES_UPSTREAM: tuple[str, ...] = (
    "✧ 星象干扰，共鸣中断.. ✧",
    "✧ 灵子浓度不足，演算超时.. ✧",
    "✧ 迷雾过重，无法看清牌面.. ✧",
    "✧ 潜意识链接丢失.. 请重试 ✧",
)

AI_FAILURE_MESSAGES_FILTERED: tuple[str, ...] = (
    "✧ 触碰命运盲区，演算终止.. ✧",
    "✧ 牌意混沌，系统拒绝解读.. ✧",
    "✧ 涉足禁忌领域，阿卡夏记录已锁定.. ✧",
)

AI_FAILURE_MESSAGES_INTERNAL: tuple[str, ...] = (
    "✧ 命运之轮逆位（系统故障）.. ✧",
    "✧ 观测坍缩，请稍后重新抽取.. ✧",
    "✧ 星盘崩坏，正在尝试重铸.. ✧",
)


def pick_pending_message() -> str:
    return random.choice(AI_PENDING_MESSAGES)


def pick_failure_message(category: TarotAIFailureCategory) -> str:
    if category == "filtered":
        return random.choice(AI_FAILURE_MESSAGES_FILTERED)
    if category == "upstream":
        return random.choice(AI_FAILURE_MESSAGES_UPSTREAM)
    return random.choice(AI_FAILURE_MESSAGES_INTERNAL)
