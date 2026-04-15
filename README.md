<div align="center">

  <img src="./logo.png" alt="天气助手 Logo" width="128" />

  # 🌈 astrbot_plugin_weather_assistant —— 天气助手

  [![License](https://img.shields.io/badge/License-AGPLv3-blue.svg)](./LICENSE) [![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/) [![AstrBot](https://img.shields.io/badge/AstrBot-4.9.2%2B-orange.svg)](https://github.com/AstrBotDevs/AstrBot) [![GitHub](https://img.shields.io/badge/Author-tnzhy06-blue)](https://github.com/tnzhy06)

  **☁️ 基于和风天气 API 的强大天气插件，支持精准查询与多维度主动推送，让你的机器人化身贴心的气象管家**

</div>

------

## ✨ 功能特性

- 🌡️ **实时天气查询**：获取当前温度、体感温度、湿度、风向风速等信息，可自定义展示的指标
- 📅 **多日天气预报**：支持 3 - 30 天的天气预报。
- 🌧️ **分钟级降水**：支持中国 1 公里精度的分钟级降雨预报，出门不再被淋雨。
- 🔔 **智能主动推送**：实时天气、每日预报、降水预警可独立配置，按需开启。
- 🚀 **JWT 鉴权**：支持更安全的和风天气 JWT 鉴权模式。

------

## 🛠️ 插件安装

### 方式一：插件市场安装（推荐）

1. 进入 AstrBot 管理面板。
2. 在 **插件市场** 搜索 `天气助手`。
3. 点击 **一键安装**。

### 方式二：手动安装


```
cd AstrBot/data/plugins
git clone https://github.com/tnzhy06/astrbot_plugin_weather_assistant.git
```

完成后重启 AstrBot 即可生效。

------

## ⚙️ 配置说明

插件配置已在管理页面进行分模块处理，主要分为 4 个配置组：

1. **全局配置**
2. **实时天气配置**
3. **天气预报配置**
4. **分钟级降水配置**

> 💡 **API 获取指南**：
>
> 请前往 [和风天气开发服务](https://dev.qweather.com/) 注册账号并创建项目，获取 `API Key` 或 `JWT` 凭据。获取方式参考文档 [开发配置 | 和风天气开发服务](https://dev.qweather.com/docs/configuration/)。

------

## 📖 使用指南

### 指令列表

| **指令**    | **别名**             | **参数**        | **说明**                   |
| ----------- | -------------------- | --------------- | -------------------------- |
| `/weather`  | `/天气`, `/当前天气` | `<位置>`        | 查询指定城市的实时天气状况 |
| `/forecast` | `/天气预报`, `/预报` | `<位置> [天数]` | 查询未来天气预报           |
| `/minutely` | `/分钟降水`, `/降水` | `<经纬度>`      | 基于经纬度查询分钟级降水   |

### 使用示例

- ` /weather 杭州`
- ` /forecast 上海 7d`
- ` /minutely 120.15,30.28`
**💡若指令后不加参数将使用插件配置中的默认值**

------

## ❓ 常见问题

> **Q: JWT 鉴权失败怎么办？**
>
> - 请核对 `jwt_kid` 和 `jwt_project_id` 是否与和风后台一致。
> - 确保私钥为 **ED25519** 格式，且复制时包含完整的 `-----BEGIN...` 标识。

> **Q: 分钟级降水为什么报错？**
>
> - 该功能必须输入经纬度。格式严格要求为：`经度,纬度` (例如 `121.47,31.23`)。

------

## 🤝 贡献与反馈

1. 🌟 **Star** 这个项目以示鼓励。
2. 🐛 提交 [Issue](https://www.google.com/search?q=https://github.com/tnzhy06/astrbot_plugin_weather_assistant/issues) 报告 Bug 或提出新功能建议。
3. 🔧 欢迎提交 **Pull Request** 共同改进代码。

------

## 📄 开源协议

本项目基于 [AGPL-3.0 License](https://www.google.com/search?q=https://github.com/tnzhy06/astrbot_plugin_weather_assistant/blob/main/LICENSE) 开源。

------

*Powered by [和风天气](https://www.qweather.com/)*