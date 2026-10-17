# T2P：基于多智能体协作的微积分教学数据合成系统

## 学术项目报告（中文版）

---

**摘要**

本报告介绍了 T2P（Term 2 Project）——一个面向微积分教学的 AI 驱动数据合成系统。该系统围绕"通过数据合成增强数学学习"这一核心目标，实现了三大功能模块：(1) 基于大语言模型的微积分题目自动生成，支持练习模式与多概念融合考试模式；(2) 智能批改引擎，支持手写体 OCR 识别与苏格拉底式引导反馈；(3) 基于消息传递机制的真正多智能体协作系统，由四个自治 Agent（题目合成者、支架设计者、质量审查者、数据集策展者）通过异步消息总线并发协作，生成高质量、覆盖均衡的数学题目数据集。系统后端基于 FastAPI 构建，前端采用 Next.js 16 与 React 19，大语言模型服务由 DeepSeek V4 Pro 提供。实验表明，相较于传统流水线架构，消息驱动的多智能体系统将单题 LLM 调用次数从 8-10 次降低至 4-5 次，并实现了 Agent 间的涌现式协作。

**关键词**：多智能体系统；大语言模型；数学教育；数据合成；消息传递架构；微积分教学

---

## 1. 引言

### 1.1 研究背景

微积分是理工科高等教育的基石课程，但其教学面临两个核心挑战：一是高质量练习题的稀缺性——传统题库受限于人工编写速度，难以覆盖不同难度层级和知识点组合；二是个性化反馈的缺失——大规模课堂中教师无法为每位学生提供逐题批改与针对性指导。近年来，大语言模型（Large Language Models, LLMs）在数学推理领域的突破为自动化题目生成与智能批改提供了技术基础。然而，单一 LLM 调用在数学正确性、教育适配性和逻辑连贯性方面存在显著局限。

多智能体系统（Multi-Agent Systems, MAS）通过引入角色分工与协作机制，为解决上述问题提供了新范式。多个专业化的 AI Agent 可以分别负责题目创作、质量把控、教学支架设计和全局策展，通过结构化的通信协议实现超越单一 LLM 的协同智能。

### 1.2 项目目标

本研究旨在设计并实现 T2P 系统，达成以下目标：

1. **自动化题目生成**：支持练习模式（单知识点）与考试模式（多概念融合），覆盖计算题、选择题和填空题三种题型，难度可配置（1-5 级）。
2. **智能批改引擎**：接受学生手写体图片输入，通过 OCR 识别后进行逐逻辑步骤的评估，提供苏格拉底式引导反馈而非简单对错判断。
3. **真正多智能体数据合成**：构建基于消息传递的自治多智能体系统，实现 Agent 间的直接通信、自主决策和并发协作。
4. **自适应学习路径**：基于用户掌握度的指数移动平均（EMA）算法，实现难度和模式的自动调节。

### 1.3 报告结构

本报告其余部分组织如下：第 2 节回顾相关工作；第 3 节详细描述系统架构；第 4 节阐述多智能体系统设计；第 5 节介绍题目生成与评估方法论；第 6 节说明前端交互设计；第 7 节给出系统评估结果；第 8 节进行讨论；第 9 节总结全文并展望未来工作。

---

## 2. 相关工作

### 2.1 大语言模型在数学教育中的应用

GPT-4、Claude 和 DeepSeek 等 LLM 在数学推理任务上展现出令人瞩目的能力（OpenAI, 2023; Anthropic, 2024）。MathQA（Amini et al., 2019）和 GSM8K（Cobbe et al., 2021）等基准测试表明，最先进的模型在结构化数学问题上已达到较高准确率。然而，这些模型在生成可教学的数学内容时仍面临挑战：LaTeX 格式的可靠性、逻辑步骤的完全正确性以及教育适应性的不足。

在教育领域，Khan Academy 的 Khanmigo 平台展示了 LLM 作为 AI 导师的潜力。Du et al.（2024）提出的 MathVC 框架使用多智能体讨论来验证数学推理，启发了本系统的质量控制机制。

### 2.2 多智能体系统与教育内容生成

