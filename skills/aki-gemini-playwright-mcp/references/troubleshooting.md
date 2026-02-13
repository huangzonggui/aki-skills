# Troubleshooting

## "Composer not ready"
- Gemini not logged in for the MCP profile.
- Fix: Open the profile window and log in on `https://gemini.google.com/app`.

## No image found
- Gemini didn't render an image (prompt not supported or model limit).
- Fix: Use explicit image request (e.g., "生成一张…的图片") and retry.

## Empty/invalid image file
- Blob/image URL expired while downloading.
- Fix: Re-run and keep the page active; avoid switching tabs during generation.

## Slow or timeout
- Increase `timeoutMs` in the MCP tool call.
