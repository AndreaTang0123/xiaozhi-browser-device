# 仓库改造审计：单一用途局域网模拟设备客户端

日期：2026-09-14
背景：本仓库 fork 自 huangjunsen0406/py-xiaozhi，改造目标是只作为连接自建局域网
xiaozhi-esp32-server 的模拟设备数据采集客户端（博士研究项目），不连官方/云端服务，
不对外发布、不接受外部贡献。

## 一、硬编码/默认指向官方服务的代码路径（改造对象，非删除对象）

| 位置 | 内容 |
|---|---|
| `src/utils/config_manager.py:71,76` | `DEFAULT_CONFIG` 硬编码 `OTA_VERSION_URL = "https://api.tenclass.net/xiaozhi/ota/"`、`AUTHORIZATION_URL = "https://xiaozhi.me/"`，需改成局域网 server 地址 |
| `src/protocols/websocket_protocol.py:61` | 按 `wss://` 前缀判断走 TLS 分支，需确认自建 server 的 `ws://` URL 能正确命中 |
| `src/ui/cli/activation.py` / `gui/activation.py` / `shared/activation.py` | 激活提示文案硬编码"请访问 xiaozhi.me 输入验证码" |
| `src/utils/common_utils.py:60` | 验证码提取关键词表包含 `"xiaozhi.me"` 字符串匹配，非网络调用，但若自建服务提示文案不同需要跟着改 |

## 二、分类结果

### KEEP（本地连接链路必需，未改动）

`main.py`；`pyproject.toml`/`requirements.txt`/`uv.lock`；
`src/activation/`、`src/audio_codecs/`、`src/audio_processing/`、`src/bootstrap/`、
`src/constants/`、`src/core/`、`src/logging/`；
`src/mcp/mcp_server.py`、`tool_catalog.py`、`tooling.py`、`plugins/`（host/loader/registry/subprocess_*）；
`src/mcp/tools/app/`、`screenshot/`、`volume/`、`weather/`（mock 数据，无云端依赖）；
`src/mcp/tools/camera/base_camera.py`、`capture_backend.py`、`normal_camera.py`、`register.py`；
`src/plugins/`（audio/base/manager/mcp/shortcuts/ui*/wake_word）；
`src/protocols/protocol.py`、`websocket_protocol.py`；
`src/ui/cli`、`src/ui/gui`、`src/ui/tui`、`src/ui/shared`；
`src/utils/`（activation_announcer/audio_device/audio_utils/config_manager/opus_loader/resource_finder/common_utils）；
`libs/`；`models/`；
`assets/icon.*`、`assets/xiaozhi.manifest`、`assets/emojis/`、`assets/sounds/`（语言目录取舍见下）；
`scripts/camera_scanner.py`、`check_mcp_plugin.py`、`debug_audio_devices.py`、`dir_tree.py`、
`keyword_generator.py`、`py_audio_scanner.py`；
`format_code.sh`/`format_code.bat`；`tests/`；`LICENSE`（上游 MIT 协议合规保留）。

### REWRITE（保留但按新定位重写）

- `README.md` — 改为"局域网模拟设备客户端"定位
- `src/utils/config_manager.py` 的 `DEFAULT_CONFIG` — OTA/激活地址默认值
- `src/ui/*/activation.py`（cli/gui/shared）— 激活提示文案

### DELETE — 已执行（2026-09-14 清理）

零引用，直接删除：
- `CONTRIBUTING.md` / `CONTRIBUTING_ZH.md` — 面向外部贡献者的治理文件
- `assets/AtomGit.svg` — README 里的 AtomGit 徽章图
- `documents/` — 独立 VitePress 文档站，面向开源用户
- `examples/mcp_plugins/` — 社区示例 MCP 插件
- `checke_opus.sh` — 一次性本地调试脚本
- `release.py` — 发版自动化，不对外发版不需要
- `build.json` / `py-xiaozhi.spec` — PyInstaller 打包配置
- `deep-audit.md` / `risk-analysis.md` — 旧的一次性审计笔记
- `README.zh.md` — 不再维护双语文档

有代码引用，删除文件的同时清理了引用（详见 git 历史/commit）：
- `src/protocols/mqtt_protocol.py` / `mqtt_udp.py` / `mqtt_crypto.py` — 官方云端 MQTT+UDP
  传输分支，自建 server 未使用
- `src/ui/gpio/` — 树莓派物理按键模式，非浏览器/工作站模拟场景
- `src/mcp/tools/music/` 及 `scripts/music_cache_scanner.py`、`scripts/bundle_ffmpeg.sh` —
  依赖酷我、lxmusicapi.onrender.com 等第三方云端音乐 API，与 xiaozhi 协议无关，
  产生数据采集范围之外的外部网络请求
- `src/mcp/tools/camera/vl_camera.py` — 依赖智谱 AI 云端视觉 API

## 三、清理时顺带做的代码修补

删除有引用的模块后，为保证 `python main.py` 仍可正常启动，同步清理了以下
装配代码（均已确认无残留 import，`py_compile` 全部通过）：

- `src/core/protocol_manager.py` — `set_protocol` 去掉 `mqtt` 分支，恒用 WebSocket
- `main.py` — `--mode` 去掉 `gpio` 选项，`--protocol` 只保留 `websocket`
- `src/ui/__init__.py`、`src/ui/shared/factory.py`、`src/activation/factory.py` 等 —
  去掉 gpio 视口分支及相关 docstring
- `src/bootstrap/plugin_wiring.py`、`src/bootstrap/container.py`、
  `src/plugins/mcp.py`、`src/mcp/mcp_server.py` — 去掉 MusicPlayer 的创建/注入/清理
- `src/plugins/audio.py` — 去掉 TTS 期间暂停/恢复音乐的逻辑
- `src/plugins/ui.py`、`src/plugins/ui_presenter.py`、`src/core/event_bus.py` —
  去掉音乐状态/歌词的事件订阅与展示，移除对应 `Events.MUSIC_*` 常量
- `src/mcp/tools/camera/register.py` — `create_camera()` 恒返回 `NormalCamera`
- `pyproject.toml` / `requirements.txt` — 去掉 `paho-mqtt`、`gpiozero`、`lgpio`、
  `openai`（原本只被 vl_camera.py 使用）依赖

## 四、已知的无害残留（未清理，供参考）

以下内容引用的是已删除模块*之外*的通用配置项/UI 挂件，不会导致 import 报错或运行崩溃，
只是功能上变成"摆设"，出于改造成本考虑未动：

- `src/utils/config_manager.py` 的 `DEFAULT_CONFIG["MUSIC"]` 配置块、
  `AEC_OPTIONS.MUSIC_PARALLEL`、`PATHS.MUSIC_CACHE_DIR` — 音乐功能已删，这些配置键不再被任何代码读取
- `src/ui/gui/models/settings_model.py` / `settings/system_options.py` 里
  `music*`、`aecMusicParallel`、`pathMusicCacheDir` 等 GUI 设置属性 — 对应的 QML 设置面板仍会显示这些输入框，但改了不生效
- `src/audio_codecs/audio_codec.py` 里的 `_music_fifo` / `write_music_pcm` /
  `clear_music_queue` — 通用的"音乐轨道混音到 TTS 输出"能力，现在没有调用方，但本身独立于已删模块，不会报错
- `assets/sounds/` 仍保留全部 40+ 语言目录（47M），未精简到 zh-CN/en-US

如果需要进一步收紧（删掉上面这些残留配置项/UI），告诉我一声我再动手。
