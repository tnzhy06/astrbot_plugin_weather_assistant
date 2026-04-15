import time
from typing import Any

import jwt

from astrbot.api import AstrBotConfig, logger


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

    def get_jwt_expire_seconds(self) -> int:
        """获取 JWT 过期秒数，并做安全范围校验。"""
        raw_expire = self.get_group_value("global_config", "jwt_expire_seconds", 3600)
        try:
            expire_seconds = int(raw_expire)
        except (TypeError, ValueError):
            logger.warning("jwt_expire_seconds 非法，已回退到默认值 3600 秒")
            return 3600

        # 和风天气文档约束最大 24 小时，这里同时限制最小值避免过短导致频繁失效。
        if expire_seconds < 60:
            logger.warning("jwt_expire_seconds 小于 60，已自动调整为 60 秒")
            return 60
        if expire_seconds > 86400:
            logger.warning("jwt_expire_seconds 大于 86400，已自动调整为 86400 秒")
            return 86400
        return expire_seconds

    def build_auth_headers(self) -> dict[str, str]:
        """根据配置构建鉴权头。"""
        auth_type = (
            str(self.get_group_value("global_config", "auth_type", "api_key"))
            .strip()
            .lower()
        )
        headers: dict[str, str] = {}
        if auth_type == "jwt":
            jwt_token = self._build_qweather_jwt_token()
            if jwt_token:
                headers["Authorization"] = f"Bearer {jwt_token}"
            return headers

        api_key = str(self.get_group_value("global_config", "api_key", "")).strip()
        if api_key:
            headers["X-QW-Api-Key"] = api_key
        return headers

    def _build_qweather_jwt_token(self) -> str:
        """生成和风天气 JWT。

        使用 kid + project_id + 私钥自动签发。
        """
        kid = str(self.get_group_value("global_config", "jwt_kid", "")).strip()
        project_id = str(
            self.get_group_value("global_config", "jwt_project_id", "")
        ).strip()
        private_key = str(
            self.get_group_value("global_config", "jwt_private_key", "")
        ).strip()

        if not (kid and project_id and private_key):
            return ""

        # 兼容用户在 WebUI 中以 \n 形式保存多行私钥。
        normalized_private_key = private_key.replace("\\n", "\n")
        now = int(time.time())
        expire_seconds = self.get_jwt_expire_seconds()
        payload = {
            "sub": project_id,
            "iat": now - 30,
            # JWT 有效期可由配置项 jwt_expire_seconds 自定义。
            "exp": now + expire_seconds,
        }
        headers = {
            "alg": "EdDSA",
            "kid": kid,
        }
        try:
            token = jwt.encode(
                payload=payload,
                key=normalized_private_key,
                algorithm="EdDSA",
                headers=headers,
            )
        except Exception as exc:
            logger.error(
                f"构建和风天气 JWT 失败，请检查 kid/project_id/私钥 是否正确: {exc}"
            )
            return ""
        return str(token).strip()
