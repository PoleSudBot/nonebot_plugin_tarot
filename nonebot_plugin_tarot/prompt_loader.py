from pathlib import Path

from .types import TarotReading

PROMPT_PATH = Path(__file__).with_name("prompt.md")
OUTPUT_CONSTRAINTS = """
请只输出最终解读正文，不要输出你的思考过程，不要输出 `<think>` 标签，不要使用代码块。
允许使用简洁的 Markdown 段落或列表，但不要重复列出牌面原始信息，也不要写“作为AI”之类的表述。
""".strip()


def load_base_prompt() -> str:
    if not PROMPT_PATH.exists():
        return ""
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_system_prompt(formation_prompt: str) -> str:
    sections = [load_base_prompt(), formation_prompt.strip(), OUTPUT_CONSTRAINTS]
    return "\n\n".join(section for section in sections if section)


def build_user_prompt(
    command_name: str,
    question: str,
    reading: TarotReading,
) -> str:
    lines = [
        f"用户问题：{question}",
        f"触发指令：{command_name}",
        f"所用牌阵：{reading.formation_name}",
        "",
        "本次抽牌结果：",
    ]

    for card in reading.cards:
        lines.append(
            f"- {card.label}｜牌位：{card.position_name}｜牌名：{card.card_name}｜方向：{card.orientation}｜基础牌义：{card.meaning}"
        )

    lines.append("")
    lines.append(
        "请结合用户问题和以上牌面信息，直接给出一段完整、自然、可读的中文解读。"
    )
    return "\n".join(lines)
