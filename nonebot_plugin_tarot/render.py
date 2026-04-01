import base64
from pathlib import Path

from zhenxun import ui
from zhenxun.utils.common_utils import format_usage_for_markdown

from .data_source import (
    FORMATION_SPECS,
    build_unknown_formation_markdown,
    normalize_formation_name,
)
from .types import TarotCardDraw, TarotReading

AI_RESULT_TEMPLATE = Path(__file__).parent / "templates" / "ai_result.html"


def _to_data_uri(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def _chunk_cards(cards: tuple[TarotCardDraw, ...], max_per_row: int = 5) -> list[list[TarotCardDraw]]:
    total = len(cards)
    if total <= 0:
        return []
        
    num_rows = (total + max_per_row - 1) // max_per_row
    base_count = total // num_rows
    remainder = total % num_rows
    
    rows = []
    start = 0
    for i in range(num_rows):
        count = base_count + (1 if i < remainder else 0)
        rows.append(list(cards[start : start + count]))
        start += count
        
    return rows


async def render_unknown_formation(query: str) -> bytes:
    normalized = normalize_formation_name(query)
    page_data = {
        "title": "未找到牌阵",
        "metadata": [
            {"label": "查询", "value": normalized},
            {"label": "可用牌阵", "value": len(FORMATION_SPECS)},
        ],
        "sections": [
            {
                "title": "可用牌阵",
                "content": [
                    format_usage_for_markdown(build_unknown_formation_markdown(query))
                ],
                "is_admin": False,
            }
        ],
    }
    component = ui.template("pages/builtin/help", data=page_data)
    return await ui.render(
        component,
        use_cache=False,
        device_scale_factor=2,
        clip_selector=".wrapper",
        clip_padding=20,
        disable_animations=True,
    )


async def render_ai_result(
    command_name: str,
    question: str,
    reading: TarotReading,
    interpretation: str,
) -> bytes:
    import markdown
    from nonebot_plugin_htmlrender import template_to_pic

    ROMAN_NUMERALS = {
        1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V',
        6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X',
        11: 'XI', 12: 'XII', 13: 'XIII', 14: 'XIV', 15: 'XV',
        16: 'XVI', 17: 'XVII', 18: 'XVIII', 19: 'XIX', 20: 'XX',
        21: 'XXI'
    }

    card_rows = []
    for row in _chunk_cards(reading.cards):
        row_data = []
        for card in row:
            display_label = "切牌" if card.label == "切牌" else ROMAN_NUMERALS.get(card.index, str(card.index))
            row_data.append(
                {
                    "label": display_label,
                    "position_name": card.position_name,
                    "card_title": card.card_title,
                    "meaning": card.meaning,
                    "image_uri": _to_data_uri(card.thumbnail_bytes),
                }
            )
        card_rows.append(row_data)

    # Use markdown module to render interpretation
    md_interpretation = markdown.markdown(interpretation, extensions=["extra"])

    page_data = {
        "title": "塔罗占卜结果",
        "formation": reading.formation_name,
        "question": question,
        "card_rows": card_rows,
        "interpretation": md_interpretation,
    }

    return await template_to_pic(
        template_path=str(Path(__file__).parent / "templates"),
        template_name="ai_result.html",
        templates={"data": page_data},
        pages={"viewport": {"width": 880, "height": 10}},
        wait=0,
    )
