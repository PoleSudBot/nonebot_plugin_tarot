from datetime import datetime
from zoneinfo import ZoneInfo

from tortoise import fields

from zhenxun.services.db_context import Model

_LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def get_today_local_date():
    return datetime.now(_LOCAL_TZ).date()


class TarotAIDailyUsage(Model):
    id = fields.IntField(pk=True, generated=True)
    user_id = fields.CharField(max_length=64, description="用户ID")
    platform = fields.CharField(max_length=32, description="平台")
    usage_date = fields.DateField(description="使用日期")
    used_count = fields.IntField(default=0, description="已使用次数")
    bonus_count = fields.IntField(default=0, description="当天额外次数")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tarot_ai_daily_usage"
        table_description = "塔罗AI每日使用记录"
        unique_together = (("user_id", "platform", "usage_date"),)

    @classmethod
    async def get_today_record(
        cls,
        user_id: str,
        platform: str,
    ) -> "TarotAIDailyUsage":
        record, _ = await cls.get_or_create(
            user_id=user_id,
            platform=platform,
            usage_date=get_today_local_date(),
            defaults={"used_count": 0, "bonus_count": 0},
        )
        return record

    @classmethod
    async def get_remaining_count(
        cls,
        user_id: str,
        platform: str,
        daily_limit: int,
    ) -> int:
        record = await cls.get_today_record(user_id, platform)
        return daily_limit + record.bonus_count - record.used_count

    @classmethod
    async def add_bonus_today(
        cls,
        user_id: str,
        platform: str,
        count: int,
    ) -> "TarotAIDailyUsage":
        record = await cls.get_today_record(user_id, platform)
        record.bonus_count += count
        await record.save(update_fields=["bonus_count", "updated_at"])
        return record

    @classmethod
    async def consume_today(
        cls,
        user_id: str,
        platform: str,
    ) -> "TarotAIDailyUsage":
        record = await cls.get_today_record(user_id, platform)
        record.used_count += 1
        await record.save(update_fields=["used_count", "updated_at"])
        return record