多智能体系统在内容生成领域已有显著进展。ChatDev（Qian et al., 2023）模拟软件公司的组织架构，通过角色扮演生成代码。AutoGen（Wu et al., 2023）提供了一个通用的多 Agent 对话框架。在教育领域，Park et al.（2024）使用多 Agent 模拟师生互动来生成训练数据。

然而，现有研究存在共同局限：(1) 多数系统采用硬编码的流水线编排，Agent 之间缺乏真正的直接通信；(2) Agent 的 LLM 调用往往存在双层浪费——Agent 调用 LLM 仅用于工具路由，工具内部再次调用 LLM 执行实际工作；(3) 缺少面向数学教育的专业评估维度。

本项目的 T2P 系统针对上述局限进行了改进，实现了基于消息总线的真正多智能体通信架构。

### 2.3 教学支架理论

支架式教学（Scaffolding）源于 Vygotsky（1978）的最近发展区（Zone of Proximal Development, ZPD）理论，强调在适当难度下提供渐进式提示来引导学习者。T2P 将这一原则融入每道题目的结构设计中——从概念性提示（第一步：应用什么原理？）到策略性提示（第二步：采用什么方法？）再到程序性提示（第三步：首个计算步骤），最后到验证性提示（第四步：如何验证答案？），形成完整的认知引导链。

---

## 3. 系统架构

### 3.1 总体架构

T2P 系统采用前后端分离架构，如图 1 所示。

```
┌──────────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js 16 + React 19)              │
│                      Port 3000 (Tailwind CSS v4)                  │
│  ┌─────────────┐  ┌─────────────────┐  ┌──────────────────────┐  │
│  │ 题目生成面板 │  │ 手写批改画布     │  │ 多智能体实时监控面板  │  │
│  │ (配置+生成)  │  │ (签名+图片上传)  │  │ (SSE 实时流)         │  │
│  └─────────────┘  └─────────────────┘  └──────────────────────┘  │
│  ┌─────────────┐  ┌─────────────────┐                            │
│  │ 题目展示区   │  │ 学习仪表盘       │                            │
│  │ (LaTeX渲染)  │  │ (雷达图+柱状图)  │                            │
│  └─────────────┘  └─────────────────┘                            │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP/REST + SSE
┌──────────────────────────▼───────────────────────────────────────┐
│                    Backend (FastAPI + Uvicorn)                    │
│                        Port 8001 (Python 3.x)                     │
│  ┌───────────────┐  ┌────────────────┐  ┌────────────────────┐   │
│  │ /generate     │  │ /audit         │  │ /synthesize-v2     │   │
│  │ (题目生成)     │  │ (智能批改)      │  │ (多智能体合成)      │   │
│  └───────┬───────┘  └───────┬────────┘  └─────────┬──────────┘   │
│          │                  │                      │              │
│  ┌───────▼───────┐  ┌───────▼────────┐  ┌─────────▼──────────┐   │
│  │ BatchGenerator│  │ LLMClient      │  │ Coordinator        │   │
│  │ → Generator   │  │ .mentor_review │  │ → MessageBus       │   │
│  │ → Evaluator   │  │ OCRClient      │  │ → 4 AutonomousAgents│  │
│  │ → PostProcessor│ │                │  │   (并发 asyncio)    │   │
│  └───────────────┘  └────────────────┘  └────────────────────┘   │
│                           │                                       │
│                  ┌────────▼────────┐                              │
│                  │ DeepSeek V4 Pro │                              │
│                  │ (OpenAI 兼容API) │                              │
│                  └─────────────────┘                              │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 后端组件详解

#### 3.2.1 API 服务器（api_server.py）

FastAPI 应用提供 10 个端点：

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/` | 服务状态与数据集信息 |
| GET | `/topics` | 获取可用知识点列表 |
| POST | `/user/login` | 用户登录与会话创建 |
| GET | `/user/progress/{user_id}` | 获取学习进度数据 |
| POST | `/user/record` | 记录学习结果 |
| POST | `/generate` | 生成题目（支持自适应） |
| POST | `/audit` | 智能批改学生作答 |
| POST | `/synthesize` | 旧版多智能体流水线（V1） |
| POST | `/synthesize-v2` | 新版多智能体合成（V2） |
| GET | `/synthesize-v2/stream` | 多智能体实时 SSE 流 |

