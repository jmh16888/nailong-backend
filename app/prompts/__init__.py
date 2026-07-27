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

STORY_SYSTEM = "你是儿童动画编剧，为奶龙（黄色小恐龙，憨厚可爱）的历险故事写分镜剧本，只输出 JSON。"


def story_prompt(descriptions: list[str], theme: str, sec_per_scene: float) -> str:
    photos_block = "\n".join(f"照片{i + 1}: {d}" for i, d in enumerate(descriptions))
    return f"""把下面 {len(descriptions)} 张照片串成一个"{theme}"小故事，每张照片对应一幕。

{photos_block}

要求：
1. 剧情有连贯逻辑：起因 → 经过 → 结尾，奶龙是主角；
2. 每幕 narration 是 1~2 句旁白（奶龙口吻或讲故事口吻，共 40 字以内，适合配音朗读）；
3. 运镜和动作要变化，避免连续两幕相同；
4. 只输出 JSON 数组，长度必须等于照片数 {len(descriptions)}。

每幕字段：
- photo_index: 照片序号（从 0 开始）
- narration: 旁白文案
- camera_motion: {_options(CameraMotion)}
- avatar_action: {_options(AvatarAction)}
- duration_sec: {sec_per_scene} 左右（旁白长可适当增加，1.5~10）

输出示例：
[{{"photo_index":0,"narration":"奶龙第一次来到校园，对一切都很好奇！","camera_motion":"zoom_in","avatar_action":"walk_across","duration_sec":3.0}}]"""


# ============ 可选彩蛋：精致版形象文生图（CogView-3-Flash） ============

def fancy_avatar_prompt(features) -> str:
    return (
        "Q版卡通形象，一只可爱的黄色小恐龙（奶龙风格），圆润身材，呆萌表情，"
        f"特征：{features.hair_color.value}色{features.hair_style.value}发型，"
        f"{'戴着' + features.glasses.value + '眼镜，' if features.glasses.value != 'none' else ''}"
        f"表情{features.expression.value}，"
        "纯色背景，全身像，儿童绘本插画风格，柔和配色，高清"
    )
