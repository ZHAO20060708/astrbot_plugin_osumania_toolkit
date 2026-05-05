<div align="center">

# AstrBot Osu!mania Toolkit

✨ **在 AstrBot 上重实现 nonebot-plugin-osumania-toolkit 的图像叠加能力** ✨

参考项目：<https://github.com/LeoBlackMT/nonebot-plugin-osumania-toolkit>

</div>

## 功能

- `/osugreek <name> [chromatic] [glitch]`：对图片做色散/故障效果并叠加希腊字母素材。
- `/osumania <name> [chromatic] [glitch]`：与 `/osugreek` 等价的别名命令。
- `/osugreek_list`：列出 `images/` 下可用素材。
- 支持“命令内直接带图”或“回复一条带图消息”。

## AstrBot 环境准备

1. 将仓库放入 AstrBot 的 `data/plugins/astrbot_plugin_osumania_toolkit`。
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 启动 AstrBot，并在插件列表启用本插件。

## 素材准备

将透明底 PNG 素材放进插件目录 `images/`，文件名（去掉 `.png`）就是命令中的 `<name>` 参数。

## 命令示例

- `/osugreek alpha`
- `/osugreek beta 10`
- `/osumania gamma 8 3`
- `/osugreek_list`