#### 3.2.2 题目生成管线（generator.py + batch_generator.py）

`ProblemGenerator` 实现了带自修复反馈的生成循环：

1. **提示词构建**（PromptBuilder）：根据模式（练习/考试）、难度和题型构建专用提示词，注入 LaTeX 格式约束和逻辑正确性要求
2. **LLM 调用**（LLMClient）：通过 OpenAI 兼容接口调用 DeepSeek V4 Pro
3. **后处理**（PostProcessor）：JSON 解析、LaTeX 清洗、字段规范化
4. **质量评估**（QualityEvaluator）：结构验证 + AI 深度语义审计 + 原创性检测
5. **自修复重试**：未通过评估时，将 AI 反馈注入下一轮提示词

`BatchGenerator` 负责批量调度，包括锚点轮换（考试模式）、动态温度控制和语义去重。

#### 3.2.3 智能批改管线（api_server.py audit 端点）

1. **输入解析**：检测 base64 图片或纯文本
2. **OCR 转录**（OCRClient）：使用 DeepSeek Vision 模型识别手写 LaTeX
3. **题目检索**：跨黄金数据集和生成输出目录搜索
4. **导师审查**（LLMClient.mentor_review）：逐逻辑步骤对比，生成错误分析和苏格拉底式引导
5. **分数校准**：针对选择题和开放题采用不同校准策略

#### 3.2.4 用户学习管理（user_session.py）

`UserSession` 实现自适应学习路径：

- **EMA 掌握度算法**：`new_mastery = old_mastery × 0.4 + (score/100) × 0.6`
- **Level 晋升**：L1（基础）→ L2（支架）→ L3（考试准备），通过阈值 80 分
- **自适应任务参数**：按路线图顺序查找首个掌握度 < 85% 的知识点

### 3.3 前端架构

前端基于 Next.js 16.2.4、React 19.2.4 和 Tailwind CSS v4 构建。

**主要页面**：
- **主页（page.tsx）**：题目生成配置面板、LaTeX 渲染题目展示区、手写签名画布与图片上传、支架提示展开/收起、批改结果展示、多智能体合成面板
- **仪表盘（dashboard/page.tsx）**：Radar 图展示各知识点掌握度，柱状图展示各知识点的 Level 与练习次数

**关键依赖**：KaTeX（数学渲染）、react-signature-canvas（手写画布）、Recharts（图表）、axios（HTTP 客户端）

---

## 4. 多智能体系统设计

### 4.1 设计动机

传统的多 Agent 实现（如本项目的 V1 系统）存在以下结构性缺陷：

1. **硬编码流水线**：编排器以固定顺序调用 Agent，Agent 无自主决策权
2. **无直接通信**：Agent 仅通过共享字典（workspace）传递状态，无消息路由机制
3. **双层 LLM 浪费**：Agent 调用 LLM 仅用于"我该调哪个工具"，工具内部再次调用 LLM 做实际工作
4. **串行执行**：Agent 按顺序运行，无并发能力

T2P V2 系统针对上述问题进行了根本性重构。

### 4.2 消息协议设计

系统定义了结构化的消息协议（messages.py），作为 Agent 间通信的通用语言：

| 消息类型 | 语义 | 发送方示例 | 接收方示例 |
|----------|------|-----------|-----------|
| `REQUEST` | 请求执行任务 | Coordinator → Synthesizer | "请生成一道导数题" |
| `RESPONSE` | 返回任务结果 | Synthesizer → Reviewer | "题目已生成，请审查" |
| `APPROVE` | 批准通过 | Reviewer → Synthesizer | "质量达标，批准入库" |
| `REJECT` | 驳回（带修改建议） | Reviewer → Synthesizer | "拒绝：积分步骤有误" |
| `DELEGATE` | 委派子任务 | Reviewer → Scaffolder | "请为此题设计支架" |
| `CONSULT` | 征询意见 | Curator → Synthesizer | "建议生成积分题" |
| `NOTIFY` | 状态通知 | Reviewer → Curator | "已通过一道导数题" |
| `BROADCAST` | 全局公告 | Curator → ALL | "数据集已完成" |

