from typing import Any


def get_weather_fields_config(config_value: Any) -> dict[str, bool]:
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
    if not isinstance(config_value, dict):
        return defaults

    merged = defaults.copy()
    for key in defaults:
        if key in config_value:
            merged[key] = bool(config_value[key])
    return merged


def build_weather_text(
    location: str,
    payload: dict[str, Any],
    matched_full_name: str,
    fields: dict[str, bool],
) -> str:
    """将接口数据格式化为用户可读文本（支持按配置控制指标开关）。"""
    now = payload.get("now", {})
    update_time = now and payload.get("updateTime", "")
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


def build_forecast_text(
    location: str, payload: dict[str, Any], days: str, matched_full_name: str
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


def build_minutely_text(
    payload: dict[str, Any], location: str, show_details: bool
) -> str:
    """将分钟级降水数据格式化为用户可读文本。"""
    summary = str(payload.get("summary", "")).strip()
    update_time = str(payload.get("updateTime", "")).strip()
    minutely_list = payload.get("minutely", [])

    lines = [f"📍 坐标: {location}"]
    if summary:
        lines.append(f"🌦️ 概述: {summary}")

    if show_details:
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
