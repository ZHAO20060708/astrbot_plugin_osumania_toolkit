# AstrBot Osu!mania Toolkit

适用于 [AstrBot](https://github.com/Soulter/AstrBot) 的 osu!mania 谱面、回放、成绩与图像处理工具箱。

## 项目简介

本插件将 [nonebot-plugin-osumania-toolkit](https://github.com/LeoBlackMT/nonebot-plugin-osumania-toolkit) 的核心算法与功能移植至 AstrBot，集成了谱面卡片生成、多算法难度推算、回放分析与成绩转换等功能，并加入了 `osugreek` 希腊字母与 `oli`（One Last Image）图像特效。

发送 `/omtk` 可在聊天中查看交互式命令帮助菜单。

---

## 核心特性与架构亮点

1. **高精度难度估算（Tosu/JS Parity）**
   * **多估计算法支持**：内置 `Mixed`（综合推荐）、`Roxy`（111 维元模型 + 7 流 Strain 曲线）、`Sunny`（严格步进插值 + CArrV2 经典有效权重）、`Azusa`、`Daniel`、`Companella`（ONNX 神经网络段位模型，按需惰性加载）。
   * **Mixed 综合路由**：对齐前沿 RC 路由机制，以 Roxy 算法为核心、附带 Azusa 偏好门控与 Daniel 溢出回退。
   * **Interlude 浮点单精度逐位对齐**：Python 计算镜像 JS `Math.fround` (float32) 算子量化，消除跨端星数漂移。
   * **新增段位物量数据**：补充包含 `l2`、`t3` 等在内的全新段位物量定义。

2. **高保真回放判定与分数转换（Interlude Parity）**
   * **回放命中时序对齐**：完整镜像 Interlude `Events.fs` 判定逻辑，精准保留活跃 Hold 状态、释放判定、head deltas 与鬼键（ghost tap）连击语义。
   * **全规则集支持**：支持 osu!、Etterna、Malody、Quaver、StepMania 及自定义 `.ruleset` 分数与判定重算。
   * **真实比例卡片渲染**：成绩转换卡片（`/cvtscore`）判定柱按真实相对时隙宽度渲染。

3. **轻量化渲染运行时与资源优化**
   * **浏览器按需冷启与自动休眠**：内置 Chromium 实例零常驻运行，首次出图请求时拉起，连续 10 分钟空闲无任务自动退出并释放内存。
   * **前端静态体积脱水**：剔除冗余 WASM 编译变体，静态资产体积精简 60%（从 110MB 压至 44MB）。
   * **纯开源文远圆体**：内置开源 **文远圆体（WenYuan Rounded SC 400/900）** 替代专有 Torus 字体，中英文字阶圆润清晰。

4. **单谱解析共享与分层缓存**
   * **单次解析克隆分发**：引入 `osu_file.clone()` 容器浅拷贝，链路分析与批量处理时单张谱面仅从磁盘解析一次，消除重复 IO。
   * **MinaCalc 结果指纹缓存**：基于谱面内容 SHA256 与运行器二进制指纹建立计算缓存，算过的谱面跳过进程调用。
   * **Jinja2 模板内存常驻**：避免每次卡片渲染重复读取磁盘编译 HTML。

---

## 命令一览

| 命令 | 别名 | 功能 | 输入与选项 |
|:----:|:----:|:----|:----|
| `/omtk` | — | 帮助菜单 / 命令详情 | `/omtk [命令名] [页码]` |
| `/ma` | `/mag` | 新版 ManiaMapAnalyser 谱面分析卡片 | 数字 bid、`b<bid>` 或 osu 谱面网址；支持选项 `-n/-a/-p/-e/-g` 与 `+dt/+ht/+in/+ho` |
| `/mapview` | `/rework` | 谱面键型分析与难度估计 | 单个 `.osu/.mc`、`b<bid>`/网址使用新版卡片；图包支持批量分析；支持 `+mods x倍速 OD值` |
| `/ett` | `/msd` | Etterna MSD 难度计算 | 回复谱面/图包 或 `b<bid>`；支持 `x倍速` 与目标分数率 |
| `/pattern` | `/键型` | 谱面键型分析 | 回复谱面/图包 或 `b<bid>`；加 `-d` 输出详细文本 |
| `/analyze` | `/分析` | 回放作弊 / 异常分析 | 回复 `.osr/.mr`，可选指定 `b<bid>`；加 `-reason` 输出判定详情 |
| `/delta` | `/偏差` | 判定偏差柱状图 | 回复 `.osr/.mr` 并指定 `b<bid>` |
| `/scatter` | `/散点` | 判定散点图 | 回复 `.osr/.mr` 并指定 `b<bid>` |
| `/spectrum` | `/频谱` | 回放打击频谱图 | 回复 `.osr/.mr` |
| `/lifebar` | `/血条`,`/life` | 回放血条变化折线图 | 回复 `.osr` |
| `/pressingtime` | `/按压` | 回放按键时间分析图 | 回复 `.osr/.mr` |
| `/acc` | `/单曲` | 单曲 ACC 计算与反算 | 段位名 / `b<bid>` / 谱面文件；支持交互式输入与成绩反算 |
| `/cvtscore` | `/转换` | 按目标 ruleset 重算成绩 | 回放 + 谱面 + 目标 ruleset（支持多轮交互引导） |
| `/percy` | `/投皮` | LN 投皮程度查看 / 修改 | 回复 `.png` 面身图片，`/percy [目标程度] [lazer]` |
| `/osugreek` | `/希腊字母` | 希腊字母 / 色散 / 故障特效 | 附带或回复图片 |
| `/oli` | — | One Last Image 风格图像特效 | 附带或回复图片 |

> 大多数命令支持「回复一条包含文件的消息」或「直接携带 `b<谱面ID>` / 谱面网址」。

---

## 安装与环境说明

1. 将本插件目录克隆或下载至 AstrBot 的 `data/plugins/astrbot_plugin_osumania_toolkit`。
2. 依赖项由插件自带的引导模块（`dependency_bootstrap.py`）或 AstrBot 自动安装，包含科学计算栈（`numpy`, `scipy`, `pandas`, `matplotlib`, `onnxruntime`）与 `playwright`。
3. `/ett` 依赖自带的 Linux x86-64 Etterna MinaCalc 运行器 `algorithm/ett/official_minacalc_runner`。插件启动时会自动添加执行权限；若报权限错误，可手动执行：
   ```bash
   chmod +x algorithm/ett/official_minacalc_runner
   ```
4. `/ma` 与 `/mapview` 的单图分析直接复用内置的无头 Chromium 实例进行渲染；成绩转换与散点卡片由内置 Jinja2 模板引擎驱动。

---

## 配置说明（可在 WebUI 中配置）

| 配置项 | 类型 | 默认值 | 说明 |
|:-----:|:----:|:----:|:----|
| `omtk_cache_max_age` | int | 24 | 缓存文件最大保留时间（小时），设为 0 在清理时删除所有缓存 |
| `max_file_size_mb` | int | 50 | 允许处理的单个文件大小上限（MB），0 为无限制 |
| `batch_max_charts` | int | 15 | 图包批量分析单次最多处理谱面数，0 为无限制 |
| `default_convert_od` | int | 8 | `.mc` 转 `.osu` 时默认的 OverallDifficulty |
| `default_convert_hp` | int | 8 | `.mc` 转 `.osu` 时默认的 HPDrainRate |
| `max_concurrency` | int | 5 | 谱面卡片渲染并发任务上限 |
| `render_timeout_seconds` | int | 120 | 谱面卡片渲染超时限制（秒） |
| `capture_target` | string | `full_card` | 截图目标：`full_card`（完整卡片）或 `graph_only`（仅难度折线图） |
| `content_bar` | string | `Auto` | 新版卡片主体：`None`、`Auto`、`Pattern`、`Etterna`、`Graph`、`Full` |
| `estimator_algorithm` | string | `Mixed` | 难度估算算法：`Mixed`、`Roxy`、`Sunny`、`Azusa`、`Daniel`、`Companella` |
| `sr_text` | string | `ReworkSR` | 卡片主难度文本：`ReworkSR`、`MSD`、`Pattern`、`InterludeSR`、`Auto` |
| `diff_text` | string | `Difficulty` | 卡片副难度文本：`Difficulty`、`Graph`、`MSD`、`Pattern`、`ReworkSR`、`None` |
| `etterna_version` | string | `0.72.3` | Etterna MinaCalc 版本（支持 `0.72.3`、`0.74.0`、`0.75.0`） |
| `companella_etterna_version` | string | `0.74.0` | Companella 模型绑定的 Etterna 版本 |
| `enable_cover_art` | bool | `true` | 使用谱面封面提取主题色作为卡片背景 |
| `enable_floating_triangles` | bool | `true` | 显示卡片浮动三角纹理背景 |
| `custom_background_color` | string | `#000000` | 覆盖卡片背景色（十六进制 #RRGGBB；#000000 表示跟随封面提取） |
| `use_osu_font` | bool | `true` | 使用内置字阶字体（文远圆体） |

> 键型聚类阈值与作弊判定等更深层参数详见 `config.py`。

---

## 致谢

* 核心算法与工具实现移植自 [LeoBlackMT/nonebot-plugin-osumania-toolkit](https://github.com/LeoBlackMT/nonebot-plugin-osumania-toolkit)。
* 谱面卡片前端与数据流对齐自 [LeoBlackMT/osumania_map_analyser](https://github.com/LeoBlackMT/osumania_map_analyser)。
* `osugreek` 算法参考 [YakumoZn/nonebot-plugin-osugreek](https://github.com/YakumoZn/nonebot-plugin-osugreek)。
* `oli` 图像特效参考 [itorr/one-last-image](https://github.com/itorr/one-last-image)。
* 第三方依赖与字体开源许可详见 [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md)。
