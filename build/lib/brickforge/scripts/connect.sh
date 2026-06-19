#!/bin/bash
# BrickForge Bridge Auth -- Pure Python, zero dependencies
# Launches an embedded Python script that handles OAuth PKCE directly.
# No Databricks CLI needed. Just Python 3 + a browser.

# --- Config (replaced by Setup App when served as download) ---
APP_URL="${APP_URL:-${1:-}}"
NONCE="${NONCE:-${2:-}}"
NONCE_ID="${NONCE_ID:-${3:-$NONCE}}"
WS_DEFAULT="${WS_DEFAULT:-${4:-}}"
APP_URL="${APP_URL%/}"
if [ -z "$APP_URL" ] || [ -z "$NONCE" ]; then
  echo "Usage: bash connect.sh <app-url> <nonce> [nonce_id] [ws_default]"
  exit 1
fi

# Find python3
PY=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then PY="$cmd"; break; fi
done
if [ -z "$PY" ]; then
  echo ""
  echo "  Python 3 is required but not installed."
  echo ""
  OS="$(uname -s 2>/dev/null || echo Windows)"
  case "$OS" in
    Darwin)
      echo "  Install on macOS (pick one):"
      echo "    1. Open Terminal and run:  brew install python3"
      echo "    2. Or download from:       https://www.python.org/downloads/macos/"
      ;;
    Linux)
      echo "  Install on Linux:"
      echo "    Ubuntu/Debian:  sudo apt install python3"
      echo "    Fedora/RHEL:    sudo dnf install python3"
      ;;
    MINGW*|MSYS*|CYGWIN*)
      echo "  Install on Windows:"
      echo "    1. Run:                    winget install Python.Python.3.12"
      echo "    2. Or open Microsoft Store and search for 'Python 3.12'"
      echo "    3. Or download from:       https://www.python.org/downloads/windows/"
      ;;
    *)
      echo "  Download from: https://www.python.org/downloads/"
      ;;
  esac
  echo ""
  echo "  After installing, run this script again."
  echo ""
  exit 1
fi

exec "$PY" - "$APP_URL" "$NONCE" "$NONCE_ID" "$WS_DEFAULT" << 'PYTHON_SCRIPT'
import sys, os, secrets, hashlib, base64, json, socket, webbrowser, ssl
import http.server, urllib.request, urllib.parse
from threading import Timer

APP_URL = sys.argv[1].rstrip('/')
NONCE = sys.argv[2]
NONCE_ID = sys.argv[3]
WS_DEFAULT = sys.argv[4] if len(sys.argv) > 4 else ''

# ── ANSI ────────────────────────────────────────────────────────────────────
BOLD, B, G, R, Y, C, M, W, DIM = '\033[1m', '\033[34m', '\033[32m', '\033[31m', '\033[33m', '\033[36m', '\033[35m', '\033[0m', '\033[2m'
OK   = f'  {G}✓{W}'
FAIL = f'  {R}✗{W}'
WARN = f'  {Y}⚠{W}'
INFO = f'  {C}→{W}'
RUN  = f'  {B}~{W}'

def section(title):
    print(f'\n{BOLD}{B}═══ {title} ═══{W}')

print(f'\n{BOLD}{M}╔══════════════════════════════════════════════╗{W}')
print(f'{BOLD}{M}║       BrickForge  ·  bridge auth             ║{W}')
print(f'{BOLD}{M}╚══════════════════════════════════════════════╝{W}\n')

print(f'{INFO} App URL:  {DIM}{APP_URL}{W}')
print(f'{INFO} Nonce:    {DIM}{NONCE_ID[:8]}...{W}')
print(f'{INFO} OS:       {DIM}{os.uname().sysname}{W}')
print(f'{INFO} Python:   {DIM}{sys.version.split()[0]}{W}')
print(f'{INFO} Mode:     {DIM}Pure Python (no CLI needed){W}')

# ── Step 1: Target workspace ───────────────────────────────────────────────
section('Workspace')

ws = WS_DEFAULT
if not ws:
    try:
        # Read from /dev/tty to work with bash <(curl ...) where stdin is the pipe
        import io
        tty = io.open('/dev/tty')
        print('  Target workspace URL: ', end='', flush=True)
        ws = tty.readline().strip()
        tty.close()
    except Exception:
        ws = ''
ws = ws.rstrip('/')
if not ws:
    print(f'{FAIL} No workspace URL provided')
    sys.exit(1)
if not ws.startswith('http'):
    ws = 'https://' + ws
if not ws.startswith('http'):
    ws = 'https://' + ws
print(f'{OK} Target: {C}{ws}{W}')
print()
print(f'  {BOLD}{Y}A 7-day Personal Access Token (PAT) will be created{W}')
print(f'  {DIM}on {ws}{W}')
print(f'  {DIM}Your browser will open for authentication.{W}')
print()

