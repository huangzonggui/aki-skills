#!/usr/bin/env bun
import fs from 'node:fs';
import path from 'node:path';

const ARTICLE_PATH = '/Users/aki/Downloads/Browsers/自媒体/1. AI个人IP话题/0. .大模型调用量排行榜/阮一峰-Kimi的一体化Manus的分层.md';
const IMAGES_DIR = '/Users/aki/Downloads/Browsers/自媒体/1. AI个人IP话题/0. .大模型调用量排行榜/images';

const content = fs.readFileSync(ARTICLE_PATH, 'utf-8');

// Extract image URLs from the web_reader result
const imageUrlPatterns = [
  /!\[Image 1: cover_image\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 2\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 3\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 4\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 5\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 6\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 7\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 8\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 9\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 10\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 11\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 12\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 13\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 14\]\((https://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 15\]\((http://mmbiz\.qpic\.cn/[^\)]+)\)/g,
  /!\[Image 16: 作者头像\]\((http://mmbiz\.qpic\.cn/[^\)]+)\)/g,
];

// All URLs from the article
const imageUrls: string[] = [
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
  'http://mmbiz.qpic.cn/mmbiz_png/XjGG4txZI4HyawHDh0C3MUyfv7q5JFbhibkh9RI6nJPRGmujsjhpickmKSI8V1tLlbuxwia95KxMOAqQMpfPTpC1Q/0?wx_fmt=png',
  'http://mmbiz.qpic.cn/mmbiz_png/XjGG4txZI4HyawHDh0C3MUyfv7q5JFbhibkh9RI6nJPRGmujsjhpickmKSI8V1tLlbuxwia95KxMOAqQMpfPTpC1Q/0?wx_fmt=png',
];

// Create images directory
fs.mkdirSync(IMAGES_DIR, { recursive: true });

const downloaded: { url: string; localPath: string }[] = [];

// Download images
for (let i = 0; i < imageUrls.length; i++) {
  const url = imageUrls[i];
  try {
    const ext = url.includes('gif') ? 'gif' : url.includes('png') ? 'png' : 'jpg';
    const fileName = `image-${i + 1}.${ext}`;
    const localPath = path.join(IMAGES_DIR, fileName);

    console.log(`Downloading ${fileName}...`);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Failed: ${response.status}`);
    const arrayBuffer = await response.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    fs.writeFileSync(localPath, buffer);

    downloaded.push({ url, localPath: `./images/${fileName}` });
    console.log(`  ✓ ${fileName}`);
  } catch (err) {
    console.error(`  ✗ Failed to download image ${i + 1}:`, err);
  }
}

console.log(`\nDownloaded ${downloaded.length}/${imageUrls.length} images`);

// Update markdown with local paths
let updatedContent = content;
for (const { url, localPath } of downloaded) {
  updatedContent = updatedContent.replace(url, localPath);
}

// Write updated markdown
fs.writeFileSync(ARTICLE_PATH, updatedContent, 'utf-8');
console.log(`\nUpdated markdown with local image paths.`);
