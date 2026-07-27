# 照片转奶龙卡通系统 —— 后端实现方案

> 角色分工：后端（调用大模型 API + 图像处理）
> 技术栈：Python 3.10 + FastAPI REST API
> 硬件：本地 8GB 显存 GPU
> 预算：0 元（免费 API + 轻量本地模型）

---

## 一、模型选型（已核实免费状态）

### 免费 API（主力，官方文档确认"完全免费"，非新用户额度）

| 模型 | 用途 | 官方原文 |
|---|---|---|
| **GLM-4V-Flash** | 图像理解：五官特征描述、场景分析、照片多维度描述 | "智谱推出的首个**完全免费**的图像理解模型" |
| **GLM-4-Flash** | 文本生成：动画剧本、游戏配置、prompt 扩写 | 平台免费模型（同系列） |
| **CogView-3-Flash** | 文生图（可选：精致版奶龙形象、素材生成） | "智谱推出的**免费**图像生成模型" |

- 文档来源：https://docs.bigmodel.cn/cn/guide/models/free/glm-4v-flash 、https://docs.bigmodel.cn/cn/guide/models/free/cogview-3-flash
- 这些是**平台级免费模型**（2024 年推出至今一直免费），不是新用户赠送额度。注意两点：
  1. 有速率/并发限制（注册后在控制台"速率限制"页可见），代码里必须做限流 + 指数退避重试。

### 各环节由谁来做（"图片生成是 GLM 做的吗？"）

| 环节 | 谁来做 | 方式 |
|---|---|---|
| 看图理解（五官特征/场景分析/照片描述） | GLM-4V-Flash | 免费 API |
| 写动画剧本/游戏配置/prompt 扩写 | GLM-4-Flash | 免费 API |
| 文生图（开发期一次性做素材库、可选"精致版"形象彩蛋） | CogView-3-Flash | 免费 API，不进运行时主流程 |
| 背景卡通化 | AnimeGANv2 | **本地**，不联网 |
| 奶龙形象合成 + 换装 | Pillow 纸娃娃图层合成 | **本地**，毫秒级 |
| 人脸关键点/表情量化 | MediaPipe | 本地 CPU |

即：**GLM 系只负责"理解图"和"写字"；真正的图像产出（卡通化、形象合成）都在本地做**。
CogView 文生图仅用于开发期制作素材和可选彩蛋，演示时生图不依赖网络。

### 本地模型（轻量，8GB 显存绰绰有余）

| 模型 | 用途 | 显存 |
|---|---|---|
| MediaPipe Face Landmarker | 人脸关键点（468 点）+ 52 维表情 blendshapes（笑容/眨眼等） | 0（CPU） |
| AnimeGANv2 | 背景卡通化（宫崎骏/新海诚画风，权重仅 ~15MB） | ~1GB，CPU 也能跑 |
| rembg (u2net) | 抠图，制作奶龙图层素材 | ~1GB（CPU 可） |
| edge-tts | 动画旁白配音（免费网络服务） | 0 |

同时驻留峰值 ~2GB，8GB 非常宽裕。

### API Key 获取与调用

1. https://www.bigmodel.cn/ 手机号注册
2. 控制台 → API keys（https://www.bigmodel.cn/usercenter/proj-mgmt/apikeys）→ 创建 key
3. 调用（OpenAI 兼容格式）：

```python
from openai import OpenAI
client = OpenAI(api_key="你的key", base_url="https://open.bigmodel.cn/api/paas/v4/")

# 图像理解（GLM-4V-Flash，图片传 base64 或公网 URL）
resp = client.chat.completions.create(
    model="glm-4v-flash",
    messages=[{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,...."}},
        {"type": "text", "text": "用 JSON 描述这张图片的场景……"},
    ]}],
)

# 文本生成（GLM-4-Flash）
resp = client.chat.completions.create(model="glm-4-flash", messages=[...])

# 文生图（CogView-3-Flash）
resp = client.images.generate(model="cogview-3-flash", prompt="奶龙风格……")
img_url = resp.data[0].url
```

---

## 二、项目结构

