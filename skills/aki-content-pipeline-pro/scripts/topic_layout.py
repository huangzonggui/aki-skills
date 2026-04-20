#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


IMAGE_PLATFORMS = ("wechat", "xiaohongshu", "douyin")
DEFAULT_RENDER_PLATFORMS_BY_MODE = {
    "prod": list(IMAGE_PLATFORMS),
    "test": ["wechat"],
}

VIDEO_PLATFORM_CONFIG = {
    "wechat": {
        "dir": "wechat",
        "label": "wechat_video",
        "voice_script": "voice_wechat_video.md",
        "voice_tts_script": "voice_wechat_video_tts.md",
        "draft_suffix": "_wechat",
        "display": "微信视频号",
        "adaptive_source_label": "wechat_video",
    },
    "xiaohongshu": {
        "dir": "xiaohongshu",
        "label": "xhs_video",
        "voice_script": "voice_xhs_video.md",
        "voice_tts_script": "voice_xhs_video_tts.md",
        "draft_suffix": "_xhs",
        "display": "小红书视频",
        "adaptive_source_label": "xhs_video",
    },
    "douyin": {
        "dir": "douyin",
        "label": "douyin_video",
        "voice_script": "voice_douyin_video.md",
        "voice_tts_script": "voice_douyin_video_tts.md",
        "draft_suffix": "_douyin",
        "display": "抖音视频",
        "adaptive_source_label": "douyin_video",
    },
}


@dataclass(frozen=True)
class TopicLayout:
    root: Path

    @property
    def meta_dir(self) -> Path:
        return self.root / "meta"

    @property
    def refs_dir(self) -> Path:
        return self.root / "refs"

    @property
    def prompts_dir(self) -> Path:
        return self.root / "prompts"

    @property
    def copies_dir(self) -> Path:
        return self.root / "copies"

    @property
    def images_dir(self) -> Path:
        return self.root / "images"

    @property
    def video_dir(self) -> Path:
        return self.root / "video"

    @property
    def core_note_path(self) -> Path:
        return self.root / "core_note.md"

    @property
    def core_note_draft_path(self) -> Path:
        return self.root / "core_note.draft.md"

    @property
    def outline_path(self) -> Path:
        return self.root / "outline.md"

    @property
    def content_plan_path(self) -> Path:
        return self.meta_dir / "content_plan.json"

    @property
    def topic_meta_path(self) -> Path:
        return self.meta_dir / "topic_meta.json"

    @property
    def ingest_report_path(self) -> Path:
        return self.meta_dir / "ingest_report.json"

    @property
    def prompt_review_path(self) -> Path:
        return self.meta_dir / "prompt_title_review.md"

    @property
    def image_cost_summary_md(self) -> Path:
        return self.meta_dir / "image_cost_summary.md"

    @property
    def image_cost_summary_json(self) -> Path:
        return self.meta_dir / "image_cost_summary.json"

    @property
    def publish_images_dir(self) -> Path:
        return self.meta_dir / "wechat_publish_images"

    @property
    def wechat_article_path(self) -> Path:
        return self.copies_dir / "wechat_article.md"

    @property
    def wechat_imagepost_copy_path(self) -> Path:
        return self.copies_dir / "wechat_imagepost_copy.md"

    @property
    def xiaohongshu_post_path(self) -> Path:
        return self.copies_dir / "xiaohongshu_post.md"

    def platform_images_dir(self, platform: str) -> Path:
        return self.images_dir / platform

    def platform_original_images_dir(self, platform: str) -> Path:
        return self.platform_images_dir(platform) / "originals"

    def video_platform_dir(self, platform: str) -> Path:
        return self.video_dir / VIDEO_PLATFORM_CONFIG[platform]["dir"]

    def video_timeline_path(self, platform: str) -> Path:
        return self.video_platform_dir(platform) / "timeline.json"

    def video_voice_script_path(self, platform: str) -> Path:
        return self.video_platform_dir(platform) / VIDEO_PLATFORM_CONFIG[platform]["voice_script"]

    def video_voice_tts_script_path(self, platform: str) -> Path:
        return self.video_platform_dir(platform) / VIDEO_PLATFORM_CONFIG[platform]["voice_tts_script"]

    def video_output_dir(self, platform: str) -> Path:
        return self.video_platform_dir(platform) / "output"

    def video_output_video_path(self, platform: str) -> Path:
        return self.video_output_dir(platform) / "video.mp4"

    def video_export_report_path(self, platform: str) -> Path:
        return self.video_output_dir(platform) / "export_report.json"

    def video_stage_dir(self, platform: str) -> Path:
        return self.video_platform_dir(platform) / ".draft_input"

    def video_stage_script_path(self, platform: str) -> Path:
        return self.video_stage_dir(platform) / "script.md"

    def video_stage_images_dir(self, platform: str) -> Path:
        return self.video_stage_dir(platform) / "images"

    def ensure_structure(self) -> None:
        dirs = [
            self.meta_dir,
            self.refs_dir,
            self.prompts_dir,
            self.copies_dir,
            self.images_dir,
            self.video_dir,
        ]
        for platform in IMAGE_PLATFORMS:
            dirs.append(self.platform_images_dir(platform))
            dirs.append(self.platform_original_images_dir(platform))
        for platform in VIDEO_PLATFORM_CONFIG:
            dirs.extend(
                [
                    self.video_platform_dir(platform),
                    self.video_output_dir(platform),
                ]
            )
        for path in dirs:
            path.mkdir(parents=True, exist_ok=True)


def resolve_layout(topic_root: str | Path) -> TopicLayout:
    return TopicLayout(Path(topic_root).expanduser().resolve())
