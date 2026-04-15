from typing import Any

from astrbot.api import AstrBotConfig


class WeatherConfig:
    """天气插件配置访问器。"""

    def __init__(self, config: AstrBotConfig):
        self._config = config

    def get_group_config(self, group_key: str) -> dict[str, Any]:
        """读取分组配置。"""
        group = self._config.get(group_key, {})
        if isinstance(group, dict):
            return group
        return {}

    def get_group_value(self, group_key: str, key: str, default: Any) -> Any:
        """按分组读取配置，兼容旧版顶层字段。"""
        group = self.get_group_config(group_key)
        if key in group:
            return group[key]
        # 兼容旧版配置，避免升级后用户历史配置立即失效。
        return self._config.get(key, default)

    def normalize_api_host(self) -> str:
        """标准化 API Host，兼容用户只填写域名的情况。"""
        host = str(self.get_group_value("global_config", "api_host", "")).strip()
        if not host:
            return ""
        if not host.startswith(("http://", "https://")):
            host = f"https://{host}"
        return host.rstrip("/")

    def build_auth_headers(self) -> dict[str, str]:
        """根据配置构建鉴权头。"""
        auth_type = (
            str(self.get_group_value("global_config", "auth_type", "api_key"))
            .strip()
            .lower()
        )
        headers: dict[str, str] = {}
        if auth_type == "jwt":
            jwt_token = str(
                self.get_group_value("global_config", "jwt_token", "")
            ).strip()
            if jwt_token:
                headers["Authorization"] = f"Bearer {jwt_token}"
            return headers

        api_key = str(self.get_group_value("global_config", "api_key", "")).strip()
        if api_key:
            headers["X-QW-Api-Key"] = api_key
        return headers
