<div align="center">

# AstrBot Osu!mania Toolkit

✨ **适用于 AstrBot 的 Osu!mania 图片处理与合成插件** ✨

基于 [nonebot-plugin-osugreek](https://github.com/YakumoZn/nonebot-plugin-osugreek) 移植/重构

</div>

## 📖 介绍

这是一个能够为图片添加自定义希腊字母覆盖层，并生成非常炫酷的“色散（Chromatic Aberration）”及“故障（Glitch）”特效图片的 AstrBot 插件。非常适合用来制作类似于 osu!mania 段位认证、极客风格头像或是单纯的蒸汽波风格艺术图。

## ⚙️ 安装与准备

1. 通过 AstrBot 或手动将此插件克隆至：`data/plugins/` 安装。
2. 安装后，插件目录会自动生成一个 `images` 文件夹（绝对路径约为 `data/plugins/astrbot_plugin_osumania_toolkit/images`）。
3. **重要：** 你需要将含有透明背景的**希腊字母图片**或其他自定义遮罩（格式要求为`.png`）放入该 `images` 文件夹中。图片的文件名（不包含扩展名）即为你之后在指令中需要输入的“名称”。

## 💡 使用方法

在对话中向机器人发送以下指令（**需要附带一张图片**，或者在某些平台通过引用回复带有图片的特定消息）：

```text
/osugreek <名称> [色散强度] [故障强度]
```

或者使用帮助指令：

```text
/osugreek help
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

## 🤝 致谢

本插件灵感与原版实现及图片参考了：
- [YakumoZn/nonebot-plugin-osugreek](https://github.com/YakumoZn/nonebot-plugin-osugreek)