```
nailong-backend/
├── app/
│   ├── main.py                # FastAPI 入口：路由、CORS、静态目录挂载
│   ├── config.py              # pydantic-settings：API key、模型路径、device、开关
│   ├── api/v1/
│   │   ├── avatars.py         # 奶龙形象生成/换装
│   │   ├── backgrounds.py     # 背景卡通化
│   │   ├── games.py           # 游戏素材包/排行榜
│   │   └── videos.py          # 动画视频生成（异步任务）
│   ├── schemas/               # pydantic 模型（特征 JSON 的枚举定义，前后端契约，已冻结 v1）
│   ├── services/
│   │   ├── vlm.py             # GLM-4V-Flash 客户端（限流 + 重试 + JSON 解析）
│   │   ├── llm.py             # GLM-4-Flash 文本生成
│   │   ├── image_gen.py       # CogView-3-Flash 文生图（可选）
│   │   ├── face.py            # MediaPipe 关键点 + 表情 blendshapes
│   │   ├── avatar_compose.py  # Pillow 图层合成（纸娃娃系统）
│   │   ├── cartoon.py         # AnimeGANv2 + OpenCV 纯算法兜底
│   │   ├── game_packager.py   # 游戏素材包 + 关卡配置 JSON
│   │   └── video_renderer.py  # moviepy 渲染 + edge-tts 配音
│   ├── prompts/               # 分层 prompt 库（报告里 prompt engineering 的素材）
│   ├── assets/                # 奶龙图层素材库、游戏精灵、中文字体
│   └── storage/               # uploads/ outputs/（StaticFiles 挂载供前端取图）
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

依赖：`fastapi uvicorn python-multipart pydantic-settings openai mediapipe opencv-python-headless pillow numpy torch torchvision moviepy edge-tts rembg tenacity httpx tqdm`

---

## 三、三大功能的 pipeline 设计

### 功能 1：奶龙形象生成 + 换装

核心思路：**不做"端到端 AI 生图"，做"AI 识别 + 规则映射 + 图层合成"（纸娃娃系统）**。
原因：端到端生图无法保证奶龙 IP 一致性、无法支持确定性换装、效果不可控；纸娃娃系统 100% 本地、零成本、毫秒级、换装天然就是换图层（奇迹暖暖的玩法）。

```
照片 ──► MediaPipe 人脸关键点+表情(blendshapes) ──┐
     ──► GLM-4V-Flash 结构化属性描述(JSON) ────────┼─► 特征JSON
                                                  │
特征JSON ──► 规则引擎映射 ──► 图层选择(发型/眼镜/衣服/表情/肤色)
                        ──► Pillow 合成 ──► 奶龙形象 PNG(透明底)
换装请求 ──► 换图层重新合成（同一形象 ID 保留其他特征）
```

- **结构化属性 prompt**（prompt engineering 重点）：限定枚举值 + 只输出 JSON + few-shot，例如
  `{gender, age_group, face_shape, hair_style(黑长直/短卷发/马尾/光头…), hair_color, glasses(无/圆框/方框/墨镜), expression, skin_tone, accessories}`
- MediaPipe 的 blendshapes 提供可解释的量化特征（`mouthSmile`、`eyeBlink`…），报告里可作为"本地可解释特征 × VLM 语义特征融合"的亮点。
- **素材库 = 纸娃娃方案的前提，但不需要手绘**：基础奶龙身体（"根据照片生成形象"用）和换装部件（发型/眼镜/衣服/配饰，"二次改造"用）是**同一套图层素材库**的两类层，开发期用 CogView-3-Flash 一次性生成 + rembg 抠图 + 脚本切层即可（也可队友手绘补充）。**运行时合成完全本地、不调 API**。图层规范需尽早和前端对齐（锚点、尺寸、命名）。
- 若完全不做素材库，只能走纯文生图路线（特征 JSON → CogView 直接画）：每次生成的奶龙长得不一样、换装结果不可控、出图慢且可能不像奶龙 → 不作主路线，仅作"精致手绘版"彩蛋。

**接口：**
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/avatars/analyze` | 上传照片 → 特征 JSON + 人脸裁剪图 |
| POST | `/api/v1/avatars/compose` | 特征 JSON + 风格 → 奶龙形象 PNG |
| PUT | `/api/v1/avatars/{id}/outfit` | 换装/换发型/换表情 → 新 PNG |
| GET | `/api/v1/assets/wardrobe` | 可选部件清单（前端换装界面用） |

