#!/usr/bin/env python3
import os
import re
import urllib.request
from pathlib import Path

# Article path
ARTICLE_DIR = Path("/Users/aki/Downloads/Browsers/自媒体/1. AI个人IP话题/0. .大模型调用量排行榜")
ARTICLE_FILE = ARTICLE_DIR / "阮一峰-Kimi的一体化Manus的分层.md"
IMAGES_DIR = ARTICLE_DIR / "images"

# Create images directory
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Read article
with open(ARTICLE_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# All image URLs from the article
image_urls = [
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4E9icrlOYibNKfL8jFzwMP4kicSdAx0gXZOxj0Bxhtyia5z7AMEmBntWkBmvyIh1EGQialcqY9Jr2B9nAg/0?wx_fmt=jpeg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3V5eknLwoC0zMHDTQuYibCHV2Wz1ZxWUTYBREw9dXHbJCbibmnCJh5kUg/640?wx_fmt=other&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3TW6tN5mokCrVS3tJu1T6gic1QAvSITa8EqXYXfwtpd5NQ00AKic8hs3Q/640?wx_fmt=other&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3ibARJ9hmQzakkLVFM2eFYAiaslkUtVwLBiccLkicriamgBjPH5gRcI5tmzQ/640?wx_fmt=other&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE39cfs0Zhibge8zwNFuHj94Sxd9iaAicKEtRdM2iav1DAbFly3h61Rza4PQw/640?wx_fmt=other&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3fGs1lRibzOlDXyBiaibhe7ib2ZpsJWpiaMhF7yjLqMnntwS1X8nYEDDqykg/640?wx_fmt=other&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3myauxK31ndq3TRmORRwLLBb5wWuWjUriaNqYEStYz7kCibd9T8p1qXrw/640?wx_fmt=other&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3UhI0bvozr6HKudndvyv3INRLNIpIeWOaXWiaDWuFHPHOicrAXfevd2jw/640?wx_fmt=other&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_gif/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3qqQb0Fj27NC9pWAia0PfqciakLV7NLR1aib7OpIxC1ObRGyGMnVXYUByA/640?wx_fmt=gif&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3RVqpRXcUyciccfUU8tvyyPfAozge35VrhjsKq4AA71VSDKkVlmxFafw/640?wx_fmt=other&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3uD5BiaN3nFg5y35IIvQ46H0iaibHvl19WTbsMrzibeXWJwvf1jQdmyjqBg/640?wx_fmt=other&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3jdPOxQNYlXLoR1zRKFpGc27NdIxMbmhhU5th0SCXm9GvibE093TBeag/640?wx_fmt=other&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE39OwCfj0g3TBKIvbVvbdibvcicRibP8cFHyoY9ouQgUcspw3FOKZkml08Q/640?wx_fmt=other&from=appmsg',
    'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3ubCCoIwQRKalIbE2x8oOsqxXaqGhowfrGvy3fHZfzGMcVCGpWJmubg/640?wx_fmt=other&from=appmsg',
]

print(f"Downloading {len(image_urls)} images...")

# Download images
url_to_local = {}
for i, url in enumerate(image_urls):
    ext = 'gif' if 'gif' in url else 'png' if 'png' in url else 'jpg'
    filename = f"image-{i+1}.{ext}"
    local_path = IMAGES_DIR / filename
    relative_path = f"./images/{filename}"

    try:
        print(f"  Downloading {filename}...")
        urllib.request.urlretrieve(url, local_path)
        url_to_local[url] = relative_path
        print(f"    ✓ {filename}")
    except Exception as e:
        print(f"    ✗ Failed: {e}")

# Update markdown content
updated_content = content
for url, local_path in url_to_local.items():
    updated_content = updated_content.replace(url, local_path)

# Save updated markdown
with open(ARTICLE_FILE, 'w', encoding='utf-8') as f:
    f.write(updated_content)

print(f"\nDone! Downloaded {len(url_to_local)} images.")
print(f"Updated: {ARTICLE_FILE}")
