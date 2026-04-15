import asyncio
from datetime import datetime, timedelta

import httpx

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register

from .core.client import QWeatherClient
from .core.config import WeatherConfig
from .core.formatters import (
    build_forecast_text,
    build_minutely_text,
    build_weather_text,
    get_weather_fields_config,
)
from .core.geo import resolve_location_via_geo
from .core.validators import (
    is_direct_weather_location,
    is_lonlat,
    normalize_forecast_days,
)


@register(
    "astrbot_plugin_weather_assistant",
    "tnzhy06",
    "基于和风天气 API 的天气助手",
    "1.5.2",
)
class WeatherAssistantPlugin(Star):
    """天气助手插件：提供实时天气、天气预报和分钟级降水查询能力。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._http_client = httpx.AsyncClient(timeout=12.0)
        self._weather_config = WeatherConfig(config)
        self._qweather_client = QWeatherClient(self._http_client, self._weather_config)
        self._push_stop_event = asyncio.Event()
        self._push_tasks: list[asyncio.Task] = []
        self._start_active_push_tasks()

    def _start_active_push_tasks(self) -> None:
        """启动三类主动推送循环任务。"""
        self._push_tasks = [
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

    def _default_location(self) -> str:
        """读取默认位置。"""
        return str(
            self._weather_config.get_group_value(
                "global_config", "default_location", ""
            )
        ).strip()

    async def _resolve_display_name_for_lonlat(
        self, location_input: str
    ) -> tuple[str, str]:
        """经纬度输入时，通过 GeoAPI 解析展示名称。"""
        geo_resolved = await resolve_location_via_geo(
            self._qweather_client, location_input
        )
        if not geo_resolved:
            # 解析失败时不回显经纬度，避免在消息中暴露坐标。
            return "未知地点", ""
        _, display_name, full_name = geo_resolved
        return display_name, full_name

    async def _resolve_location_for_weather(
        self, location_input: str
    ) -> tuple[str, str, str] | None:
        """解析地点，返回 (查询参数, 展示名, 命中全名)。"""
        if is_direct_weather_location(location_input):
            resolved_location = location_input.strip()
            if is_lonlat(location_input):
                display_name, full_name = await self._resolve_display_name_for_lonlat(
                    location_input
                )
                return resolved_location, display_name, full_name
            return resolved_location, location_input, ""

        geo_resolved = await resolve_location_via_geo(
            self._qweather_client, location_input
        )
        if not geo_resolved:
            return None
        return geo_resolved

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
            # 当前按 QQ 场景映射到已加载的 aiocqhttp 平台实例 ID。
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
        platform_manager = self.context.platform_manager
        # 优先使用公开方法，兼容不同版本字段。
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
        push_handler,
    ) -> None:
        """通用主动推送循环。"""
        while not self._push_stop_event.is_set():
            enabled, interval_minutes, start_time = self._get_push_schedule(group_key)
            if not enabled:
                try:
                    await asyncio.wait_for(self._push_stop_event.wait(), timeout=30)
                    return
                except asyncio.TimeoutError:
                    continue

            delay_seconds = self._calc_seconds_until_next_run(
                start_time, interval_minutes
            )
            try:
                await asyncio.wait_for(
                    self._push_stop_event.wait(), timeout=delay_seconds
                )
                return
            except asyncio.TimeoutError:
                pass

            if self._push_stop_event.is_set():
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
            success = await self.context.send_message(
                session, MessageChain().message(text)
            )
            if not success:
                logger.warning("主动推送发送失败，未找到对应平台: %s", session)

    async def _push_weather_now_once(self) -> None:
        """执行一次实时天气主动推送。"""
        location_input = self._default_location()
        if not location_input:
            logger.warning("实时天气主动推送失败：未配置 default_location")
            return

        resolved = await self._resolve_location_for_weather(location_input)
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
        location_input = self._default_location()
        if not location_input:
            logger.warning("天气预报主动推送失败：未配置 default_location")
            return

        resolved = await self._resolve_location_for_weather(location_input)
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
        location_input = self._default_location()
        if not location_input:
            logger.warning("分钟级降水主动推送失败：未配置 default_location")
            return
        if not is_lonlat(location_input):
            logger.warning("分钟级降水主动推送失败：default_location 需为经纬度")
            return

        display_name, _ = await self._resolve_display_name_for_lonlat(location_input)
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

    @filter.command("weather", alias={"天气", "当前天气"})
    async def weather_now(self, event: AstrMessageEvent, location: str = ""):
        """查询当前天气。

        Args:
            location(string): 位置(LocationID 或 经纬度，如 101010100 或 116.41,39.92)
        """
        location_input = location.strip() if location else self._default_location()
        if not location_input:
            yield event.plain_result(
                "请提供位置参数，例如：/weather 101010100 或 /weather 116.41,39.92"
            )
            return

        try:
            display_name = location_input
            full_name = ""
            resolved = await self._resolve_location_for_weather(location_input)
            if not resolved:
                yield event.plain_result(
                    "未找到匹配地点，请尝试更完整地名（如：北京市朝阳区、温州市鹿城区）。"
                )
                return
            resolved_location, display_name, full_name = resolved

            data = await self._qweather_client.query_weather_now(resolved_location)
            code = str(data.get("code", ""))
            if code != "200":
                logger.warning("和风天气返回非 200 状态码: %s", data)
                yield event.plain_result(
                    f"天气查询失败，接口返回 code={code}。请检查 location 或鉴权配置。"
                )
                return

            fields = get_weather_fields_config(
                self._weather_config.get_group_value(
                    "weather_now_config", "weather_fields", {}
                )
            )
            weather_text = build_weather_text(display_name, data, full_name, fields)
            yield event.plain_result(weather_text)
        except httpx.HTTPStatusError as exc:
            logger.error("和风天气 HTTP 异常: %s", exc)
            yield event.plain_result(
                f"天气查询失败：HTTP {exc.response.status_code}，请检查 API Host、路径或鉴权。"
            )
        except httpx.RequestError as exc:
            logger.error("和风天气请求异常: %s", exc)
            yield event.plain_result("天气查询失败：网络请求异常，请稍后重试。")
        except ValueError as exc:
            yield event.plain_result(f"配置错误：{exc}")
        except Exception as exc:
            logger.exception("天气查询发生未预期异常: %s", exc)
            yield event.plain_result("天气查询失败：发生未预期错误，请查看日志。")

    @filter.command("forecast", alias={"天气预报", "预报"})
    async def weather_forecast(
        self, event: AstrMessageEvent, location: str = "", days: str = ""
    ):
        """查询每日天气预报。

        Args:
            location(string): 地点（地名/LocationID/经纬度）
            days(string): 预报天数，支持 3d/7d/10d/15d/30d
        """
        location_input = location.strip() if location else self._default_location()
        if not location_input:
            yield event.plain_result("请提供位置参数，例如：/forecast 北京市 7d")
            return

        try:
            default_days = str(
                self._weather_config.get_group_value(
                    "forecast_config", "forecast_default_days", "3d"
                )
            )
            normalized_days = normalize_forecast_days(days, default_days)

            display_name = location_input
            full_name = ""
            resolved = await self._resolve_location_for_weather(location_input)
            if not resolved:
                yield event.plain_result("未找到匹配地点，请尝试其他地名。")
                return
            resolved_location, display_name, full_name = resolved

            data = await self._qweather_client.query_weather_daily(
                resolved_location, normalized_days
            )
            code = str(data.get("code", ""))
            if code != "200":
                logger.warning("天气预报返回非 200 状态码: %s", data)
                yield event.plain_result(
                    f"天气预报查询失败，接口返回 code={code}。请检查 location 或鉴权配置。"
                )
                return

            forecast_text = build_forecast_text(
                display_name, data, normalized_days, full_name
            )
            yield event.plain_result(forecast_text)
        except httpx.HTTPStatusError as exc:
            logger.error("天气预报 HTTP 异常: %s", exc)
            yield event.plain_result(
                f"天气预报查询失败：HTTP {exc.response.status_code}，请检查 API Host、路径或鉴权。"
            )
        except httpx.RequestError as exc:
            logger.error("天气预报请求异常: %s", exc)
            yield event.plain_result("天气预报查询失败：网络请求异常，请稍后重试。")
        except ValueError as exc:
            yield event.plain_result(f"参数或配置错误：{exc}")
        except Exception as exc:
            logger.exception("天气预报查询发生未预期异常: %s", exc)
            yield event.plain_result("天气预报查询失败：发生未预期错误，请查看日志。")

    @filter.command("minutely", alias={"分钟降水", "降水"})
    async def minutely_precip(self, event: AstrMessageEvent, location: str = ""):
        """查询分钟级降水（未来 2 小时每 5 分钟）。

        Args:
            location(string): 经纬度（经度,纬度），例如 116.41,39.92
        """
        location_input = location.strip() if location else self._default_location()

        if not location_input:
            yield event.plain_result(
                "请提供经纬度参数，例如：/minutely 116.41,39.92（分钟级降水仅支持经纬度）"
            )
            return

        if not is_lonlat(location_input):
            yield event.plain_result(
                "分钟级降水查询仅支持经纬度格式（经度,纬度），例如：116.41,39.92。"
            )
            return

        try:
            display_name, _ = await self._resolve_display_name_for_lonlat(
                location_input
            )
            data = await self._qweather_client.query_minutely_precip(location_input)
            code = str(data.get("code", ""))
            if code != "200":
                logger.warning("分钟级降水返回非 200 状态码: %s", data)
                yield event.plain_result(
                    f"分钟级降水查询失败，接口返回 code={code}。请检查经纬度或鉴权配置。"
                )
                return

            show_details = bool(
                self._weather_config.get_group_value(
                    "minutely_precip_config", "minutely_show_details", True
                )
            )
            yield event.plain_result(
                build_minutely_text(data, display_name, show_details)
            )
        except httpx.HTTPStatusError as exc:
            logger.error("分钟级降水 HTTP 异常: %s", exc)
            yield event.plain_result(
                f"分钟级降水查询失败：HTTP {exc.response.status_code}，请检查 API Host、路径或鉴权。"
            )
        except httpx.RequestError as exc:
            logger.error("分钟级降水请求异常: %s", exc)
            yield event.plain_result("分钟级降水查询失败：网络请求异常，请稍后重试。")
        except ValueError as exc:
            yield event.plain_result(f"配置错误：{exc}")
        except Exception as exc:
            logger.exception("分钟级降水查询发生未预期异常: %s", exc)
            yield event.plain_result("分钟级降水查询失败：发生未预期错误，请查看日志。")

    async def terminate(self):
        """插件卸载/停用时关闭推送任务和 HTTP 客户端。"""
        self._push_stop_event.set()
        for task in self._push_tasks:
            task.cancel()
        if self._push_tasks:
            await asyncio.gather(*self._push_tasks, return_exceptions=True)
        await self._http_client.aclose()