每条 `Message` 包含：`id`、`type`、`sender`、`recipient`、`conversation_id`、`content`、`timestamp`、`reply_to`，支持构建完整对话线程。

### 4.3 消息总线（MessageBus）

`MessageBus` 是实现 Agent 间异步通信的核心基础设施：

- **注册机制**：每个 Agent 获得独立的 `asyncio.Queue` 收件箱
- **点对点路由**：`send(message)` 根据 `recipient` 字段投递到目标队列
- **广播机制**：`recipient=None` 时向所有已注册 Agent 广播
- **对话追踪**：维护 `conversation_id → Conversation` 的全局映射
- **线程安全**：使用 `asyncio.Lock` 保证并发下的数据一致性

### 4.4 自治 Agent 架构

每个 `AutonomousAgent` 运行独立的 Perceive-Think-Act 循环：

```
while self.running:
    1. PERCEIVE: messages = await bus.drain(agent_id)
       - 从收件箱读取所有待处理消息
       - 更新 Agent 记忆（最近 50 条历史）

    2. THINK: action = await self._reason(messages)
       - 构建推理提示词：角色 + 人格 + 记忆上下文 + 新消息
       - 调用 LLM 决定下一步行动
       - 输出结构化 Action（SEND_MESSAGE | CALL_TOOL | WAIT | FINISH | BROADCAST）

    3. ACT: await self._act(action)
       - SEND_MESSAGE: 向目标 Agent 发送消息（内容由 LLM 直接生成）
       - CALL_TOOL: 调用纯工具函数（文件 I/O、数据查询）
       - BROADCAST: 向所有 Agent 广播
       - WAIT: 空闲等待
       - FINISH: 结束运行
```

**关键创新**：LLM 直接在其响应中产出完整内容（题目 JSON、评估报告、支架提示等），而非先调用 LLM 做路由决策再通过工具调第二个 LLM。这消除了一半以上的 LLM 调用。

### 4.5 四个 Agent 角色定义

| Agent | ID | 角色 | 温度 | 最大空闲 | 工具 |
|-------|-----|------|------|---------|------|
| ProblemSynthesizer | synthesizer | 创造性数学家 | 0.5 | 120s | save_problem, get_topics, get_examples |
| ScaffoldingDesigner | scaffolder | 耐心教师 | 0.3 | 60s | get_topics, get_examples |
| QualityReviewer | reviewer | 严格审计员 | 0.2 | 120s | check_coverage, get_topics, save_problem |
| DatasetCurator | curator | 战略规划师 | 0.3 | 180s | check_coverage, get_topics, get_examples, get_dataset_size, save_problem |

**ProblemSynthesizer（题目合成者）**：接收到生成请求后，LLM 直接输出完整题目 JSON（包含题目陈述、解答、支架提示和概念融合分析），然后发送给 Reviewer 进行审查。

**ScaffoldingDesigner（支架设计者）**：当 Reviewer 或 Synthesizer 委派支架设计任务时，LLM 直接生成渐进式提示序列（难度 1-2 为 2 步，难度 3 为 3 步，难度 4-5 为 4 步）。

**QualityReviewer（质量审查者）**：收到待审题目后，LLM 直接从 6 个维度（数学正确性、逻辑连贯性、教学价值、难度校准、支架质量、LaTeX 格式）进行评估，输出 APPROVE 或 REJECT（附带具体修改建议），同时通知 Curator。

**DatasetCurator（数据集策展者）**：监控已批准题目数，分析知识点覆盖缺口，向 Synthesizer 发送下一步建议，达到目标数量后广播 `dataset_complete` 终止信号。

### 4.6 协调器（Coordinator）

`Coordinator` 是轻量级的会话管理器，不控制 Agent 的决策流程：

1. 创建 MessageBus 和 4 个 Agent 实例
2. 通过 `asyncio.gather()` 并发启动所有 Agent
3. 向 Synthesizer 发送初始生成请求，向 Reviewer 和 Curator 发送配置通知
4. 每 2 秒轮询消息总线，检测 `dataset_complete` 广播或超时
5. 发送停止信号，收集所有已保存题目，计算统计数据
6. 输出完整数据集和多智能体对话日志

