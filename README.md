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