# ── Step 2: Discover OAuth endpoints ───────────────────────────────────────
section('OAuth discovery')

discovery_url = f'{ws}/oidc/.well-known/oauth-authorization-server'
print(f'{RUN} Fetching {DIM}{discovery_url}{W}')
ctx = ssl.create_default_context()
try:
    with urllib.request.urlopen(discovery_url, timeout=10, context=ctx) as r:
        endpoints = json.loads(r.read())
    auth_endpoint = endpoints['authorization_endpoint']
    token_endpoint = endpoints['token_endpoint']
    print(f'{OK} Auth:  {DIM}{auth_endpoint}{W}')
    print(f'{OK} Token: {DIM}{token_endpoint}{W}')
except Exception as e:
    print(f'{FAIL} OAuth discovery failed: {e}')
    print(f'  {DIM}This workspace may not support OAuth. Try the CLI version or enter a token manually.{W}')
    sys.exit(1)

# ── Step 3: PKCE + localhost server ────────────────────────────────────────
section('Authentication')

verifier = secrets.token_urlsafe(64)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
state = secrets.token_urlsafe(16)

# Find free port
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(('localhost', 0))
port = sock.getsockname()[1]
sock.close()

redirect_uri = f'http://localhost:{port}'
auth_url = (
    f'{auth_endpoint}'
    f'?client_id=databricks-cli'
    f'&redirect_uri={urllib.parse.quote(redirect_uri, safe="")}'
    f'&response_type=code'
    f'&scope=all-apis+offline_access'
    f'&state={state}'
    f'&code_challenge={challenge}'
    f'&code_challenge_method=S256'
)

auth_code = [None]
bridge_url_holder = [None]

