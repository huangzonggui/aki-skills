# Troubleshooting

## Proxy

If Gemini Web is flaky:
- prefer TUN mode
- avoid mixed `HTTP_PROXY` + `HTTPS_PROXY` + `ALL_PROXY` stacks when possible
- if you must override, prefer a single `ALL_PROXY=socks5://...` endpoint

## Cookie issues

If the script reports missing `__Secure-1PSID` or `__Secure-1PSIDTS`:
- open Chrome
- confirm Gemini is logged in
- close Chrome
- rerun the script

## Quality

The script can pin the Gemini chat header to `gemini-2.5-pro`, but Google may still route image generation to `Nano Banana 2`.

If the raw response contains `Nano Banana 2`, that is Google-side routing, not a local parsing bug.

## Resolution

The script treats small preview images as invalid when it can see larger dimensions in the raw Gemini response.

If full-resolution download still fails:
- keep the raw response file
- inspect the expected width/height in the metadata json
- rerun with more retries
