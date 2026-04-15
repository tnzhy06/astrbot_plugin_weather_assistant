from typing import Any

import httpx

from .config import WeatherConfig


class QWeatherClient:
    """和风天气 API 客户端封装。"""

    def __init__(self, http_client: httpx.AsyncClient, weather_config: WeatherConfig):
        self._http_client = http_client
        self._config = weather_config

    def _build_common_context(self) -> tuple[str, dict[str, str]]:
        api_host = self._config.normalize_api_host()
        if not api_host:
            raise ValueError("未配置 API Host，请先在插件配置中填写。")

        headers = self._config.build_auth_headers()
        if not headers:
            raise ValueError(
                "未配置鉴权信息，请填写 API Key 或 JWT（jwt_kid/jwt_project_id/jwt_private_key）。"
            )

        return api_host, headers

    async def query_weather_now(self, location: str) -> dict[str, Any]:
        """调用和风天气实时天气接口。"""
        api_host, headers = self._build_common_context()
        url = f"{api_host}/v7/weather/now"
        params = {
            "location": location,
            # 强制中文返回，避免用户配置导致多语言输出不一致。
            "lang": "zh",
            # 强制公制单位（摄氏度等），避免不同配置造成输出口径不一致。
            "unit": "m",
        }
        resp = await self._http_client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def query_city_lookup(self, location: str) -> dict[str, Any]:
        """调用 GeoAPI 进行城市搜索，解析 LocationID。"""
        api_host, headers = self._build_common_context()
        url = f"{api_host}/geo/v2/city/lookup"
        params = {
            "location": location,
            # 强制中文返回，避免用户配置导致多语言输出不一致。
            "lang": "zh",
            "range": str(
                self._config.get_group_value("global_config", "geo_range", "cn")
            ).strip()
            or "cn",
            "number": int(
                self._config.get_group_value("global_config", "geo_number", 10) or 10
            ),
        }
        resp = await self._http_client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def query_weather_daily(self, location: str, days: str) -> dict[str, Any]:
        """调用和风天气每日预报接口。"""
        api_host, headers = self._build_common_context()
        url = f"{api_host}/v7/weather/{days}"
        params = {
            "location": location,
            # 强制中文返回，避免用户配置导致多语言输出不一致。
            "lang": "zh",
            # 强制公制单位（摄氏度等），避免不同配置造成输出口径不一致。
            "unit": "m",
        }
        resp = await self._http_client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def query_minutely_precip(self, location: str) -> dict[str, Any]:
        """调用和风天气分钟级降水接口。"""
        api_host, headers = self._build_common_context()
        url = f"{api_host}/v7/minutely/5m"
        params = {
            "location": location,
            # 强制中文返回，避免用户配置导致多语言输出不一致。
            "lang": "zh",
        }
        resp = await self._http_client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()