def do_token_exchange(code):
    """Exchange auth code for token, encrypt, build bridge URL. Returns bridge URL or None."""
    print(f'{OK} Auth code received {DIM}({code[:16]}...){W}')

    section('Token')
    print(f'{RUN} Exchanging code for token...')
    token_data = urllib.parse.urlencode({
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': 'databricks-cli',
        'redirect_uri': redirect_uri,
        'code_verifier': verifier,
    }).encode()
    req = urllib.request.Request(token_endpoint, data=token_data, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            token_resp = json.loads(r.read())
        TOKEN = token_resp['access_token']
        REFRESH_TOKEN = token_resp.get('refresh_token', '')
        print(f'{OK} Token acquired {DIM}({len(TOKEN)} chars, {TOKEN[:6]}...){W}')
        print(f'{OK} Expires in: {DIM}{token_resp.get("expires_in", "?")}s{W}')
        if REFRESH_TOKEN:
            print(f'{OK} Refresh token: {DIM}({len(REFRESH_TOKEN)} chars){W}')
    except Exception as e:
        print(f'{FAIL} Token exchange failed: {e}')
        return None

    # User info
    print(f'{RUN} Fetching user info...')
    try:
        me_req = urllib.request.Request(f'{ws}/api/2.0/preview/scim/v2/Me', headers={'Authorization': f'Bearer {TOKEN}'})
        with urllib.request.urlopen(me_req, timeout=10, context=ctx) as r:
            me = json.loads(r.read())
        BRIDGE_USER = me.get('userName', 'unknown')
    except Exception:
        BRIDGE_USER = 'unknown'
    print(f'{OK} User: {C}{BRIDGE_USER}{W}')

    global _pat_ok, _wl_ok, _wl_ip
    _pat_ok = False
    _wl_ok = False
    _wl_ip = ''

    # Check for existing brickforge PAT before creating a new one
    import datetime
    PAT = ''
    today = datetime.date.today().strftime('%Y%m%d')
    pat_name = f'brickforge-7days-{today}'
    print(f'{RUN} Checking for existing brickforge PAT...')
    try:
        list_req = urllib.request.Request(
            f'{ws}/api/2.0/token/list',
            headers={'Authorization': f'Bearer {TOKEN}'},
        )
        with urllib.request.urlopen(list_req, timeout=10, context=ctx) as r:
            tokens = json.loads(r.read()).get('token_infos', [])
        now = int(datetime.datetime.now().timestamp() * 1000)
        for t in tokens:
            comment = t.get('comment', '')
            expiry = t.get('expiry_time', 0)
            if comment.startswith('brickforge-') and expiry > now:
                remaining_h = int((expiry - now) / 3600000)
                print(f'{OK} Found active PAT: {DIM}{comment} ({remaining_h}h remaining){W}')
                # Delete old PAT and create fresh one (can't retrieve existing token value)
                try:
                    tid = t.get('token_id', '')
                    del_req = urllib.request.Request(
                        f'{ws}/api/2.0/token/delete',
                        data=json.dumps({'token_id': tid}).encode(),
                        headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'},
                        method='POST'
                    )
                    urllib.request.urlopen(del_req, timeout=10, context=ctx)
                    print(f'{OK} Revoked old PAT to create fresh one')
                except Exception:
                    pass  # deletion failed, will create with different name
                tokens = None  # force creation
                break
        else:
            tokens = None  # no existing PAT found, create one
    except Exception:
        tokens = None  # list failed, try to create

    if tokens is None:
        print(f'{RUN} Creating PAT ({pat_name})...')
        try:
            pat_req = urllib.request.Request(
                f'{ws}/api/2.0/token/create',
                data=json.dumps({'lifetime_seconds': 604800, 'comment': pat_name}).encode(),
                headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(pat_req, timeout=10, context=ctx) as r:
                pat_resp = json.loads(r.read())
            PAT = pat_resp.get('token_value', '')
            if PAT:
                _pat_ok = True
                print(f'{OK} PAT created: {DIM}{PAT[:12]}... (7 days){W}')
            else:
                print(f'{FAIL} PAT response empty -- falling back to JWT')
        except Exception as e:
            print(f'{FAIL} PAT creation failed: {str(e)[:80]}')
            print(f'{INFO} Falling back to JWT + refresh token')

    # Whitelist Setup App IP on target workspace (if running remotely)
    section('Network')
    print(f'{RUN} Checking Setup App IP...')
    try:
        app_ip_req = urllib.request.Request(f'{APP_URL}/api/setup/my-ip')
        with urllib.request.urlopen(app_ip_req, timeout=5) as r:
            app_ip_data = json.loads(r.read())
        app_ip = app_ip_data.get('ip', '')
        if app_ip:
            _wl_ip = app_ip
            print(f'{INFO} Setup App IP: {DIM}{app_ip}{W}')
            print(f'{RUN} Whitelisting {app_ip} on {ws}...')
            try:
                import datetime as _dt
                label = f'brickforge-{app_ip}-{_dt.date.today().strftime("%Y%m%d")}'
                wl_data = json.dumps({'label': label, 'list_type': 'ALLOW', 'ip_addresses': [f'{app_ip}/32']}).encode()
                wl_req = urllib.request.Request(
                    f'{ws}/api/2.0/ip-access-lists',
                    data=wl_data, method='POST',
                    headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}
                )
                with urllib.request.urlopen(wl_req, timeout=10, context=ctx) as r:
                    json.loads(r.read())
                _wl_ok = True
                print(f'{OK} IP whitelisted: {app_ip}/32')
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    print(f'{FAIL} Cannot whitelist IP (admin required)')
                    print(f'{INFO} Ask your workspace admin to allow {Y}{app_ip}{W}')
                elif e.code in (400, 409):
                    err_body = e.read().decode() if hasattr(e, 'read') else ''
                    if 'already' in err_body.lower() or 'exist' in err_body.lower() or 'duplicate' in err_body.lower() or e.code == 409:
                        _wl_ok = True
                        print(f'{OK} IP already whitelisted')
                    else:
                        print(f'{FAIL} Whitelist failed: HTTP {e.code}')
                        print(f'{INFO} Ask your workspace admin to allow {Y}{app_ip}{W}')
            except Exception as e:
                print(f'{FAIL} Whitelist failed: {str(e)[:80]}')
                print(f'{INFO} Ask your workspace admin to allow {Y}{app_ip}{W}')
        else:
            print(f'{OK} Could not detect Setup App IP -- skipping')
    except Exception as e:
        print(f'{OK} Setup App IP check skipped ({str(e)[:60]})')

    # Encrypt
    section('Encryption')
    print(f'{RUN} Encrypting token...')
    import subprocess
    if PAT:
        token_bundle = json.dumps({'pat': PAT})
    else:
        token_bundle = json.dumps({'access_token': TOKEN, 'refresh_token': REFRESH_TOKEN, 'token_endpoint': token_endpoint})
    try:
        proc = subprocess.run(
            ['openssl', 'enc', '-aes-256-cbc', '-a', '-A', '-pass', f'pass:{NONCE}', '-pbkdf2'],
            input=token_bundle.encode(), capture_output=True, timeout=5
        )
        ENCRYPTED = proc.stdout.decode().strip()
        if not ENCRYPTED:
            raise Exception('empty output')
        print(f'{OK} Encrypted {DIM}({len(ENCRYPTED)} chars){W}')
    except Exception as e:
        print(f'{WARN} openssl not available ({e}) -- token sent over HTTPS only')
        ENCRYPTED = f'PLAIN:{token_bundle}'

    # Build bridge URL
    encoded = urllib.parse.quote(ENCRYPTED, safe='')
    encoded_host = urllib.parse.quote(ws, safe='')
    encoded_user = urllib.parse.quote(BRIDGE_USER, safe='')
    return f'{APP_URL}/#bridge/{NONCE_ID}/{encoded}/{encoded_host}/{encoded_user}'


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if qs.get('state', [None])[0] != state:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'State mismatch')
            return
        auth_code[0] = qs.get('code', [None])[0]

        # Do the full token exchange + encryption before responding
        bridge_url_holder[0] = do_token_exchange(auth_code[0])

        if bridge_url_holder[0]:
            # Redirect browser directly to the Setup App with the token
            self.send_response(302)
            self.send_header('Location', bridge_url_holder[0])
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><body style="font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#0d0d12;color:#FF3522"><h2>Token exchange failed. Check terminal.</h2></body></html>')
    def log_message(self, *a): pass

