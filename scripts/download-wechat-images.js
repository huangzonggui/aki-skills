#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

const ARTICLE_FILE = '/Users/aki/Downloads/Browsers/自媒体/1. AI个人IP话题/0. .大模型调用量排行榜/阮一峰-Kimi的一体化Manus的分层.md';
const IMAGES_DIR = path.join(path.dirname(ARTICLE_FILE), 'images');

// Create images directory
if (!fs.existsSync(IMAGES_DIR)) {
  fs.mkdirSync(IMAGES_DIR, { recursive: true });
}

// Image URLs
const imageUrls = [
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4E9icrlOYibNKfL8jFzwMP4kicSdAx0gXZOxj0Bxhtyia5z7AMEmBntWkBmvyIh1EGQialcqY9Jr2B9nAg/0?wx_fmt=jpeg',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3V5eknLwoC0zMHDTQuYibCHV2Wz1ZxWUTYBREw9dXHbJCbibmnCJh5kUg/640?wx_fmt=other',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3TW6tN5mokCrVS3tJu1T6gic1QAvSITa8EqXYXfwtpd5NQ00AKic8hs3Q/640?wx_fmt=other',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3ibARJ9hmQzakkLVFM2eFYAiaslkUtVwLBiccLkicriamgBjPH5gRcI5tmzQ/640?wx_fmt=other',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE39cfs0Zhibge8zwNFuHj94Sxd9iaAicKEtRdM2iav1DAbFly3h61Rza4PQw/640?wx_fmt=other',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3fGs1lRibzOlDXyBiaibhe7ib2ZpsJWpiaMhF7yjLqMnntwS1X8nYEDDqykg/640?wx_fmt=other',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3myauxK31ndq3TRmORRwLLBb5wWuWjUriaNqYEStYz7kCibd9T8p1qXrw/640?wx_fmt=other',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3UhI0bvozr6HKudndvyv3INRLNIpIeWOaXWiaDWuFHPHOicrAXfevd2jw/640?wx_fmt=other',
  'https://mmbiz.qpic.cn/mmbiz_gif/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3qqQb0Fj27NC9pWAia0PfqciakLV7NLR1aib7OpIxC1ObRGyGMnVXYUByA/640?wx_fmt=gif',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3RVqpRXcUyciccfUU8tvyyPfAozge35VrhjsKq4AA71VSDKkVlmxFafw/640?wx_fmt=other',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3uD5BiaN3nFg5y35IIvQ46H0iaibHvl19WTbsMrzibeXWJwvf1jQdmyjqBg/640?wx_fmt=other',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3jdPOxQNYlXLoR1zRKFpGc27NdIxMbmhhU5th0SCXm9GvibE093TBeag/640?wx_fmt=other',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE39OwCfj0g3TBKIvbVvbdibvcicRibP8cFHyoY9ouQgUcspw3FOKZkml08Q/640?wx_fmt=other',
  'https://mmbiz.qpic.cn/mmbiz_jpg/XjGG4txZI4GPxZVRDiaZmdlLibOu6nXLE3ubCCoIwQRKalIbE2x8oOsqxXaqGhowfrGvy3fHZfzGMcVCGpWJmubg/640?wx_fmt=other',
];

function downloadImage(url, filepath) {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https') ? https : http;
    const file = fs.createWriteStream(filepath);

    protocol.get(url, (res) => {
      if (res.statusCode === 302 || res.statusCode === 301) {
        file.close();
        downloadImage(res.headers.location, filepath).then(resolve).catch(reject);
        return;
      }
      res.pipe(file);
      file.on('finish', () => {
        file.close();
        resolve();
      });
    }).on('error', (err) => {
      file.close();
      fs.unlink(filepath, () => {});
      reject(err);
    });
  });
}

async function main() {
  const content = fs.readFileSync(ARTICLE_FILE, 'utf-8');
  let updatedContent = content;

  console.log(`Downloading ${imageUrls.length} images...`);

  for (let i = 0; i < imageUrls.length; i++) {
    const url = imageUrls[i];
    const ext = url.includes('gif') ? 'gif' : url.includes('png') ? 'png' : 'jpg';
    const filename = `image-${i + 1}.${ext}`;
    const localPath = path.join(IMAGES_DIR, filename);
    const relativePath = `./images/${filename}`;

    try {
      process.stdout.write(`  [${i+1}/${imageUrls.length}] Downloading ${filename}...`);
      await downloadImage(url, localPath);
      console.log(' ✓');

      // Replace URL with local path in content
      updatedContent = updatedContent.replace(url, relativePath);
    } catch (err) {
      console.log(' ✗ Error:', err.message);
    }
  }

  // Write updated markdown
  fs.writeFileSync(ARTICLE_FILE, updatedContent, 'utf-8');
  console.log(`\n✓ Article updated: ${ARTICLE_FILE}`);
  console.log(`✓ Images saved to: ${IMAGES_DIR}`);
}

main().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
