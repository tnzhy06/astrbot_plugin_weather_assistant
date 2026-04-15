from astrbot.api import logger

from .client import QWeatherClient
from .config import WeatherConfig
from .validators import is_direct_weather_location, is_lonlat


async def resolve_location_via_geo(
    client: QWeatherClient, location_input: str
) -> tuple[str, str, str] | None:
    """通过 GeoAPI 解析输入，返回 (location_id, 展示名称, 消歧信息)。"""
    geo_data = await client.query_city_lookup(location_input)
    code = str(geo_data.get("code", ""))
    if code != "200":
        logger.warning("GeoAPI 返回非 200 状态码: %s", geo_data)
        return None

    results = geo_data.get("location", [])
    if not results:
        return None

    best = results[0]
    location_id = str(best.get("id", "")).strip()
    if not location_id:
        return None

    name = str(best.get("name", "")).strip() or location_input
    adm2 = str(best.get("adm2", "")).strip()
    adm1 = str(best.get("adm1", "")).strip()
    country = str(best.get("country", "")).strip()
    full_name = " / ".join([part for part in (country, adm1, adm2, name) if part])
    return location_id, name, full_name


class LocationResolver:
    """地点解析服务，集中处理默认位置与 GeoAPI 解析。"""

    def __init__(self, qweather_client: QWeatherClient, weather_config: WeatherConfig):
        self._qweather_client = qweather_client
        self._weather_config = weather_config

    def default_location(self) -> str:
        """读取默认位置。"""
        return str(
            self._weather_config.get_group_value(
                "global_config", "default_location", ""
            )
        ).strip()

    async def resolve_display_name_for_lonlat(
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

    async def resolve_location_for_weather(
        self, location_input: str
    ) -> tuple[str, str, str] | None:
        """解析地点，返回 (查询参数, 展示名, 命中全名)。"""
        if is_direct_weather_location(location_input):
            resolved_location = location_input.strip()
            if is_lonlat(location_input):
                display_name, full_name = await self.resolve_display_name_for_lonlat(
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