server = http.server.HTTPServer(('localhost', port), CallbackHandler)
server.timeout = 120

print(f'{RUN} Opening browser for OAuth...')
print(f'  {DIM}Callback: {redirect_uri}{W}')
print(f'  {DIM}If the browser doesn\'t open, copy this URL:{W}')
print(f'  {DIM}{auth_url[:100]}...{W}\n')

webbrowser.open(auth_url)

# Timeout guard
def timeout_handler():
    if not auth_code[0]:
        print(f'\n{FAIL} Timed out waiting for OAuth callback (120s)')
        os._exit(1)
timer = Timer(120, timeout_handler)
timer.daemon = True
timer.start()

server.handle_request()
server.server_close()
timer.cancel()

if not auth_code[0]:
    print(f'{FAIL} No auth code received')
    sys.exit(1)

# ── Done ───────────────────────────────────────────────────────────────────
section('Connect')

if bridge_url_holder[0]:
    print(f'{OK} Browser redirected to Setup App\n')

    # Summary
    _pat_ok = globals().get('_pat_ok', False)
    _wl_ok = globals().get('_wl_ok', False)
    _wl_ip = globals().get('_wl_ip', '')
    has_issues = not _pat_ok or (not _wl_ok and _wl_ip)

    W_ = 46  # inner width between ║ chars
    def _p(s): return s + ' ' * max(0, W_ - len(s))

    if has_issues:
        print(f'{BOLD}{Y}╔{"═"*W_}╗{W}')
        print(f'{BOLD}{Y}║{W}{_p("  Token delivered -- some steps need attention")}{BOLD}{Y}║{W}')
        print(f'{BOLD}{Y}╠{"═"*W_}╣{W}')
        print(f'{BOLD}{Y}║{W}{_p("  ✓ Authenticated")}{BOLD}{Y}║{W}')
        if _pat_ok:
            print(f'{BOLD}{Y}║{W}{_p("  ✓ PAT created (7 days)")}{BOLD}{Y}║{W}')
        else:
            print(f'{BOLD}{Y}║{W}{_p("  ✗ PAT failed (using JWT -- expires in 1h)")}{BOLD}{Y}║{W}')
        if _wl_ip:
            if _wl_ok:
                print(f'{BOLD}{Y}║{W}{_p("  ✓ IP whitelisted")}{BOLD}{Y}║{W}')
            else:
                print(f'{BOLD}{Y}║{W}{_p(f"  ✗ IP whitelist failed ({_wl_ip})")}{BOLD}{Y}║{W}')
        print(f'{BOLD}{Y}║{W}{" "*W_}{BOLD}{Y}║{W}')
        print(f'{BOLD}{Y}║{W}{_p("  To resolve, try one of:")}{BOLD}{Y}║{W}')
        print(f'{BOLD}{Y}║{W}{_p("  - Connect to your corporate VPN and retry")}{BOLD}{Y}║{W}')
        print(f'{BOLD}{Y}║{W}{_p("  - Run from an authorized network")}{BOLD}{Y}║{W}')
        print(f'{BOLD}{Y}║{W}{_p("  - Ask workspace admin to whitelist your IP")}{BOLD}{Y}║{W}')
        if _wl_ip and not _wl_ok:
            print(f'{BOLD}{Y}║{W}{_p(f"    IP to whitelist: {_wl_ip}")}{BOLD}{Y}║{W}')
        print(f'{BOLD}{Y}╚{"═"*W_}╝{W}\n')
    else:
        print(f'{BOLD}{G}╔{"═"*W_}╗{W}')
        print(f'{BOLD}{G}║{W}{_p("  All good -- Setup App is ready.")}{BOLD}{G}║{W}')
        print(f'{BOLD}{G}║{W}{_p("  You can close this window.")}{BOLD}{G}║{W}')
        print(f'{BOLD}{G}╚{"═"*W_}╝{W}\n')
else:
    print(f'{FAIL} Token exchange failed. Check errors above.\n')
PYTHON_SCRIPT
