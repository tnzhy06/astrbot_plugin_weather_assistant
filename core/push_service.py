import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.star import Context

from .client import QWeatherClient
from .config import WeatherConfig
from .formatters import (
    build_forecast_text,
    build_minutely_text,
    build_weather_text,
    get_weather_fields_config,
)
from .geo import LocationResolver
from .validators import is_lonlat, normalize_forecast_days


class ActivePushService:
    """主动推送服务，负责任务调度与消息发送。"""

    def __init__(
        self,
        context: Context,
        weather_config: WeatherConfig,
        qweather_client: QWeatherClient,
        location_resolver: LocationResolver,
    ):
        self._context = context
        self._weather_config = weather_config
        self._qweather_client = qweather_client
        self._location_resolver = location_resolver
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        """启动三类主动推送循环任务。"""
        self._tasks = [
            asyncio.create_task(
                self._run_active_push_loop(
                    "weather_now_config",
                    "实时天气",
                    self._push_weather_now_once,
                )
            ),
            asyncio.create_task(
                self._run_active_push_loop(
                    "forecast_config",
                    "天气预报",
                    self._push_forecast_once,
                )
            ),
            asyncio.create_task(
                self._run_active_push_loop(
                    "minutely_precip_config",
                    "分钟级降水",
                    self._push_minutely_once,
                )
            ),
        ]

    async def stop(self) -> None:
        """停止主动推送循环任务。"""
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    def _parse_push_session_list(self) -> list[str]:
        """解析主动推送会话列表，转为 unified_msg_origin。"""
        raw_value = self._weather_config.get_group_value(
            "global_config", "active_push_sessions", []
        )
        entries: list[str] = []
        if isinstance(raw_value, list):
            entries = [str(item).strip() for item in raw_value]
        elif isinstance(raw_value, str):
            entries = [
                part.strip() for part in raw_value.replace("\r", "\n").split("\n")
            ]

        aiocqhttp_platform_id = self._get_aiocqhttp_platform_id()
        if not aiocqhttp_platform_id:
            logger.warning(
                "未检测到 aiocqhttp 平台实例，主动推送会话无法映射，请检查平台是否已启用。"
            )
            return []

        sessions: list[str] = []
        for entry in entries:
            if not entry:
                continue
            role, sep, target = entry.partition(":")
            if not sep:
                logger.warning("主动推送会话项格式错误，已跳过: %s", entry)
                continue
            role = role.strip().lower()
            target = target.strip()
            if not target:
                logger.warning("主动推送会话项缺少 ID，已跳过: %s", entry)
                continue
            if role == "user":
                sessions.append(f"{aiocqhttp_platform_id}:FriendMessage:{target}")
            elif role == "group":
                sessions.append(f"{aiocqhttp_platform_id}:GroupMessage:{target}")
            else:
                logger.warning(
                    "主动推送会话项类型错误（仅支持 user/group），已跳过: %s", entry
                )
        return sessions

    def _get_aiocqhttp_platform_id(self) -> str | None:
        """获取当前已加载的 aiocqhttp 平台实例 ID。"""
        platform_manager = self._context.platform_manager
        platforms = (
            platform_manager.get_insts()
            if hasattr(platform_manager, "get_insts")
            else getattr(platform_manager, "platform_insts", [])
        )
        for platform in platforms:
            try:
                meta = platform.meta()
            except Exception:
                continue
            if str(getattr(meta, "name", "")).strip().lower() == "aiocqhttp":
                platform_id = str(getattr(meta, "id", "")).strip()
                if platform_id:
                    return platform_id
        return None

    def _get_push_schedule(self, group_key: str) -> tuple[bool, int, str]:
        """读取推送配置：开关、间隔（分钟）、开始时间（HH:MM）。"""
        enabled = bool(
            self._weather_config.get_group_value(
                group_key, "active_push_enabled", False
            )
        )
        raw_interval = self._weather_config.get_group_value(
            group_key, "active_push_interval_minutes", 60
        )
        try:
            interval_minutes = int(raw_interval)
        except (TypeError, ValueError):
            interval_minutes = 60
        if interval_minutes < 1:
            interval_minutes = 1
        start_time = (
            str(
                self._weather_config.get_group_value(
                    group_key, "active_push_start_time", "08:00"
                )
            ).strip()
            or "08:00"
        )
        return enabled, interval_minutes, start_time

    def _calc_seconds_until_next_run(
        self, start_time: str, interval_minutes: int
    ) -> float:
        """根据开始时间和间隔，计算距离下一次执行的秒数。"""
        now = datetime.now()
        try:
            hour_str, minute_str = start_time.split(":", 1)
            hour = int(hour_str)
            minute = int(minute_str)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except ValueError:
            logger.warning(
                "主动推送开始时间格式错误（应为 HH:MM），已回退到 08:00: %s", start_time
            )
            hour = 8
            minute = 0

        anchor = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        interval = timedelta(minutes=max(1, interval_minutes))
        if now < anchor:
            next_run = anchor
        else:
            elapsed_seconds = (now - anchor).total_seconds()
            steps = int(elapsed_seconds // interval.total_seconds()) + 1
            next_run = anchor + steps * interval
        return max(1.0, (next_run - now).total_seconds())

    async def _run_active_push_loop(
        self,
        group_key: str,
        task_name: str,
        push_handler: Callable[[], Awaitable[None]],
    ) -> None:
        """通用主动推送循环。"""
        while not self._stop_event.is_set():
            enabled, interval_minutes, start_time = self._get_push_schedule(group_key)
            if not enabled:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=30)
                    return
                except asyncio.TimeoutError:
                    continue

            delay_seconds = self._calc_seconds_until_next_run(
                start_time, interval_minutes
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay_seconds)
                return
            except asyncio.TimeoutError:
                pass

            if self._stop_event.is_set():
                return
            try:
                await push_handler()
            except Exception as exc:
                logger.exception("主动推送任务执行失败（%s）: %s", task_name, exc)

    async def _broadcast_text_to_sessions(self, text: str) -> None:
        """向主动推送配置中的所有会话发送文本消息。"""
        sessions = self._parse_push_session_list()
        if not sessions:
            logger.warning(
                "主动推送已启用，但会话列表为空，请先配置 global_config.active_push_sessions"
            )
            return

        for session in sessions:
            success = await self._context.send_message(
                session, MessageChain().message(text)
            )
            if not success:
                logger.warning("主动推送发送失败，未找到对应平台: %s", session)

    async def _push_weather_now_once(self) -> None:
        """执行一次实时天气主动推送。"""
        location_input = self._location_resolver.default_location()
        if not location_input:
            logger.warning("实时天气主动推送失败：未配置 default_location")
            return

        resolved = await self._location_resolver.resolve_location_for_weather(
            location_input
        )
        if not resolved:
            logger.warning("实时天气主动推送失败：无法解析地点 %s", location_input)
            return
        resolved_location, display_name, full_name = resolved

        data = await self._qweather_client.query_weather_now(resolved_location)
        code = str(data.get("code", ""))
        if code != "200":
            logger.warning("实时天气主动推送失败，接口返回 code=%s", code)
            return

        fields = get_weather_fields_config(
            self._weather_config.get_group_value(
                "weather_now_config", "weather_fields", {}
            )
        )
        body = build_weather_text(display_name, data, full_name, fields)
        await self._broadcast_text_to_sessions(f"【天气助手-实时天气推送】\n{body}")

    async def _push_forecast_once(self) -> None:
        """执行一次天气预报主动推送。"""
        location_input = self._location_resolver.default_location()
        if not location_input:
            logger.warning("天气预报主动推送失败：未配置 default_location")
            return

        resolved = await self._location_resolver.resolve_location_for_weather(
            location_input
        )
        if not resolved:
            logger.warning("天气预报主动推送失败：无法解析地点 %s", location_input)
            return
        resolved_location, display_name, full_name = resolved

        default_days = str(
            self._weather_config.get_group_value(
                "forecast_config", "forecast_default_days", "3d"
            )
        )
        normalized_days = normalize_forecast_days("", default_days)
        data = await self._qweather_client.query_weather_daily(
            resolved_location, normalized_days
        )
        code = str(data.get("code", ""))
        if code != "200":
            logger.warning("天气预报主动推送失败，接口返回 code=%s", code)
            return

        body = build_forecast_text(display_name, data, normalized_days, full_name)
        await self._broadcast_text_to_sessions(f"【天气助手-天气预报推送】\n{body}")

    async def _push_minutely_once(self) -> None:
        """执行一次分钟级降水主动推送。"""
        location_input = self._location_resolver.default_location()
        if not location_input:
            logger.warning("分钟级降水主动推送失败：未配置 default_location")
            return
        if not is_lonlat(location_input):
            logger.warning("分钟级降水主动推送失败：default_location 需为经纬度")
            return

        display_name, _ = await self._location_resolver.resolve_display_name_for_lonlat(
            location_input
        )
        data = await self._qweather_client.query_minutely_precip(location_input)
        code = str(data.get("code", ""))
        if code != "200":
            logger.warning("分钟级降水主动推送失败，接口返回 code=%s", code)
            return

        show_details = bool(
            self._weather_config.get_group_value(
                "minutely_precip_config", "minutely_show_details", True
            )
        )
        body = build_minutely_text(data, display_name, show_details)
        await self._broadcast_text_to_sessions(f"【天气助手-分钟级降水推送】\n{body}")
