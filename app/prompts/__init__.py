"""分层 prompt 库：所有发给大模型的 prompt 集中在这里。

设计要点（报告里 prompt engineering 章节的素材）：
1. 枚举值由 schemas 动态生成 —— prompt 约束与接口契约永远一致，不会漂移；
2. 限定输出格式为纯 JSON + 给出示例（few-shot）；
3. 角色设定 + 任务拆解 + 不确定时的兜底规则。
"""
from ..schemas.avatar import (
    Accessory, AgeGroup, Expression, FaceShape, GenderStyle, Glasses, HairColor, HairStyle,
    Outfit, SkinTone,
)
from ..schemas.background import SceneType, TimeOfDay
from ..schemas.video import AvatarAction, CameraMotion


def _options(enum_cls) -> str:
    return "/".join(e.value for e in enum_cls)


# ============ 第一层：人像特征分析（GLM-4V-Flash） ============

PORTRAIT_SYSTEM = "你是一个严谨的人像特征分析员，只输出 JSON，不输出任何其他文字。"

PORTRAIT_PROMPT = f"""分析这张人脸照片，提取卡通形象设计所需的特征。

要求：
1. 每个字段只能从给定的候选值中选择一个，禁止编造候选值以外的词；
2. 拿不准的字段选最接近的，不要留空；
3. accessories 是数组，没有明显配饰就输出 []；
4. notes 用一句中文自由描述（20 字以内），其余字段一律用英文候选值；
5. 只输出 JSON 对象，不要输出解释。

字段与候选值：
- gender_style: {_options(GenderStyle)}  （形象设计偏男性化/女性化/中性，不是性别鉴定）
- age_group: {_options(AgeGroup)}
- face_shape: {_options(FaceShape)}
- hair_style: {_options(HairStyle)}
- hair_color: {_options(HairColor)}
- glasses: {_options(Glasses)}
- expression: {_options(Expression)}
- skin_tone: {_options(SkinTone)}
- accessories: 数组，元素候选 {_options(Accessory)}
- notes: 自由文本

输出示例：
{{"gender_style":"girl","age_group":"young_adult","face_shape":"oval","hair_style":"ponytail","hair_color":"black","glasses":"none","expression":"happy","skin_tone":"light","accessories":[],"notes":"扎马尾的女生，笑得很开心"}}"""


# ============ 第二层：场景分析（GLM-4V-Flash，驱动游戏主题） ============

SCENE_SYSTEM = "你是一个游戏场景设计师，擅长把真实照片改造成游戏关卡，只输出 JSON。"

SCENE_PROMPT = f"""分析这张照片的场景，为 2D 横版跑酷游戏设计主题。

要求：
1. 枚举字段只能从候选值中选；
2. main_elements 列 3~6 个画面中最显眼的东西（中文名词短语）；
3. obstacle_hints 结合场景元素，给出 2~4 个适合做障碍物的东西（中文名词），要具体（如"树桩"而不是"植物"）；
4. suggested_theme 起一个有童趣的游戏主题名（6 字以内）；
5. 只输出 JSON 对象。

字段与候选值：
- scene_type: {_options(SceneType)}
- indoor: true/false
- time_of_day: {_options(TimeOfDay)}
- main_elements: 字符串数组
- color_tone: 主色调（2~4 个字，如 暖黄/冷蓝/翠绿）
- suggested_theme: 游戏主题名
- obstacle_hints: 字符串数组

输出示例：
{{"scene_type":"campus","indoor":false,"time_of_day":"day","main_elements":["教学楼","梧桐树","自行车","操场"],"color_tone":"暖黄","suggested_theme":"校园大冒险","obstacle_hints":["路障","花坛","石阶"]}}"""


