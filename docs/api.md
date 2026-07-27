# 照片转奶龙卡通系统 — 前端接口文档

> 后端：FastAPI · Base URL：`http://<host>:8000` · 业务前缀：`/api/v1`
> 在线调试（Swagger）：`http://<host>:8000/docs`
> 版本：v0.1.0（契约已冻结）

---

## 1. 通用约定

### 1.1 URL 规则

- 接口：`{BASE}/api/v1/...`
- 图片/视频资源：响应中的 `url` 均为**相对路径**，前端拼 base 访问：
  - 生成产物：`/static/...`（如 `/static/outputs/avatars/xxx.png`）
  - 素材库：`/assets/...`（如 `/assets/nailong/glasses/round.png`）

### 1.2 资源引用对象 `ImageRef`

多数接口用 `ImageRef` 表示一张图：

```json
{ "id": "a1b2c3d4e5f6", "url": "/static/outputs/avatars/a1b2c3d4e5f6.png" }
```

### 1.3 错误格式

- 成功：HTTP 200，body 即业务数据（**无外层包装**，直接是各接口的响应模型）。
- 失败：HTTP 4xx/5xx，body 为 FastAPI 标准错误：

```json
{ "detail": "形象不存在: xxx（先 analyze 或 compose）" }
```

常见错误码：

| 状态码 | 场景 |
|---|---|
| 400 | 空文件 / 不支持的图片类型 / 图片超过 20MB |
| 404 | avatar_id / background_id / job_id 不存在 |
| 422 | 请求体字段校验失败（枚举值非法、缺字段等） |

### 1.4 上传限制

- 图片类型：`image/jpeg` / `image/png` / `image/webp` / `image/bmp`
- 大小：≤ 20MB

### 1.5 业务流程总览

```
照片 ──► /avatars/analyze ──► avatar_id + features（五官特征JSON）
                                  │
                                  ▼
                        /avatars/compose ──► 奶龙形象PNG
                                  │
场景照片 ──► /backgrounds/cartoonize ──► background_id + 场景标签
                                  │
                                  ▼
                        /games/package ──► 游戏素材包（前端引擎消费）
                                  │
多张照片 ──► /uploads ──► /videos/generate ──► 轮询 /videos/{job_id} ──► 成片mp4
```

---

## 2. 系统

### GET `/api/health` — 健康检查

```json
{
  "status": "ok",
  "zhipu_key_configured": true,
  "models": { "vlm": "glm-4v-flash", "llm": "glm-4-flash", "image_gen": "cogview-3-flash" }
}
```

---

## 3. 上传

### POST `/api/v1/uploads` — 上传照片

`multipart/form-data`，字段 `file`。

**响应 `UploadResponse`**

| 字段 | 类型 | 说明 |
|---|---|---|
| photo_id | string | 照片 ID，视频生成等接口用它引用 |
| url | string | 图片访问 URL |
| width / height | int | 像素尺寸 |

```json
{ "photo_id": "3f9a1c2b4d5e", "url": "/static/uploads/3f9a1c2b4d5e.jpg", "width": 1080, "height": 1440 }
```

> 注：视频生成走 `/uploads`；而形象分析、背景卡通化各自直接收文件，不需先走本接口。

---

## 4. 奶龙形象

### 4.1 POST `/api/v1/avatars/analyze` — 上传人脸照片，输出结构化五官特征

`multipart/form-data`，字段 `file`。内部：MediaPipe 人脸检测 + GLM-4V 特征提取（失败自动降级默认特征，接口不会挂）。

**响应 `AvatarAnalyzeResponse`**