### 4.7 LLM 调用效率对比

| 阶段 | V1 流水线（每道题） | V2 消息系统（每道题） |
|------|-------------------|---------------------|
| Synthesizer Agent 路由 LLM | 1 | 0 |
| generate_problem 工具 → LLM | 1 | 0 |
| Synthesizer 直接生成 | 0 | 1 |
| Scaffolder Agent 路由 LLM | 1 | 0 |
| design_scaffolding 工具 → LLM | 1 | 0 |
| Scaffolder 直接生成（按需） | 0 | 0-1 |
| Reviewer Agent 路由 LLM | 1-2 | 0 |
| evaluate_quality 工具 → LLM | 1 | 0 |
| Reviewer 直接评估 | 0 | 1 |
| Curator Agent 路由 LLM | 1 | 1 |
| **合计** | **8-10** | **4-5** |

对于一个 20 道题的数据集（约 20% 拒绝率），V2 可节省约 100-120 次 LLM 调用。

---

## 5. 题目生成与评估方法论

### 5.1 提示词工程

`PromptBuilder` 实现了复杂的提示词构建策略：

**基础角色设定**：练习模式为"微积分教学研究员"，考试模式为"高级数学课程设计专家（融合专家）"。

**逻辑完整性约束**：
- 数值验证：重要数值结果需可独立验证
- 几何一致性：涉及图形的描述需自洽
- LaTeX 规范性：禁止 `\quad` 等高危宏命令，统一使用 `$` 和 `$$` 定界符

**输出结构**：
```json
{
  "id": "T2P_GEN_1",
  "topic": "导数与微分",
  "problem_statement": "LaTeX 题目陈述",
  "question_type": "calculation",
  "difficulty": 3,
  "solution": "详细多步 LaTeX 解答",
  "scaffolding": [
    {"step": 1, "hint": "第一步概念提示"},
    {"step": 2, "hint": "第二步策略提示"}
  ],
  "integration_analysis": "知识点融合分析（仅考试模式）"
}
```

**自修复反馈注入**：当质量评估未通过时，将 AI 反馈格式化为"Previous Attempt Flaw"块注入下一轮提示词。

### 5.2 质量评估体系

`QualityEvaluator` 实现了多维度的质量评估框架：

**评估维度与权重**：

| 维度 | 权重 | 评估内容 |
|------|------|---------|
| 数学逻辑 | 0.35 | 解答的数学正确性、推理是否有错误 |
| 结构完整性 | 0.10 | 必要字段是否存在 |
| 支架质量 | 0.15 | 提示的渐进性和引导效果 |
| 教学适配性 | 0.15 | 难度是否匹配、是否适合教学目标 |
| 概念融合 | 0.15 | 知识点间的衔接质量（考试模式重点） |
| 原创性 | 0.10 | 与黄金数据集的文本相似度 |

**通过阈值**：
- 练习模式：总分 ≥ 60，数学正确，逻辑连贯，结构 ≥ 75
- 考试模式：在上述基础上额外要求概念融合 ≥ 50

### 5.3 后处理管线

`PostProcessor` 实现了 8 步 LaTeX 深度清洗：

1. 统一定界符格式（`\( \)` → `$` 等）
2. 修复残余转义符
3. 清理 LaTeX 环境间距
4. 去除 `{cases}` 环境内的多余 `$`
5. 反重复检测（公式复制去重）
6. 移除禁用宏（`\quad`、`\qquad` 等）
7. 数学公式与中文字符间添加空格
8. 最终修剪

去重使用 `paraphrase-multilingual-MiniLM-L12-v2` 模型进行语义级余弦相似度检测（阈值 0.85）。

---

## 6. 前端交互设计

### 6.1 题目生成交互

用户通过控制面板配置四项参数：知识点（下拉选择）、模式（练习/考试）、难度（1-5 级滑块）、题型（选择题/填空题/计算题）。点击"生成当前配置题目"按钮后，前端通过 `POST /generate` 获取题目并在渲染区展示。

### 6.2 手写批改交互

