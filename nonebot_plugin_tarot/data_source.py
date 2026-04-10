import asyncio
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import random

from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.adapters.onebot.v11.event import (
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.matcher import Matcher
from PIL import Image

from zhenxun.utils.platform import PlatformUtils

from .config import (
    EventNotSupport,
    PLUGIN_TAROT_JSON_PATH,
    ResourceError,
    ensure_plugin_data_layout,
    get_tarot,
    tarot_config,
)
from .storage import save_tarot_resource
from .types import TarotCardDraw, TarotReading

try:
    import ujson as json
except ModuleNotFoundError:
    import json


@dataclass(frozen=True)
class FormationSpec:
    name: str
    aliases: tuple[str, ...]
    cards_num: int
    is_cut: bool
    representations: tuple[tuple[str, ...], ...]
    suitable_for: str
    # 预留给 LLM 的专属 System Prompt，方便未来 AI 接入
    ai_prompt: str = (
        "请结合用户提出的问题以及上述牌阵的各个位置和牌意，"
        "给出客观、有启发性的详细解读。"
    )

    @property
    def all_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


FORMATION_SPECS: tuple[FormationSpec, ...] = (
    FormationSpec(
        name="圣三角牌阵",
        aliases=("圣三角", "三牌阵"),
        cards_num=3,
        is_cut=False,
        representations=(("现状与处境", "建议采取的行动", "最终可能的结果"),),
        suitable_for="通用问题、快速判断和短期建议",
        ai_prompt=(
            "用户正在使用【圣三角牌阵】进行占卜。请结合用户的问题，"
            "从「现状/处境」、「对策/行动」、「未来/结果」（或根据具体牌位）三个维度进行连贯的推演分析，"
            "并提供具有建设性和指导意义的最终建议。"
        ),
    ),
    FormationSpec(
        name="时间之流牌阵",
        aliases=("时间之流", "时间流", "过去现在未来"),
        cards_num=4,
        is_cut=True,
        representations=(
            (
                "过去的经验与起因",
                "当下的状况与挑战",
                "未来的发展趋势",
                "问卜者的主观想法与潜意识",
            ),
        ),
        suitable_for="梳理阶段变化、查看过去现在未来的走向",
        ai_prompt=(
            "用户正在使用【时间之流牌阵】。请先指出切牌（主观想法）如何影响了局势，"
            "然后按线性时间（过去 -> 现在 -> 未来）剖析事情的来龙去脉与未来走向，给出行事指引。"
        ),
    ),
    FormationSpec(
        name="四要素牌阵",
        aliases=("四要素", "元素牌阵"),
        cards_num=4,
        is_cut=False,
        representations=(
            (
                "火：象征行动，行动上的建议",
                "气：象征言语，沟通上的对策",
                "水：象征感情，情感上的态度",
                "土：象征物质，现实和物质上的准备",
            ),
        ),
        suitable_for="从行动、沟通、情绪和现实条件四个方面拆解问题",
        ai_prompt=(
            "用户正在使用【四要素牌阵】。请分别从火（行动方向）、气（沟通思考）、水（情感直觉）、土（物质保障）"
            "四个独立的维度，为用户的问题提供全方位视角的拆解和对策。"
        ),
    ),
    FormationSpec(
        name="五牌阵",
        aliases=("五牌", "五张牌阵"),
        cards_num=5,
        is_cut=False,
        representations=(
            (
                "核心症结或主要问题",
                "过去产生的影响因素",
                "顺其自然的发展趋势",
                "导致现状的主要原因",
                "采取行动可能带来的最终结果",
            ),
        ),
        suitable_for="分析成因、现状、未来与行动结果",
        ai_prompt=(
            "用户正在使用【五牌阵】。请重点分析“主要问题”与“主要原因”的因果关系，"
            "并比对“顺其自然的发展趋势”与“采取行动可能带来的最终结果”，为用户指明行动的价值。"
        ),
    ),
    FormationSpec(
        name="吉普赛十字阵",
        aliases=("吉普赛十字", "感情十字", "恋爱十字"),
        cards_num=5,
        is_cut=False,
        representations=(
            (
                "对方目前的想法与态度",
                "你自己的想法与态度",
                "两人相处中存在的客观问题",
                "二人目前的外部环境",
                "这段关系最终的发展结果",
            ),
        ),
        suitable_for="感情、暧昧、关系磨合与双人互动问题",
        ai_prompt=(
            "用户正在使用【吉普赛十字阵】占卜情感。请着重比对双方“想法与态度”的同频度，"
            "结合“客观问题”和“外部环境”的双重阻力，预测并给出关系发展的结果及相处建议。"
        ),
    ),
    FormationSpec(
        name="马蹄牌阵",
        aliases=("马蹄", "马蹄铁"),
        cards_num=6,
        is_cut=True,
        representations=(
            (
                "当前的现状",
                "未来可预见的情况",
                "未来不可预知的变数",
                "即将发生的近期事件",
                "最终的发展结果",
                "问卜者内心的主观想法",
            ),
        ),
        suitable_for="查看近期走势、外部变量和短期结果",
        ai_prompt=(
            "用户正在使用【马蹄牌阵】。请综合分析现状，提醒用户关注“不可预知的变数”与“即将发生的事件”，"
            "结合切牌反映出的真实态度，给出规避风险并争取最优结果的建议。"
        ),
    ),
    FormationSpec(
        name="六芒星牌阵",
        aliases=("六芒星", "六角星"),
        cards_num=7,
        is_cut=False,
        representations=(
            (
                "过去的基础与成因",
                "当前的实际状况",
                "未来的自然发展趋势",
                "给出的对策与建议",
                "周围的外部环境与影响",
                "问卜者的真实态度或潜意识",
                "针对该问题的最终预测结果",
            ),
        ),
        suitable_for="复杂问题的综合分析、对策制定与结果预测",
        ai_prompt=(
            "用户正在使用【六芒星牌阵】。这是一个非常全面的分析模型，分为上三角（外部时间与环境）和下三角（内部与对策）。"
            "请统筹这些因素，梳理内外力量的碰撞，最终推导出关于事情发展方向的客观逻辑闭环与温和建议。"
        ),
    ),
    FormationSpec(
        name="平安扇牌阵",
        aliases=("平安扇", "扇牌阵"),
        cards_num=4,
        is_cut=False,
        representations=(
            (
                "目前的人际关系现状",
                "与对方结识的因缘或过去",
                "双方关系未来的阶段性发展",
                "双方关系的最终结论",
            ),
        ),
        suitable_for="朋友、同事、家人等人际关系主题",
        ai_prompt=(
            "用户正在使用【平安扇牌阵】。请解读这段人际关系带来的业力或缘分（因缘），结合现状与未来发展，"
            "告诉用户在与此人相处时应抱有何种期待或划定怎样的边界。"
        ),
    ),
    FormationSpec(
        name="沙迪若之星牌阵",
        aliases=("沙迪若之星", "沙迪若", "星牌阵"),
        cards_num=6,
        is_cut=False,
        representations=(
            (
                "问卜者在这个问题上的真实感受",
                "问题本身的核心本质",
                "潜藏在问题下的影响因素",
                "将问卜者与问题纠缠在一起的过去往事",
                "解决问题需要注意与考虑的细节",
                "顺其自然可能导向的结果",
            ),
        ),
        suitable_for="自我梳理、情绪困扰和问题根源分析",
        ai_prompt=(
            "用户正在使用【沙迪若之星牌阵】。请引导用户关注自己的感受，解开“过去往事”的执念，"
            "进而认清“问题本质”，并提供温和、治愈的心理抚慰与解脱烦恼的可行性建议。"
        ),
    ),
    FormationSpec(
        name="凯尔特十字牌阵",
        aliases=("凯尔特十字", "凯尔特十字阵", "十字牌阵"),
        cards_num=10,
        is_cut=False,
        representations=(
            (
                "问题的核心状况",
                "面临的阻碍或顺流（挑战）",
                "显意识与理性的想法",
                "潜意识与深层的恐惧",
                "过去的经验与基础成因",
                "近期的阶段性发展",
                "问卜者自身的当前状态",
                "周围环境的影响与他人干预",
                "内心的希望与担忧",
                "最终的具体结果",
            ),
        ),
        suitable_for="复杂、长期、信息量大的综合问题",
        ai_prompt=(
            "用户使用磅礴的【凯尔特十字牌阵】。请运用极强的逻辑分析能力，把这10张牌串联成命运演进的过程："
            "展示核心冲突是什么，内外意识的拉扯，环境因素推波助澜，进而推导出最终结局的最可能走向。要求解读具备深度但语气保持谦逊。"
        ),
    ),
    FormationSpec(
        name="二选一牌阵",
        aliases=("二选一", "选择牌阵", "抉择牌阵"),
        cards_num=6,
        is_cut=False,
        representations=(
            (
                "方案A目前的现状",
                "方案A未来的发展",
                "方案B目前的现状",
                "方案B未来的发展",
                "问卜者的真实偏好与潜意识倾向",
                "最后的综合建议与指引",
            ),
        ),
        suitable_for="A/B 选择题、路线抉择和方案比较",
        ai_prompt=(
            "用户面临两难选择，使用了【二选一牌阵】。请将方案 A 和方案 B 的利弊、未来潜力放在天平两端对比。"
            "结合问卜者内心的真实倾向，帮助其打破选择困难，给出清晰但留有余地的选择倾向参考。"
        ),
    ),
    FormationSpec(
        name="身心灵牌阵",
        aliases=("身心灵", "状态牌阵", "自我探索"),
        cards_num=3,
        is_cut=False,
        representations=(
            (
                "身体的健康状况与能量水平",
                "心理的情绪状态与思维模式",
                "灵性层面的指引与觉知",
            ),
        ),
        suitable_for="个人状态、自我成长、压力和恢复节奏",
        ai_prompt=(
            "用户使用了【身心灵牌阵】。请温柔地分析用户的劳累程度、情绪负荷与深层直觉体验，"
            "不要只做预测，而是要重点给予指导——如何爱自己、如何调整身心磁场以获得真正的平衡。"
        ),
    ),
    FormationSpec(
        name="关系发展牌阵",
        aliases=("关系发展", "关系牌阵", "感情发展"),
        cards_num=5,
        is_cut=False,
        representations=(
            (
                "你在关系中的位置与状态",
                "对方在关系中的位置与状态",
                "你们目前的关系现状",
                "发展中将面临的阻碍",
                "关系未来的发展趋势",
            ),
        ),
        suitable_for="感情、合作、人际互动与关系走向",
        ai_prompt=(
            "用户询问关系未来发展，使用了【关系发展牌阵】。请剖析双方供求关系（双方地位、心态是否对等），"
            "指出现状的张力及潜在的“阻碍”，并为跨越阻碍、达成良性终局提出切实可行的建议。"
        ),
    ),
    FormationSpec(
        name="爱情金字塔牌阵",
        aliases=("爱情金字塔", "感情金字塔"),
        cards_num=4,
        is_cut=False,
        representations=(
            (
                "你对这段感情的真实想法与态度",
                "对方对这段感情的想法与态度",
                "你们目前的情感现状与互动表现",
                "这段关系未来的关键发展及预测",
            ),
        ),
        suitable_for="短期感情走势、两人关系现状及未来发展",
        ai_prompt=(
            "用户使用【爱情金字塔牌阵】探测感情状态。请先评估基石（即双方当下的态度和现状）是否结实稳固，"
            "进而推演顶部的“未来发展预测”。若一方态度消极，应如何破局？请给予清晰的建设性指导。"
        ),
    ),
    FormationSpec(
        name="一周运势牌阵",
        aliases=("一周运势", "周运牌阵", "周运"),
        cards_num=7,
        is_cut=False,
        representations=(
            (
                "周一的运势与主要能量",
                "周二的运势与指引",
                "周三的运势与指引",
                "周四的运势与指引",
                "周五的运势与指引",
                "周六的周末开端状态",
                "周日的放松与总结建议",
            ),
        ),
        suitable_for="预测未来一周每天的基本运势走势",
        ai_prompt=(
            "用户希望通过【一周运势牌阵】查看未来七天运势。请概述整周运势的大致起伏节奏，然后分别提炼出每天的关键事件或情绪点"
            "（例如哪天有挑战，哪天适合顺势而为），统合牌意给出整体的开运寄语。"
        ),
    ),
    FormationSpec(
        name="灵感对应牌阵",
        aliases=("灵感对应", "双方内心", "心迹牌阵"),
        cards_num=6,
        is_cut=False,
        representations=(
            (
                "你对这段关系的真实看法与评价",
                "对方对这段关系的真实看法与评价",
                "你认为对方目前处于什么状态",
                "对方认为你目前处于什么状态",
                "你在关系中对未来的期盼或恐惧",
                "对方在关系中对未来的期盼或恐惧",
            ),
        ),
        suitable_for="深入剖析双方的心理状态、认知差异和真实渴望",
        ai_prompt=(
            "用户使用【灵感对应牌阵】。此牌阵意在寻找认知偏差：你以为的TA，是不是真实的TA？"
            "请通过互相映射的牌位比对两人是否存在信息差、对未来的期待是否一致，然后给出最深刻、透彻的心理学级别洞察分析。"
        ),
    ),
)

DEFAULT_AI_FORMATION_NAME = "圣三角牌阵"
IMAGE_FORMAT_EXTENSION_MAP = {
    "JPEG": "jpg",
    "JPG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
    "GIF": "gif",
}


def normalize_formation_name(name: str) -> str:
    return name.strip()


def _build_formation_alias_map() -> dict[str, FormationSpec]:
    alias_map: dict[str, FormationSpec] = {}
    for formation in FORMATION_SPECS:
        for alias in formation.all_names:
            normalized = normalize_formation_name(alias)
            if normalized in alias_map:
                raise ValueError(f"Duplicate tarot formation alias: {normalized}")
            alias_map[normalized] = formation
    return alias_map


FORMATION_ALIAS_MAP = _build_formation_alias_map()


def get_formations() -> tuple[FormationSpec, ...]:
    return FORMATION_SPECS


def get_formation(query: str) -> FormationSpec | None:
    normalized = normalize_formation_name(query)
    if not normalized:
        return None
    return FORMATION_ALIAS_MAP.get(normalized)


def get_default_ai_formation() -> FormationSpec:
    formation = get_formation(DEFAULT_AI_FORMATION_NAME)
    if formation is None:
        raise ResourceError(f"默认AI牌阵 {DEFAULT_AI_FORMATION_NAME} 未配置")
    return formation


def _format_aliases(formation: FormationSpec) -> str:
    return "、".join(formation.aliases)


def format_formation_catalog() -> str:
    lines = []
    for formation in FORMATION_SPECS:
        lines.append(
            f"- `{formation.name}`：{formation.suitable_for}  \n"
            f"  别名：{_format_aliases(formation)}"
        )
    return "\n".join(lines)


def build_unknown_formation_markdown(query: str) -> str:
    normalized = normalize_formation_name(query)
    return "\n".join(
        [
            f"## 未找到牌阵 `{normalized}`",
            "",
            "### 可用牌阵",
            format_formation_catalog(),
            "",
            "### 使用示例",
            "- `占卜 圣三角`",
            "- `塔罗牌阵 凯尔特十字`",
            "- `占卜 圣三角 【我马上要考试了，会怎么样】`",
            "- `塔罗牌 【考试的结果】`",
            "",
            "AI 模式未指定牌阵时，会默认使用 `圣三角牌阵`。",
        ]
    )


def build_usage_text() -> str:
    return "\n".join(
        [
            "## 塔罗牌",
            "",
            "### 普通模式",
            "- `塔罗牌`",
            "- `抽塔罗牌`",
            "- `占卜`",
            "- `占卜 <牌阵名>`",
            "- `塔罗牌阵 <牌阵名>`",
            "- `抽塔罗牌阵 <牌阵名>`",
            "",
            "### AI 模式",
            "- `占卜 【问题】`",
            "- `占卜 <牌阵名> 【问题】`",
            "- `塔罗牌 【问题】`",
            "- `抽塔罗牌 【问题】`",
            "- `塔罗牌阵 <牌阵名> 【问题】`",
            "- `抽塔罗牌阵 <牌阵名> 【问题】`",
            "",
            "AI 模式未指定牌阵时，默认使用 `圣三角牌阵`。",
            "",
            "### 使用示例",
            "- `占卜 圣三角`",
            "- `占卜 【我马上要考试了，会怎么样】`",
            "- `塔罗牌 【考试的结果】`",
            "- `占卜 凯尔特十字 【这段关系会怎么发展】`",
            "",
            "### 牌阵说明",
            "",
            format_formation_catalog(),
            "",
            "### 管理选项",
            "",
            "- `开启群聊转发` / `关闭群聊转发`：切换群聊合并转发模式",
        ]
    ).strip()


def chain_reply(
    bot: Bot,
    chain: list[dict[str, str | dict[str, str | Message | MessageSegment]]],
    msg: Message | MessageSegment,
) -> list[dict[str, str | dict[str, str | Message | MessageSegment]]]:
    return _append_forward_node(
        chain,
        msg,
        uin=bot.self_id,
        name=next(iter(tarot_config.nickname), "Tarot"),
    )


def _append_forward_node(
    chain: list[dict[str, str | dict[str, str | Message | MessageSegment]]],
    msg: Message | MessageSegment,
    *,
    uin: str,
    name: str,
) -> list[dict[str, str | dict[str, str | Message | MessageSegment]]]:
    data = {
        "type": "node",
        "data": {
            "name": name,
            "uin": uin,
            "content": msg,
        },
    }
    chain.append(data)
    return chain


def pick_theme() -> str:
    """
    Random choose a theme from the union of local & official themes
    """
    ensure_plugin_data_layout()
    sub_themes_dir: list[str] = [
        f.name for f in tarot_config.tarot_path.iterdir() if f.is_dir()
    ]

    if len(sub_themes_dir) > 0:
        themes = set(sub_themes_dir).union(tarot_config.tarot_official_themes)
        return random.choice(list(themes))

    return random.choice(tarot_config.tarot_official_themes)


def pick_sub_types(theme: str) -> list[str]:
    """
    Random choose a sub type of the "theme".
    If it is in official themes, all the sub types are available.
    """
    ensure_plugin_data_layout()
    all_sub_types: list[str] = [
        "MajorArcana",
        "Cups",
        "Pentacles",
        "Swords",
        "Wands",
    ]

    if theme == "BilibiliTarot":
        return all_sub_types

    if theme == "TouhouTarot":
        return ["MajorArcana"]

    sub_types: list[str] = [
        f.name
        for f in (tarot_config.tarot_path / theme).iterdir()
        if f.is_dir() and f.name in all_sub_types
    ]

    return sub_types


def _detect_image_extension(image_format: str | None) -> str:
    normalized = (image_format or "").upper().strip()
    return IMAGE_FORMAT_EXTENSION_MAP.get(normalized, normalized.lower() or "png")


class Tarot:
    def __init__(self):
        self.tarot_json = PLUGIN_TAROT_JSON_PATH
        self.is_chain_reply: bool = tarot_config.chain_reply

    async def divine(
        self,
        bot: Bot,
        matcher: Matcher,
        event: MessageEvent,
        formation_query: str | None = None,
    ) -> None:
        """
        General tarot divination.
        """
        if formation_query:
            formation = get_formation(formation_query)
            if formation is None:
                raise ResourceError(f"未找到牌阵：{formation_query}")
        else:
            formation = random.choice(FORMATION_SPECS)

        reading = await self.draw_ai_reading(formation)

        if isinstance(event, GroupMessageEvent) and self.is_chain_reply:
            chain = await self._build_divine_forward_chain(
                bot,
                event,
                formation.name,
                reading,
            )
            await bot.send_group_forward_msg(group_id=event.group_id, messages=chain)
            return

        await matcher.send(f"启用{formation.name}，正在洗牌中")

        for index, card in enumerate(reading.cards):
            msg = self._build_card_message(card)

            if isinstance(event, PrivateMessageEvent):
                if index < len(reading.cards) - 1:
                    await matcher.send(msg)
                else:
                    await matcher.finish(msg)
            elif isinstance(event, GroupMessageEvent):
                if index < len(reading.cards) - 1:
                    await matcher.send(msg)
                    await asyncio.sleep(1)
                else:
                    await matcher.finish(msg)
            else:
                raise EventNotSupport

    async def _build_divine_forward_chain(
        self,
        bot: Bot,
        event: GroupMessageEvent,
        formation_name: str,
        reading: TarotReading,
    ) -> list[dict[str, str | dict[str, str | Message | MessageSegment]]]:
        chain: list[dict[str, str | dict[str, str | Message | MessageSegment]]] = []
        trigger_user_id = event.get_user_id()
        trigger_name = await self._get_trigger_user_name(bot, event)

        _append_forward_node(
            chain,
            event.get_message(),
            uin=trigger_user_id,
            name=trigger_name,
        )
        chain_reply(
            bot,
            chain,
            MessageSegment.text(f"启用{formation_name}，正在洗牌中"),
        )

        for card in reading.cards:
            chain_reply(bot, chain, self._build_card_message(card))
        return chain

    async def _get_trigger_user_name(
        self,
        bot: Bot,
        event: GroupMessageEvent,
    ) -> str:
        user_id = event.get_user_id()
        user = await PlatformUtils.get_user(
            bot,
            user_id,
            group_id=str(event.group_id),
        )
        if user:
            return user.card or user.name or user_id

        sender = getattr(event, "sender", None)
        card = getattr(sender, "card", None) if sender else None
        nickname = getattr(sender, "nickname", None) if sender else None
        return card or nickname or user_id

    async def onetime_divine(self) -> Message | MessageSegment:
        """
        One-time divination.
        """
        theme = pick_theme()
        card = (await self._draw_cards(theme, ("",), is_cut=False))[0]
        return MessageSegment.text("回应是：\n") + self._build_card_body(card)

    async def draw_ai_reading(self, formation: FormationSpec) -> TarotReading:
        theme = pick_theme()
        cards = await self._draw_cards(
            theme,
            tuple(random.choice(formation.representations)),
            formation.is_cut,
        )
        if len(cards) != formation.cards_num:
            raise ResourceError(
                f"Tarot formation {formation.name} is configured incorrectly."
            )
        return TarotReading(
            formation_name=formation.name,
            formation_prompt=formation.ai_prompt,
            theme=theme,
            cards=tuple(cards),
        )

    def switch_chain_reply(self, new_state: bool) -> None:
        """
        开启/关闭全局群聊转发模式
        """
        self.is_chain_reply = new_state

    def _load_cards(
        self,
    ) -> dict[str, dict[str, dict[str, str | dict[str, str]]]]:
        ensure_plugin_data_layout()
        with self.tarot_json.open("r", encoding="utf-8") as f:
            content = json.load(f)
        return content.get("cards", {})

    def _random_cards(
        self,
        all_cards: dict[str, dict[str, dict[str, str | dict[str, str]]]],
        theme: str,
        num: int = 1,
    ) -> list[dict[str, str | dict[str, str]]]:
        """
        Iterate the sub directory, get the subset of cards
        """
        sub_types: list[str] = pick_sub_types(theme)

        if len(sub_types) < 1:
            raise ResourceError(f"本地塔罗牌主题 {theme} 为空！请检查资源！")

        subset: dict[str, dict[str, str | dict[str, str]]] = {
            k: v for k, v in all_cards.items() if v.get("type") in sub_types
        }

        cards_index: list[str] = random.sample(list(subset), num)
        return [subset[k] for k in cards_index]

    async def _draw_cards(
        self,
        theme: str,
        representations: tuple[str, ...],
        is_cut: bool,
    ) -> list[TarotCardDraw]:
        all_cards = self._load_cards()
        cards_info_list = self._random_cards(all_cards, theme, len(representations))
        cards: list[TarotCardDraw] = []
        for index, position_name in enumerate(representations):
            label = (
                "切牌"
                if is_cut and index == len(representations) - 1
                else f"第{index + 1}张牌"
            )
            cards.append(
                await self._build_card_draw(
                    theme=theme,
                    card_info=cards_info_list[index],
                    index=index + 1,
                    label=label,
                    position_name=position_name,
                )
            )
        return cards

    async def _build_card_draw(
        self,
        theme: str,
        card_info: dict[str, str | dict[str, str]],
        index: int,
        label: str,
        position_name: str,
    ) -> TarotCardDraw:
        image = await self._get_card_image(theme, card_info)
        meaning_data = card_info.get("meaning")
        if not isinstance(meaning_data, dict):
            raise ResourceError("塔罗牌牌义配置缺失")

        orientation = "正位" if random.random() < 0.5 else "逆位"
        meaning_key = "up" if orientation == "正位" else "down"
        meaning = str(meaning_data.get(meaning_key, "")).strip()

        if orientation == "逆位":
            image = image.rotate(180)

        return TarotCardDraw(
            index=index,
            label=label,
            position_name=position_name,
            card_name=str(card_info.get("name_cn", "")).strip(),
            orientation=orientation,
            meaning=meaning,
            image_bytes=self._image_to_png_bytes(image),
            thumbnail_bytes=self._build_thumbnail_bytes(image),
        )

    async def _get_card_image(
        self,
        theme: str,
        card_info: dict[str, str | dict[str, str]],
    ) -> Image.Image:
        card_type = str(card_info.get("type", "")).strip()
        image_name = str(card_info.get("pic", "")).strip()
        local_name = ""
        image_dir: Path = tarot_config.tarot_path / theme / card_type

        for path in image_dir.glob(image_name + ".*"):
            local_name = path.name

        if not local_name:
            if theme in tarot_config.tarot_official_themes:
                data = await get_tarot(theme, card_type, image_name)
                if data is None:
                    raise ResourceError("图片下载出错，请重试或将资源部署本地。")
                try:
                    with Image.open(BytesIO(data)) as image:
                        copied_image = image.copy()
                        extension = _detect_image_extension(image.format)
                except OSError as exc:
                    raise ResourceError("塔罗牌图片资源损坏或格式无法识别。") from exc

                try:
                    save_tarot_resource(
                        data,
                        theme=theme,
                        card_type=card_type,
                        image_name=image_name,
                        extension=extension,
                    )
                except OSError as exc:
                    raise ResourceError(
                        "塔罗牌图片缓存失败，请检查 data 目录权限。"
                    ) from exc

                return copied_image

            raise ResourceError(
                f"Tarot image {theme}/{card_type}/{image_name} doesn't exist! "
                f"Make sure the type {card_type} is complete."
            )

        with Image.open(image_dir / local_name) as image:
            return image.copy()

    def _image_to_png_bytes(self, image: Image.Image) -> bytes:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _build_thumbnail_bytes(self, image: Image.Image) -> bytes:
        thumbnail = image.copy()
        thumbnail.thumbnail((220, 330))
        return self._image_to_png_bytes(thumbnail)

    def _build_card_body(self, card: TarotCardDraw) -> Message | MessageSegment:
        return MessageSegment.text(
            f"「{card.card_title}」「{card.meaning}」\n"
        ) + MessageSegment.image(BytesIO(card.image_bytes))

    def _build_card_message(self, card: TarotCardDraw) -> Message | MessageSegment:
        return MessageSegment.text(f"{card.display_title}\n") + self._build_card_body(
            card
        )


tarot_manager = Tarot()
