import asyncio
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import random

from nonebot.adapters.onebot.v11 import Bot, MessageSegment
from nonebot.adapters.onebot.v11.event import (
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.matcher import Matcher
from PIL import Image

from .config import EventNotSupport, ResourceError, get_tarot, tarot_config

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

    @property
    def all_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


FORMATION_SPECS: tuple[FormationSpec, ...] = (
    FormationSpec(
        name="圣三角牌阵",
        aliases=("圣三角", "三牌阵"),
        cards_num=3,
        is_cut=False,
        representations=(
            ("处境", "行动", "结果"),
            ("现状", "愿望", "行动"),
        ),
        suitable_for="通用问题、快速判断和短期建议",
    ),
    FormationSpec(
        name="时间之流牌阵",
        aliases=("时间之流", "时间流", "过去现在未来"),
        cards_num=4,
        is_cut=True,
        representations=(("过去", "现在", "未来", "问卜者的主观想法"),),
        suitable_for="梳理阶段变化、查看过去现在未来的走向",
    ),
    FormationSpec(
        name="四要素牌阵",
        aliases=("四要素", "元素牌阵"),
        cards_num=4,
        is_cut=False,
        representations=(
            (
                "火，象征行动，行动上的建议",
                "气，象征言语，言语上的对策",
                "水，象征感情，感情上的态度",
                "土，象征物质，物质上的准备",
            ),
        ),
        suitable_for="从行动、沟通、情绪和现实条件四个方面拆解问题",
    ),
    FormationSpec(
        name="五牌阵",
        aliases=("五牌", "五张牌阵"),
        cards_num=5,
        is_cut=True,
        representations=(
            (
                "现在或主要问题",
                "过去的影响",
                "未来",
                "主要原因",
                "行动可能带来的结果",
            ),
        ),
        suitable_for="分析成因、现状、未来与行动结果",
    ),
    FormationSpec(
        name="吉普赛十字阵",
        aliases=("吉普赛十字", "感情十字", "恋爱十字"),
        cards_num=5,
        is_cut=False,
        representations=(
            (
                "对方的想法",
                "你的想法",
                "相处中存在的问题",
                "二人目前的环境",
                "关系发展的结果",
            ),
        ),
        suitable_for="感情、暧昧、关系磨合与双人互动问题",
    ),
    FormationSpec(
        name="马蹄牌阵",
        aliases=("马蹄", "马蹄铁"),
        cards_num=6,
        is_cut=True,
        representations=(
            (
                "现状",
                "可预知的情况",
                "不可预知的情况",
                "即将发生的",
                "结果",
                "问卜者的主观想法",
            ),
        ),
        suitable_for="查看近期走势、外部变量和短期结果",
    ),
    FormationSpec(
        name="六芒星牌阵",
        aliases=("六芒星", "六角星"),
        cards_num=7,
        is_cut=True,
        representations=(
            ("过去", "现在", "未来", "对策", "环境", "态度", "预测结果"),
        ),
        suitable_for="复杂问题的综合分析、对策制定与结果预测",
    ),
    FormationSpec(
        name="平安扇牌阵",
        aliases=("平安扇", "扇牌阵"),
        cards_num=4,
        is_cut=False,
        representations=(
            (
                "人际关系现状",
                "与对方结识的因缘",
                "双方关系的发展",
                "双方关系的结论",
            ),
        ),
        suitable_for="朋友、同事、家人等人际关系主题",
    ),
    FormationSpec(
        name="沙迪若之星牌阵",
        aliases=("沙迪若之星", "沙迪若", "星牌阵"),
        cards_num=6,
        is_cut=True,
        representations=(
            (
                "问卜者的感受",
                "问卜者的问题",
                "问题下的影响因素",
                "将问卜者与问题纠缠在一起的往事",
                "需要注意/考虑的",
                "可能的结果",
            ),
        ),
        suitable_for="自我梳理、情绪困扰和问题根源分析",
    ),
    FormationSpec(
        name="凯尔特十字牌阵",
        aliases=("凯尔特十字", "凯尔特十字阵", "十字牌阵"),
        cards_num=10,
        is_cut=False,
        representations=(
            (
                "问题核心",
                "当前阻碍",
                "显意识",
                "潜意识",
                "过去基础",
                "近期发展",
                "你的状态",
                "周围环境",
                "希望与担忧",
                "最终结果",
            ),
        ),
        suitable_for="复杂、长期、信息量大的综合问题",
    ),
    FormationSpec(
        name="二选一牌阵",
        aliases=("二选一", "选择牌阵", "抉择牌阵"),
        cards_num=6,
        is_cut=False,
        representations=(
            (
                "方案A现状",
                "方案A发展",
                "方案B现状",
                "方案B发展",
                "你的真实倾向",
                "综合建议",
            ),
        ),
        suitable_for="A/B 选择题、路线抉择和方案比较",
    ),
    FormationSpec(
        name="身心灵牌阵",
        aliases=("身心灵", "状态牌阵", "自我探索"),
        cards_num=3,
        is_cut=False,
        representations=(("身体状态", "心理状态", "灵性指引"),),
        suitable_for="个人状态、自我成长、压力和恢复节奏",
    ),
    FormationSpec(
        name="关系发展牌阵",
        aliases=("关系发展", "关系牌阵", "感情发展"),
        cards_num=5,
        is_cut=False,
        representations=(
            (
                "你的位置",
                "对方的位置",
                "关系现状",
                "关系阻碍",
                "未来发展",
            ),
        ),
        suitable_for="感情、合作、人际互动与关系走向",
    ),
)


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


def _format_aliases(formation: FormationSpec) -> str:
    return "、".join(formation.aliases)


def format_formation_catalog() -> str:
    lines = []
    for formation in FORMATION_SPECS:
        lines.append(
            f"- **{formation.name}**（别名：{_format_aliases(formation)}）  \n"
            f"  适合：{formation.suitable_for}"
        )
    return "\n".join(lines)


def build_unknown_formation_message(query: str) -> str:
    normalized = normalize_formation_name(query)
    return "\n".join(
        [
            f"未找到牌阵「{normalized}」",
            "可用牌阵如下：",
            format_formation_catalog(),
            "示例：占卜 圣三角牌阵",
            "示例：塔罗牌阵 凯尔特十字",
        ]
    )


def build_usage_text() -> str:
    return "\n".join(
        [
            "## 🔮 塔罗牌",
            "",
            "- **占卜**  ",
            "  随机选取牌阵进行详细占卜",
            "- **占卜 <牌阵名>**  ",
            "  使用指定牌阵占卜",
            "- **塔罗牌 / 抽塔罗牌**  ",
            "  抽取单张塔罗牌给予回应",
            "- **塔罗牌阵 <牌阵名> / 抽塔罗牌阵 <牌阵名>**  ",
            "  使用指定牌阵占卜",
            "",
            "## 🧭 使用示例",
            "",
            "- `塔罗牌`",
            "- `抽塔罗牌`",
            "- `占卜`",
            "- `占卜 圣三角`",
            "- `塔罗牌阵 凯尔特十字`",
            "- `抽塔罗牌阵 二选一`",
            "",
            "## 🃏 牌阵说明",
            "",
            format_formation_catalog(),
            "",
            "## ⚙️ 管理选项",
            "",
            "- **开启/关闭群聊转发**  ",
            "  开启或关闭占卜结果并发转发模式 [仅超管]",
        ]
    ).strip()


def chain_reply(
    bot: Bot,
    chain: list[dict[str, str | dict[str, str | MessageSegment]]],
    msg: MessageSegment,
) -> list[dict[str, str | dict[str, str | MessageSegment]]]:
    data = {
        "type": "node",
        "data": {
            "name": next(iter(tarot_config.nickname)),
            "uin": bot.self_id,
            "content": msg,
        },
    }
    chain.append(data)
    return chain


def pick_theme() -> str:
    """
    Random choose a theme from the union of local & official themes
    """
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


class Tarot:
    def __init__(self):
        self.tarot_json: Path = Path(__file__).parent / "tarot.json"
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
        1. Choose a theme
        2. Pick a specific formation or choose one randomly
        3. Get the divined cards list and their text
        4. Generate message (or chain reply if enabled)
        """
        theme: str = pick_theme()
        all_cards = self._load_cards()

        if formation_query:
            formation = get_formation(formation_query)
            if formation is None:
                await matcher.finish(build_unknown_formation_message(formation_query))
        else:
            formation = random.choice(FORMATION_SPECS)

        await matcher.send(f"启用{formation.name}，正在洗牌中")

        cards_num = formation.cards_num
        cards_info_list = self._random_cards(all_cards, theme, cards_num)
        representations = list(random.choice(formation.representations))

        if len(representations) != cards_num:
            raise ResourceError(
                f"Tarot formation {formation.name} is configured incorrectly."
            )

        chain = []
        for i in range(cards_num):
            if formation.is_cut and i == cards_num - 1:
                msg_header = MessageSegment.text(f"切牌「{representations[i]}」\n")
            else:
                msg_header = MessageSegment.text(
                    f"第{i + 1}张牌「{representations[i]}」\n"
                )

            flag, msg_body = await self._get_text_and_image(theme, cards_info_list[i])
            if not flag:
                await matcher.finish(msg_body)

            if isinstance(event, PrivateMessageEvent):
                if i < cards_num - 1:
                    await matcher.send(msg_header + msg_body)
                else:
                    await matcher.finish(msg_header + msg_body)
            elif isinstance(event, GroupMessageEvent):
                if self.is_chain_reply:
                    chain = chain_reply(bot, chain, msg_header + msg_body)
                else:
                    if i < cards_num - 1:
                        await matcher.send(msg_header + msg_body)
                        await asyncio.sleep(1)
                    else:
                        await matcher.finish(msg_header + msg_body)
            else:
                raise EventNotSupport

        if self.is_chain_reply:
            await bot.send_group_forward_msg(group_id=event.group_id, messages=chain)

    async def onetime_divine(self) -> MessageSegment:
        """
        One-time divination.
        """
        theme: str = pick_theme()
        all_cards = self._load_cards()
        card_info_list = self._random_cards(all_cards, theme)
        flag, body = await self._get_text_and_image(theme, card_info_list[0])
        return "回应是" + body if flag else body

    def switch_chain_reply(self, new_state: bool) -> None:
        """
        开启/关闭全局群聊转发模式
        """
        self.is_chain_reply = new_state

    def _load_cards(
        self,
    ) -> dict[str, dict[str, dict[str, str | dict[str, str]]]]:
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

    async def _get_text_and_image(
        self,
        theme: str,
        card_info: dict[str, str | dict[str, str]],
    ) -> tuple[bool, MessageSegment]:
        """
        Get a tarot image & text according to the "card_info"
        """
        _type: str = card_info.get("type")
        _name: str = card_info.get("pic")
        img_name: str = ""
        img_dir: Path = tarot_config.tarot_path / theme / _type

        for p in img_dir.glob(_name + ".*"):
            img_name = p.name

        if img_name == "":
            if theme in tarot_config.tarot_official_themes:
                data = await get_tarot(theme, _type, _name)
                if data is None:
                    return False, MessageSegment.text(
                        "图片下载出错，请重试或将资源部署本地……"
                    )

                img: Image.Image = Image.open(BytesIO(data))
            else:
                raise ResourceError(
                    f"Tarot image {theme}/{_type}/{_name} doesn't exist! "
                    f"Make sure the type {_type} is complete."
                )
        else:
            img = Image.open(img_dir / img_name)

        name_cn: str = card_info.get("name_cn")
        if random.random() < 0.5:
            meaning: str = card_info.get("meaning").get("up")
            msg = MessageSegment.text(f"「{name_cn}正位」「{meaning}」\n")
        else:
            meaning = card_info.get("meaning").get("down")
            msg = MessageSegment.text(f"「{name_cn}逆位」「{meaning}」\n")
            img = img.rotate(180)

        buf = BytesIO()
        img.save(buf, format="png")

        return True, msg + MessageSegment.image(buf)


tarot_manager = Tarot()