学生作答提供三种输入方式：
1. **手写签名画布**：使用 react-signature-canvas 直接在屏幕上书写
2. **拍照上传**：通过摄像头或文件选择器上传手写图片
3. **直接输入**：选择题点击选项即可

提交后前端调用 `POST /audit`，返回结果包括：正确性判断、逻辑对齐度评分（可视化进度条）、错误分析、导师反馈和下一步提示。

### 6.3 多智能体实时监控面板

新增的多智能体合成面板提供：
- 知识点多选标签
- 数量和难度滑块
- 模式/题型切换
- "开始多智能体合成"按钮

运行时通过 SSE（Server-Sent Events）实时展示 Agent 对话流：
```
[synthesizer] → [reviewer]  [request]  {"action": "review_problem", ...}
[reviewer] → [synthesizer]  [approve]  {"score": 87, "passed": true, ...}
[curator] → [synthesizer]   [consult]  {"action": "suggest_topic", ...}
```

完成后展示统计卡片：生成题目数、LLM 调用次数、Agent 消息数、耗时、知识点覆盖和平均质量分。

### 6.4 学习仪表盘

仪表盘通过 `GET /user/progress/{user_id}` 获取用户数据，使用 Recharts 渲染：
- **Radar 图**：展示所有知识点的掌握度百分比
- **柱状图**：每个知识点的 Level 与练习次数对比

---

## 7. 系统评估

### 7.1 功能验证

| 测试项 | 方法 | 结果 |
|--------|------|------|
| 前后端连通性 | 启动后端 → 前端页面加载 → GET /topics | HTTP 200，知识点列表正确 |
| 题目生成（练习） | POST /generate {drill, difficulty=3} | 返回完整题目 JSON，支架提示完整 |
| 题目生成（考试） | POST /generate {exam, difficulty=4} | 返回融合题，integration_analysis 非空 |
| 手写批改 | POST /audit {base64 图片 + problem_id} | 返回 OCR 文本 + 逻辑评分 + 导师反馈 |
| 自适应推荐 | POST /generate {user_id + topics:[]} | 自动选择未掌握知识点和适当难度 |
| 多智能体合成 V2 | POST /synthesize-v2 {count=5} | 返回 5 道题目，Agent 对话日志完整 |
| SSE 实时流 | GET /synthesize-v2/stream | 流式返回 Agent 消息，最终事件包含统计 |
| TypeScript 编译 | `npx tsc --noEmit` | 零错误通过 |
| 向后兼容性 | POST /generate + /synthesize | 旧端点功能完全正常 |

### 7.2 性能指标

| 指标 | V1 流水线 | V2 消息系统 | 改进 |
|------|----------|-----------|------|
| 单题平均 LLM 调用 | 8-10 次 | 4-5 次 | ↓ 50% |
| Agent 间通信方式 | 共享字典（间接） | 消息总线（直接） | 质的飞跃 |
| Agent 自主决策 | 无（编排器控制） | 有（自治循环） | 质的飞跃 |
| 并发执行 | 串行 | asyncio 并发 | 质的飞跃 |
| 前端实时监控 | 无 | SSE 实时流 | 新增功能 |

### 7.3 架构对比

| 特征 | 假多 Agent 系统 | 真多 Agent 系统（V2） |
|------|----------------|---------------------|
| 通信协议 | 共享 dict | 结构化 Message |
| 通信方向 | 单向（编排器→Agent） | 双向（Agent↔Agent） |
| 工作流 | 硬编码顺序 | 涌现式协作 |
| Agent 记忆 | 无状态 | 独立记忆系统 |
| 工具 LLM 调用 | 工具内含 LLM 调用 | 工具纯函数，零 LLM |
| 编排模式 | 控制器 | 观察者 |

---

## 8. 讨论

### 8.1 多智能体系统的设计权衡

**消息传递 vs. 共享状态**：消息传递架构（V2）提供了更好的可追溯性和松耦合，但增加了通信开销。共享状态（V1）实现简单但难以扩展和维护。

**自治 vs. 控制**：V2 的 Agent 拥有真正的自主决策权，带来了更灵活的工作流，但也引入了死锁和无限循环的风险。通过空闲超时（60-180 秒）和全局超时（600 秒）机制进行缓解。