def scene_from_text_prompt(prompt: str) -> str:
    """据用户输入的背景文本描述，输出 SceneTags JSON（GLM-4-Flash 纯文本）。"""
    return f"""根据下面这段背景描述文本，为 2D 横版跑酷游戏设计主题。

要求：
1. 枚举字段只能从候选值中选；
2. main_elements 列 3~6 个描述里最显眼的东西（中文名词短语）；
3. obstacle_hints 结合描述元素，给出 2~4 个适合做障碍物的东西（中文名词），要具体（如"树桩"而不是"植物"）；
4. suggested_theme 起一个有童趣的游戏主题名（6 字以内）；
5. 只输出 JSON 对象。

字段与候选值：
- scene_type: {_options(SceneType)}
- indoor: true/false
- time_of_day: {_options(TimeOfDay)}
- main_elements: 字符串数组
- color_tone: 主色调（2~4 个字，如 暖黄/冷蓝/翠绿）
- suggested_theme: 游戏主题名
- obstacle_hints: 字符串数组

背景描述：{prompt}

输出示例：
{{"scene_type":"forest","indoor":false,"time_of_day":"day","main_elements":["木屋","松树","小溪","蘑菇"],"color_tone":"翠绿","suggested_theme":"森林大冒险","obstacle_hints":["树桩","蘑菇","岩石"]}}"""


# ============ 第三层：照片多维度描述（GLM-4V-Flash，视频分镜素材） ============

PHOTO_DESC_SYSTEM = "你是动画分镜师，用富有画面感的中文描述照片，只输出 JSON。"

PHOTO_DESC_PROMPT = """多维度描述这张照片，供后续编写动画剧本使用。

只输出 JSON 对象，字段：
- summary: 一句话概括（20 字以内）
- scene: 场景类型与环境（30 字以内）
- subjects: 画面主体（人物/动物/物体）及状态（40 字以内）
- atmosphere: 氛围情绪（如 温馨/欢快/宁静/神秘）
- highlight: 最适合做动画桥段的画面细节（30 字以内）"""


# ============ 第四层：分镜剧本（GLM-4-Flash，纯文本） ============

STORY_SYSTEM = "你是儿童动画编剧，为Q版卡通主角的历险故事写分镜剧本，只输出 JSON。"


def story_prompt(descriptions: list[str], theme: str, sec_per_scene: float) -> str:
    photos_block = "\n".join(f"照片{i + 1}: {d}" for i, d in enumerate(descriptions))
    return f"""把下面 {len(descriptions)} 张照片串成一个"{theme}"小故事，每张照片对应一幕。

{photos_block}

要求：
1. 剧情有连贯逻辑：起因 → 经过 → 结尾，主角是Q版卡通形象；
2. 每幕 narration 是 1~2 句旁白（主角口吻或讲故事口吻，共 40 字以内，适合配音朗读）；
3. 运镜和动作要变化，避免连续两幕相同；
4. 只输出 JSON 数组，长度必须等于照片数 {len(descriptions)}。

每幕字段：
- photo_index: 照片序号（从 0 开始）
- narration: 旁白文案
- camera_motion: {_options(CameraMotion)}
- avatar_action: {_options(AvatarAction)}
- duration_sec: {sec_per_scene} 左右（旁白长可适当增加，1.5~10）

输出示例：
[{{"photo_index":0,"narration":"主角第一次来到校园，对一切都很好奇！","camera_motion":"zoom_in","avatar_action":"walk_across","duration_sec":3.0}}]"""


# ============ 主展示形象文生图（CogView-3-Flash） ============