| 字段 | 类型 | 说明 |
|---|---|---|
| avatar_id | string | **形象 ID，后续 compose/outfit/游戏/视频都用它** |
| face_crop | ImageRef | 裁剪出的人脸图 |
| features | [FaceFeatures](#411-facefeatures核心契约) | 结构化五官特征 |
| signals | MediapipeSignals | 本地量化信号（报告亮点，前端可不展示） |

`MediapipeSignals`：

| 字段 | 类型 | 说明 |
|---|---|---|
| face_detected | bool | 是否检测到人脸（false 时 face_crop 为整图缩放） |
| smile_score | float 0~1 | 微笑强度 |
| eye_open_ratio | float 0~1 | 眼睛睁开程度 |
| face_width_height_ratio | float | 脸宽/脸长 |

```json
{
  "avatar_id": "9c8b7a6f5e4d",
  "face_crop": { "id": "9c8b7a6f5e4d", "url": "/static/outputs/faces/9c8b7a6f5e4d.jpg" },
  "features": {
    "gender_style": "girl", "age_group": "young_adult", "face_shape": "oval",
    "hair_style": "ponytail", "hair_color": "black", "glasses": "none",
    "expression": "happy", "skin_tone": "light", "accessories": [],
    "outfit": "none", "notes": "扎马尾的年轻女生，笑得很开心"
  },
  "signals": { "face_detected": true, "smile_score": 0.812, "eye_open_ratio": 0.95, "face_width_height_ratio": 0.78 }
}
```

### 4.2 POST `/api/v1/avatars/compose` — 特征 JSON → 奶龙形象 PNG（纸娃娃合成）

**请求 `ComposeRequest`**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| features | FaceFeatures | ✅ | 可直接回传 analyze 的 features（可改） |
| avatar_id | string? | | 传 analyze 返回的 id 则形象图挂在同一记录下 |
| with_fancy | bool | | 额外生成 CogView 精致手绘版彩蛋（慢 10~30s，失败自动降级为 null） |

**响应 `AvatarComposeResponse`**

| 字段 | 类型 | 说明 |
|---|---|---|
| avatar_id | string | 形象 ID |
| image | ImageRef | 合成的奶龙形象 PNG（透明底） |
| layers | string[] | 实际使用的图层 asset 路径（调试/换装界面用） |
| fancy_image | ImageRef? | 精致手绘版（with_fancy=true 且成功时返回） |

### 4.3 PUT `/api/v1/avatars/{avatar_id}/outfit` — 换装 / 换发型 / 换表情

**只传要更换的槽位**，未传的保持原样。请求体 `OutfitChangeRequest`（全部可选）：

| 字段 | 枚举 |
|---|---|
| hair_style | HairStyle |
| hair_color | HairColor |
| glasses | Glasses |
| outfit | Outfit |
| accessory | Accessory（单槽，传 `none` 表示摘除） |
| expression | Expression |

**响应 `OutfitChangeResponse`**

| 字段 | 类型 | 说明 |
|---|---|---|
| avatar_id | string | |
| image | ImageRef | 换装后的形象 PNG |
| layers | string[] | |
| features | FaceFeatures | 换装合并后的完整特征（前端可缓存） |

404：形象不存在（需先 analyze 或 compose）。

### 4.4 GET `/api/v1/assets/wardrobe` — 可换装部件清单（换装界面数据源）

**响应 `WardrobeResponse`**：`categories[]`，每项：

| 字段 | 类型 | 说明 |
|---|---|---|
| slot | string | 槽位：`hair_style` / `hair_color` / `glasses` / `outfit` / `accessory` / `expression` |
| items | WardrobeItem[] | `{ id, name, preview }`：id 即枚举值，name 为中文展示名，preview 为部件预览图（部分槽位可能为 null） |

### 4.1.1 FaceFeatures（核心契约）

所有字段均为**枚举**，与素材库图层一一对应，前端表单/换装请直接用枚举值：

| 字段 | 枚举类型 | 说明 |
|---|---|---|
| gender_style | GenderStyle | 形象风格倾向（非真实性别判定） |
| age_group | AgeGroup | 年龄段 |
| face_shape | FaceShape | 脸型 |
| hair_style | HairStyle | 发型 |
| hair_color | HairColor | 发色 |
| glasses | Glasses | 眼镜，默认 `none` |
| expression | Expression | 表情，默认 `happy` |
| skin_tone | SkinTone | 肤色，默认 `light` |
| accessories | Accessory[] | 配饰列表 |
| outfit | Outfit | 穿搭槽位（VLM 不预测，换装时设置），默认 `none` |
| notes | string | VLM 自由文本补充（不进规则，供展示） |

### 枚举值总表

| 枚举 | 取值（中文名） |
|---|---|
| GenderStyle | `boy` 男 · `girl` 女 · `neutral` 中性 |
| AgeGroup | `child` 儿童 · `teen` 少年 · `young_adult` 青年 · `middle_aged` 中年 · `senior` 老年 |
| FaceShape | `round` 圆脸 · `oval` 鹅蛋脸 · `square` 方脸 · `long` 长脸 · `heart` 心形脸 |
| HairStyle | `bald` 光头 · `buzz` 板寸 · `short` 短发 · `medium` 及肩发 · `long_straight` 黑长直 · `long_curly` 长卷发 · `ponytail` 马尾 · `twin_tails` 双马尾 · `bun` 丸子头 |
| HairColor | `black` 黑色 · `brown` 棕色 · `blonde` 金色 · `gray_white` 灰白 · `colorful` 彩色 |
| Glasses | `none` 无 · `round` 圆框 · `square` 方框 · `sunglasses` 墨镜 |
| Expression | `happy` 开心 · `neutral` 平静 · `surprised` 惊讶 · `cool` 酷 · `shy` 害羞 |
| SkinTone | `fair` · `light` · `medium` · `tan` · `dark` |
| Outfit | `none` 奶龙本体 · `tshirt` T恤 · `hoodie` 卫衣 · `dress` 连衣裙 · `suit` 西装 · `cape` 披风 |
| Accessory | `none` 无 · `hat` 帽子 · `headband` 发箍 · `bow` 蝴蝶结 · `scarf` 围巾 |

---

## 5. 背景卡通化

### POST `/api/v1/backgrounds/cartoonize` — 照片 → 卡通背景 + 场景标签

`multipart/form-data`：

| 字段 | 类型 | 说明 |
|---|---|---|
| file | 文件 | 场景照片 |
| style | string | 画风，见下表，默认 `paprika` |

**CartoonStyle 枚举**（AnimeGANv2 权重）：

| 值 | 说明 |
|---|---|
| `paprika` | 今敏《红辣椒》风：色彩浓郁，风景人像皆宜 |
| `face_paint_v2` | 肖像彩绘 v2：柔和明亮，人像更好看 |
| `face_paint_v1` | 肖像彩绘 v1：笔触更重 |
| `celeba_distill` | 人像精简风：轻量快速 |

**响应 `CartoonizeResponse`**

| 字段 | 类型 | 说明 |
|---|---|---|
| background_id | string | 背景 ID（游戏素材包用它引用） |
| image | ImageRef | 卡通化后的背景图 |
| scene | SceneTags | GLM-4V 场景标签（驱动游戏主题） |

`SceneTags`：

| 字段 | 类型 | 说明 |
|---|---|---|
| scene_type | enum | `indoor` / `street` / `forest` / `seaside` / `mountain` / `campus` / `sky` / `other` |
| indoor | bool | 是否室内 |
| time_of_day | enum | `day` / `dusk` / `night` |
| main_elements | string[] | 画面主要元素，如 `["教学楼","梧桐树"]` |
| color_tone | string | 主色调，如 `暖黄` |
| suggested_theme | string | 建议游戏主题名，如 `森林大冒险` |
| obstacle_hints | string[] | 建议障碍物元素 |

---

## 6. 游戏

### 6.1 POST `/api/v1/games/package` — 形象 + 背景 + 难度 → 游戏素材包 + 关卡配置

**请求 `GamePackageRequest`**

| 字段 | 类型 | 默认 | 约束 |
|---|---|---|---|
| avatar_id | string | — | 必填，需已 compose |
| background_id | string | — | 必填，需已 cartoonize |
| difficulty | `easy`/`normal`/`hard` | `normal` | |
| duration_sec | int | 60 | 30~300，一局时长 |
| heart_count | int | 3 | 1~9，生命数 |
| coin_count | int | 20 | 0~200，金币投放数 |

404：形象/背景不存在。

**响应 `GamePackageResponse`**

| 字段 | 类型 | 说明 |
|---|---|---|
| game_id | string | |
| background | ImageRef | 背景图 |
| character | CharacterSprite | `{ run_frames: ImageRef[], jump_frame: ImageRef }` 角色帧序列 |
| obstacles | SpriteInfo[] | 障碍物精灵 `{ name, image, width, height }`（width/height 供碰撞盒参考） |
| coin_sprite | SpriteInfo | 金币精灵 |
| config | GameConfig | 关卡配置，**前端游戏引擎直接消费** |

`GameConfig`（物理/数值参数）：

| 字段 | 类型 | 说明 |
|---|---|---|
| difficulty / duration_sec / heart_count / coin_count | — | 回显请求值 |
| gravity | float | 重力加速度，像素/秒² |
| move_speed | float | 角色水平移动速度，像素/秒 |
| jump_velocity | float | 起跳初速度，像素/秒 |
| obstacle_speed | float | 障碍物移动速度，像素/秒 |
| obstacle_interval_min / max | float | 障碍物刷新间隔区间（秒） |

### 6.2 POST `/api/v1/games/scores` — 提交分数（免登录）

| 字段 | 类型 | 约束 |
|---|---|---|
| nickname | string | 1~16 字符 |
| score | int | ≥ 0 |
| difficulty | enum | 默认 `normal` |
| game_id | string? | 可选 |

**响应 `LeaderboardEntry`**：`{ rank, nickname, score, difficulty, created_at }`
（rank 为本次提交在同难度下的即时名次）

### 6.3 GET `/api/v1/games/leaderboard` — 排行榜

Query 参数：`difficulty`（默认 `normal`）、`limit`（默认 20，1~100）。

**响应 `LeaderboardResponse`**：`entries[]` 同 `LeaderboardEntry`，按分数降序、同分按时间先者在前。

---

## 7. 动画视频

### 7.1 POST `/api/v1/videos/generate` — 提交视频生成任务（异步）

照片需先走 `POST /uploads` 拿到 `photo_id`。

**请求 `VideoGenerateRequest`**

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| photo_ids | string[] | — | 1~10 张，按顺序串成故事 |
| avatar_id | string? | null | 提供则奶龙形象出镜 |
| theme | string | `奶龙历险记` | ≤50 字，影响剧本风格 |
| with_narration | bool | true | 是否生成 edge-tts 旁白配音 |
| transition | `fade`/`slide`/`none` | `fade` | 转场 |
| sec_per_scene | float | 3.0 | 1.5~10，默认每幕时长 |

404：任一 photo_id 不存在。

**响应 `VideoJobResponse`**（提交时 status=`pending`）→ 用 `job_id` 轮询。

### 7.2 GET `/api/v1/videos/{job_id}` — 查询任务状态/结果

**响应 `VideoJobResponse`**

| 字段 | 类型 | 说明 |
|---|---|---|
| job_id | string | |
| status | `pending`/`processing`/`done`/`failed` | |
| progress | float 0~1 | |
| stage | string | 当前阶段：排队中/卡通化/照片描述/剧本生成/配音/渲染/完成 |
| storyboard | Scene[]? | 分镜剧本，生成后可见，前端可预览 |
| video | ImageRef? | 成片 mp4，status=done 时返回 |
| error | string? | 失败原因 |

`Scene`（分镜一幕）：

| 字段 | 类型 | 说明 |
|---|---|---|
| photo_id | string | 对应的照片 |
| narration | string | 旁白文案，1~2 句，奶龙口吻 |
| camera_motion | enum | `zoom_in`/`zoom_out`/`pan_left`/`pan_right`/`static` |
| avatar_action | enum | `walk_across` 走过画面 / `bounce` 原地弹跳 / `peek_corner` 角落探出 / `none` |
| duration_sec | float | 1.5~10 |

**前端轮询建议**：间隔 3~5s；`status=done` 取 `video.url`，`failed` 展示 `error`。总超时建议 ≥ 10 分钟（取决于照片数与是否配音）。

---

## 8. 附：完整调用示例（伪代码）

```js
// 1. 形象
const fd = new FormData(); fd.append("file", portraitFile);
const { avatar_id, features } = await post("/api/v1/avatars/analyze", fd);
const avatar = await post("/api/v1/avatars/compose", { features, avatar_id });

// 2. 换装
await put(`/api/v1/avatars/${avatar_id}/outfit`, { outfit: "cape", accessory: "bow" });

// 3. 背景
const bf = new FormData(); bf.append("file", sceneFile); bf.append("style", "paprika");
const bg = await post("/api/v1/backgrounds/cartoonize", bf);

// 4. 游戏
const pack = await post("/api/v1/games/package", {
  avatar_id, background_id: bg.background_id, difficulty: "normal",
});
// pack.config / pack.character / pack.obstacles → 交给游戏引擎

// 5. 视频（异步）
const up = await post("/api/v1/uploads", photoFormData);       // 每张一次
const job = await post("/api/v1/videos/generate", {
  photo_ids: [up.photo_id], avatar_id, theme: "奶龙历险记",
});
// 轮询 GET /api/v1/videos/{job.job_id} 直到 status === "done"
```
