import re

from nonebot.adapters.onebot.v11 import Message

from .types import BonusCommand, ParsedTarotCommand

TAROT_COMMAND_PATTERN = r"^(?P<cmd>塔罗牌|抽塔罗牌)(?:\s+(?P<arg>.+?))?\s*$"
DIVINE_COMMAND_PATTERN = (
    r"^(?P<cmd>占卜|塔罗牌阵|抽塔罗牌阵)(?:\s+(?P<arg>.+?))?\s*$"
)
BONUS_COMMAND_PATTERN = r"^补魔(?:\s+.+)?$"

TAROT_COMMAND_RE = re.compile(TAROT_COMMAND_PATTERN)
DIVINE_COMMAND_RE = re.compile(DIVINE_COMMAND_PATTERN)
AI_QUESTION_RE = re.compile(r"^(?P<prefix>.*?)\s*【(?P<question>.+?)】\s*$")


def parse_tarot_command(
    text: str,
    command_re: re.Pattern[str],
) -> ParsedTarotCommand:
    matched = command_re.fullmatch(text.strip())
    if matched is None:
        raise ValueError(f"无法解析塔罗指令: {text}")

    command = matched.group("cmd")
    raw_arg = matched.group("arg")
    arg = raw_arg.strip() if raw_arg else ""

    if not arg:
        return ParsedTarotCommand(
            command=command,
            raw_arg=None,
            formation_query=None,
            question=None,
            is_ai=False,
        )

    question_match = AI_QUESTION_RE.fullmatch(arg)
    if question_match:
        prefix = question_match.group("prefix").strip()
        question = question_match.group("question").strip()
        return ParsedTarotCommand(
            command=command,
            raw_arg=arg,
            formation_query=prefix or None,
            question=question or None,
            is_ai=True,
        )

    return ParsedTarotCommand(
        command=command,
        raw_arg=arg,
        formation_query=arg,
        question=None,
        is_ai=False,
    )


def parse_bonus_command(message: Message) -> BonusCommand | None:
    text_parts: list[str] = []
    target_user_id: str | None = None

    for segment in message:
        if segment.type == "at" and target_user_id is None:
            qq = str(segment.data.get("qq", "")).strip()
            if qq and qq not in {"0", "all"}:
                target_user_id = qq
        elif segment.type == "text":
            text_parts.append(segment.data.get("text", ""))

    plain_text = re.sub(r"\s+", " ", "".join(text_parts)).strip()
    if not plain_text.startswith("补魔"):
        return None

    rest = re.sub(r"^补魔\s*", "", plain_text).strip()
    if not rest and target_user_id is None:
        return None

    if target_user_id is None:
        tokens = rest.split()
        if len(tokens) != 2:
            return None
        target_user_id, count_text = tokens
    else:
        tokens = rest.split()
        if len(tokens) != 1:
            return None
        count_text = tokens[0]

    if not target_user_id.isdigit():
        return None

    try:
        count = int(count_text)
    except ValueError:
        return None

    if count <= 0:
        return None

    return BonusCommand(target_user_id=target_user_id, count=count)
