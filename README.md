# astrbot_plugin_weather_assistant

基于和风天气 API 的 AstrBot 天气助手插件。

当前版本功能：

- 查询实时天气（Weather Now）
- 查询每日天气预报（Weather Daily Forecast）
- 查询分钟级降水（Minutely 5m）
- 基于和风 GeoAPI 自动模糊搜索地点，支持到区县级（如 `北京市朝阳区`、`温州市鹿城区`）

## 配置项

请在 AstrBot WebUI 的插件配置中填写：

- 全局配置（`global_config`）
- 实时天气相关配置（`weather_now_config`）
- 天气预报相关配置（`forecast_config`）
- 分钟级降水相关配置（`minutely_precip_config`）

其中常用项：

- `global_config.api_host`：和风天气控制台分配的专属 API Host
- `global_config.auth_type`：`jwt` 或 `api_key`
- `global_config.jwt_kid`：JWT 凭据的 `kid`（推荐）
- `global_config.jwt_project_id`：项目 ID，作为 JWT 的 `sub`（推荐）
- `global_config.jwt_private_key`：ED25519 私钥 PEM 全文（推荐）
- `global_config.jwt_expire_seconds`：JWT 过期时间（秒，默认 `3600`，支持 `60~86400`）
- `global_config.default_location`：默认查询位置（如需使用分钟级降水，建议填写经纬度）
- `weather_now_config.weather_fields`：实时天气返回指标开关
- `forecast_config.forecast_default_days`：天气预报默认天数（`3d/7d/10d/15d/30d`）
- `minutely_precip_config.minutely_show_details`：分钟级降水是否显示各时段明细（默认开启）

说明：插件已固定使用中文返回（`lang=zh`），不再提供语言配置项。
说明：插件已固定使用公制单位（`unit=m`），不再提供温度单位配置项。

JWT 推荐配置方式：

1. 将 `global_config.auth_type` 设为 `jwt`
2. 填写 `global_config.jwt_kid`
3. 填写 `global_config.jwt_project_id`
4. 填写 `global_config.jwt_private_key`（完整 PEM）
5. 可选填写 `global_config.jwt_expire_seconds`（不填默认 3600 秒）

插件会自动生成并携带 `Authorization: Bearer <JWT>` 请求头，无需额外配置 token 字符串。

如果你只想返回天气和温度，可以将 `weather_fields` 配置为：

```json
{
  "match_location": false,
  "location": false,
  "weather": true,
  "temperature": true,
  "feels_like": false,
  "humidity": false,
  "wind": false,
  "precip": false,
  "pressure": false,
  "visibility": false,
  "obs_time": false,
  "update_time": false
}
```

## 使用方式

- `/weather 101010100`
- `/weather 116.41,39.92`
- `/weather 北京市朝阳区`
- `/forecast 北京市`
- `/forecast 温州市 7d`
- `/天气预报 广州市 15`
- `/minutely 116.41,39.92`
- `/分钟降水 116.41,39.92`
- `/天气 101010100`

未传入位置时，会尝试使用 `default_location`。
