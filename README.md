# astrbot_plugin_weather_assistant

基于和风天气 API 的 AstrBot 天气助手插件。

当前版本功能：

- 查询实时天气
- 查询每日天气预报
- 查询分钟级降水

## 配置项

请在 AstrBot WebUI 的插件配置中填写：

- 全局配置（`global_config`）
- 实时天气相关配置（`weather_now_config`）
- 天气预报相关配置（`forecast_config`）
- 分钟级降水相关配置（`minutely_precip_config`）

主动消息推送配置：

- `global_config.active_push_sessions`：主动推送会话列表
- 列表每一项格式：`user:个人QQ号` / `group:QQ群号`
- 示例：`["user:12345678", "group:87654321"]`

在以下三个配置分组中均可独立配置主动推送：

- `weather_now_config`（实时天气）
- `forecast_config`（天气预报）
- `minutely_precip_config`（分钟级降水）

每个分组包含以下字段：

- `active_push_enabled`：是否启用主动推送
- `active_push_interval_minutes`：推送间隔时间（分钟）
- `active_push_start_time`：开始推送时间（`HH:MM`）

说明：

- 分钟级降水主动推送要求 `default_location` 为经纬度。
- QQ 主动推送会自动映射到当前已加载的 `aiocqhttp` 平台实例 ID（不是固定字符串）。

JWT 推荐配置方式：

1. 将 `global_config.auth_type` 设为 `jwt`
2. 填写 `global_config.jwt_kid`
3. 填写 `global_config.jwt_project_id`
4. 填写 `global_config.jwt_private_key`（完整 PEM）
5. 可选填写 `global_config.jwt_expire_seconds`（不填默认 3600 秒）

插件会自动生成并携带 `Authorization: Bearer <JWT>` 请求头，无需额外配置 token 字符串。

## 使用方式

- `/weather 杭州`
- `/forecast 杭州 7d`
- `/minutely 116.41,39.92`

- `/天气 杭州`
- `/预报 杭州 7d`
- `/降水 116.41,39.92`

- `/当前天气 杭州`
- `/天气预报 杭州 15`
- `/分钟降水 116.41,39.92`

未传入位置时，使用默认查询位置。
