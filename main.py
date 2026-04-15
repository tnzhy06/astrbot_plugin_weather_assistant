from typing import Any

import httpx

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


@register(
    "astrbot_plugin_weather_assistant",
    "tnzhy06",
    "基于和风天气 API 的天气助手",
    "1.5.1",
)
class WeatherAssistantPlugin(Star):
    """天气助手插件：提供实时天气查询能力。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._http_client = httpx.AsyncClient(timeout=12.0)
        self._allowed_forecast_days = {"3d", "7d", "10d", "15d", "30d"}

    def _get_group_config(self, group_key: str) -> dict[str, Any]:
        """读取分组配置。"""
        group = self.config.get(group_key, {})
        if isinstance(group, dict):
            return group
        return {}

    def _get_group_value(self, group_key: str, key: str, default: Any) -> Any:
        """按分组读取配置，兼容旧版顶层字段。"""
        group = self._get_group_config(group_key)
        if key in group:
            return group[key]
        # 兼容旧版配置，避免升级后用户历史配置立即失效。
        return self.config.get(key, default)

    def _normalize_api_host(self) -> str:
        """标准化 API Host，兼容用户只填写域名的情况。"""
        host = str(self._get_group_value("global_config", "api_host", "")).strip()
        if not host:
            return ""
        if not host.startswith(("http://", "https://")):
            host = f"https://{host}"
        return host.rstrip("/")

    def _build_auth_headers(self) -> dict[str, str]:
        """根据配置构建鉴权头。"""
        auth_type = (
            str(self._get_group_value("global_config", "auth_type", "api_key"))
            .strip()
            .lower()
        )
        headers: dict[str, str] = {}
        if auth_type == "jwt":
            jwt_token = str(
                self._get_group_value("global_config", "jwt_token", "")
            ).strip()
            if jwt_token:
                headers["Authorization"] = f"Bearer {jwt_token}"
            return headers

        api_key = str(self._get_group_value("global_config", "api_key", "")).strip()
        if api_key:
            headers["X-QW-Api-Key"] = api_key
        return headers

    async def _query_weather_now(self, location: str) -> dict[str, Any]:
        """调用和风天气实时天气接口。"""
        api_host = self._normalize_api_host()
        if not api_host:
            raise ValueError("未配置 API Host，请先在插件配置中填写。")

        headers = self._build_auth_headers()
        if not headers:
            raise ValueError("未配置鉴权信息，请填写 API Key 或 JWT Token。")

        url = f"{api_host}/v7/weather/now"
        params = {
            "location": location,
            "lang": str(self._get_group_value("global_config", "lang", "zh")).strip()
            or "zh",
            "unit": str(self._get_group_value("global_config", "unit", "m")).strip()
            or "m",
        }

        resp = await self._http_client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def _query_city_lookup(self, location: str) -> dict[str, Any]:
        """调用 GeoAPI 进行城市搜索，解析 LocationID。"""
        api_host = self._normalize_api_host()
        if not api_host:
            raise ValueError("未配置 API Host，请先在插件配置中填写。")

        headers = self._build_auth_headers()
        if not headers:
            raise ValueError("未配置鉴权信息，请填写 API Key 或 JWT Token。")

        url = f"{api_host}/geo/v2/city/lookup"
        params = {
            "location": location,
            "lang": str(self._get_group_value("global_config", "lang", "zh")).strip()
            or "zh",
            # 默认把搜索限制在中国，避免模糊搜索跨国误命中。
            "range": str(
                self._get_group_value("global_config", "geo_range", "cn")
            ).strip()
            or "cn",
            # 控制返回条目数量，取首条作为最佳匹配。
            "number": int(
                self._get_group_value("global_config", "geo_number", 10) or 10
            ),
        }
        resp = await self._http_client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def _query_weather_daily(self, location: str, days: str) -> dict[str, Any]:
        """调用和风天气每日预报接口。"""
        api_host = self._normalize_api_host()
        if not api_host:
            raise ValueError("未配置 API Host，请先在插件配置中填写。")

        headers = self._build_auth_headers()
        if not headers:
            raise ValueError("未配置鉴权信息，请填写 API Key 或 JWT Token。")

        url = f"{api_host}/v7/weather/{days}"
        params = {
            "location": location,
            "lang": str(self._get_group_value("global_config", "lang", "zh")).strip()
            or "zh",
            "unit": str(self._get_group_value("global_config", "unit", "m")).strip()
            or "m",
        }

        resp = await self._http_client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def _query_minutely_precip(self, location: str) -> dict[str, Any]:
        """调用和风天气分钟级降水接口。"""
        api_host = self._normalize_api_host()
        if not api_host:
            raise ValueError("未配置 API Host，请先在插件配置中填写。")

        headers = self._build_auth_headers()
        if not headers:
            raise ValueError("未配置鉴权信息，请填写 API Key 或 JWT Token。")

        url = f"{api_host}/v7/minutely/5m"
        params = {
            "location": location,
            "lang": str(self._get_group_value("global_config", "lang", "zh")).strip()
            or "zh",
        }

        resp = await self._http_client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def _normalize_forecast_days(self, days_input: str) -> str:
        """标准化预报天数参数，兼容 3/3天/3d 等写法。"""
        days = days_input.strip().lower()
        if not days:
            days = (
                str(
                    self._get_group_value(
                        "forecast_config", "forecast_default_days", "3d"
                    )
                )
                .strip()
                .lower()
            )

        if days.endswith("天"):
            days = f"{days[:-1]}d"
        if days.isdigit():
            days = f"{days}d"

        if days not in self._allowed_forecast_days:
            raise ValueError(
                "预报天数仅支持 3d/7d/10d/15d/30d（也可输入 3/7/10/15/30）"
            )
        return days

    @staticmethod
    def _is_lonlat(location: str) -> bool:
        """判断输入是否为合法经纬度字符串（经度,纬度）。"""
        cleaned = location.strip()
        if "," not in cleaned:
            return False
        parts = [part.strip() for part in cleaned.split(",")]
        if len(parts) != 2:
            return False
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            return False
        return -180 <= lon <= 180 and -90 <= lat <= 90

    @staticmethod
    def _is_direct_weather_location(location: str) -> bool:
        """判断输入是否可直接用于天气接口（ID 或经纬度）。"""
        cleaned = location.strip()
        if not cleaned:
            return False
        if "," in cleaned:
            return True
        # 和风 LocationID 可能是纯数字，也可能是含数字的字母数字串。
        # 纯英文单词（如 beijing）不应被当作 ID 直传。
        return cleaned.isdigit() or (
            cleaned.isalnum() and any(ch.isdigit() for ch in cleaned)
        )

    async def _resolve_location_via_geo(
        self, location_input: str
    ) -> tuple[str, str, str] | None:
        """通过 GeoAPI 解析输入，返回 (location_id, 展示名称, 消歧信息)。"""
        geo_data = await self._query_city_lookup(location_input)
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

    def _get_weather_fields_config(self) -> dict[str, bool]:
        """读取天气指标开关配置，未配置时使用默认值。"""
        defaults: dict[str, bool] = {
            "match_location": True,
            "location": True,
            "weather": True,
            "temperature": True,
            "feels_like": True,
            "humidity": True,
            "wind": True,
            "precip": True,
            "pressure": True,
            "visibility": True,
            "obs_time": True,
            "update_time": True,
        }
        config_value = self._get_group_value("weather_now_config", "weather_fields", {})
        if not isinstance(config_value, dict):
            return defaults

        merged = defaults.copy()
        for key in defaults:
            if key in config_value:
                merged[key] = bool(config_value[key])
        return merged

    def _build_weather_text(
        self, location: str, payload: dict[str, Any], matched_full_name: str = ""
    ) -> str:
        """将接口数据格式化为用户可读文本（支持按配置控制指标开关）。"""
        fields = self._get_weather_fields_config()
        now = payload.get("now", {})
        update_time = payload.get("updateTime", "")
        obs_time = now.get("obsTime", "")
        text = now.get("text", "未知")
        temp = now.get("temp", "--")
        feels_like = now.get("feelsLike", "--")
        humidity = now.get("humidity", "--")
        wind_dir = now.get("windDir", "--")
        wind_scale = now.get("windScale", "--")
        wind_speed = now.get("windSpeed", "--")
        precip = now.get("precip", "--")
        pressure = now.get("pressure", "--")
        vis = now.get("vis", "--")

        lines: list[str] = []
        if fields["match_location"] and matched_full_name:
            lines.append(f"🔎 命中地点: {matched_full_name}")
        if fields["location"]:
            lines.append(f"📍 地点: {location}")
        if fields["weather"]:
            lines.append(f"🌤️ 天气: {text}")
        if fields["temperature"]:
            # 体感温度单独可控；关闭后只展示实际温度。
            if fields["feels_like"]:
                lines.append(f"🌡️ 温度: {temp}°C (体感 {feels_like}°C)")
            else:
                lines.append(f"🌡️ 温度: {temp}°C")
        elif fields["feels_like"]:
            lines.append(f"🌡️ 体感温度: {feels_like}°C")
        if fields["humidity"]:
            lines.append(f"💧 湿度: {humidity}%")
        if fields["wind"]:
            lines.append(f"🌬️ 风: {wind_dir} {wind_scale}级 ({wind_speed} km/h)")
        if fields["precip"]:
            lines.append(f"🌧️ 降水: {precip} mm")
        if fields["pressure"]:
            lines.append(f"🧭 气压: {pressure} hPa")
        if fields["visibility"]:
            lines.append(f"👀 能见度: {vis} km")
        if fields["obs_time"]:
            lines.append(f"🕒 观测时间: {obs_time}")
        if fields["update_time"]:
            lines.append(f"🔄 数据更新时间: {update_time}")

        return "\n".join(lines)

    def _build_forecast_text(
        self,
        location: str,
        payload: dict[str, Any],
        days: str,
        matched_full_name: str = "",
    ) -> str:
        """将每日预报数据格式化为用户可读文本。"""
        lines: list[str] = []
        if matched_full_name:
            lines.append(f"🔎 命中地点: {matched_full_name}")
        lines.append(f"📍 地点: {location}")
        lines.append(f"🗓️ {days} 天气预报")

        daily_list = payload.get("daily", [])
        for day in daily_list:
            fx_date = day.get("fxDate", "--")
            text_day = day.get("textDay", "--")
            text_night = day.get("textNight", "--")
            temp_min = day.get("tempMin", "--")
            temp_max = day.get("tempMax", "--")
            precip = day.get("precip", "--")
            humidity = day.get("humidity", "--")
            lines.append(
                f"{fx_date} | {text_day}/{text_night} | {temp_min}~{temp_max}°C | "
                f"降水 {precip}mm | 湿度 {humidity}%"
            )

        update_time = payload.get("updateTime", "")
        if update_time:
            lines.append(f"🔄 数据更新时间: {update_time}")
        return "\n".join(lines)

    def _build_minutely_text(self, payload: dict[str, Any], location: str) -> str:
        """将分钟级降水数据格式化为用户可读文本。"""
        summary = str(payload.get("summary", "")).strip()
        update_time = str(payload.get("updateTime", "")).strip()
        minutely_list = payload.get("minutely", [])
        show_details = bool(
            self._get_group_value(
                "minutely_precip_config", "minutely_show_details", True
            )
        )

        lines = [f"📍 坐标: {location}"]
        if summary:
            lines.append(f"🌦️ 概述: {summary}")

        if show_details:
            # 仅展示前 12 条（约 60 分钟）避免消息过长。
            for item in minutely_list[:12]:
                fx_time = item.get("fxTime", "--")
                precip = item.get("precip", "--")
                precip_type = item.get("type", "--")
                if precip_type == "rain":
                    precip_type_zh = "雨"
                elif precip_type == "snow":
                    precip_type_zh = "雪"
                else:
                    precip_type_zh = precip_type
                lines.append(f"{fx_time} | {precip_type_zh} | 5分钟降水 {precip} mm")

        if update_time:
            lines.append(f"🔄 数据更新时间: {update_time}")
        return "\n".join(lines)

    @filter.command("weather", alias={"天气", "当前天气"})
    async def weather_now(self, event: AstrMessageEvent, location: str = ""):
        """查询当前天气。

        Args:
            location(string): 位置(LocationID 或 经纬度，如 101010100 或 116.41,39.92)
        """
        location_input = location.strip() if location else ""
        if not location_input:
            location_input = str(
                self._get_group_value("global_config", "default_location", "")
            ).strip()

        if not location_input:
            yield event.plain_result(
                "请提供位置参数，例如：/weather 101010100 或 /weather 116.41,39.92"
            )
            return

        try:
            display_name = location_input
            full_name = ""
            if self._is_direct_weather_location(location_input):
                resolved_location = location_input.strip()
            else:
                geo_resolved = await self._resolve_location_via_geo(location_input)
                if not geo_resolved:
                    yield event.plain_result(
                        "未找到匹配地点，请尝试更完整地名（如：北京市朝阳区、温州市鹿城区）。"
                    )
                    return
                resolved_location, display_name, full_name = geo_resolved

            data = await self._query_weather_now(resolved_location)
            code = str(data.get("code", ""))
            if code != "200":
                logger.warning("和风天气返回非 200 状态码: %s", data)
                yield event.plain_result(
                    f"天气查询失败，接口返回 code={code}。请检查 location 或鉴权配置。"
                )
                return

            weather_text = self._build_weather_text(display_name, data, full_name)
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
        location_input = location.strip() if location else ""
        if not location_input:
            location_input = str(
                self._get_group_value("global_config", "default_location", "")
            ).strip()

        if not location_input:
            yield event.plain_result("请提供位置参数，例如：/forecast 北京市 7d")
            return

        try:
            normalized_days = self._normalize_forecast_days(days)
            display_name = location_input
            full_name = ""
            if self._is_direct_weather_location(location_input):
                resolved_location = location_input.strip()
            else:
                geo_resolved = await self._resolve_location_via_geo(location_input)
                if not geo_resolved:
                    yield event.plain_result(
                        "未找到匹配地点，请尝试更完整地名（如：北京市朝阳区、温州市鹿城区）。"
                    )
                    return
                resolved_location, display_name, full_name = geo_resolved

            data = await self._query_weather_daily(resolved_location, normalized_days)
            code = str(data.get("code", ""))
            if code != "200":
                logger.warning("天气预报返回非 200 状态码: %s", data)
                yield event.plain_result(
                    f"天气预报查询失败，接口返回 code={code}。请检查 location 或鉴权配置。"
                )
                return

            forecast_text = self._build_forecast_text(
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

    @filter.command("minutely", alias={"分钟降水", "降水分钟预报"})
    async def minutely_precip(self, event: AstrMessageEvent, location: str = ""):
        """查询分钟级降水（未来 2 小时每 5 分钟）。

        Args:
            location(string): 经纬度（经度,纬度），例如 116.41,39.92
        """
        location_input = location.strip() if location else ""
        if not location_input:
            location_input = str(
                self._get_group_value("global_config", "default_location", "")
            ).strip()

        if not location_input:
            yield event.plain_result(
                "请提供经纬度参数，例如：/minutely 116.41,39.92（分钟级降水仅支持经纬度）"
            )
            return

        if not self._is_lonlat(location_input):
            yield event.plain_result(
                "分钟级降水查询仅支持经纬度格式（经度,纬度），例如：116.41,39.92。"
            )
            return

        try:
            data = await self._query_minutely_precip(location_input)
            code = str(data.get("code", ""))
            if code != "200":
                logger.warning("分钟级降水返回非 200 状态码: %s", data)
                yield event.plain_result(
                    f"分钟级降水查询失败，接口返回 code={code}。请检查经纬度或鉴权配置。"
                )
                return

            yield event.plain_result(self._build_minutely_text(data, location_input))
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