### 功能 2：背景卡通化 + 游戏素材包

```
照片 ──► AnimeGANv2 卡通化 ──► 游戏背景图
     ──► GLM-4V-Flash 场景分析(JSON: 室内/森林/街道/海边、白天/夜晚、主要元素、色调)
                            ──► 决定游戏主题皮肤 + 障碍物精灵组合
背景+形象+难度参数 ──► game_packager ──► 游戏素材包:
    { 背景URL, 角色精灵URL, 障碍物组合, 关卡配置JSON
      {gravity, speed, obstacle_density, coin_count, heart_count, duration, difficulty} }
```

- 游戏本体（跑酷/跳跃躲避）由前端用 HTML5 Canvas / Phaser 实现，**后端只负责素材 + 配置**，边界清晰。
- 角色跑跳帧：用 Pillow 对形象 PNG 做挤压/倾斜/翻转的简单仿射变换生成 2~3 帧，成本低效果好。
- OpenCV 经典卡通化（双边滤波 + 色彩量化 + 边缘叠加）作为 AnimeGAN 的零模型兜底。
- 排行榜（已确认做，极简免登录）：SQLite 存 `昵称+分数+难度`，满足组员方案里的排行榜需求，不引入用户系统。

**接口：**
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/backgrounds/cartoonize` | 照片 → 卡通背景 + 场景标签 JSON |
| POST | `/api/v1/games/package` | 形象+背景+难度 → 素材包 + 关卡配置 |
| GET | `/api/v1/games/assets/{name}` | 精灵/背景静态资源 |
| POST/GET | `/api/v1/games/scores` `/leaderboard` | 排行榜（免登录） |

### 功能 3：动画视频生成（异步任务）

```
N 张照片 ──► AnimeGANv2 逐张卡通化
        ──► GLM-4V-Flash 逐张多维度描述（与形象/场景分析 prompt 同源）
        ──► GLM-4-Flash 把 N 段描述串成"奶龙历险记"分镜剧本(JSON):
            每幕 {对应照片, 旁白文案, 运镜方式, 转场, 奶龙动作}
        ──► moviepy 渲染: Ken Burns 推拉摇移 + 交叉转场
            + 奶龙形象在场景中移动/弹跳 + 中文字幕
            + edge-tts 旁白配音 ──► mp4
```

- 长任务必须异步：`BackgroundTasks` + 内存/文件任务表，前端轮询进度。
- 需要 ffmpeg 和中文字体（思源黑体等免费可商用字体）。

**接口：**
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/videos/generate` | 照片列表+主题 → job_id |
| GET | `/api/v1/videos/{job_id}` | 状态/进度/mp4 地址 |

---

## 四、数据集批量标注（暂缓，不在当前后端范围）

课程要求为 2000 训练集 + 369 验证集生成多维度描述，由负责标注的队友推进，当前不做。
后端侧的 VLM 客户端（限流/重试/JSON 校验）写好后可直接复用成批量脚本，需要时再加。

---

## 五、建议排期

| 时间 | 内容 |
|---|---|
| D1–2 | 环境 + FastAPI 骨架 + **接口 schemas 冻结（mock 先行）** + 打通 GLM-4V-Flash |
| D3–6 | 人脸分析 + 纸娃娃合成 + 素材库制作（和前端对齐图层规范） |
| D5–7 | AnimeGANv2 背景卡通化 + 场景分析 + 游戏素材包 |
| D8–10 | 视频渲染 pipeline + 配音 |
| D11–12 | 前后端联调（CORS、静态资源、接口契约） |
| D13+ | 报告素材整理（prompt 对比实验、效果对比截图） |

## 六、风险与对策

| 风险 | 对策 |
|---|---|
| 免费 API 限流/故障 | 全局限流器 + 指数退避重试；演示素材预生成缓存 |
| 奶龙素材没人画 | CogView-3-Flash 生成 + rembg 抠图 + 脚本切层 |
| 演示现场断网 | 预生成演示素材缓存（形象/背景/视频各备一份） |
| 前端等接口 | 先冻结 schemas（mock 数据先行），并行开发 |
