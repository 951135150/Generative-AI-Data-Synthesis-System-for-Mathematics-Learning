# 完整演示与录制说明

## 内容和诚实边界

视频包含本机启动验收说明、实际密码登录、选择题错答、计算题正确作答、课程引用原文、
学习报告、概念证据、本地课程搜索和一次多角色协作。

- 页面操作访问真实前后端，不替换或拦截 API 响应。
- 启动使用 `start.ps1`，独立端口 8003 / 3103，正式录制前预热服务与模型。
- 演示数据库位于 `.runtime/demo/<session>/demo.db`，不是个人学习数据库。
- `demo_learner` 的 39 次初始练习通过真实 API 按人工指定的对错模式生成；它是合成历史。
- 预演和录制各新增两次独立练习，每次都核对前后端计数增加 2。
- 原始密码随机生成，仅留在忽略的私有配置中；录屏只显示密码输入框的掩码。
- 本地 E5 检索真实运行；题目、导师回复及角色推理是明确标注的离线模板。
- 课程站位和掌握度不等于真实期末成绩或经过研究校准的知识追踪估计。
- 配音为 Windows 本地 Microsoft Huihui Desktop 合成语音，不调用付费语音服务。
- 字幕根据每段实际音频时长按句分配时间，非逐字强制对齐；MP4 内嵌可见字幕，另附 SRT。

## 交付文件

文件写入 `reports/demo/<session>/`，为了避免 Git 仓库膨胀，生成媒体不会自动纳入版本控制。

- `Calculus_Atelier_中文演示.mp4`：中文配音和可见字幕，1600×900，H.264/AAC。
- `Calculus_Atelier_字幕静音版.mp4`：相同画面和字幕，没有音轨，适合自己讲解。
- `Calculus_Atelier_中文.srt`：可编辑字幕；`讲稿.md`：带章节时间的中文讲稿。
- `acceptance.json`：实际界面验收结果、计数、运行模式和已知局限，无密码和访问令牌。
- `delivery.json`：输出时长、文件大小、配音来源及完整解码校验结果。
- `screens/`：各章节原始截图和最终视频取帧，供检查布局、字体和字幕。

线上面试分享配音版时，记得在会议软件中开启共享电脑声音；如果准备现场讲解，建议播放静音版。

## 复现

### 英文项目演示

英文版采用 `data/evaluation/demo_narration_en.json` 和 Microsoft David Desktop 英文配音。
旁白以学生学习流程为主，不讲解测试环境、账户准备或接口配置；实际运行方式仍保留在验收元数据中。
英文片头是项目介绍画面，正式应用页面不修改运行状态提示。

在下述录制步骤中，给配音命令添加
`-NarrationFile data/evaluation/demo_narration_en.json`，给音频检查命令添加
`--narration data/evaluation/demo_narration_en.json`，并在运行录制脚本前设置：

```powershell
$env:DEMO_NARRATION='data/evaluation/demo_narration_en.json'
```

请使用独立的新会话目录。英文输出为 `Calculus_Atelier_Project_Demo_EN.mp4`、
`Calculus_Atelier_EN_Silent.mp4`、`Calculus_Atelier_EN.srt` 和 `Narration_EN.md`。

### 通用录制步骤

使用新的会话目录，避免覆盖既有演示数据。下列目录只是示例：

```powershell
.\.venv\Scripts\python.exe scripts/prepare_demo.py --folder .runtime/demo/my_session
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/demo_voice.ps1 -OutputDirectory .runtime/demo/my_session/voice
.\.venv\Scripts\python.exe scripts/render_demo.py --folder .runtime/demo/my_session --audio-info
$env:DATABASE_URL='sqlite:///.runtime/demo/my_session/demo.db'
$env:OUTPUT_DIR='.runtime/demo/my_session/output'
$env:NEXT_DIST_DIR='.next-e2e'
.\start.ps1 -ApiPort 8003 -WebPort 3103
```

另一个终端运行：

```powershell
node scripts/record_demo.mjs .runtime/demo/my_session --rehearsal
node scripts/record_demo.mjs .runtime/demo/my_session
.\.venv\Scripts\python.exe scripts/render_demo.py --folder .runtime/demo/my_session
```

录屏使用已安装的 Google Chrome，以及 Playwright 的小型 FFmpeg 组件：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH=Join-Path (Get-Location) '.runtime/playwright'
node t2p-web/node_modules/playwright/cli.js install ffmpeg
.\.venv\Scripts\python.exe -m pip install --target .runtime/video-tools --no-deps --cache-dir .runtime/pip-cache imageio-ffmpeg==0.6.0
```

依赖与媒体均放在项目磁盘，不安装新的大型模型或整套浏览器。结束后在启动终端按 Ctrl+C，
只停止启动器拥有的两个服务。

## 本轮验收观察到的展示局限

完整主流程可以运行，但不应把“可以演示”说成“没有任何待改进点”：

- 加速生成的模拟练习没有真实计时；学习报告的学习时长仍可能为 0 分钟，未伪造为数小时。
- 离线多角色模拟的平均质量可能显示 0.0，占位不应解释成真实 AI 质量得分。
- 启动说明卡是视频讲解画面，不属于系统功能页；正式网页部分不修改应用源码来伪装功能。
- 没有测试真实 DeepSeek、手写 OCR 或正式部署；不能据本视频声称这些能力已经验收。
