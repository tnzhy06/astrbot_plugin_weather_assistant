from astrbot.api import logger

from .client import QWeatherClient


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