# 枚举值 → 中文标签：prompt 约束与接口契约共用一套词汇，避免漂移。
# avatars.py 的衣橱展示也复用本表（从本模块 import LABELS）。
LABELS: dict = {
    GenderStyle: {"boy": "男生感", "girl": "女生感", "neutral": "中性"},
    AgeGroup: {"child": "儿童", "teen": "少年", "young_adult": "青年",
               "middle_aged": "中年", "senior": "老年"},
    FaceShape: {"round": "圆脸", "oval": "鹅蛋脸", "square": "方脸",
                "long": "长脸", "heart": "心形脸"},
    SkinTone: {"fair": "白皙", "light": "浅色", "medium": "中等", "tan": "小麦色", "dark": "深色"},
    HairStyle: {"bald": "光头", "buzz": "板寸", "short": "短发", "medium": "及肩发",
                "long_straight": "黑长直", "long_curly": "长卷发", "ponytail": "马尾",
                "twin_tails": "双马尾", "bun": "丸子头"},
    HairColor: {"black": "黑色", "brown": "棕色", "blonde": "金色",
                "gray_white": "灰白", "colorful": "彩色"},
    Glasses: {"none": "无", "round": "圆框", "square": "方框", "sunglasses": "墨镜"},
    Outfit: {"none": "角色本体", "tshirt": "T恤", "hoodie": "卫衣",
             "dress": "连衣裙", "suit": "西装", "cape": "披风"},
    Accessory: {"none": "无", "hat": "帽子", "headband": "发箍", "bow": "蝴蝶结", "scarf": "围巾"},
    Expression: {"happy": "开心", "neutral": "平静", "surprised": "惊讶", "cool": "酷", "shy": "害羞"},
}


def _cn(enum_cls, value) -> str:
    """枚举值 → 中文标签，缺失则回退原值"""
    return LABELS.get(enum_cls, {}).get(value, value)


AVATAR_PROMPT_BUILDER_SYSTEM = (
    "你是人物外貌描述助手。根据给出的人物特征，用一段连贯的中文描述这个人的外貌"
    "（性别感、年龄段、发型发色、肤色、眼镜、表情、穿搭、配饰）。"
    "不要写画风、背景、构图、分辨率等生图指令，只输出外貌描述本身，50字以内，"
    "不要解释、不要引号、不要换行。"
)


def avatar_prompt_builder_prompt(features) -> str:
    """交给 GLM-4-Flash 的 user 内容：把 FaceFeatures（含 VLM notes）铺成中文。

    GLM-4 只输出人物外貌描述；cogview_avatar 再用写死的 Q版卡通风前后缀包住它交 CogView。
    """
    parts = []
    parts.append(f"性别倾向：{_cn(GenderStyle, features.gender_style.value)}；")
    parts.append(f"年龄段：{_cn(AgeGroup, features.age_group.value)}；")
    parts.append(f"脸型：{_cn(FaceShape, features.face_shape.value)}；")
    parts.append(f"肤色：{_cn(SkinTone, features.skin_tone.value)}；")
    parts.append(f"发型发色：{_cn(HairColor, features.hair_color.value)}"
                 f"{_cn(HairStyle, features.hair_style.value)}；")
    if features.glasses.value != "none":
        parts.append(f"眼镜：{_cn(Glasses, features.glasses.value)}；")
    parts.append(f"表情：{_cn(Expression, features.expression.value)}；")
    if features.outfit.value != "none":
        parts.append(f"穿搭：{_cn(Outfit, features.outfit.value)}；")
    accs = [_cn(Accessory, a.value) for a in features.accessories if a.value != "none"]
    if accs:
        parts.append(f"配饰：{'、'.join(accs)}；")
    if getattr(features, "notes", ""):
        parts.append(f"补充描述：{features.notes}；")
    return "请根据以下人物特征，用一段中文描述这个人的外貌（不要写画风/背景/构图）：\n" + "".join(parts)


def sprite_prompt(kind: str) -> str:
    """游戏精灵 CogView prompt：单个障碍物/金币，纯色背景居中，Q版卡通风。"""
    names = {"stone": "一块灰色的岩石", "stump": "一截木树桩", "cone": "一个橙色路障锥",
             "flower": "一朵小花", "coin": "一枚金色游戏金币"}
    name = names.get(kind, f"一个{kind}")
    return (f"Q版卡通图标，{name}，纯色浅色背景，居中构图，"
            f"Q版卡通风，高清，无文字无水印")
