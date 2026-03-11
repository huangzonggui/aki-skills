# WeChat Subscription API Publish Map

Last reviewed: 2026-02-17
Primary doc root:
- https://developers.weixin.qq.com/doc/subscription/api/

## Draft Pipeline (Recommended for this skill)

1. Get token
- `POST /cgi-bin/stable_token`
- Doc: `base/api_getstableaccesstoken.html`

2. Upload content images (for HTML content)
- `POST /cgi-bin/media/uploadimg`
- Doc: `material/permanent/api_uploadimage.html`
- Return: image URL

3. Upload permanent material image (for media ID)
- `POST /cgi-bin/material/add_material?type=image`
- Doc: `material/permanent/api_addmaterial.html`
- Return: `media_id`

4. Add draft
- `POST /cgi-bin/draft/add`
- Doc: `draftbox/draftmanage/api_draft_add.html`

### `article_type` notes (from subscription docs)

- `article_type=news`:
  - requires `thumb_media_id` (permanent media ID)
  - content is rich text/HTML article body

- `article_type=newspic`:
  - uses image-message payload
  - requires `image_info.image_list[].image_media_id`
  - images must be permanent material IDs

## Publish-to-user pipeline (optional next stage)

After draft, publishing related APIs are under `public/`:

1. Submit publish task
- `POST /cgi-bin/freepublish/submit`

2. Query publish status
- `POST /cgi-bin/freepublish/get`

3. Batch query publish records
- `POST /cgi-bin/freepublish/batchget`

4. Delete publish record
- `POST /cgi-bin/freepublish/delete`

5. Get article by article_id
- `POST /cgi-bin/freepublish/getarticle`

## Mass messaging pipeline (different from draft)

Under `notify/message/`:
- `uploadnewsmsg`
- `sendall`
- `preview`
- `massmsgget`
- `deletemassmsg`

These are for mass send flows, not the draft box flow used by this skill.
