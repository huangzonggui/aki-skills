from pathlib import Path
import importlib.util


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_script.py"
SPEC = importlib.util.spec_from_file_location("generate_script", MODULE_PATH)
generate_script = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(generate_script)


def test_fallback_cover_like_input_does_not_collapse_to_empty():
    source = """
平台说明：平台是微信视频号。保留信息密度和判断感，别太像口号式短视频。

全局标题：Claude Opus 4.7 发布：能力刻意削弱，编程和视觉能力大提升，但贵、“没人味”
当前段落类型：cover
当前段落主题：Claude Opus 4.7 发布：能力刻意削弱，编程和视觉能力大提升，但贵、“没人味”
目标时长：4 秒

请只围绕当前图片绑定的内容写这一段口播，不要抢后面图片的内容。

当前段落素材如下：

封面图绑定整条内容的总标题：Claude Opus 4.7 发布：能力刻意削弱，编程和视觉能力大提升，但贵、“没人味”

全局分页预览：
Page 01: Claude Opus 4.7 是最强Claude的削弱版
Page 02: 隐形涨价与新功能
Page 03: 编程能力从“会写”到“懂行”
Page 04: 指令遵循更严格，但也可能让你“不适应”
""".strip()

    fallback = generate_script._fallback_script(source, 4, "wechat_video")
    processed = generate_script._post_process_script(fallback, 4).strip()

    assert processed
    assert "最强Claude的削弱版" in processed


def test_strip_reasoning_markup_removes_leading_think_block():
    text = "<think>internal</think>\n\n第一句\n第二句"

    result = generate_script._strip_reasoning_markup(text)

    assert result == "第一句\n第二句"
