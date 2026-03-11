#!/usr/bin/env python3
"""
Bilibili 视频信息抓取器 - 防风控版本
"""

import json
import time
import random
import requests
from datetime import datetime

# 防风控配置
MIN_DELAY = 3  # 最小延迟秒数
MAX_DELAY = 8  # 最大延迟秒数

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com',
    'Accept': 'application/json, text/plain, */*',
}

def random_delay():
    """随机延迟，模拟真人操作"""
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    print(f"  ⏳ 等待 {delay:.1f} 秒...")
    time.sleep(delay)

def get_space_videos(mid, page=1, retry=3):
    """获取用户空间视频列表"""
    url = f"https://api.bilibili.com/x/space/arc/search"
    params = {
        'mid': mid,
        'pn': page,
        'ps': 20,
        'json': 1
    }
    
    for attempt in range(retry):
        try:
            random_delay()
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
            data = resp.json()
            
            if data.get('code') == 0:
                return data.get('data', {}).get('list', {}).get('vlist', [])
            elif '过于频繁' in str(data.get('message', '')):
                wait_time = random.uniform(10, 20)
                print(f"  ⚠️ 触发限流，等待 {wait_time:.0f} 秒...")
                time.sleep(wait_time)
            else:
                print(f"  ⚠️ 错误: {data.get('message')}")
                return []
        except Exception as e:
            print(f"  ⚠️ 请求失败: {e}")
            time.sleep(2)
    
    return []

def get_video_info(bvid, retry=3):
    """获取单个视频详细信息"""
    url = "https://api.bilibili.com/x/web-interface/view"
    params = {'bvid': bvid}
    
    for attempt in range(retry):
        try:
            random_delay()
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
            data = resp.json()
            
            if data.get('code') == 0:
                return data.get('data', {})
            elif '过于频繁' in str(data.get('message', '')):
                wait_time = random.uniform(15, 30)
                print(f"  ⚠️ 触发限流，等待 {wait_time:.0f} 秒...")
                time.sleep(wait_time)
        except Exception as e:
            print(f"  ⚠️ 请求失败: {e}")
            time.sleep(2)
    
    return None

def get_subtitle(bvid, cid):
    """获取视频字幕"""
    url = "https://api.bilibili.com/x/player/v2"
    params = {'bvid': bvid, 'cid': cid}
    
    try:
        random_delay()
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        
        if data.get('code') == 0:
            subtitles = data.get('data', {}).get('subtitle', {}).get('subtitles', [])
            if subtitles:
                # 获取字幕内容
                subtitle_url = subtitles[0].get('subtitle_url')
                if subtitle_url:
                    sub_resp = requests.get(f"https:{subtitle_url}", headers=HEADERS, timeout=10)
                    return sub_resp.json()
    except:
        pass
    
    return None

def main():
    # 新智元AIEra 的 mid
    mid = 519463151
    
    print(f"🎬 开始抓取新智元AIEra (mid={mid}) 的视频...")
    
    # 获取所有视频
    all_videos = []
    for page in range(1, 6):  # 最多5页
        print(f"\n📄 获取第 {page} 页...")
        videos = get_space_videos(mid, page)
        if not videos:
            break
        all_videos.extend(videos)
        print(f"  ✅ 获取到 {len(videos)} 个视频")
    
    print(f"\n📊 共获取 {len(all_videos)} 个视频")
    
    # 保存视频列表
    with open('/root/.openclaw/workspace/memory/bilibili_videos_raw.json', 'w', encoding='utf-8') as f:
        json.dump(all_videos, f, ensure_ascii=False, indent=2)
    
    # 获取详细信息（只取前20个）
    detailed_videos = []
    for i, video in enumerate(all_videos[:20]):
        bvid = video['bvid']
        print(f"\n📹 获取视频 {i+1}/20: {bvid} - {video['title'][:30]}...")
        
        info = get_video_info(bvid)
        if info:
            detailed_videos.append({
                'bvid': bvid,
                'title': info.get('title'),
                'description': info.get('desc'),
                'duration': info.get('duration'),
                'pubdate': info.get('pubdate'),
                'view': info.get('stat', {}).get('view'),
                'like': info.get('stat', {}).get('like'),
                'coin': info.get('stat', {}).get('coin'),
                'favorite': info.get('stat', {}).get('favorite'),
                'share': info.get('stat', {}).get('share'),
                'reply': info.get('stat', {}).get('reply'),
                'aid': info.get('aid'),
                'cid': info.get('cid'),
            })
    
    # 保存详细信息
    with open('/root/.openclaw/workspace/memory/bilibili_videos_detailed.json', 'w', encoding='utf-8') as f:
        json.dump(detailed_videos, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 抓取完成！共获取 {len(detailed_videos)} 个视频详细信息")
    print(f"📁 保存至: /root/.openclaw/workspace/memory/bilibili_videos_detailed.json")

if __name__ == '__main__':
    main()