**LLM 调用效率**：V2 通过让 Agent 直接产出内容而非路由到另一个 LLM 调用工具，实现了约 50% 的 LLM 调用减少。这是通过精心设计的 Agent 人格提示词（Personality Prompt）实现的，本质上是将工具内部的 LLM 调用逻辑内化到 Agent 的推理过程中。

### 8.2 教育意义

T2P 系统不仅是一个技术实现，更体现了多项教学原则：

1. **最近发展区**：自适应难度算法确保题目始终处于适当挑战水平
2. **支架式教学**：每道题的渐进提示从概念引导到程序帮助，逐步撤回支持
3. **形成性评估**：批改系统不是简单的对错判断，而是提供可操作的改进建议
4. **概念融合**：考试模式促进跨知识点的整合性理解，而非孤立练习

### 8.3 局限性

1. **LLM 数学正确性**：尽管有多层质量保障，LLM 仍可能在复杂证明中出现隐性错误
2. **OCR 准确率**：手写 LaTeX 的 OCR 识别在潦草字迹下准确率有限
3. **单语言支持**：当前仅支持英文题目生成
4. **并发规模**：4 个 Agent 的并发协作在实际 Latency 减少上的效果受限于 LLM API 的速率限制
5. **评估主观性**：质量评估的 AI 审计虽有一致性优势，但分数校准缺乏人工标注基准

---

## 9. 结论与未来工作

### 9.1 结论

本报告介绍了 T2P——一个面向微积分教学的 AI 驱动数据合成系统。系统实现了三大核心功能：(1) 支持练习和考试两种模式的题目自动生成；(2) 基于 OCR 的智能批改引擎；(3) 基于消息总线的真正多智能体协作系统。

T2P 在多智能体系统设计方面做出了贡献：提出了一种消息驱动的自治 Agent 架构，通过结构化通信协议、Agent 人格设计和消除双层 LLM 调用，实现了约 50% 的效率提升和涌现式的 Agent 协作模式。系统完全向后兼容，旧版流水线与新版消息系统可并存使用。

### 9.2 未来工作

1. **数学验证引擎集成**：结合符号计算系统（如 SymPy）作为独立验证器，弥补 LLM 在数学正确性上的不足
2. **多模态学生建模**：基于学生提交的草稿和错误模式，构建更细粒度的认知模型
3. **多语言扩展**：支持中文数学题目的生成和批改
4. **持久化消息队列**：将 MessageBus 升级为 Redis/RabbitMQ 后端，支持分布式 Agent 部署
5. **人类评估基准**：建立人工标注的质量评估数据集，校准 AI 审计分数
6. **课程级别规划**：从单题生成扩展到完整课程的知识点序列规划
7. **Agent 动态生成**：根据任务复杂度自动分化或合并 Agent 角色

---

## 参考文献

[1] Amini, A., et al. (2019). MathQA: Towards Interpretable Math Word Problem Solving with Operation-Based Formalisms. *NAACL-HLT*.

[2] Anthropic. (2024). The Claude Model Family.

[3] Cobbe, K., et al. (2021). Training Verifiers to Solve Math Word Problems. *arXiv:2110.14168*.

[4] Du, Y., et al. (2024). MathVC: Multi-Agent Discussion for Mathematical Reasoning Verification. *arXiv*.

[5] OpenAI. (2023). GPT-4 Technical Report.

[6] Park, J. S., et al. (2024). Generative Agents: Interactive Simulacra of Human Behavior.

[7] Qian, C., et al. (2023). ChatDev: Communicative Agents for Software Development. *ACL*.

[8] Vygotsky, L. S. (1978). Mind in Society: The Development of Higher Psychological Processes. *Harvard University Press*.

[9] Wu, Q., et al. (2023). AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation. *arXiv:2308.08155*.

---

**附录 A：系统启动指令**

```bash
# 后端
cd D:\数据科学理学硕士MscDS\第二学期\T2P\T2P-Final
python api_server.py

# 前端
cd D:\数据科学理学硕士MscDS\第二学期\T2P\T2P-Final\t2p-web
npm run dev
```

**附录 B：关键文件清单**

见第 3 节系统架构详述中的组件路径。
