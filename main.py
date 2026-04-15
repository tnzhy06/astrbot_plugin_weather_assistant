import httpx

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
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
            if is_direct_weather_location(location_input):
                resolved_location = location_input.strip()
                if is_lonlat(location_input):
                    (
                        display_name,
                        full_name,
                    ) = await self._resolve_display_name_for_lonlat(location_input)
            else:
                geo_resolved = await resolve_location_via_geo(
                    self._qweather_client, location_input
                )
                if not geo_resolved:
                    yield event.plain_result(
                        "未找到匹配地点，请尝试更完整地名（如：北京市朝阳区、温州市鹿城区）。"
                    )
                    return
                resolved_location, display_name, full_name = geo_resolved

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
            if is_direct_weather_location(location_input):
                resolved_location = location_input.strip()
                if is_lonlat(location_input):
                    (
                        display_name,
                        full_name,
                    ) = await self._resolve_display_name_for_lonlat(location_input)
            else:
                geo_resolved = await resolve_location_via_geo(
                    self._qweather_client, location_input
                )
                if not geo_resolved:
                    yield event.plain_result(
                        "未找到匹配地点，请尝试更完整地名（如：北京市朝阳区、温州市鹿城区）。"
                    )
                    return
                resolved_location, display_name, full_name = geo_resolved

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
        """插件卸载/停用时关闭 HTTP 客户端。"""
        await self._http_client.aclose()
