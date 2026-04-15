def is_lonlat(location: str) -> bool:
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


def is_direct_weather_location(location: str) -> bool:
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


def normalize_forecast_days(days_input: str, default_days: str) -> str:
    """标准化预报天数参数，兼容 3/3天/3d 等写法。"""
    allowed_forecast_days = {"3d", "7d", "10d", "15d", "30d"}
    days = days_input.strip().lower()
    if not days:
        days = default_days.strip().lower()

    if days.endswith("天"):
        days = f"{days[:-1]}d"
    if days.isdigit():
        days = f"{days}d"

    if days not in allowed_forecast_days:
        raise ValueError("预报天数仅支持 3d/7d/10d/15d/30d（也可输入 3/7/10/15/30）")
    return days
