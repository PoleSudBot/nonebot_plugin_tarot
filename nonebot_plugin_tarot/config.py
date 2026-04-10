import shutil
from pathlib import Path
from typing import Any, Dict, List, Set, Union

import httpx
import nonebot
from aiocache import cached
from nonebot import logger
from pydantic import BaseModel, Extra

from zhenxun.configs.config import Config

try:
    import ujson as json
except ModuleNotFoundError:
    import json


PLUGIN_DIR = Path(__file__).parent
LEGACY_RESOURCE_DIR = PLUGIN_DIR / "resource"
LEGACY_TAROT_JSON_PATH = PLUGIN_DIR / "tarot.json"
PLUGIN_DATA_DIR = Path("data") / "nonebot_plugin_tarot"
PLUGIN_RESOURCE_DIR = PLUGIN_DATA_DIR / "resource"
PLUGIN_TAROT_JSON_PATH = PLUGIN_DATA_DIR / "tarot.json"
PLUGIN_AI_RESULT_DIR = PLUGIN_DATA_DIR / "ai_results"


class PluginConfig(BaseModel, extra=Extra.ignore):
    '''
        Path of tarot images resource
    '''
    tarot_path: Path = PLUGIN_RESOURCE_DIR
    chain_reply: bool = True
    tarot_auto_update: bool = False
    nickname: Set[str] = {"Bot"}

    '''
        DO NOT CHANGE THIS VALUE IN ANY .ENV FILES
    '''
    tarot_official_themes: List[str] = ["BilibiliTarot", "TouhouTarot"]


driver = nonebot.get_driver()
tarot_config: PluginConfig = PluginConfig.parse_obj(
    driver.config.dict(exclude_unset=True))

AI_CONFIG_MODULE = "tarot"
DEFAULT_AI_MODEL_NAME = "Gemini/gemini-3-flash-proview"
DEFAULT_AI_DAILY_LIMIT = 1
DEFAULT_AI_COST_GOLD = 30


class DownloadError(Exception):
    pass


class ResourceError(Exception):

    def __init__(self, msg: str):
        self.msg = msg

    def __str__(self):
        return self.msg

    __repr__ = __str__


class EventNotSupport(Exception):
    pass


def _is_directory_empty(path: Path) -> bool:
    return not path.exists() or not any(path.iterdir())


def _uses_default_tarot_path() -> bool:
    return tarot_config.tarot_path == PLUGIN_RESOURCE_DIR


def ensure_plugin_data_layout() -> None:
    PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PLUGIN_AI_RESULT_DIR.mkdir(parents=True, exist_ok=True)
    tarot_config.tarot_path.mkdir(parents=True, exist_ok=True)

    if (
        _uses_default_tarot_path()
        and LEGACY_RESOURCE_DIR.exists()
        and _is_directory_empty(PLUGIN_RESOURCE_DIR)
    ):
        shutil.copytree(LEGACY_RESOURCE_DIR, PLUGIN_RESOURCE_DIR, dirs_exist_ok=True)
        logger.info("Migrated tarot resource to data/nonebot_plugin_tarot/resource")

    if not PLUGIN_TAROT_JSON_PATH.exists() and LEGACY_TAROT_JSON_PATH.exists():
        PLUGIN_TAROT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LEGACY_TAROT_JSON_PATH, PLUGIN_TAROT_JSON_PATH)
        logger.info("Migrated tarot.json to data/nonebot_plugin_tarot/tarot.json")


def get_ai_model_name() -> str:
    return str(
        Config.get_config(
            AI_CONFIG_MODULE,
            "AI_MODEL_NAME",
            DEFAULT_AI_MODEL_NAME,
        )
        or DEFAULT_AI_MODEL_NAME
    )


def get_ai_daily_limit() -> int:
    value = Config.get_config(
        AI_CONFIG_MODULE,
        "AI_DAILY_LIMIT",
        DEFAULT_AI_DAILY_LIMIT,
    )
    return int(value if value is not None else DEFAULT_AI_DAILY_LIMIT)


def get_ai_cost_gold() -> int:
    value = Config.get_config(
        AI_CONFIG_MODULE,
        "AI_COST_GOLD",
        DEFAULT_AI_COST_GOLD,
    )
    return int(value if value is not None else DEFAULT_AI_COST_GOLD)


async def download_url(name: str, is_json: bool = False) -> Union[Dict[str, Any], bytes, None]:
    url: str = "https://raw.fgit.ml/MinatoAquaCrews/nonebot_plugin_tarot/master/nonebot_plugin_tarot/" + name

    async with httpx.AsyncClient() as client:
        for i in range(3):
            try:
                response: httpx.Response = await client.get(url)
                if response.status_code != 200:
                    continue

                return response.json() if is_json else response.content

            except Exception:
                logger.warning(
                    f"Error occurred when downloading {url}, {i+1}/3")

    logger.warning("Abort downloading")
    return None


@driver.on_startup
async def tarot_version_check() -> None:
    '''
        Get the latest version of tarot.json from repo
    '''
    ensure_plugin_data_layout()

    tarot_json_path = PLUGIN_TAROT_JSON_PATH

    cur_version: float = 0
    if tarot_json_path.exists():
        with tarot_json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            cur_version = data.get("version", 0)

    # Auto update check on startup if TAROT_AUTO_UPDATE
    if tarot_config.tarot_auto_update:
        response: Dict[str, Any] = await download_url("tarot.json", is_json=True)
    else:
        response = None

    if response is None:
        if not tarot_json_path.exists():
            logger.warning("Tarot text resource missing! Please check!")
            raise ResourceError("Missing necessary resource: tarot.json!")
    else:
        try:
            version: float = response.get("version", 0)
        except KeyError:
            logger.warning(
                "Tarot text resource downloaded incompletely! Please check!")
            raise DownloadError

        # Update when there is a newer version
        if version > cur_version:
            with tarot_json_path.open("w", encoding="utf-8") as f:
                json.dump(response, f, ensure_ascii=False, indent=4)
                logger.info(
                    f"Updated tarot.json, version: {cur_version} -> {version}")


@cached(ttl=180)
async def get_tarot(_theme: str, _type: str, _name: str) -> Union[bytes, None]:
    '''
        Downloads tarot image and stores cache temporarily
        if downloading failed, return None
    '''
    logger.info(
        f"Downloading tarot image {_theme}/{_type}/{_name} from repo")

    resource: str = "resource/" + f"{_theme}/{_type}/{_name}"
    data = await download_url(resource)

    if data is None:
        logger.warning(
            f"Downloading tarot image {_theme}/{_type}/{_name} failed!")

    return data
