#!/usr/bin/env python3
"""
Aki 写作风格润色脚本
基于个人写作风格和创作原则对文章进行润色
"""

import argparse
import sys
from pathlib import Path


def read_article(file_path: Path) -> str:
    """读取文章内容"""
    if not file_path.exists():
        raise FileNotFoundError(f"文章不存在: {file_path}")
    return file_path.read_text(encoding="utf-8")


def polish_article(content: str) -> tuple[str, list[str]]:
    """
    润色文章内容

    Returns:
        (润色后的内容, 修改点列表)
    """
    modifications = []

    # 这里将实际的润色逻辑交给AI处理
    # 脚本主要负责文件IO和流程控制
    return content, modifications


def main():
    parser = argparse.ArgumentParser(description="Aki 写作风格润色")
    parser.add_argument("--article", required=True, help="文章路径")
    parser.add_argument("--output", help="输出路径（默认覆盖原文件）")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际修改")

    args = parser.parse_args()

    article_path = Path(args.article).expanduser().resolve()

    # 读取文章
    content = read_article(article_path)

    # 打印提示信息
    print(f"正在润色文章: {article_path}")
    print(f"\n请使用 aki-writing-polisher skill 来进行实际润色")
    print("\n润色规则:")
    print("- 开头要克制，直入正题")
    print("- 减少评价词，让内容自己说话")
    print("- 问题要突出，单独成行")
    print("- 复杂概念要展开解释")
    print("- 结尾要干脆，不要过度升华")
    print("- 允许节制地加入情感共鸣")
    print("- 转述词偏好中性表达")


if __name__ == "__main__":
    main()
