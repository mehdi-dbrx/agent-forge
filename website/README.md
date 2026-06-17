# brickforge.dev - Landing Page

Single-page landing site for BrickForge, served by a Cloudflare Worker at [brickforge.dev](https://brickforge.dev).

## Architecture

A Cloudflare Worker (`worker.js`) imports `index.html` as a text module and serves it directly at the edge. No static file hosting, no build step, no framework. One HTML file with inline CSS, inline SVGs, and a base64-encoded hero screenshot.

```
worker.js       <- 6-line Worker that serves index.html
index.html      <- Self-contained landing page (~1.2MB due to base64 screenshot)
wrangler.toml   <- Worker config: name, routes, account
```

## DNS Setup

The domain `brickforge.dev` is registered on Cloudflare. A proxied AAAA record points to `100::` (standard Cloudflare placeholder for Workers routes). The Worker route intercepts all requests to `brickforge.dev/*`.

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| AAAA | brickforge.dev | 100:: | Proxied (orange cloud) |

## Deploy

Requires [Wrangler](https://developers.cloudflare.com/workers/wrangler/) and Cloudflare auth:

```bash
# First time only - authenticate
npx wrangler login

# Deploy (from this directory)
cd website
npx wrangler deploy
```

That's it. Takes ~10 seconds. The Worker is deployed globally to Cloudflare's edge network.

## Edit and Redeploy

1. Edit `index.html`
2. Run `npx wrangler deploy` from this directory
3. Live in ~10 seconds

## Update the Hero Screenshot

The hero screenshot is base64-encoded inline in `index.html`. To replace it:

1. Take a new screenshot of the Setup App
2. Optionally process it through [shots.so](https://shots.so) for 3D tilt + background
3. Resize to ~1200px wide: `sips -Z 1200 input.png --out hero-screenshot-sm.png`
4. Re-encode and inject:

```python
python3 << 'EOF'
import base64
with open('hero-screenshot-sm.png', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()
with open('index.html', 'r') as f:
    html = f.read()
# Replace the existing base64 data URI
import re
html = re.sub(
    r'data:image/png;base64,[A-Za-z0-9+/=]+',
    f'data:image/png;base64,{b64}',
    html,
    count=1
)
with open('index.html', 'w') as f:
    f.write(html)
EOF
```

5. `npx wrangler deploy`

## Files

| File | Purpose |
|------|---------|
| `index.html` | Self-contained landing page (HTML + CSS + SVG icons + base64 screenshot) |
| `worker.js` | Cloudflare Worker - imports and serves index.html |
| `wrangler.toml` | Worker config: name, account_id, routes to brickforge.dev |
| `hero-screenshot.png` | Original screenshot (2.5MB, not deployed) |
| `hero-screenshot-sm.png` | Resized screenshot (900KB, source for base64) |
| `screenshot.png` | Raw Setup App screenshot (not deployed) |
| `youtube-script.md` | Video script for BrickForge demo video |
| `.gitignore` | Excludes `.wrangler/` cache |

## Wrangler Config

```toml
name = "brickforge-site"
main = "worker.js"
account_id = "68bd4c20ed6384951d7ba6b5acad1a56"

[[rules]]
type = "Text"
globs = ["**/*.html"]
fallthrough = true

routes = [
  { pattern = "brickforge.dev", zone_name = "brickforge.dev" },
  { pattern = "www.brickforge.dev", zone_name = "brickforge.dev" }
]
```

The `account_id` is the Cloudflare account ID (not a secret - it's in every API URL).

## Troubleshooting

**522 error after deploy**: The AAAA DNS record for `brickforge.dev` must be **Proxied** (orange cloud), not DNS Only. Check in Cloudflare Dashboard > brickforge.dev > DNS.

**Fonts render as serif on iOS**: Verify `-apple-system` and `-webkit-font-smoothing` CSS properties don't have spaces after the dashes. A regex find-replace can break vendor prefixes.

**Deploy goes to workers.dev instead of custom domain**: The Worker route needs to be created via the Cloudflare API if `wrangler deploy` doesn't bind it automatically:

```bash
curl -X POST "https://api.cloudflare.com/client/v4/zones/<ZONE_ID>/workers/routes" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"pattern":"brickforge.dev/*","script":"brickforge-site"}'
```
