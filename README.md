<div align="center">

# AstrBot Osu!mania Greek

✨ **适用于 AstrBot 的 Osu!mania 工具箱插件** ✨

🚧 **正在逐步移植并实现 [nonebot-plugin-osugreek](https://github.com/YakumoZn/nonebot-plugin-osugreek) 的各项功能** 🚧

</div>

## 📖 介绍

本插件致力于为 AstrBot 提供一站式的 osu!mania 实用工具。目前项目处于**持续开发和移植**阶段，正在逐步实现并重构 [nonebot-plugin-osugreek](https://github.com/YakumoZn/nonebot-plugin-osugreek) 的功能生态。

当前已实现的功能包括炫酷的图片处理（`osugreek` 希腊字母/色散/故障特效）、段位/单曲 ACC 的精准判定计算和 One Last Image 特效。未来将会有更多原插件的实用功能被移植过来并加入其中，还会根据群友的要求增加新功能！

## ⚙️ 安装与准备

1. 通过 AstrBot 或手动将此插件克隆至：`data/plugins/` 安装。
2. 安装后，插件目录会自动生成一个 `images` 文件夹（绝对路径约为 `data/plugins/astrbot_plugin_osumania_toolkit/images`）。
3. **重要：** 你需要将含有透明背景的**希腊字母图片**或其他自定义遮罩（格式要求为`.png`）放入该 `images` 文件夹中。图片的文件名（不包含扩展名）即为你之后在指令中需要输入的“名称”。

## 💡 使用方法

### 🎨 图片特效 (osugreek / 希腊字母)

在对话中向机器人发送以下指令（**需要附带一张图片**，或者在某些平台通过引用回复带有图片的特定消息）：

```text
/osugreek <名称> [色散强度] [故障强度]
或
/希腊字母 <名称> [色散强度] [故障强度]
```

或者使用帮助指令：

```text
/osugreek help
或
/希腊字母 help
```

### 📌 参数说明

- **`<名称>`**: `images` 文件夹下素材的名称（不含 `.png`）。
- **`[色散强度]`** *(可选)*: 对底图进行 RGB 分离时的偏移量。范围：`1` - `20`，默认值为：`4`。
- **`[故障强度]`** *(可选)*: 对底图进行类似赛博朋克/故障艺术处理的强度。范围：`0` - `5`，默认值为：`0`（即不开启）。

---

### 示例用法

1. **基本使用（仅默认色散）**：
   发送指令附带图片：
   `/osugreek alpha` 
   机器人会自动在图片中间叠加 `alpha.png`，并做默认（4级）色散处理。

2. **调整色散强度**：
   发送指令附带图片：
   `/osugreek beta 10`
   图像分离感将更加强烈。

3. **附加故障特效**：
   发送指令附带图片：
   `/osugreek delta 8 3`
   使用强度为 `8` 的色散并在原图上叠加强度为 `3` 的噪点、偏移与局部线条故障效果，满满的科技感。

---

### 🧮 段位 ACC 计算 (acc / 段位)

除了图片处理，本插件还提供了 osu!mania 的段位和单曲 ACC 计算功能：

```text
/acc [参数]
/单曲 [参数]
```

- **交互模式**：直接输入 `/acc` 会进入交互模式，机器人会逐步引导您输入。
- **快捷计算**：支持直接在命令后附加参数，可以传入段位名称（如 `luminal`）、谱面 ID，或直接通过客户端回复/上传 `.osu` 谱面文件。
- **计算支持**：支持计算最终 ACC 或 ACC 的增减变化情况，包含对 ScoreV2 段位的验证与支持。

### 🎞️ One Last Image 特效 (oli)

生成《新世纪福音战士新剧场版：终》“One Last Kiss” 风格的线稿与高对比度渐变海报特效。需要在命令中附带一张图片或回复带有图片的被引用消息。

```text
/oli [模式(normal/diff/diff2)] [参数=值 ...]
```

- **交互与帮助**：输入 `/oli help` 可以快速查看支持的所有参数及详细说明。
- **模式**：
  - `normal`: 默认模式，只输出处理后的图片。
  - `diff`: 上下对比模式（上方为渲染图，下方为原图）。
  - `diff2`: 对角线斜切对比模式。
- **可选动态参数设置**：
  可以通过拼接 `参数名=值` 对图像处理项进行高度定制调整。主要支持如下等参数：
  - `zoom` (浮点，设置缩放), `cover` (布尔，控制居中防比例拉伸裁切)
  - `light` (浮点，亮度补偿), `shade` (布尔，启用铅笔阴影), `kuma` (布尔，开启极简多段渐变色彩映射), `invert_color` (布尔，使输出图片变为反色效果)
  - `watermark` (布尔，右下角开启水印渲染), `convolute_name` (字符串，指定图层处理的画笔粗细设置：精细/一般/稍粗/超粗/极粗/浮雕/线稿 等)
  - 以及诸如 `denoise` 降噪, `bevel_position` 修改对角切割比例 等。

【输入示例】：
`/oli diff2 zoom=1.1 invert_color=True watermark=False convolute_name=稍粗`

## 🤝 致谢

本插件灵感与原版实现及图片参考了：
- [YakumoZn/nonebot-plugin-osugreek](https://github.com/YakumoZn/nonebot-plugin-osugreek)
One Last Image 特效代码参考了：
- [itorr/one-last-image](https://github.com/itorr/one-last-image)
