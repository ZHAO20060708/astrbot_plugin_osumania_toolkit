<div align="center">

# AstrBot Osu!mania Toolkit

✨ **适用于 AstrBot 的 osu!mania 高级分析与实用工具插件** ✨
PORTED BY CLAUDE OPUS 4.8

</div>

## 📖 介绍

本插件将 [nonebot-plugin-osumania-toolkit](https://github.com/LeoBlackMT/nonebot-plugin-osumania-toolkit)
的功能移植到 AstrBot，提供谱面分析、难度估计、回放分析、成绩转换等一站式 osu!mania 工具，
并加入了 `osugreek` 希腊字母特效与 `oli`（One Last Image）特效。

发送 `/omtk` 获取命令帮助菜单。

## 🧰 命令一览

| 命令 | 别名 | 功能 | 输入 |
|:----:|:----:|:----|:----|
| `/omtk` | — | 帮助菜单 / 命令详情 | `/omtk [命令名] [页码]` |
| `/mapview` | `/rework` | 谱面键型分析与难度估计 | 回复 `.osu/.mc/.osz/.mcz` 或 `b<bid>`/网址；支持 `+mods x倍速 OD值` |
| `/ett` | `/msd` | Etterna MSD 难度计算 | 回复谱面/图包 或 `b<bid>`；仅支持 `x倍速` |
| `/pattern` | `/键型` | 谱面键型分析 | 回复谱面/图包 或 `b<bid>`；加 `-d` 输出详细文本 |
| `/analyze` | `/分析` | 回放作弊/异常分析 | 回复 `.osr/.mr`，可选 `b<bid>`；加 `-reason` 输出详情 |
| `/delta` | `/偏差` | 判定偏差柱状图 | 回复 `.osr/.mr` 并指定 `b<bid>` |
| `/scatter` | `/散点` | 判定散点图 | 回复 `.osr/.mr` 并指定 `b<bid>` |
| `/spectrum` | `/频谱` | 回放打击频谱图 | 回复 `.osr/.mr` |
| `/lifebar` | `/血条`,`/life` | 回放血条变化图 | 回复 `.osr` |
| `/pressingtime` | `/按压` | 按键时间分析图 | 回复 `.osr/.mr` |
| `/acc` | `/单曲` | 单曲 ACC 计算 | 段位名 / `b<bid>` / 谱面文件；支持交互与反算 |
| `/cvtscore` | `/转换` | 按目标 ruleset 重算成绩 | 回放 + 谱面 + 目标 ruleset（支持交互） |
| `/percy` | `/投皮` | LN 投皮程度查看/修改 | 回复 `.png` 面身图片，`/percy [目标程度] [lazer]` |
| `/osugreek` | `/希腊字母` | 希腊字母 / 色散 / 故障特效 | 附带或回复图片 |
| `/oli` | — | One Last Image 风格特效 | 附带或回复图片 |

> 大多数命令支持「回复一条包含文件的消息」或「直接 `b<谱面ID>` / mania 谱面网址」两种方式。
> 文件大小与图包批量上限可在配置中调整。

## ⚙️ 安装与依赖

1. 将本插件放入 AstrBot 的 `data/plugins/` 目录。
2. 安装 Python 依赖（见 `requirements.txt`）：`numpy`、`scipy`、`matplotlib`、`Pillow`
   （`Pillow`/`aiohttp` 通常随 AstrBot 提供）。
3. `/ett` 依赖自带的 Etterna MinaCalc 可执行文件
   `algorithm/ett/official_minacalc_runner`（Linux x86-64）。插件启动时会自动尝试为其
   添加执行权限；若 `/ett` 报权限错误，请手动执行：
   `chmod +x algorithm/ett/official_minacalc_runner`。
4. 卡片类命令（`/mapview` `/ett` `/pattern` `/cvtscore`）通过 AstrBot 的 HTML 渲染器
   生成图片，请确保 AstrBot 的文转图 / HTML 渲染功能可用。

## 💡 使用提示

- 合并转发：图包批量分析与多页帮助会以合并转发形式发送，目前在 OneBot（aiocqhttp）
  平台体验最佳；其它平台会退化为多条消息发送。
- `/cvtscore` 自定义 ruleset：参考原项目的
  [规则集示例](https://github.com/LeoBlackMT/nonebot-plugin-osumania-toolkit/blob/main/docs/ruleset-description.jsonc)，
  将 `.ruleset` 放入 `rulesets/` 目录。
- 分析结果由算法生成，仅供参考。

## ⚙️ 配置说明（节选）

| 配置项 | 类型 | 默认值 | 说明 |
|:-----:|:----:|:----:|:----|
| `omtk_cache_max_age` | int | 24 | 缓存文件最大保留时间（小时） |
| `default_convert_od` | int | 8 | `.mc` 转 `.osu` 的默认 OverallDifficulty |
| `default_convert_hp` | int | 8 | `.mc` 转 `.osu` 的默认 HPDrainRate |
| `max_file_size_mb` | int | 50 | 允许处理的最大文件大小（MB），0 表示无限制 |
| `batch_max_charts` | int | 15 | 图包批量分析单次最多处理谱面数，0 表示无限制 |

> 键型分析与作弊分析还有大量可调参数，详见 `config.py` 中的注释。

## 🤝 致谢

- osu!mania 工具核心移植自 [LeoBlackMT/nonebot-plugin-osumania-toolkit](https://github.com/LeoBlackMT/nonebot-plugin-osumania-toolkit)
  （难度/键型/MSD/成绩转换等算法详见其 README 的「参考内容」）。
- `osugreek` 特效参考 [YakumoZn/nonebot-plugin-osugreek](https://github.com/YakumoZn/nonebot-plugin-osugreek)。
- `oli` 特效参考 [itorr/one-last-image](https://github.com/itorr/one-last-image)。
