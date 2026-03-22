from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Request, Body
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import shutil
import base64
import httpx
import re
import os
import io
import logging
import json
import hmac
import psycopg2
from psycopg2.extras import RealDictCursor
import anthropic
import subprocess as _subprocess
import zipfile
import hashlib
import time
import tempfile
import threading
from bs4 import BeautifulSoup
from collections import deque
import ipaddress

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR.parent / '.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not set")

ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'change-me-admin-token')

# ============ PERSISTENT OBJECT STORAGE (via Replit sidecar) ============
GCS_BUCKET_ID = os.environ.get('DEFAULT_OBJECT_STORAGE_BUCKET_ID')
REPLIT_SIDECAR = "http://127.0.0.1:1106"

async def _gcs_signed_url(filename: str, method: str = "PUT", ttl_sec: int = 3600) -> str:
    from datetime import timedelta
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_sec)).isoformat()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{REPLIT_SIDECAR}/object-storage/signed-object-url",
            json={"bucket_name": GCS_BUCKET_ID, "object_name": f"uploads/{filename}", "method": method, "expires_at": expires_at},
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["signed_url"]

async def upload_to_gcs(file_data: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
    if not GCS_BUCKET_ID:
        raise RuntimeError("GCS bucket not configured")
    signed_url = await _gcs_signed_url(filename, "PUT")
    async with httpx.AsyncClient() as client:
        resp = await client.put(signed_url, content=file_data, headers={"Content-Type": content_type}, timeout=120)
        resp.raise_for_status()
    logger.info(f"Uploaded to GCS: uploads/{filename}")
    return f"/api/uploads/{filename}"

async def download_from_gcs(filename: str):
    if not GCS_BUCKET_ID:
        raise FileNotFoundError("GCS not configured")
    signed_url = await _gcs_signed_url(filename, "GET")
    async with httpx.AsyncClient() as client:
        resp = await client.get(signed_url, timeout=60)
        if resp.status_code == 404:
            raise FileNotFoundError(f"File not found in GCS: {filename}")
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "application/octet-stream")
        return resp.content, content_type

# Local fallback for dev when GCS not configured
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

def get_db():
    last_err = None
    for attempt in range(3):
        try:
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=10)
            return conn
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    raise last_err

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            year TEXT NOT NULL,
            cover_image TEXT NOT NULL,
            hook_text TEXT NOT NULL,
            cover_athletes TEXT NOT NULL,
            description TEXT NOT NULL,
            youtube_embed TEXT DEFAULT '',
            "order" INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS comments (
            id TEXT PRIMARY KEY,
            author_name TEXT NOT NULL,
            content TEXT NOT NULL,
            parent_id TEXT,
            is_admin BOOLEAN DEFAULT FALSE,
            likes INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS email_subscriptions (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            subscribed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS petition_signatures (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT,
            email TEXT,
            signed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS page_views (
            id SERIAL PRIMARY KEY,
            viewed_at TEXT NOT NULL,
            user_agent TEXT
        );

        CREATE TABLE IF NOT EXISTS file_backups (
            id TEXT PRIMARY KEY,
            file_key TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            original_content TEXT NOT NULL,
            change_description TEXT,
            backed_up_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS clips (
            id TEXT PRIMARY KEY,
            game_id TEXT NOT NULL,
            title TEXT NOT NULL,
            platform TEXT NOT NULL,
            embed_url TEXT NOT NULL,
            description TEXT,
            "order" INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS site_content (
            id TEXT PRIMARY KEY,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS proof (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            source TEXT,
            proof_type TEXT DEFAULT 'stat',
            number TEXT,
            icon TEXT DEFAULT 'chart',
            "order" INTEGER DEFAULT 0,
            image_url TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mockups (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            media_type TEXT DEFAULT 'image',
            image_url TEXT,
            video_embed_url TEXT,
            "order" INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS votes (
            id TEXT PRIMARY KEY,
            game_id TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS creator_submissions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            platform TEXT NOT NULL,
            profile_url TEXT NOT NULL,
            content_url TEXT NOT NULL,
            description TEXT NOT NULL,
            follower_count TEXT,
            status TEXT DEFAULT 'pending',
            submitted_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS community_posts (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            author_name TEXT NOT NULL,
            author_handle TEXT NOT NULL,
            author_avatar TEXT,
            follower_count TEXT,
            content TEXT NOT NULL,
            post_url TEXT,
            screenshot_url TEXT,
            "order" INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS social_feed (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT,
            url TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS deployment_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS deployment_history (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            status TEXT NOT NULL,
            url TEXT,
            error_message TEXT,
            logs TEXT DEFAULT '[]',
            started_at TIMESTAMPTZ DEFAULT NOW(),
            finished_at TIMESTAMPTZ
        );
        CREATE TABLE IF NOT EXISTS editor_conversations (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            steps TEXT DEFAULT '[]',
            files_changed INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS suggestions (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            sources TEXT DEFAULT '[]',
            priority TEXT DEFAULT 'medium',
            is_new BOOLEAN DEFAULT TRUE,
            generated_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS health_checks (
            component TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            message TEXT,
            response_ms INTEGER DEFAULT 0,
            checked_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS system_events (
            id TEXT PRIMARY KEY,
            feature TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            status TEXT DEFAULT 'ok',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    cur.execute("ALTER TABLE petition_signatures ADD COLUMN IF NOT EXISTS email TEXT")
    cur.execute("ALTER TABLE editor_conversations ADD COLUMN IF NOT EXISTS session_id TEXT DEFAULT 'legacy'")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_editor_conv_session ON editor_conversations(session_id)")
    conn.commit()
    cur.close()
    conn.close()

init_db()

def _log_event(feature: str, action: str, details: str = "", status: str = "ok"):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO system_events (id, feature, action, details, status) VALUES (%s,%s,%s,%s,%s)",
            (str(uuid.uuid4()), feature, action, str(details)[:2000], status)
        )
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

# ============ HEALTH MONITORING ============

def _run_health_checks():
    checks = []
    # DB check
    try:
        t0 = time.time()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        ms = int((time.time() - t0) * 1000)
        cur.close(); conn.close()
        checks.append({"component": "database", "status": "ok", "message": f"Connected in {ms}ms", "response_ms": ms})
    except Exception as e:
        checks.append({"component": "database", "status": "error", "message": str(e)[:200], "response_ms": -1})
    # Disk check
    import shutil as _shutil
    try:
        usage = _shutil.disk_usage("/")
        pct = (usage.used / usage.total) * 100
        free_gb = usage.free // (1024**3)
        status = "ok" if pct < 80 else ("warn" if pct < 90 else "error")
        checks.append({"component": "disk", "status": status, "message": f"{pct:.1f}% used, {free_gb}GB free", "response_ms": 0})
    except Exception as e:
        checks.append({"component": "disk", "status": "warn", "message": str(e)[:100], "response_ms": 0})
    # Memory check
    try:
        with open("/proc/meminfo") as f:
            lines = {l.split(":")[0]: int(l.split()[1]) for l in f.readlines() if ":" in l}
        total = lines.get("MemTotal", 1)
        avail = lines.get("MemAvailable", total)
        pct = ((total - avail) / total) * 100
        status = "ok" if pct < 80 else ("warn" if pct < 90 else "error")
        checks.append({"component": "memory", "status": status, "message": f"{pct:.1f}% used", "response_ms": 0})
    except Exception as e:
        checks.append({"component": "memory", "status": "ok", "message": "Cannot read memory info", "response_ms": 0})
    # API self-check
    try:
        import urllib.request as _ur
        t0 = time.time()
        _ur.urlopen("http://127.0.0.1:8000/api/petition/count", timeout=5)
        ms = int((time.time() - t0) * 1000)
        checks.append({"component": "api", "status": "ok", "message": f"API responded in {ms}ms", "response_ms": ms})
    except Exception as e:
        checks.append({"component": "api", "status": "warn", "message": str(e)[:100], "response_ms": -1})
    # Save to DB
    try:
        conn = get_db(); cur = conn.cursor()
        for c in checks:
            cur.execute("""INSERT INTO health_checks (component, status, message, response_ms, checked_at)
                           VALUES (%s,%s,%s,%s,NOW())
                           ON CONFLICT (component) DO UPDATE SET status=EXCLUDED.status, message=EXCLUDED.message, response_ms=EXCLUDED.response_ms, checked_at=NOW()""",
                        (c["component"], c["status"], c["message"], c.get("response_ms", 0)))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

def _health_monitor_loop():
    time.sleep(10)
    while True:
        try:
            _run_health_checks()
        except Exception:
            pass
        time.sleep(300)

threading.Thread(target=_health_monitor_loop, daemon=True).start()

# ============ SUGGESTIONS ENGINE ============

_SUGGESTION_CATEGORIES = ["Fan Growth", "Technical Improvements", "Business Strategy", "Community Engagement", "Content Ideas"]

def _run_suggestions_safe():
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM petition_signatures")
        sig_count = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM comments")
        comment_count = cur.fetchone()["c"]
        cur.close(); conn.close()

        client = get_anthropic_client()
        prompt = f"""You are a growth strategist for the NBA 2K Legacy Vault — a fan campaign to get 2K Sports to build a "game-within-a-game" mode preserving 2K15, 2K16, 2K17, 2K20 online forever.

Current stats: {sig_count} petition signatures, {comment_count} community comments.

Generate 5 specific, actionable suggestions to grow this campaign. Draw on real examples from gaming history and fan campaigns that succeeded.

Categories: {_SUGGESTION_CATEGORIES}

For each item:
- category: one of the above
- title: max 7 words
- description: 1-2 sentences, actionable
- priority: high/medium/low
- sources: 2 real examples

Return ONLY a JSON array — no markdown, no extra text:
[{{"category":"...","title":"...","description":"...","priority":"...","sources":["...","..."]}}]"""

        response = client.messages.create(model=CHAT_MODEL, max_tokens=1200,
                                          messages=[{"role": "user", "content": prompt}])
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            suggestions = json.loads(text)
        except json.JSONDecodeError:
            last_complete = text.rfind("},")
            if last_complete == -1:
                last_complete = text.rfind("}")
            if last_complete != -1:
                repaired = text[:last_complete + 1] + "]"
                suggestions = json.loads(repaired)
            else:
                raise

        conn = get_db(); cur = conn.cursor()
        for s in suggestions:
            cur.execute("""INSERT INTO suggestions (id, category, title, description, sources, priority, is_new, generated_at)
                           VALUES (%s,%s,%s,%s,%s,%s,TRUE,NOW())""",
                        (str(uuid.uuid4()), s.get("category","General"), s.get("title",""), s.get("description",""),
                         json.dumps(s.get("sources",[])), s.get("priority","medium")))
        conn.commit(); cur.close(); conn.close()
        logger.info(f"Generated {len(suggestions)} suggestions")
    except Exception as e:
        logger.error(f"Suggestions generation error: {e}")

def _suggestions_loop():
    time.sleep(30)
    while True:
        _run_suggestions_safe()
        time.sleep(21600)

threading.Thread(target=_suggestions_loop, daemon=True).start()

app = FastAPI(title="NBA 2K Legacy Vault API")
api_router = APIRouter(prefix="/api")

_cors_raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
_cors_allow_credentials = "*" not in _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["http://localhost:5173"],
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        if path.startswith('/api/admin') and path != '/api/admin/login':
            token = request.headers.get('x-admin-token')
            if not token or not hmac.compare_digest(token, ADMIN_TOKEN):
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

        response: StarletteResponse = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)

def _require_admin_token(request: Request):
    token = request.headers.get("x-admin-token")
    if not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")

_CHAT_RATE_LIMIT = 10
_CHAT_RATE_WINDOW = 3600
_chat_rate_tracker: dict[str, deque] = {}

_TRUSTED_PROXY_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)

def _is_trusted_proxy(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _TRUSTED_PROXY_NETS)
    except ValueError:
        return False

def _get_client_ip(request: Request) -> str:
    direct_host = request.client.host if request.client else None
    if direct_host and _is_trusted_proxy(direct_host):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return direct_host or "unknown"

def _check_chat_rate_limit(ip: str) -> bool:
    now = time.time()
    stale = [k for k, v in _chat_rate_tracker.items() if v and v[-1] < now - _CHAT_RATE_WINDOW]
    for k in stale:
        del _chat_rate_tracker[k]
    if ip not in _chat_rate_tracker:
        _chat_rate_tracker[ip] = deque()
    q = _chat_rate_tracker[ip]
    while q and q[0] < now - _CHAT_RATE_WINDOW:
        q.popleft()
    if len(q) >= _CHAT_RATE_LIMIT:
        return False
    q.append(now)
    return True

# ============ MODELS ============

class GameBase(BaseModel):
    title: str
    year: str
    cover_image: str
    hook_text: str
    cover_athletes: str
    description: str
    youtube_embed: Optional[str] = ""
    order: int = 0
    is_active: bool = True

class GameCreate(GameBase):
    pass

class GameUpdate(BaseModel):
    title: Optional[str] = None
    year: Optional[str] = None
    cover_image: Optional[str] = None
    hook_text: Optional[str] = None
    cover_athletes: Optional[str] = None
    description: Optional[str] = None
    youtube_embed: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None

class Game(GameBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class CommentCreate(BaseModel):
    author_name: str
    content: str
    parent_id: Optional[str] = None
    is_admin: bool = False

class Comment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    author_name: str
    content: str
    parent_id: Optional[str] = None
    is_admin: bool = False
    likes: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    replies: List["Comment"] = []

class EmailSubscriptionCreate(BaseModel):
    email: str

class EmailSubscription(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    subscribed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PetitionSignCreate(BaseModel):
    name: str
    location: Optional[str] = None
    email: Optional[str] = None

class PetitionSign(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    location: Optional[str] = None
    email: Optional[str] = None
    signed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AdminLogin(BaseModel):
    password: str

class OperatorAgentRequest(BaseModel):
    message: str
    execute: bool = False
    confirm_actions: List[str] = Field(default_factory=list)
    confirm_all: bool = False

class ClipCreate(BaseModel):
    game_id: str
    title: str
    platform: str
    embed_url: str
    description: Optional[str] = None
    order: int = 0

class ClipUpdate(BaseModel):
    title: Optional[str] = None
    platform: Optional[str] = None
    embed_url: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None

class Clip(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    game_id: str
    title: str
    platform: str
    embed_url: str
    description: Optional[str] = None
    order: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class SiteContentUpdate(BaseModel):
    key: str
    value: str

class SiteContent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key: str
    value: str
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ProofCreate(BaseModel):
    title: str
    description: str
    source: Optional[str] = None
    proof_type: str = "stat"
    number: Optional[str] = None
    icon: str = "chart"
    order: int = 0
    image_url: Optional[str] = None

class ProofUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    proof_type: Optional[str] = None
    number: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = None
    image_url: Optional[str] = None

class Proof(ProofCreate):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class MockupCreate(BaseModel):
    title: str
    description: str
    media_type: str = "image"
    image_url: Optional[str] = None
    video_embed_url: Optional[str] = None
    order: int = 0

class MockupUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    media_type: Optional[str] = None
    image_url: Optional[str] = None
    video_embed_url: Optional[str] = None
    order: Optional[int] = None

class Mockup(MockupCreate):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str

class VoteCreate(BaseModel):
    game_id: str

class CreatorSubmission(BaseModel):
    name: str
    platform: str
    profile_url: str
    content_url: str
    description: str
    follower_count: Optional[str] = None

class CommunityPost(BaseModel):
    platform: str
    author_name: str
    author_handle: str
    author_avatar: Optional[str] = None
    follower_count: Optional[str] = None
    content: str
    post_url: Optional[str] = None
    screenshot_url: Optional[str] = None
    order: int = 0

class SocialFeedItem(BaseModel):
    platform: str
    author: str
    content: str
    timestamp: Optional[str] = None
    url: Optional[str] = None

class Base64Upload(BaseModel):
    data: str
    filename: Optional[str] = "pasted_image.png"

# ============ HELPERS ============

def row_to_dict(row):
    if row is None:
        return None
    return dict(row)

def rows_to_list(rows):
    return [dict(r) for r in rows]

# ============ GAME ROUTES ============

@api_router.get("/games", response_model=List[Game])
async def get_games():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM games WHERE is_active = TRUE ORDER BY "order" ASC')
    games = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return games

@api_router.get("/games/all", response_model=List[Game])
async def get_all_games():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM games ORDER BY "order" ASC')
    games = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return games

@api_router.get("/games/{game_id}", response_model=Game)
async def get_game(game_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM games WHERE id = %s', (game_id,))
    game = row_to_dict(cur.fetchone())
    cur.close(); conn.close()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game

@api_router.post("/games", response_model=Game)
async def create_game(game_data: GameCreate):
    game = Game(**game_data.model_dump())
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''INSERT INTO games (id, title, year, cover_image, hook_text, cover_athletes, description, youtube_embed, "order", is_active, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (game.id, game.title, game.year, game.cover_image, game.hook_text, game.cover_athletes,
                 game.description, game.youtube_embed, game.order, game.is_active, game.created_at, game.updated_at))
    conn.commit(); cur.close(); conn.close()
    return game

@api_router.put("/games/{game_id}", response_model=Game)
async def update_game(game_id: str, game_data: GameUpdate):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM games WHERE id = %s', (game_id,))
    existing = row_to_dict(cur.fetchone())
    if not existing:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Game not found")
    update_data = {k: v for k, v in game_data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join([f'"{k}" = %s' for k in update_data.keys()])
    cur.execute(f'UPDATE games SET {set_clause} WHERE id = %s', list(update_data.values()) + [game_id])
    conn.commit()
    cur.execute('SELECT * FROM games WHERE id = %s', (game_id,))
    updated = row_to_dict(cur.fetchone())
    cur.close(); conn.close()
    return updated

@api_router.delete("/games/{game_id}")
async def delete_game(game_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM games WHERE id = %s', (game_id,))
    if cur.rowcount == 0:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Game not found")
    conn.commit(); cur.close(); conn.close()
    return {"message": "Game deleted"}

# ============ COMMENT ROUTES ============

@api_router.get("/comments", response_model=List[Comment])
async def get_comments():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM comments WHERE parent_id IS NULL ORDER BY created_at DESC')
    top_level = rows_to_list(cur.fetchall())
    for comment in top_level:
        cur.execute('SELECT * FROM comments WHERE parent_id = %s ORDER BY created_at ASC', (comment["id"],))
        comment["replies"] = rows_to_list(cur.fetchall())
        for reply in comment["replies"]:
            reply["replies"] = []
    cur.close(); conn.close()
    return top_level

@api_router.post("/comments", response_model=Comment)
async def create_comment(comment_data: CommentCreate):
    comment = Comment(author_name=comment_data.author_name, content=comment_data.content,
                      parent_id=comment_data.parent_id, is_admin=comment_data.is_admin)
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT INTO comments (id, author_name, content, parent_id, is_admin, likes, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                (comment.id, comment.author_name, comment.content, comment.parent_id, comment.is_admin, 0, comment.created_at))
    conn.commit(); cur.close(); conn.close()
    return comment

@api_router.post("/comments/{comment_id}/like")
async def like_comment(comment_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE comments SET likes = likes + 1 WHERE id = %s', (comment_id,))
    if cur.rowcount == 0:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Comment not found")
    conn.commit()
    cur.execute('SELECT likes FROM comments WHERE id = %s', (comment_id,))
    likes = cur.fetchone()["likes"]
    cur.close(); conn.close()
    return {"likes": likes}

@api_router.delete("/comments/{comment_id}")
async def delete_comment(comment_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM comments WHERE parent_id = %s', (comment_id,))
    cur.execute('DELETE FROM comments WHERE id = %s', (comment_id,))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Comment deleted"}

# ============ EMAIL SUBSCRIPTION ROUTES ============

@api_router.post("/subscribe", response_model=EmailSubscription)
async def subscribe_email(subscription: EmailSubscriptionCreate):
    sub = EmailSubscription(email=subscription.email)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO email_subscriptions (id, email, subscribed_at) VALUES (%s,%s,%s)',
                    (sub.id, sub.email, sub.subscribed_at))
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        cur.execute('SELECT * FROM email_subscriptions WHERE email = %s', (subscription.email,))
        sub = EmailSubscription(**row_to_dict(cur.fetchone()))
    cur.close(); conn.close()
    return sub

@api_router.get("/subscriptions", response_model=List[EmailSubscription])
async def get_subscriptions():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM email_subscriptions ORDER BY subscribed_at DESC')
    subs = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return subs

@api_router.delete("/subscriptions/{sub_id}")
async def delete_subscription(sub_id: str, request: Request):
    _require_admin_token(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM email_subscriptions WHERE id = %s', (sub_id,))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Subscription deleted"}

# ============ PETITION ROUTES ============

@api_router.post("/petition/sign", response_model=PetitionSign)
async def sign_petition(sign_data: PetitionSignCreate):
    sig = PetitionSign(name=sign_data.name, location=sign_data.location, email=sign_data.email)
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT INTO petition_signatures (id, name, location, email, signed_at) VALUES (%s,%s,%s,%s,%s)',
                (sig.id, sig.name, sig.location, sig.email, sig.signed_at))
    conn.commit(); cur.close(); conn.close()
    return sig

@api_router.get("/petition/count")
async def get_petition_count():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as count FROM petition_signatures')
    count = cur.fetchone()["count"]
    cur.close(); conn.close()
    return {"count": count}

@api_router.get("/petition/signatures")
async def get_petition_signatures():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, name, location, signed_at FROM petition_signatures ORDER BY signed_at DESC')
    sigs = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return sigs

@api_router.get("/admin/petition/signatures")
async def get_petition_signatures_admin():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM petition_signatures ORDER BY signed_at DESC')
    sigs = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return sigs

@api_router.delete("/petition/{sig_id}")
async def delete_petition_signature(sig_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM petition_signatures WHERE id = %s', (sig_id,))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Signature deleted"}

# ============ ANALYTICS ROUTES ============

@api_router.post("/analytics/pageview")
async def record_pageview(request: Request):
    conn = get_db()
    cur = conn.cursor()
    ua = request.headers.get("user-agent", "")
    now = datetime.now(timezone.utc).isoformat()
    cur.execute('INSERT INTO page_views (viewed_at, user_agent) VALUES (%s,%s)', (now, ua))
    conn.commit(); cur.close(); conn.close()
    return {"ok": True}

@api_router.get("/analytics/stats")
async def get_analytics_stats():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as total FROM page_views')
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as today FROM page_views WHERE viewed_at >= %s",
                (datetime.now(timezone.utc).strftime("%Y-%m-%d"),))
    today = cur.fetchone()["today"]
    cur.execute('SELECT COUNT(*) as count FROM petition_signatures')
    signatures = cur.fetchone()["count"]
    cur.close(); conn.close()
    return {"total_views": total, "today_views": today, "signatures": signatures}

# ============ ADMIN ROUTES ============

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me-admin-password")

@api_router.post("/admin/login")
async def admin_login(login_data: AdminLogin):
    if login_data.password == ADMIN_PASSWORD:
        return {"success": True, "token": ADMIN_TOKEN}
    raise HTTPException(status_code=401, detail="Invalid password")

MISSION_ACTIONS = {
    "dashboard_summary": {"classification": "read-only", "requires_confirmation": False, "simulation_only": False},
    "content_list": {"classification": "read-only", "requires_confirmation": False, "simulation_only": False},
    "games_list": {"classification": "read-only", "requires_confirmation": False, "simulation_only": False},
    "community_list": {"classification": "read-only", "requires_confirmation": False, "simulation_only": False},
    "creator_list": {"classification": "read-only", "requires_confirmation": False, "simulation_only": False},
    "health_list": {"classification": "read-only", "requires_confirmation": False, "simulation_only": False},
    "doctor_diagnostic": {"classification": "read-only", "requires_confirmation": False, "simulation_only": False},
    "deploy_history": {"classification": "read-only", "requires_confirmation": False, "simulation_only": False},
    "system_log": {"classification": "read-only", "requires_confirmation": False, "simulation_only": False},
    "editor_tree": {"classification": "read-only", "requires_confirmation": False, "simulation_only": False},
    "health_run": {"classification": "safe write", "requires_confirmation": False, "simulation_only": False},
    "suggestions_generate": {"classification": "safe write", "requires_confirmation": False, "simulation_only": False},
    "suggestions_list": {"classification": "read-only", "requires_confirmation": False, "simulation_only": False},
    "doctor_lock_in": {"classification": "requires confirmation", "requires_confirmation": True, "simulation_only": False},
}

def _operator_planner(message: str):
    m = (message or "").lower()
    actions = []
    if any(k in m for k in ["dashboard", "overview", "summary", "stats"]):
        actions.append("dashboard_summary")
    if any(k in m for k in ["content", "headline", "copy", "text"]):
        actions.append("content_list")
    if any(k in m for k in ["game", "games"]):
        actions.append("games_list")
    if any(k in m for k in ["community", "post"]):
        actions.append("community_list")
    if any(k in m for k in ["creator", "submission"]):
        actions.append("creator_list")
    if any(k in m for k in ["health check", "run health", "check health"]):
        actions.append("health_run")
    if "health" in m:
        actions.append("health_list")
    if any(k in m for k in ["doctor", "diagnostic", "diagnose"]):
        actions.append("doctor_diagnostic")
    if any(k in m for k in ["lock in", "lock-in", "verify build"]):
        actions.append("doctor_lock_in")
    if any(k in m for k in ["suggestion", "ideas"]):
        actions.append("suggestions_list")
    if any(k in m for k in ["generate suggestion", "new suggestions"]):
        actions.append("suggestions_generate")
    if "deploy" in m:
        actions.append("deploy_history")
    if any(k in m for k in ["log", "events"]):
        actions.append("system_log")
    if any(k in m for k in ["editor", "code tree"]):
        actions.append("editor_tree")
    if not actions:
        actions = ["dashboard_summary", "health_list", "suggestions_list"]
    seen = set()
    deduped = []
    for action in actions:
        if action in seen:
            continue
        seen.add(action)
        meta = MISSION_ACTIONS.get(action, {"classification": "read-only", "requires_confirmation": False, "simulation_only": True})
        deduped.append({"action": action, **meta})
    return deduped

def _operator_dashboard_summary():
    conn = get_db()
    cur = conn.cursor()
    tables = [
        "games", "comments", "site_content", "community_posts", "creator_submissions",
        "health_checks", "suggestions", "deployment_history"
    ]
    out = {}
    for t in tables:
        cur.execute(f"SELECT COUNT(*) as c FROM {t}")
        out[t] = cur.fetchone()["c"]
    cur.close(); conn.close()
    return out

@api_router.post("/admin/operator-agent/chat")
async def operator_agent_chat(req: OperatorAgentRequest):
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    actions = _operator_planner(message)
    if not req.execute:
        _log_event("mission_control", "plan", f"Message: {message[:180]} | Actions: {[a['action'] for a in actions]}", "ok")
        return {
            "mode": "plan",
            "message": message,
            "actions": actions,
            "assistant_reply": f"I planned {len(actions)} action(s). Turn on execute mode to run them."
        }

    _log_event("mission_control", "execute_start", f"Message: {message[:180]} | Actions: {[a['action'] for a in actions]}", "ok")
    results = []
    confirmed = set(req.confirm_actions or [])
    for item in actions:
        action = item["action"]
        needs_confirmation = bool(item.get("requires_confirmation"))
        if needs_confirmation and not (req.confirm_all or action in confirmed):
            skip = {
                "action": action,
                "ok": False,
                "status": "skipped_confirmation_required",
                "error": f"Action '{action}' requires explicit confirmation.",
            }
            results.append(skip)
            _log_event("mission_control", "execute_skipped", f"{action} skipped: confirmation required", "warn")
            continue
        try:
            if action == "dashboard_summary":
                results.append({"action": action, "ok": True, "data": _operator_dashboard_summary()})
            elif action == "content_list":
                conn = get_db(); cur = conn.cursor()
                cur.execute("SELECT key, value FROM site_content ORDER BY key ASC")
                rows = rows_to_list(cur.fetchall()); cur.close(); conn.close()
                results.append({"action": action, "ok": True, "count": len(rows), "data": rows[:100]})
            elif action == "games_list":
                conn = get_db(); cur = conn.cursor()
                cur.execute('SELECT id, title, year, is_active, "order" FROM games ORDER BY "order" ASC')
                rows = rows_to_list(cur.fetchall()); cur.close(); conn.close()
                results.append({"action": action, "ok": True, "count": len(rows), "data": rows})
            elif action == "community_list":
                conn = get_db(); cur = conn.cursor()
                cur.execute('SELECT id, platform, author_name, content FROM community_posts ORDER BY "order" ASC')
                rows = rows_to_list(cur.fetchall()); cur.close(); conn.close()
                results.append({"action": action, "ok": True, "count": len(rows), "data": rows})
            elif action == "creator_list":
                conn = get_db(); cur = conn.cursor()
                cur.execute("SELECT id, name, platform, status, submitted_at FROM creator_submissions ORDER BY submitted_at DESC")
                rows = rows_to_list(cur.fetchall()); cur.close(); conn.close()
                results.append({"action": action, "ok": True, "count": len(rows), "data": rows})
            elif action == "health_run":
                threading.Thread(target=_run_health_checks, daemon=True).start()
                results.append({"action": action, "ok": True, "message": "Health check triggered"})
            elif action == "health_list":
                conn = get_db(); cur = conn.cursor()
                cur.execute("SELECT * FROM health_checks ORDER BY checked_at DESC LIMIT 50")
                rows = rows_to_list(cur.fetchall()); cur.close(); conn.close()
                results.append({"action": action, "ok": True, "count": len(rows), "data": rows})
            elif action == "doctor_diagnostic":
                results.append({"action": action, "ok": True, "data": doctor_diagnostic()})
            elif action == "doctor_lock_in":
                results.append({"action": action, "ok": True, "data": await doctor_lock_in()})
            elif action == "suggestions_generate":
                threading.Thread(target=_run_suggestions_safe, daemon=True).start()
                results.append({"action": action, "ok": True, "message": "Suggestions generation triggered"})
            elif action == "suggestions_list":
                conn = get_db(); cur = conn.cursor()
                cur.execute("SELECT * FROM suggestions ORDER BY created_at DESC LIMIT 100")
                rows = rows_to_list(cur.fetchall()); cur.close(); conn.close()
                results.append({"action": action, "ok": True, "count": len(rows), "data": rows})
            elif action == "deploy_history":
                conn = get_db(); cur = conn.cursor()
                cur.execute("SELECT * FROM deployment_history ORDER BY started_at DESC LIMIT 20")
                rows = rows_to_list(cur.fetchall()); cur.close(); conn.close()
                results.append({"action": action, "ok": True, "count": len(rows), "data": rows})
            elif action == "system_log":
                conn = get_db(); cur = conn.cursor()
                cur.execute("SELECT * FROM system_events ORDER BY created_at DESC LIMIT 100")
                rows = rows_to_list(cur.fetchall()); cur.close(); conn.close()
                results.append({"action": action, "ok": True, "count": len(rows), "data": rows})
            elif action == "editor_tree":
                results.append({"action": action, "ok": True, "data": await get_editor_tree()})
            else:
                results.append({"action": action, "ok": False, "error": "Unsupported action"})
            if results[-1].get("ok"):
                _log_event("mission_control", "execute_action_ok", action, "ok")
            else:
                _log_event("mission_control", "execute_action_failed", f"{action}: {results[-1].get('error','unknown')}", "error")
        except Exception as e:
            results.append({"action": action, "ok": False, "error": str(e)[:300]})
            _log_event("mission_control", "execute_action_failed", f"{action}: {str(e)[:200]}", "error")

    ok_count = len([r for r in results if r.get("ok")])
    failed_count = len(actions) - ok_count
    summary = f"Executed {len(actions)} action(s): {ok_count} succeeded, {failed_count} failed/skipped."
    _log_event("mission_control", "execute_end", summary, "ok" if failed_count == 0 else "warn")
    return {
        "mode": "execute",
        "message": message,
        "actions": actions,
        "results": results,
        "assistant_reply": summary
    }

@api_router.get("/admin/operator-agent/capabilities")
async def operator_agent_capabilities():
    return {
        "actions": [
            {"action": name, **meta}
            for name, meta in MISSION_ACTIONS.items()
        ],
        "notes": [
            "Plan mode simulates only (no mutations).",
            "Execute mode runs actions that map to existing admin capabilities.",
            "Actions marked requires_confirmation must be passed in confirm_actions or confirm_all=true."
        ]
    }

@api_router.post("/seed")
async def seed_games():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as count FROM games')
    count = cur.fetchone()["count"]
    if count > 0:
        cur.close(); conn.close()
        return {"message": "Games already seeded"}

    now = datetime.now(timezone.utc).isoformat()
    default_games = [
        {"id": str(uuid.uuid4()), "title": "NBA 2K15", "year": "2014",
         "cover_image": "https://images.unsplash.com/photo-1546519638-68e109498ffc?auto=format&fit=crop&w=600&q=80",
         "hook_text": "Where the modern era began", "cover_athletes": "Kevin Durant",
         "description": "The game that defined a generation. Kevin Durant on the cover of the most technically refined 2K to date.",
         "youtube_embed": "", "order": 0, "is_active": True, "created_at": now, "updated_at": now},
        {"id": str(uuid.uuid4()), "title": "NBA 2K16", "year": "2015",
         "cover_image": "https://images.unsplash.com/photo-1574623452334-1e0ac2b3ccb4?auto=format&fit=crop&w=600&q=80",
         "hook_text": "Widely considered the GOAT", "cover_athletes": "Stephen Curry, James Harden, Anthony Davis",
         "description": "Spike Lee's MyCAREER. The most beloved 2K ever made. This is the one they all want back.",
         "youtube_embed": "", "order": 1, "is_active": True, "created_at": now, "updated_at": now},
        {"id": str(uuid.uuid4()), "title": "NBA 2K17", "year": "2016",
         "cover_image": "https://images.unsplash.com/photo-1608245449230-4ac19066d2d0?auto=format&fit=crop&w=600&q=80",
         "hook_text": "Pure basketball soul", "cover_athletes": "Paul George",
         "description": "The last truly pure basketball experience. Paul George leads a game that respected the sport.",
         "youtube_embed": "", "order": 2, "is_active": True, "created_at": now, "updated_at": now},
        {"id": str(uuid.uuid4()), "title": "NBA 2K20", "year": "2019",
         "cover_image": "https://images.unsplash.com/photo-1504450758481-7338eba7524a?auto=format&fit=crop&w=600&q=80",
         "hook_text": "The final masterpiece", "cover_athletes": "Anthony Davis",
         "description": "The last great 2K before the current era. Anthony Davis headlines the most complete package.",
         "youtube_embed": "", "order": 3, "is_active": True, "created_at": now, "updated_at": now},
    ]
    for g in default_games:
        cur.execute('''INSERT INTO games (id, title, year, cover_image, hook_text, cover_athletes, description, youtube_embed, "order", is_active, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (g["id"], g["title"], g["year"], g["cover_image"], g["hook_text"], g["cover_athletes"],
                     g["description"], g["youtube_embed"], g["order"], g["is_active"], g["created_at"], g["updated_at"]))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Games seeded", "count": len(default_games)}

@api_router.get("/")
async def root():
    return {"message": "NBA 2K Legacy Vault API"}

@api_router.get("/health")
async def public_health():
    """
    Lightweight health endpoint for smoke checks and platform probes.
    Returns 503 when DB is unavailable.
    """
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1 as ok")
        cur.fetchone()
        cur.close()
        conn.close()
        return {"status": "ok", "database": "ok", "service": "nba-vault-api"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "database": "error",
                "service": "nba-vault-api",
                "detail": str(e)[:200],
            },
        )

# ============ CLIPS ROUTES ============

@api_router.get("/clips")
async def get_all_clips():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM clips ORDER BY "order" ASC')
    clips = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return clips

@api_router.get("/clips/game/{game_id}")
async def get_clips_by_game(game_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM clips WHERE game_id = %s ORDER BY "order" ASC', (game_id,))
    clips = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return clips

@api_router.post("/clips", response_model=Clip)
async def create_clip(clip_data: ClipCreate):
    clip = Clip(**clip_data.model_dump())
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''INSERT INTO clips (id, game_id, title, platform, embed_url, description, "order", created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                (clip.id, clip.game_id, clip.title, clip.platform, clip.embed_url, clip.description, clip.order, clip.created_at))
    conn.commit(); cur.close(); conn.close()
    return clip

@api_router.put("/clips/{clip_id}", response_model=Clip)
async def update_clip(clip_id: str, clip_data: ClipUpdate):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM clips WHERE id = %s', (clip_id,))
    existing = row_to_dict(cur.fetchone())
    if not existing:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Clip not found")
    update_data = {k: v for k, v in clip_data.model_dump().items() if v is not None}
    if update_data:
        set_clause = ", ".join([f'"{k}" = %s' for k in update_data.keys()])
        cur.execute(f'UPDATE clips SET {set_clause} WHERE id = %s', list(update_data.values()) + [clip_id])
        conn.commit()
    cur.execute('SELECT * FROM clips WHERE id = %s', (clip_id,))
    updated = row_to_dict(cur.fetchone())
    cur.close(); conn.close()
    return updated

@api_router.delete("/clips/{clip_id}")
async def delete_clip(clip_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM clips WHERE id = %s', (clip_id,))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Clip deleted"}

@api_router.delete("/clips/game/{game_id}")
async def delete_all_clips_for_game(game_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM clips WHERE game_id = %s', (game_id,))
    count = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    return {"message": f"Deleted {count} clips"}

# ============ SITE CONTENT ROUTES ============

DEFAULT_CONTENT = {
    "vault_headline": "One Vault. Four Eras. Infinite Play.",
    "vault_subheadline": "The revolutionary concept that changes everything.",
    "vault_description": "The NBA 2K Legacy Vault is a revolutionary 'game-within-a-game' mode. Launch full, untouched versions of 2K15, 2K16, 2K17, and 2K20 directly inside modern NBA 2K — powered by secure containers on persistent online servers.\n\nNo more sunsets. No player-base split. No cheating.\n\nFriends list works across every era. Park, Pro-Am, Rec, MyTEAM, MyCAREER — all alive forever.",
    "vault_features": "Eternal online for every classic|Unified progression & friends|Cheat-proof containers|Recurring revenue stream for 2K|OG retention + new players discovering history",
    "hero_headline": "The NBA 2K Legacy Vault",
    "hero_subheadline": "2K15 • 2K16 • 2K17 • 2K20 — All in one place.",
    "hero_tagline": "Persistent online. No resets. Ever.",
    "google_doc_url": "https://docs.google.com/document/d/1DEb_W0fxCGWaGN97KcVkVqD1JmZEOUrl5DpCCaayHe0/edit?tab=t.0#heading=h.4a00a8jkgs1z",
    "google_doc_label": "Read the Full Concept Document"
}

@api_router.get("/content")
async def get_all_content():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT key, value FROM site_content')
    rows = cur.fetchall()
    cur.close(); conn.close()
    content = {r["key"]: r["value"] for r in rows}
    for k, v in DEFAULT_CONTENT.items():
        if k not in content:
            content[k] = v
    return content

@api_router.get("/content/{key}")
async def get_content(key: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM site_content WHERE key = %s', (key,))
    row = row_to_dict(cur.fetchone())
    cur.close(); conn.close()
    if not row:
        return {"key": key, "value": DEFAULT_CONTENT.get(key, "")}
    return row

@api_router.post("/content")
async def update_content(content_data: SiteContentUpdate, request: Request):
    _require_admin_token(request)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''INSERT INTO site_content (id, key, value, updated_at) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at''',
                (str(uuid.uuid4()), content_data.key, content_data.value, now))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Content updated", "key": content_data.key}

@api_router.post("/content/seed")
async def seed_default_content(request: Request):
    _require_admin_token(request)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    cur = conn.cursor()
    for key, value in DEFAULT_CONTENT.items():
        cur.execute('''INSERT INTO site_content (id, key, value, updated_at) VALUES (%s,%s,%s,%s)
                       ON CONFLICT (key) DO NOTHING''',
                    (str(uuid.uuid4()), key, value, now))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Default content seeded"}

# ============ PROOF OF DEMAND ROUTES ============

@api_router.get("/proof")
async def get_all_proof():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM proof ORDER BY "order" ASC')
    proof = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return proof

@api_router.post("/proof", response_model=Proof)
async def create_proof(proof_data: ProofCreate):
    proof = Proof(**proof_data.model_dump())
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''INSERT INTO proof (id, title, description, source, proof_type, number, icon, "order", image_url, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (proof.id, proof.title, proof.description, proof.source, proof.proof_type, proof.number, proof.icon, proof.order, proof.image_url, proof.created_at))
    conn.commit(); cur.close(); conn.close()
    return proof

@api_router.put("/proof/{proof_id}", response_model=Proof)
async def update_proof(proof_id: str, proof_data: ProofUpdate):
    conn = get_db()
    cur = conn.cursor()
    update_data = {k: v for k, v in proof_data.model_dump().items() if v is not None}
    if update_data:
        set_clause = ", ".join([f'"{k}" = %s' for k in update_data.keys()])
        cur.execute(f'UPDATE proof SET {set_clause} WHERE id = %s', list(update_data.values()) + [proof_id])
        conn.commit()
    cur.execute('SELECT * FROM proof WHERE id = %s', (proof_id,))
    updated = row_to_dict(cur.fetchone())
    cur.close(); conn.close()
    if not updated:
        raise HTTPException(status_code=404, detail="Proof not found")
    return updated

@api_router.delete("/proof/{proof_id}")
async def delete_proof(proof_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM proof WHERE id = %s', (proof_id,))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Proof deleted"}

# ============ VAULT MOCKUP ROUTES ============

@api_router.get("/mockups")
async def get_all_mockups():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM mockups ORDER BY "order" ASC')
    mockups = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return mockups

@api_router.post("/mockups", response_model=Mockup)
async def create_mockup(mockup_data: MockupCreate):
    mockup = Mockup(**mockup_data.model_dump())
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''INSERT INTO mockups (id, title, description, media_type, image_url, video_embed_url, "order", created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                (mockup.id, mockup.title, mockup.description, mockup.media_type, mockup.image_url, mockup.video_embed_url, mockup.order, mockup.created_at))
    conn.commit(); cur.close(); conn.close()
    return mockup

@api_router.put("/mockups/{mockup_id}", response_model=Mockup)
async def update_mockup(mockup_id: str, mockup_data: MockupUpdate):
    conn = get_db()
    cur = conn.cursor()
    update_data = {k: v for k, v in mockup_data.model_dump().items() if v is not None}
    if update_data:
        set_clause = ", ".join([f'"{k}" = %s' for k in update_data.keys()])
        cur.execute(f'UPDATE mockups SET {set_clause} WHERE id = %s', list(update_data.values()) + [mockup_id])
        conn.commit()
    cur.execute('SELECT * FROM mockups WHERE id = %s', (mockup_id,))
    updated = row_to_dict(cur.fetchone())
    cur.close(); conn.close()
    if not updated:
        raise HTTPException(status_code=404, detail="Mockup not found")
    return updated

@api_router.delete("/mockups/{mockup_id}")
async def delete_mockup(mockup_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM mockups WHERE id = %s', (mockup_id,))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Mockup deleted"}

@api_router.post("/mockups/seed")
async def seed_mockups():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as count FROM mockups')
    count = cur.fetchone()["count"]
    cur.close(); conn.close()
    if count > 0:
        return {"message": "Mockups already seeded"}
    return {"message": "No default mockups to seed"}

# ============ FILE UPLOAD ROUTES ============

@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    allowed_images = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    allowed_videos = {'video/mp4', 'video/quicktime', 'video/webm', 'video/x-msvideo', 'video/mpeg', 'video/x-matroska'}
    allowed = allowed_images | allowed_videos
    content_type = file.content_type or "application/octet-stream"
    ext_lower = (file.filename or "").split('.')[-1].lower()
    video_exts = {'mp4', 'mov', 'webm', 'avi', 'mpeg', 'mkv', 'm4v'}
    if content_type not in allowed and ext_lower not in video_exts and content_type not in allowed_images:
        raise HTTPException(status_code=400, detail="Only images (JPEG, PNG, GIF, WebP) and videos (MP4, MOV, WebM, AVI) are allowed")
    ext = ext_lower if ext_lower else 'bin'
    filename = f"{uuid.uuid4()}.{ext}"
    file_data = await file.read()
    try:
        url = await upload_to_gcs(file_data, filename, content_type)
    except Exception as e:
        logger.warning(f"GCS upload failed, using local fallback: {e}")
        file_path = UPLOAD_DIR / filename
        with open(file_path, "wb") as f:
            f.write(file_data)
        url = f"/api/uploads/{filename}"
    return {"url": url, "filename": filename}

@api_router.post("/upload/base64")
async def upload_base64(upload: Base64Upload):
    try:
        if ',' in upload.data:
            header, data = upload.data.split(',', 1)
            ext = 'png'
            content_type = 'image/png'
            for fmt in ['png', 'jpeg', 'jpg', 'gif', 'webp']:
                if fmt in header:
                    ext = 'jpg' if fmt == 'jpeg' else fmt
                    content_type = f"image/{'jpeg' if fmt in ('jpeg','jpg') else fmt}"
                    break
        else:
            data = upload.data
            ext = 'png'
            content_type = 'image/png'
        image_data = base64.b64decode(data)
        filename = f"{uuid.uuid4()}.{ext}"
        try:
            url = await upload_to_gcs(image_data, filename, content_type)
        except Exception as e:
            logger.warning(f"GCS upload failed, using local fallback: {e}")
            file_path = UPLOAD_DIR / filename
            with open(file_path, "wb") as f:
                f.write(image_data)
            url = f"/api/uploads/{filename}"
        return {"url": url, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process image: {str(e)}")

@api_router.get("/uploads/{filename}")
async def serve_upload(filename: str):
    try:
        data, content_type = await download_from_gcs(filename)
        return StreamingResponse(io.BytesIO(data), media_type=content_type, headers={"Cache-Control": "public, max-age=31536000"})
    except FileNotFoundError:
        local_path = UPLOAD_DIR / filename
        if local_path.exists():
            import mimetypes
            ct = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            return StreamingResponse(open(local_path, "rb"), media_type=ct)
        raise HTTPException(status_code=404, detail="File not found")

# ============ VAULT AI CHATBOT ============

VAULT_SYSTEM_PROMPT = """You are Vault AI, your role is to serve as a knowledgeable guide to the NBA 2K Legacy Vault concept. You help people understand the vision, answer questions clearly, and provide well-researched responses.

## YOUR APPROACH
- Be helpful, clear, and professional
- Speak with confidence because you know the facts, but never be arrogant
- Adapt your tone: casual with fans, technical with developers, business-focused with executives
- When addressing concerns, respond with understanding and facts
- Always provide sources, links, or references when you have relevant information

## THE CONCEPT - NBA 2K LEGACY VAULT
The NBA 2K Legacy Vault is a "game-within-a-game" mode that would launch full, untouched versions of NBA 2K15, 2K16, 2K17, and 2K20 directly inside modern NBA 2K — powered by secure containers on persistent online servers.

No more sunsets. No player-base split. Friends list works across every era. Park, Pro-Am, Rec, MyTEAM, MyCAREER — all preserved.

## THE GAMES
- NBA 2K15 (2014) - Where the modern 2K era began. Cover: Kevin Durant
- NBA 2K16 (2015) - Widely considered the GOAT. Spike Lee MyCAREER. Cover: Stephen Curry, James Harden, Anthony Davis
- NBA 2K17 (2016) - Pure basketball soul. Cover: Paul George
- NBA 2K20 (2019) - The final masterpiece before the current era. Cover: Anthony Davis

## HOW LICENSING GETS SOLVED
Expired music, jerseys, and player likenesses handled through modular asset layers inside each container. Core gameplay code stays untouched.

## HOW IT SCALES (KUBERNETES)
Kubernetes orchestration. Each title runs in its own isolated container. Elastic scaling. Same architecture Netflix, Spotify, and Epic Games use.

## RESPONSE STYLE
- Be conversational and approachable
- Use clear, professional language — no asterisks or markdown formatting
- Provide thorough answers with supporting details
- End responses helpfully — ask if they need more detail or have other questions"""

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')

chat_sessions = {}

def identify_platform(url: str) -> str:
    url_lower = url.lower()
    if 'tiktok.com' in url_lower: return 'tiktok'
    elif 'twitter.com' in url_lower or 'x.com' in url_lower: return 'twitter'
    elif 'instagram.com' in url_lower: return 'instagram'
    elif 'reddit.com' in url_lower: return 'reddit'
    elif 'youtube.com' in url_lower or 'youtu.be' in url_lower: return 'youtube'
    else: return 'generic'

async def fetch_url_content(url: str) -> str:
    platform = identify_platform(url)
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            parts = [f"[PLATFORM: {platform.upper()}] [URL: {url}]"]
            title = soup.find('title')
            if title:
                parts.append(f"[TITLE: {title.get_text(strip=True)}]")
            og_desc = soup.find('meta', property='og:description')
            if og_desc:
                parts.append(f"[DESCRIPTION: {og_desc.get('content', '')}]")
            return " ".join(parts)
    except Exception as e:
        return f"[Could not fetch {url}: {str(e)}]"

def get_anthropic_client():
    """Get Anthropic client using Replit AI Integration if available, else fallback to direct key."""
    integration_base_url = os.environ.get('AI_INTEGRATIONS_ANTHROPIC_BASE_URL')
    integration_api_key = os.environ.get('AI_INTEGRATIONS_ANTHROPIC_API_KEY')
    direct_api_key = os.environ.get('ANTHROPIC_API_KEY')

    if integration_base_url and integration_api_key:
        return anthropic.Anthropic(api_key=integration_api_key, base_url=integration_base_url)
    elif direct_api_key:
        return anthropic.Anthropic(api_key=direct_api_key)
    else:
        raise RuntimeError("No Anthropic API credentials configured")

CHAT_MODEL = "claude-sonnet-4-5"

@api_router.post("/chat", response_model=ChatResponse)
async def chat_with_vault_ai(chat_message: ChatMessage, request: Request):
    ip = _get_client_ip(request)
    if not _check_chat_rate_limit(ip):
        raise HTTPException(status_code=429, detail="You've reached the chat limit (10 messages per hour). Please try again later!")
    session_id = chat_message.session_id or str(uuid.uuid4())
    user_msg = chat_message.message

    urls = URL_PATTERN.findall(user_msg)
    context_additions = []
    if urls:
        context_additions.append("\n\n--- LINK ANALYSIS ---")
        for url in urls[:3]:
            content = await fetch_url_content(url)
            context_additions.append(content)
        context_additions.append("--- END LINK ANALYSIS ---")

    full_message = user_msg + "".join(context_additions)

    if session_id not in chat_sessions:
        chat_sessions[session_id] = []
    chat_sessions[session_id].append({"role": "user", "content": full_message})

    last_error = None
    for attempt in range(3):
        try:
            client = get_anthropic_client()
            response = client.messages.create(
                model=CHAT_MODEL,
                max_tokens=800,
                system=VAULT_SYSTEM_PROMPT,
                messages=chat_sessions[session_id]
            )
            assistant_message = response.content[0].text
            chat_sessions[session_id].append({"role": "assistant", "content": assistant_message})
            if len(chat_sessions[session_id]) > 20:
                chat_sessions[session_id] = chat_sessions[session_id][-20:]
            return ChatResponse(response=assistant_message, session_id=session_id)
        except Exception as e:
            last_error = e
            logger.warning(f"Chat attempt {attempt + 1} failed: {str(e)}")
            if attempt < 2:
                import asyncio
                await asyncio.sleep(1)

    # All retries failed — pop the failed user message so session stays clean
    if chat_sessions.get(session_id):
        chat_sessions[session_id].pop()
    logger.error(f"Chat failed after 3 attempts: {str(last_error)}")
    raise HTTPException(status_code=500, detail=f"Chat error: {str(last_error)}")

# ============ ERA VOTING POLL ============

@api_router.get("/votes")
async def get_vote_results():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT game_id, COUNT(*) as count FROM votes GROUP BY game_id ORDER BY count DESC')
    results = cur.fetchall()
    total = sum(r["count"] for r in results)
    cur.close(); conn.close()
    return {"votes": {r["game_id"]: r["count"] for r in results}, "total": total}

@api_router.post("/votes")
async def cast_vote(vote: VoteCreate):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM games WHERE id = %s', (vote.game_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(status_code=400, detail="Invalid game selection")
    cur.execute('INSERT INTO votes (id, game_id, timestamp) VALUES (%s,%s,%s)',
                (str(uuid.uuid4()), vote.game_id, datetime.now(timezone.utc).isoformat()))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Vote recorded", "game_id": vote.game_id}

# ============ CREATOR SUBMISSIONS ============

@api_router.post("/creator-submissions")
async def submit_creator_content(submission: CreatorSubmission):
    now = datetime.now(timezone.utc).isoformat()
    sub_id = str(uuid.uuid4())
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''INSERT INTO creator_submissions (id, name, platform, profile_url, content_url, description, follower_count, status, submitted_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (sub_id, submission.name, submission.platform, submission.profile_url, submission.content_url,
                 submission.description, submission.follower_count, "pending", now))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Submission received! We'll review it soon.", "id": sub_id}

@api_router.get("/creator-submissions")
async def get_creator_submissions(status: Optional[str] = None):
    conn = get_db()
    cur = conn.cursor()
    if status:
        cur.execute('SELECT * FROM creator_submissions WHERE status = %s ORDER BY submitted_at DESC', (status,))
    else:
        cur.execute('SELECT * FROM creator_submissions ORDER BY submitted_at DESC')
    subs = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return subs

@api_router.put("/creator-submissions/{submission_id}")
async def update_submission_status(submission_id: str, status: str):
    if status not in ["pending", "approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE creator_submissions SET status = %s WHERE id = %s', (status, submission_id))
    conn.commit(); cur.close(); conn.close()
    return {"message": f"Submission {status}"}

# ============ COMMUNITY POSTS ============

@api_router.get("/community-posts")
async def get_community_posts():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM community_posts ORDER BY "order" ASC')
    posts = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return posts

@api_router.post("/community-posts")
async def create_community_post(post: CommunityPost):
    post_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''INSERT INTO community_posts (id, platform, author_name, author_handle, author_avatar, follower_count, content, post_url, screenshot_url, "order", created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (post_id, post.platform, post.author_name, post.author_handle, post.author_avatar, post.follower_count,
                 post.content, post.post_url, post.screenshot_url, post.order, now))
    conn.commit(); cur.close(); conn.close()
    return {**post.model_dump(), "id": post_id, "created_at": now}

@api_router.delete("/community-posts/{post_id}")
async def delete_community_post(post_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM community_posts WHERE id = %s', (post_id,))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Post deleted"}

# ============ SOCIAL FEED ============

@api_router.get("/social-feed")
async def get_social_feed():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM social_feed ORDER BY created_at DESC LIMIT 30')
    items = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return items

@api_router.post("/social-feed")
async def add_social_feed_item(item: SocialFeedItem):
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT INTO social_feed (id, platform, author, content, timestamp, url, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                (item_id, item.platform, item.author, item.content, item.timestamp, item.url, now))
    conn.commit(); cur.close(); conn.close()
    return {**item.model_dump(), "id": item_id, "created_at": now}

@api_router.delete("/social-feed/{item_id}")
async def delete_social_feed_item(item_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM social_feed WHERE id = %s', (item_id,))
    conn.commit(); cur.close(); conn.close()
    return {"message": "Item deleted"}

# ============ SITE EDITOR ROUTES (FULL AGENTIC IDE) ============

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SITE_ROOT = os.path.join(WORKSPACE_ROOT, "frontend")
BACKEND_ROOT = os.path.join(WORKSPACE_ROOT, "backend")

_IGNORE_DIRS = {'.git', 'node_modules', '__pycache__', 'dist', '.cache', 'venv', '.venv', '.replit-artifact', '.replit'}
_IGNORE_FILES = {'.DS_Store', 'package-lock.json', 'yarn.lock', '.gitignore', '.env'}
EDITOR_ALLOW_RUN_COMMAND = os.environ.get("EDITOR_ALLOW_RUN_COMMAND", "false").lower() in ("1", "true", "yes", "on")
EDITOR_ALLOWED_COMMAND_PREFIXES = (
    "pwd",
    "ls",
    "rg ",
    "cat ",
    "echo ",
    "python ",
    "python3 ",
    "pytest",
    "npm ",
    "pip ",
    "git status",
    "git diff",
)
_MAX_FILE_READ = 60000  # 60 KB cap for AI context

EDITOR_TOOLS = [
    {
        "name": "read_file",
        "description": "Read the full contents of any file in the project. Always read a file before editing it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to frontend/. Examples: 'src/pages/LandingPage.jsx', 'index.html', 'src/index.css'. To read a backend file prefix with '../nba-vault-backend/', e.g. '../nba-vault-backend/server.py'"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "list_directory",
        "description": "List files and folders in a directory to explore the project structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path relative to frontend/. Use '.' for site root, 'src' for source, 'src/pages' for pages, etc."}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write a file (create new or overwrite existing). Always read first if the file exists. Write COMPLETE file content — never partial snippets. Changes go live immediately via Vite hot-reload.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to frontend/. Use '../nba-vault-backend/server.py' for backend."},
                "content": {"type": "string", "description": "Complete new file content."},
                "description": {"type": "string", "description": "Plain-English description of what changed (for the non-technical admin)."}
            },
            "required": ["path", "content", "description"]
        }
    },
    {
        "name": "run_command",
        "description": "Run a shell command from the workspace root. Use for: installing packages (cd frontend && npm install <pkg>), build checks, or inspecting the environment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "description": {"type": "string", "description": "What this command does."}
            },
            "required": ["command", "description"]
        }
    }
]

AGENTIC_SYSTEM_PROMPT = """You are an expert full-stack web developer embedded in the admin panel of "NBA 2K Legacy Vault" — a React + Vite fan campaign site aimed at bringing back classic NBA 2K games.

PROJECT LAYOUT:
- Frontend: React + Vite + Tailwind CSS → frontend/
  - src/pages/LandingPage.jsx  (main page: hero, games, vault, community, petition)
  - src/pages/AdminPage.jsx    (this admin panel)
  - src/index.css              (global styles, custom Tailwind classes)
  - index.html                 (HTML shell, meta/OG tags)
  - src/App.tsx                (routing)
- Backend: FastAPI Python → backend/app/main.py
- Database: PostgreSQL (accessed via get_db() in server.py)

GOLDEN RULES:
1. Read relevant files BEFORE writing — understand existing code, don't guess
2. Write COMPLETE file content — every line, not just the changed parts
3. Preserve ALL existing features, API calls, state hooks, and event handlers
4. Keep the same code style (indentation, quotes, naming) as the existing file
5. For entirely new features: read the file structure first, then build minimally
6. When installing a package: use `cd frontend && npm install <pkg>` for frontend, `pip install <pkg>` for backend

COMMUNICATION:
- The user is NOT a developer. Explain what you're doing step-by-step in plain English
- After finishing, write a clear 2-3 sentence non-technical summary of what changed and how to see it
- If the task is ambiguous, make reasonable assumptions and explain them"""


def _safe_path(rel_path: str):
    """Resolve a path relative to SITE_ROOT and verify it stays within allowed roots."""
    clean = rel_path.lstrip("/")
    # Allow ../nba-vault-backend/ prefix for backend files
    if clean.startswith("../nba-vault-backend/"):
        abs_path = os.path.normpath(os.path.join(SITE_ROOT, clean))
    else:
        abs_path = os.path.normpath(os.path.join(SITE_ROOT, clean))

    if abs_path.startswith(os.path.normpath(SITE_ROOT)):
        return abs_path
    if abs_path.startswith(os.path.normpath(BACKEND_ROOT)):
        return abs_path
    return None


def _exec_tool(name: str, inputs: dict, steps: list, backups: list) -> str:
    if name == "read_file":
        rel = inputs.get("path", "").strip()
        full = _safe_path(rel)
        if not full:
            return "Error: Cannot access files outside the project."
        if not os.path.exists(full):
            return f"Error: File not found: {rel}"
        if os.path.isdir(full):
            return f"Error: '{rel}' is a directory. Use list_directory instead."
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            lines = len(content.splitlines())
            truncated = len(content) > _MAX_FILE_READ
            if truncated:
                content = content[:_MAX_FILE_READ]
            steps.append({"type": "read_file", "path": rel, "lines": lines, "truncated": truncated})
            return content + (f"\n\n[TRUNCATED at 60KB — total {lines} lines]" if truncated else "")
        except Exception as e:
            return f"Error reading file: {e}"

    elif name == "list_directory":
        rel = inputs.get("path", ".").strip()
        full = _safe_path(rel) if rel not in (".", "") else SITE_ROOT
        if not full or not os.path.exists(full) or not os.path.isdir(full):
            return f"Error: Directory not found: {rel}"
        try:
            items = []
            for name_ in sorted(os.listdir(full)):
                if name_ in _IGNORE_DIRS or name_ in _IGNORE_FILES or name_.startswith("."):
                    continue
                p = os.path.join(full, name_)
                if os.path.isdir(p):
                    items.append(f"📁 {name_}/")
                else:
                    kb = round(os.path.getsize(p) / 1024, 1)
                    items.append(f"📄 {name_} ({kb} KB)")
            steps.append({"type": "list_directory", "path": rel})
            return "\n".join(items) or "(empty directory)"
        except Exception as e:
            return f"Error listing directory: {e}"

    elif name == "write_file":
        rel = inputs.get("path", "").strip()
        content = inputs.get("content", "")
        description = inputs.get("description", "File updated")
        full = _safe_path(rel)
        if not full:
            return "Error: Cannot write files outside the project."
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            original = ""
            is_new = not os.path.exists(full)
            if not is_new:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    original = f.read()
                backups.append({
                    "file_key": rel,
                    "file_name": os.path.basename(full),
                    "file_path": full,
                    "original_content": original,
                    "change_description": description,
                })
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            lines = len(content.splitlines())
            steps.append({"type": "write_file", "path": rel, "description": description, "is_new": is_new})
            return f"✓ {'Created' if is_new else 'Updated'} {rel} ({lines} lines). Site hot-reloads automatically."
        except Exception as e:
            return f"Error writing file: {e}"

    elif name == "run_command":
        command = inputs.get("command", "")
        description = inputs.get("description", "")
        if not EDITOR_ALLOW_RUN_COMMAND:
            return "run_command is disabled by server policy (set EDITOR_ALLOW_RUN_COMMAND=true to enable)."
        if not any(command.strip().startswith(prefix) for prefix in EDITOR_ALLOWED_COMMAND_PREFIXES):
            return "Command blocked by policy. Allowed prefixes: " + ", ".join(EDITOR_ALLOWED_COMMAND_PREFIXES)
        try:
            result = _subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=120, cwd=WORKSPACE_ROOT
            )
            output = (result.stdout + "\n" + result.stderr).strip() or f"Done (exit {result.returncode})"
            steps.append({"type": "run_command", "command": command, "description": description,
                          "output": output[:3000], "success": result.returncode == 0})
            return output[:5000]
        except _subprocess.TimeoutExpired:
            return "Command timed out after 120 seconds."
        except Exception as e:
            return f"Error: {e}"

    return f"Unknown tool: {name}"


class AgenticRequest(BaseModel):
    message: str
    history: list = Field(default_factory=list)


@api_router.post("/admin/editor/agentic")
async def agentic_editor(req: AgenticRequest):
    steps = []
    backups_to_save = []

    messages = list(req.history)
    messages.append({"role": "user", "content": req.message})

    try:
        client = get_anthropic_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI not available: {e}")

    response_texts = []

    for _iteration in range(15):
        try:
            response = client.messages.create(
                model=CHAT_MODEL,
                max_tokens=800,
                system=AGENTIC_SYSTEM_PROMPT,
                tools=EDITOR_TOOLS,
                messages=messages,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"AI call failed: {e}")

        tool_calls = []
        for block in response.content:
            if hasattr(block, "type"):
                if block.type == "text" and block.text.strip():
                    response_texts.append(block.text)
                    steps.append({"type": "text", "content": block.text})
                elif block.type == "tool_use":
                    tool_calls.append(block)

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn" or not tool_calls:
            break

        tool_results = []
        for tc in tool_calls:
            result = _exec_tool(tc.name, tc.input, steps, backups_to_save)
            tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": result})

        messages.append({"role": "user", "content": tool_results})

    # Persist backups
    if backups_to_save:
        try:
            conn = get_db()
            cur = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            for b in backups_to_save:
                cur.execute(
                    'INSERT INTO file_backups (id, file_key, file_name, file_path, original_content, change_description, backed_up_at) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                    (str(uuid.uuid4()), b["file_key"], b["file_name"], b["file_path"], b["original_content"], b["change_description"], now)
                )
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            logger.warning(f"Backup save failed: {e}")

    # Serialize history (Anthropic objects → dicts)
    serial_history = []
    for msg in messages[-20:]:
        if isinstance(msg["content"], list):
            content = []
            for blk in msg["content"]:
                content.append(blk.model_dump() if hasattr(blk, "model_dump") else blk)
            serial_history.append({"role": msg["role"], "content": content})
        else:
            serial_history.append({"role": msg["role"], "content": msg["content"]})

    files_changed_names = [b["file_name"] for b in backups_to_save]
    if files_changed_names:
        _log_event("site_editor", "files_changed",
                   f"Files: {files_changed_names} | Prompt: {req.message[:120]}", "ok")
    return {
        "steps": steps,
        "response_text": "\n\n".join(response_texts),
        "history": serial_history,
        "files_changed": len(backups_to_save),
    }


def _build_tree(root: str, base: str, depth=0, max_depth=5):
    items = []
    try:
        for name in sorted(os.listdir(root)):
            if name in _IGNORE_DIRS or name in _IGNORE_FILES or name.startswith("."):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, base)
            if os.path.isdir(full):
                children = _build_tree(full, base, depth + 1, max_depth) if depth < max_depth else []
                items.append({"name": name, "path": rel, "type": "dir", "children": children})
            else:
                items.append({"name": name, "path": rel, "type": "file", "size_kb": round(os.path.getsize(full) / 1024, 1)})
    except PermissionError:
        pass
    return items


@api_router.get("/admin/editor/tree")
async def get_editor_tree():
    return {"children": _build_tree(SITE_ROOT, SITE_ROOT)}


@api_router.get("/admin/editor/file")
async def get_editor_file(path: str):
    full = _safe_path(path)
    if not full:
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"path": path, "name": os.path.basename(full), "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/editor/backups")
async def list_editor_backups():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, file_key, file_name, change_description, backed_up_at FROM file_backups ORDER BY backed_up_at DESC LIMIT 50')
    rows = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return rows


@api_router.post("/admin/editor/revert/{backup_id}")
async def revert_editor_backup(backup_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM file_backups WHERE id = %s', (backup_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Backup not found")
    backup = dict(row)
    cur.close(); conn.close()
    try:
        with open(backup["file_path"], "w", encoding="utf-8") as f:
            f.write(backup["original_content"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not restore: {e}")
    return {"success": True, "message": f"Reverted {backup['file_name']}"}



# ============ DEPLOYMENT MANAGER ROUTES ============

_deploy_jobs = {}  # job_id -> {status, logs, platform, url, error, started_at, finished_at}
_SENSITIVE_KEYS = {"GITHUB_TOKEN", "NETLIFY_TOKEN", "VERCEL_TOKEN"}


def _get_config(key: str):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT value FROM deployment_config WHERE key = %s", (key,))
        row = cur.fetchone()
        cur.close(); conn.close()
        return dict(row)["value"] if row else None
    except Exception:
        return None


def _set_config(key: str, value: str):
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO deployment_config (key, value, updated_at) VALUES (%s, %s, NOW()) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
        (key, value)
    )
    conn.commit(); cur.close(); conn.close()


def _get_all_config() -> dict:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT key, value FROM deployment_config")
    rows = cur.fetchall()
    cur.close(); conn.close()
    result = {}
    for row in rows:
        d = dict(row)
        result[d["key"]] = "***" if d["key"] in _SENSITIVE_KEYS else d["value"]
    return result


def _build_site(log_fn):
    log_fn("Building site with Vite...")
    build_env = {**os.environ, "PORT": "20187", "BASE_PATH": "/", "NODE_ENV": "production"}
    result = _subprocess.run(
        "cd frontend && npm run build",
        shell=True, capture_output=True, text=True, timeout=180, cwd=WORKSPACE_ROOT,
        env=build_env
    )
    if result.returncode != 0:
        raise Exception("Build failed:\n" + (result.stderr or result.stdout)[-2000:])
    dist = os.path.join(SITE_ROOT, "dist")
    file_count = sum(len(files) for _, _, files in os.walk(dist))
    log_fn(f"Build complete. {file_count} files ready to deploy.")


def _deploy_github(config: dict, log_fn) -> str:
    import tempfile as _tempfile, shutil as _shutil
    token = config["GITHUB_TOKEN"]
    username = config["GITHUB_USERNAME"]
    repo = config["GITHUB_REPO"]
    custom_domain = config.get("CUSTOM_DOMAIN", "")
    dist_dir = os.path.join(SITE_ROOT, "dist")
    tmpdir = _tempfile.mkdtemp(prefix="gh_deploy_")
    repo_dir = os.path.join(tmpdir, "repo")
    try:
        repo_url = f"https://x-access-token:{token}@github.com/{username}/{repo}.git"
        log_fn(f"Connecting to github.com/{username}/{repo}...")
        clone_cmd = ["git", "clone", "--branch", "gh-pages", "--depth", "1", repo_url, repo_dir]
        clone = _subprocess.run(clone_cmd, capture_output=True, text=True, timeout=60)
        if clone.returncode != 0:
            log_fn("gh-pages branch not found — creating orphan branch...")
            os.makedirs(repo_dir)
            _subprocess.run(["git", "init", repo_dir], capture_output=True)
            _subprocess.run(["git", "-C", repo_dir, "checkout", "--orphan", "gh-pages"], capture_output=True)
            _subprocess.run(["git", "-C", repo_dir, "remote", "add", "origin", repo_url], capture_output=True)
        else:
            log_fn("Clearing existing gh-pages content...")
            _subprocess.run(["git", "-C", repo_dir, "rm", "-rf", "--quiet", "."], capture_output=True)
        log_fn("Copying build output to repository...")
        _shutil.copytree(dist_dir, repo_dir, dirs_exist_ok=True)
        if custom_domain:
            with open(os.path.join(repo_dir, "CNAME"), "w") as f:
                f.write(custom_domain.strip())
        log_fn("Committing changes...")
        for cmd in [
            ["git", "-C", repo_dir, "config", "user.email", "deploy@nba2kvault.com"],
            ["git", "-C", repo_dir, "config", "user.name", "NBA Vault Deploy"],
            ["git", "-C", repo_dir, "add", "-A"],
            ["git", "-C", repo_dir, "commit", "-m", "Deploy: NBA 2K Legacy Vault"],
        ]:
            _subprocess.run(cmd, capture_output=True)
        log_fn("Pushing to GitHub...")
        push = _subprocess.run(["git", "-C", repo_dir, "push", "--force", "origin", "gh-pages"],
            capture_output=True, text=True, timeout=60)
        if push.returncode != 0:
            raise Exception(f"Push failed: {push.stderr[:500]}")
        # Enable GitHub Pages via API (ignore errors — might already be enabled)
        try:
            httpx.post(
                f"https://api.github.com/repos/{username}/{repo}/pages",
                headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
                json={"source": {"branch": "gh-pages", "path": "/"}}, timeout=15
            )
        except Exception:
            pass
        url = f"https://{custom_domain}" if custom_domain else f"https://{username}.github.io/{repo}"
        log_fn(f"Live at: {url}")
        return url
    finally:
        _shutil.rmtree(tmpdir, ignore_errors=True)


def _deploy_netlify(config: dict, log_fn) -> str:
    token = config["NETLIFY_TOKEN"]
    site_id = config.get("NETLIFY_SITE_ID", "")
    custom_domain = config.get("CUSTOM_DOMAIN", "")
    dist_dir = os.path.join(SITE_ROOT, "dist")
    headers = {"Authorization": f"Bearer {token}"}
    if not site_id:
        log_fn("Creating new Netlify site...")
        body = {"name": "nba-vault-legacy"}
        if custom_domain:
            body["custom_domain"] = custom_domain
        resp = httpx.post("https://api.netlify.com/api/v1/sites", headers=headers, json=body, timeout=30)
        if resp.status_code not in (200, 201):
            raise Exception(f"Could not create Netlify site: {resp.status_code} {resp.text[:400]}")
        site_data = resp.json()
        site_id = site_data["id"]
        _set_config("NETLIFY_SITE_ID", site_id)
        log_fn(f"Site created: {site_data.get('url', site_id)}")
    else:
        log_fn(f"Using existing Netlify site: {site_id}")
    log_fn("Packaging build output as zip...")
    import tempfile as _tempfile
    zip_path = os.path.join(_tempfile.mkdtemp(), "deploy.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(dist_dir):
            for fn in files:
                fp = os.path.join(root, fn)
                zf.write(fp, os.path.relpath(fp, dist_dir))
    with open(zip_path, "rb") as f:
        zip_data = f.read()
    log_fn(f"Uploading {round(len(zip_data)/1024, 1)} KB to Netlify...")
    deploy_resp = httpx.post(
        f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
        headers={**headers, "Content-Type": "application/zip"},
        content=zip_data, timeout=180
    )
    if deploy_resp.status_code not in (200, 201):
        raise Exception(f"Netlify deploy failed: {deploy_resp.status_code} {deploy_resp.text[:400]}")
    deploy_data = deploy_resp.json()
    deploy_id = deploy_data.get("id")
    log_fn("Waiting for Netlify to process deployment...")
    for _ in range(24):
        time.sleep(5)
        s = httpx.get(f"https://api.netlify.com/api/v1/deploys/{deploy_id}", headers=headers, timeout=15)
        state = s.json().get("state", "unknown")
        log_fn(f"  Status: {state}")
        if state == "ready":
            break
        if state in ("error", "failed"):
            raise Exception(f"Netlify deployment failed with state={state}")
    url = deploy_data.get("deploy_ssl_url") or deploy_data.get("url") or f"https://{site_id}.netlify.app"
    log_fn(f"Live at: {url}")
    return url


def _deploy_vercel(config: dict, log_fn) -> str:
    token = config["VERCEL_TOKEN"]
    project_name = config.get("VERCEL_PROJECT_NAME", "nba-vault-legacy")
    custom_domain = config.get("CUSTOM_DOMAIN", "")
    dist_dir = os.path.join(SITE_ROOT, "dist")
    headers = {"Authorization": f"Bearer {token}"}
    log_fn("Collecting build files...")
    files_meta = []
    files_data = {}
    for root, dirs, file_list in os.walk(dist_dir):
        for fn in file_list:
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, dist_dir)
            with open(fp, "rb") as f:
                data = f.read()
            sha = hashlib.sha1(data).hexdigest()
            files_meta.append({"file": rel, "sha": sha, "size": len(data)})
            files_data[sha] = data
    log_fn(f"Uploading {len(files_meta)} files to Vercel...")
    for meta in files_meta:
        httpx.post(
            "https://api.vercel.com/v2/files",
            headers={**headers, "x-vercel-digest": meta["sha"], "Content-Type": "application/octet-stream"},
            content=files_data[meta["sha"]], timeout=30
        )
    log_fn("Creating Vercel deployment...")
    deploy_payload = {
        "name": project_name,
        "files": [{"file": m["file"], "sha": m["sha"], "size": m["size"]} for m in files_meta],
        "projectSettings": {"framework": None},
        "target": "production",
    }
    resp = httpx.post("https://api.vercel.com/v13/deployments", headers=headers, json=deploy_payload, timeout=60)
    if resp.status_code not in (200, 201):
        raise Exception(f"Vercel deploy failed: {resp.status_code} {resp.text[:400]}")
    deploy_data = resp.json()
    deploy_url = deploy_data.get("url", "")
    log_fn(f"Deployment queued: https://{deploy_url}")
    dep_id = deploy_data.get("id")
    log_fn("Waiting for deployment to go live...")
    for _ in range(30):
        time.sleep(5)
        s = httpx.get(f"https://api.vercel.com/v13/deployments/{dep_id}", headers=headers, timeout=15)
        state = s.json().get("readyState", "UNKNOWN")
        log_fn(f"  Status: {state}")
        if state == "READY":
            break
        if state in ("ERROR", "CANCELED"):
            raise Exception(f"Vercel deployment failed (state={state})")
    if custom_domain:
        try:
            project_id = deploy_data.get("projectId")
            if project_id:
                httpx.post(f"https://api.vercel.com/v10/projects/{project_id}/domains",
                    headers=headers, json={"name": custom_domain}, timeout=15)
                log_fn(f"Custom domain {custom_domain} added (DNS setup required in your domain registrar)")
        except Exception as e:
            log_fn(f"Note: Could not auto-add custom domain: {e}")
    url = f"https://{deploy_url}"
    log_fn(f"Live at: {url}")
    return url


_DEPLOY_TIMEOUT_SECONDS = 600

def _persist_job(job_id: str, platform: str, status: str, logs: list, url=None, error=None, started_at=None, finished_at=None):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute(
            """INSERT INTO deployment_history (id, platform, status, url, error_message, logs, started_at, finished_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status, url=EXCLUDED.url,
               error_message=EXCLUDED.error_message, logs=EXCLUDED.logs, finished_at=EXCLUDED.finished_at""",
            (job_id, platform, status, url, error, json.dumps(logs), started_at, finished_at)
        )
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        logger.warning(f"Job persist failed: {e}")

def _run_deployment_job(job_id: str, platform: str, config: dict):
    job = _deploy_jobs[job_id]
    start_time = time.time()
    def log(msg: str):
        job["logs"].append({"ts": datetime.now(timezone.utc).isoformat(), "msg": msg})
        _persist_job(job_id, platform, job["status"], job["logs"], job.get("url"), job.get("error"), job["started_at"], job.get("finished_at"))
        if time.time() - start_time > _DEPLOY_TIMEOUT_SECONDS:
            raise Exception("Deployment timed out after 10 minutes.")
    try:
        log(f"Starting {platform.upper()} deployment...")
        _build_site(log)
        job["status"] = "deploying"
        if platform == "github":
            url = _deploy_github(config, log)
        elif platform == "netlify":
            url = _deploy_netlify(config, log)
        elif platform == "vercel":
            url = _deploy_vercel(config, log)
        else:
            raise Exception(f"Unknown platform: {platform}")
        job["status"] = "done"
        job["url"] = url
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        log("Deployment complete!")
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        log(f"Error: {str(e)}")
    _persist_job(job_id, platform, "success" if job["status"] == "done" else "error", job["logs"], job.get("url"), job.get("error"), job["started_at"], job.get("finished_at"))


class DeployConfigRequest(BaseModel):
    key: str
    value: str

class DeployStartRequest(BaseModel):
    platform: str


@api_router.get("/admin/deploy/config")
async def get_deploy_config():
    return _get_all_config()

@api_router.post("/admin/deploy/config")
async def set_deploy_config(req: DeployConfigRequest):
    _set_config(req.key, req.value)
    return {"success": True}

@api_router.delete("/admin/deploy/config/{key}")
async def delete_deploy_config(key: str):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM deployment_config WHERE key = %s", (key,))
    conn.commit(); cur.close(); conn.close()
    return {"success": True}

@api_router.post("/admin/deploy/start")
async def start_deployment(req: DeployStartRequest):
    platform = req.platform.lower()
    if platform not in ("github", "netlify", "vercel"):
        raise HTTPException(status_code=400, detail="Invalid platform")
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT key, value FROM deployment_config")
    config = {dict(r)["key"]: dict(r)["value"] for r in cur.fetchall()}
    cur.close(); conn.close()
    required = {
        "github": ["GITHUB_TOKEN", "GITHUB_USERNAME", "GITHUB_REPO"],
        "netlify": ["NETLIFY_TOKEN"],
        "vercel": ["VERCEL_TOKEN"],
    }
    missing = [k for k in required[platform] if not config.get(k)]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing: {missing}")
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    _deploy_jobs[job_id] = {
        "id": job_id, "platform": platform, "status": "building",
        "logs": [], "url": None, "error": None,
        "started_at": now, "finished_at": None,
    }
    t = threading.Thread(target=_run_deployment_job, args=(job_id, platform, config), daemon=True)
    t.start()
    _log_event("deploy", "frontend_deploy_started", f"Platform: {platform} | Job: {job_id}", "ok")
    return {"job_id": job_id, "status": "building"}

@api_router.get("/admin/deploy/status/{job_id}")
async def get_deployment_status(job_id: str):
    job = _deploy_jobs.get(job_id)
    if job:
        return job
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT id, platform, status, url, error_message, logs, started_at, finished_at FROM deployment_history WHERE id = %s", (job_id,))
        row = cur.fetchone()
        if row:
            r = dict(row)
            logs = []
            try:
                logs = json.loads(r.get("logs") or "[]")
            except Exception:
                pass
            status = r["status"]
            error = r.get("error_message")
            if status in ("building", "deploying"):
                started = r.get("started_at")
                if started:
                    elapsed = (datetime.now(timezone.utc) - started).total_seconds() if hasattr(started, 'total_seconds') else (datetime.now(timezone.utc) - started).total_seconds()
                    if elapsed > _DEPLOY_TIMEOUT_SECONDS:
                        status = "error"
                        error = "Deployment timed out — the server may have restarted during the build."
                        cur.execute("UPDATE deployment_history SET status='error', error_message=%s, finished_at=NOW() WHERE id=%s", (error, job_id))
                        conn.commit()
            cur.close(); conn.close()
            return {
                "id": r["id"], "platform": r["platform"],
                "status": "done" if status == "success" else status,
                "logs": logs, "url": r.get("url"),
                "error": error,
                "started_at": str(r["started_at"]) if r.get("started_at") else None,
                "finished_at": str(r["finished_at"]) if r.get("finished_at") else None,
            }
        cur.close(); conn.close()
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Job not found")

@api_router.get("/admin/deploy/history")
async def get_deployment_history():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM deployment_history ORDER BY started_at DESC LIMIT 20")
    rows = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return rows

@api_router.post("/admin/deploy/build-only")
async def build_only():
    build_env = {**os.environ, "PORT": "20187", "BASE_PATH": "/", "NODE_ENV": "production"}
    result = _subprocess.run(
        "cd frontend && npm run build",
        shell=True, capture_output=True, text=True, timeout=180, cwd=WORKSPACE_ROOT,
        env=build_env
    )
    output = (result.stdout + "\n" + result.stderr).strip()
    return {
        "success": result.returncode == 0,
        "output": output[-5000:],
        "dist_exists": os.path.isdir(os.path.join(SITE_ROOT, "dist")),
    }

# ============ HEALTH ENDPOINTS ============

@api_router.get("/admin/health")
async def get_health():
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM health_checks ORDER BY component")
        checks = rows_to_list(cur.fetchall())
        cur.close(); conn.close()
        return checks
    except Exception as e:
        return [{"component": "database", "status": "error", "message": str(e), "response_ms": -1, "checked_at": None}]

@api_router.post("/admin/health/check")
async def trigger_health_check():
    threading.Thread(target=_run_health_checks, daemon=True).start()
    _log_event("health", "manual_check_triggered", "Manual health check started by admin", "ok")
    return {"message": "Health check triggered"}

# ============ SUGGESTIONS ENDPOINTS ============

@api_router.get("/admin/suggestions")
async def get_suggestions():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM suggestions ORDER BY generated_at DESC LIMIT 100")
    suggestions = rows_to_list(cur.fetchall())
    cur.execute("UPDATE suggestions SET is_new = FALSE")
    conn.commit(); cur.close(); conn.close()
    return suggestions

@api_router.post("/admin/suggestions/generate")
async def generate_suggestions_now():
    threading.Thread(target=_run_suggestions_safe, daemon=True).start()
    _log_event("suggestions", "generate_triggered", "Admin triggered AI suggestion generation", "ok")
    return {"message": "Generating suggestions in background — check back in 30 seconds"}

@api_router.delete("/admin/suggestions/{suggestion_id}")
async def delete_suggestion(suggestion_id: str):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM suggestions WHERE id = %s", (suggestion_id,))
    conn.commit(); cur.close(); conn.close()
    return {"deleted": True}

@api_router.delete("/admin/suggestions")
async def clear_all_suggestions():
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM suggestions")
    conn.commit(); cur.close(); conn.close()
    return {"cleared": True}

# ============ EDITOR CONVERSATION HISTORY ============

@api_router.post("/admin/editor/conversation/save")
async def save_editor_message(data: dict = Body(...)):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""INSERT INTO editor_conversations (id, role, content, steps, files_changed, session_id, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,NOW())""",
                (str(uuid.uuid4()), data.get("role","user"), data.get("content",""),
                 json.dumps(data.get("steps",[])), data.get("files_changed",0),
                 data.get("session_id","legacy")))
    conn.commit(); cur.close(); conn.close()
    return {"saved": True}

@api_router.get("/admin/editor/sessions")
async def get_editor_sessions(search: str = ""):
    conn = get_db(); cur = conn.cursor()
    params = ()
    if search:
        params = (f"%{search}%",)
        cur.execute("""
            SELECT s.session_id, s.started_at, s.last_active, s.message_count,
                   s.files_changed_total, ft.content AS title
            FROM (
                SELECT session_id,
                       MIN(created_at) AS started_at,
                       MAX(created_at) AS last_active,
                       COUNT(*) AS message_count,
                       COALESCE(SUM(files_changed),0) AS files_changed_total
                FROM editor_conversations
                WHERE session_id IN (
                    SELECT DISTINCT session_id FROM editor_conversations WHERE content ILIKE %s
                )
                GROUP BY session_id
            ) s
            LEFT JOIN LATERAL (
                SELECT content FROM editor_conversations
                WHERE session_id = s.session_id AND role = 'user'
                ORDER BY created_at ASC LIMIT 1
            ) ft ON TRUE
            ORDER BY s.last_active DESC
            LIMIT 100
        """, params)
    else:
        cur.execute("""
            SELECT s.session_id, s.started_at, s.last_active, s.message_count,
                   s.files_changed_total, ft.content AS title
            FROM (
                SELECT session_id,
                       MIN(created_at) AS started_at,
                       MAX(created_at) AS last_active,
                       COUNT(*) AS message_count,
                       COALESCE(SUM(files_changed),0) AS files_changed_total
                FROM editor_conversations
                GROUP BY session_id
            ) s
            LEFT JOIN LATERAL (
                SELECT content FROM editor_conversations
                WHERE session_id = s.session_id AND role = 'user'
                ORDER BY created_at ASC LIMIT 1
            ) ft ON TRUE
            ORDER BY s.last_active DESC
            LIMIT 100
        """)
    sessions = rows_to_list(cur.fetchall())
    for s in sessions:
        if s.get("session_id") == "legacy":
            s["title"] = "Earlier conversations"
        elif s.get("title") and len(s["title"]) > 80:
            s["title"] = s["title"][:80] + "…"
        elif not s.get("title"):
            s["title"] = "Untitled conversation"
    cur.close(); conn.close()
    return sessions

@api_router.get("/admin/editor/sessions/{session_id}")
async def get_editor_session_messages(session_id: str):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM editor_conversations WHERE session_id = %s ORDER BY created_at ASC", (session_id,))
    msgs = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return msgs

@api_router.get("/admin/editor/conversations")
async def get_editor_conversations(search: str = ""):
    conn = get_db(); cur = conn.cursor()
    if search:
        cur.execute("SELECT * FROM editor_conversations WHERE content ILIKE %s ORDER BY created_at DESC LIMIT 200",
                    (f"%{search}%",))
    else:
        cur.execute("SELECT * FROM editor_conversations ORDER BY created_at DESC LIMIT 200")
    convs = rows_to_list(cur.fetchall())
    cur.close(); conn.close()
    return convs

@api_router.delete("/admin/editor/conversations")
async def clear_editor_conversations():
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM editor_conversations")
    conn.commit(); cur.close(); conn.close()
    return {"cleared": True}

# ============ BACKEND DEPLOYMENT PLATFORMS ============

BACKEND_PLATFORMS = {
    "render": {
        "id": "render", "name": "Render", "color": "#46E3B7",
        "tagline": "750 free hours/month + managed PostgreSQL",
        "best_for": "FastAPI, Flask, Django — full Python apps",
        "free_limit": "750 hrs/month, 512MB RAM, sleeps after 15min inactivity",
        "requirements": [
            {"key": "RENDER_API_KEY", "label": "Render API Key", "type": "password",
             "hint": "Go to dashboard.render.com → Account Settings → API Keys → Add API Key → copy it"},
            {"key": "RENDER_SERVICE_ID", "label": "Render Service ID", "type": "text",
             "hint": "Create a Web Service on Render. Find the service ID (starts with 'srv-') in the service URL or Settings → Service ID"},
        ],
        "optional": [
            {"key": "UPTIMEROBOT_API_KEY", "label": "UptimeRobot API Key (optional — prevents sleeping)", "type": "password",
             "hint": "Go to uptimerobot.com → My Settings → API Settings → Main API Key. This sets up a free ping every 5 min to keep your backend awake."},
        ]
    },
    "railway": {
        "id": "railway", "name": "Railway", "color": "#B247FF",
        "tagline": "$5 free credits/month, modern deploys",
        "best_for": "Any stack, built-in databases, zero config",
        "free_limit": "$5 credit/month, ~500 hrs at minimal usage",
        "requirements": [
            {"key": "RAILWAY_TOKEN", "label": "Railway API Token", "type": "password",
             "hint": "Go to railway.app → Account Settings → Tokens → New Token → copy it"},
            {"key": "RAILWAY_PROJECT_ID", "label": "Railway Project ID", "type": "text",
             "hint": "Create a project at railway.app → click your project → Settings → Project ID"},
        ],
        "optional": [
            {"key": "UPTIMEROBOT_API_KEY", "label": "UptimeRobot API Key (optional)", "type": "password",
             "hint": "Prevents backend from sleeping. uptimerobot.com → My Settings → API Settings → Main API Key"},
        ]
    },
    "leapcell": {
        "id": "leapcell", "name": "Leapcell", "color": "#FF6B35",
        "tagline": "Serverless, up to 20 services free",
        "best_for": "Serverless Python, pay-per-request",
        "free_limit": "20 free services, 1M requests/month",
        "requirements": [
            {"key": "LEAPCELL_API_KEY", "label": "Leapcell API Key", "type": "password",
             "hint": "Go to leapcell.io → Settings → API Keys → Create new key"},
        ],
        "optional": []
    },
    "supabase": {
        "id": "supabase", "name": "Supabase", "color": "#3ECF8E",
        "tagline": "Managed PostgreSQL + Auth + Edge Functions",
        "best_for": "Database migration, realtime, auth",
        "free_limit": "500MB DB, unlimited API calls, 2 projects",
        "requirements": [
            {"key": "SUPABASE_URL", "label": "Supabase Project URL", "type": "text",
             "hint": "Go to app.supabase.com → your project → Settings → API → Project URL"},
            {"key": "SUPABASE_ANON_KEY", "label": "Supabase Anon Key", "type": "password",
             "hint": "Go to app.supabase.com → your project → Settings → API → anon/public key"},
        ],
        "optional": []
    },
    "vercel_func": {
        "id": "vercel_func", "name": "Vercel Functions", "color": "#ffffff",
        "tagline": "Serverless Python functions on Vercel",
        "best_for": "API endpoints as serverless functions",
        "free_limit": "100GB bandwidth, unlimited requests, 10s timeout",
        "requirements": [
            {"key": "VERCEL_TOKEN", "label": "Vercel API Token", "type": "password",
             "hint": "Go to vercel.com → Settings → Tokens → Create → copy it"},
        ],
        "optional": []
    },
}

@api_router.get("/admin/deploy/backend/platforms")
async def get_backend_platforms():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT key, value FROM deployment_config")
    stored = {r["key"]: "***" for r in cur.fetchall()}
    cur.close(); conn.close()
    result = {}
    for pid, pl in BACKEND_PLATFORMS.items():
        reqs = pl["requirements"]
        configured = sum(1 for r in reqs if stored.get(r["key"]))
        result[pid] = {**pl, "configured": configured, "total_required": len(reqs), "ready": configured == len(reqs)}
    return result

@api_router.post("/admin/deploy/backend/start")
async def start_backend_deploy(data: dict = Body(...)):
    platform = data.get("platform")
    job_id = str(uuid.uuid4())

    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT key, value FROM deployment_config")
    config = {r["key"]: r["value"] for r in cur.fetchall()}
    cur.execute("INSERT INTO deployment_history (id, platform, status, logs, started_at) VALUES (%s,%s,'building','[]',NOW())",
                (job_id, f"backend:{platform}"))
    conn.commit(); cur.close(); conn.close()

    def log(msg):
        try:
            conn2 = get_db(); cur2 = conn2.cursor()
            cur2.execute("SELECT logs FROM deployment_history WHERE id=%s", (job_id,))
            row = cur2.fetchone()
            logs = json.loads(row["logs"] if row else "[]")
            logs.append({"ts": datetime.now(timezone.utc).isoformat(), "msg": msg})
            cur2.execute("UPDATE deployment_history SET logs=%s WHERE id=%s", (json.dumps(logs), job_id))
            conn2.commit(); cur2.close(); conn2.close()
        except Exception:
            pass

    def run_backend_deploy():
        try:
            if platform == "render":
                api_key = config.get("RENDER_API_KEY")
                service_id = config.get("RENDER_SERVICE_ID")
                if not api_key or not service_id:
                    raise Exception("Render API Key and Service ID are required")
                log("Triggering Render deployment...")
                import urllib.request as _ur, urllib.error
                req = _ur.Request(
                    f"https://api.render.com/v1/services/{service_id}/deploys",
                    data=json.dumps({"clearCache": "do_not_clear"}).encode(),
                    headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json",
                             "Content-Type": "application/json"},
                    method="POST"
                )
                try:
                    with _ur.urlopen(req, timeout=30) as resp:
                        deploy_data = json.loads(resp.read())
                    render_deploy_id = deploy_data.get("id", "")
                    log(f"Render deploy triggered (id: {render_deploy_id})")
                    log("Waiting for deployment to complete...")
                    # Poll for status
                    for i in range(30):
                        time.sleep(10)
                        try:
                            status_req = _ur.Request(
                                f"https://api.render.com/v1/deploys/{render_deploy_id}",
                                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
                            )
                            with _ur.urlopen(status_req, timeout=15) as sr:
                                status_data = json.loads(sr.read())
                            status = status_data.get("status", "")
                            log(f"Status: {status} ({(i+1)*10}s elapsed)")
                            if status == "live":
                                deploy_url = f"https://dashboard.render.com/web/{service_id}"
                                # Setup UptimeRobot if key provided
                                utr_key = config.get("UPTIMEROBOT_API_KEY")
                                if utr_key:
                                    log("Setting up UptimeRobot ping to prevent sleeping...")
                                    try:
                                        _setup_uptimerobot(utr_key, deploy_url, "NBA Vault Backend")
                                        log("UptimeRobot monitor created — backend will stay awake")
                                    except Exception as ue:
                                        log(f"UptimeRobot setup note: {ue}")
                                conn3 = get_db(); cur3 = conn3.cursor()
                                cur3.execute("UPDATE deployment_history SET status='success', url=%s, finished_at=NOW() WHERE id=%s",
                                             (deploy_url, job_id))
                                conn3.commit(); cur3.close(); conn3.close()
                                log(f"Live at {deploy_url}")
                                _deploy_jobs[job_id] = {"id": job_id, "status": "done", "url": deploy_url, "logs": []}
                                return
                            elif status in ("build_failed", "deactivated", "canceled"):
                                raise Exception(f"Render deploy failed with status: {status}")
                        except Exception as pe:
                            if "build_failed" in str(pe) or "deactivated" in str(pe):
                                raise
                    raise Exception("Deployment timed out after 5 minutes")
                except urllib.error.HTTPError as he:
                    raise Exception(f"Render API error {he.code}: {he.read().decode()[:200]}")
            else:
                log(f"Platform '{platform}' deploy: credentials stored. Follow the platform's dashboard to deploy.")
                log("Tip: Use the credentials you configured to set up your service manually.")
                log("UptimeRobot ping: set UPTIMEROBOT_API_KEY to auto-configure uptime monitoring.")
                conn3 = get_db(); cur3 = conn3.cursor()
                cur3.execute("UPDATE deployment_history SET status='success', url='See platform dashboard', finished_at=NOW() WHERE id=%s", (job_id,))
                conn3.commit(); cur3.close(); conn3.close()
                _deploy_jobs[job_id] = {"id": job_id, "status": "done", "url": "See platform dashboard", "logs": []}
                return
        except Exception as e:
            log(f"Error: {str(e)}")
            try:
                conn4 = get_db(); cur4 = conn4.cursor()
                cur4.execute("UPDATE deployment_history SET status='error', error_message=%s, finished_at=NOW() WHERE id=%s",
                             (str(e)[:500], job_id))
                conn4.commit(); cur4.close(); conn4.close()
            except Exception:
                pass
            _deploy_jobs[job_id] = {"id": job_id, "status": "error", "error": str(e), "logs": []}

    _deploy_jobs[job_id] = {"id": job_id, "status": "building", "logs": [], "platform": f"backend:{platform}"}
    threading.Thread(target=run_backend_deploy, daemon=True).start()
    return {"job_id": job_id, "status": "building"}

def _setup_uptimerobot(api_key: str, url: str, name: str):
    import urllib.request as _ur
    data = json.dumps({
        "api_key": api_key, "format": "json", "type": 1,
        "url": url, "friendly_name": name, "interval": 300
    }).encode()
    req = _ur.Request("https://api.uptimerobot.com/v2/newMonitor",
                      data=data, headers={"Content-Type": "application/json"}, method="POST")
    with _ur.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    if result.get("stat") != "ok":
        raise Exception(result.get("error", {}).get("message", "Unknown error"))

# ============ SYSTEM LOG ============

@api_router.get("/admin/system-log")
async def get_system_log(limit: int = 100):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM system_events ORDER BY created_at DESC LIMIT %s", (min(limit, 500),))
        events = rows_to_list(cur.fetchall())
        cur.close(); conn.close()
        return events
    except Exception:
        return []

# ============ SITE DOCTOR ============

_DIAGNOSTIC_ROUTES = [
    ("GET", "/api/petition/count", "Petition Count"),
    ("GET", "/api/games", "Games API"),
    ("GET", "/api/clips", "Clips API"),
    ("GET", "/api/admin/health", "Health Admin"),
    ("GET", "/api/admin/suggestions", "Suggestions Admin"),
    ("GET", "/api/admin/system-log", "System Log"),
    ("GET", "/api/petition/signatures", "Petition Signatures"),
    ("GET", "/api/comments", "Comments"),
    ("GET", "/api/admin/editor/conversations", "Editor History"),
]

_DB_TABLES = [
    "games","comments","email_subscriptions","petition_signatures","page_views",
    "file_backups","clips","site_content","proof","mockups","votes",
    "creator_submissions","community_posts","social_feed","deployment_config",
    "deployment_history","editor_conversations","suggestions","health_checks","system_events",
]

@api_router.post("/admin/doctor/solve")
async def doctor_solve(body: dict = Body(...)):
    problem = body.get("problem", "").strip()
    if not problem:
        raise HTTPException(400, "problem description is required")

    file_snippets = []
    FILES_TO_READ = [
        (Path(BACKEND_ROOT) / "server.py", 7000),
        (Path(SITE_ROOT) / "src/pages/AdminPage.jsx", 4000),
        (Path(SITE_ROOT) / "src/pages/LandingPage.jsx", 2500),
    ]
    for fpath, maxlen in FILES_TO_READ:
        try:
            content = fpath.read_text()
            tail = content[-maxlen:]
            file_snippets.append(f"=== {fpath.name} (last {maxlen} chars) ===\n{tail}")
        except Exception:
            pass

    events_ctx = ""
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT feature, action, details, status, created_at FROM system_events ORDER BY created_at DESC LIMIT 20")
        events = rows_to_list(cur.fetchall())
        cur.close(); conn.close()
        events_ctx = "\n".join(
            f"[{e['created_at']}] {e['feature']}::{e['action']} ({e['status']}) — {str(e['details'])[:120]}"
            for e in events
        )
    except Exception:
        pass

    prompt = f"""You are a senior developer maintaining the NBA 2K Legacy Vault campaign site.

PROBLEM REPORTED BY ADMIN:
{problem}

RECENT SYSTEM HISTORY (last 20 actions across all features):
{events_ctx or "No history yet"}

CODEBASE CONTEXT:
{chr(10).join(file_snippets)}

Diagnose this problem and provide a precise fix. Respond ONLY with valid JSON (no markdown, no extra text):
{{"diagnosis":"one concise sentence describing the root cause","root_cause":"exact file and function/line where the issue is","fix_description":"plain English description of what the fix does","can_auto_fix":true,"changes":[{{"file":"relative/path/from/workspace/root","find":"exact text that exists in the file","replace":"replacement text"}}]}}

Rules:
- "find" must be the EXACT text from the file (copy-paste), minimum 20 chars for uniqueness
- "file" is relative to workspace root (e.g. backend/app/main.py)
- If the problem cannot be auto-fixed (needs credentials/manual steps), set can_auto_fix to false and changes to []
- Be surgical — only change what's needed"""

    try:
        client = get_anthropic_client()
        resp = client.messages.create(model=CHAT_MODEL, max_tokens=800, messages=[{"role": "user", "content": prompt}])
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        result = json.loads(raw)
    except Exception as e:
        _log_event("doctor", "solve_failed", f"AI parse error: {e} | Problem: {problem[:80]}", "error")
        raise HTTPException(500, f"AI diagnosis failed: {e}")

    applied = []
    errors = []
    workspace_root = Path(WORKSPACE_ROOT)
    if result.get("can_auto_fix") and result.get("changes"):
        for change in result.get("changes", []):
            try:
                rel = change.get("file", "").lstrip("/")
                fpath = workspace_root / rel
                find_text = change.get("find", "")
                replace_text = change.get("replace", "")
                if not fpath.exists():
                    errors.append(f"File not found: {rel}")
                    continue
                content = fpath.read_text()
                if find_text and find_text in content:
                    fpath.write_text(content.replace(find_text, replace_text, 1))
                    applied.append(rel)
                else:
                    errors.append(f"Text not found in {rel}")
            except Exception as ex:
                errors.append(f"Error applying {change.get('file','?')}: {ex}")

    overall_status = "ok" if not errors else ("warn" if applied else "error")
    _log_event("doctor", "solve", f"Problem: {problem[:80]} | Applied: {applied} | Errors: {errors}", overall_status)
    return {
        "diagnosis": result.get("diagnosis", ""),
        "root_cause": result.get("root_cause", ""),
        "fix_description": result.get("fix_description", ""),
        "can_auto_fix": result.get("can_auto_fix", False),
        "applied": applied,
        "errors": errors,
    }


@api_router.post("/admin/doctor/reset")
async def doctor_reset():
    results = []

    cleared = len(_chat_rate_tracker)
    _chat_rate_tracker.clear()
    results.append({"step": "rate_limiter", "status": "ok", "message": f"Cleared {cleared} stale IP entries"})

    try:
        init_db()
        results.append({"step": "db_tables", "status": "ok", "message": f"All {len(_DB_TABLES)} tables verified / created"})
    except Exception as e:
        results.append({"step": "db_tables", "status": "error", "message": str(e)[:120]})

    try:
        t0 = time.time()
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT 1")
        ms = int((time.time() - t0) * 1000)
        cur.close(); conn.close()
        results.append({"step": "db_connect", "status": "ok", "message": f"Database reconnected in {ms}ms"})
    except Exception as e:
        results.append({"step": "db_connect", "status": "error", "message": str(e)[:120]})

    threading.Thread(target=_run_health_checks, daemon=True).start()
    results.append({"step": "health_check", "status": "ok", "message": "Health check triggered in background"})

    try:
        import shutil as _sh
        usage = _sh.disk_usage("/")
        pct = (usage.used / usage.total) * 100
        results.append({"step": "disk", "status": "ok" if pct < 85 else "warn", "message": f"Disk: {pct:.1f}% used"})
    except Exception:
        results.append({"step": "disk", "status": "warn", "message": "Cannot read disk info"})

    overall = "ok" if all(r["status"] == "ok" for r in results) else "warn" if any(r["status"] == "ok" for r in results) else "error"
    _log_event("doctor", "hard_reset", f"Overall: {overall} | Steps: {[r['step'] for r in results]}", overall)
    return {"overall": overall, "steps": results}


@api_router.get("/admin/doctor/diagnostic")
def doctor_diagnostic():
    import urllib.request as _ur
    report = []

    try:
        conn = get_db(); cur = conn.cursor()
        missing = []
        for table in _DB_TABLES:
            try:
                cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
            except Exception:
                missing.append(table)
        cur.close(); conn.close()
        if missing:
            report.append({"check": "db_tables", "label": "Database Tables", "status": "warn",
                           "message": f"Missing: {missing}", "auto_fixed": False})
        else:
            report.append({"check": "db_tables", "label": "Database Tables", "status": "ok",
                           "message": f"All {len(_DB_TABLES)} tables accessible", "auto_fixed": False})
    except Exception as e:
        report.append({"check": "db_tables", "label": "Database Tables", "status": "error",
                       "message": str(e)[:150], "auto_fixed": False})

    for method, path, name in _DIAGNOSTIC_ROUTES:
        try:
            t0 = time.time()
            req = _ur.Request(f"http://127.0.0.1:8000{path}", method=method)
            _ur.urlopen(req, timeout=3)
            ms = int((time.time() - t0) * 1000)
            report.append({"check": f"route_{name.lower().replace(' ','_')}", "label": name,
                           "status": "ok", "message": f"Responded in {ms}ms", "auto_fixed": False})
        except Exception as e:
            report.append({"check": f"route_{name.lower().replace(' ','_')}", "label": name,
                           "status": "error", "message": str(e)[:100], "auto_fixed": False})

    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT MAX(checked_at) as last_check FROM health_checks")
        row = cur.fetchone()
        last = row["last_check"] if row else None
        cur.close(); conn.close()
        if last:
            age = (datetime.now(timezone.utc) - last).total_seconds()
            if age < 600:
                report.append({"check": "health_monitor", "label": "Health Monitor", "status": "ok",
                               "message": f"Last check {int(age)}s ago — running on schedule", "auto_fixed": False})
            else:
                threading.Thread(target=_run_health_checks, daemon=True).start()
                report.append({"check": "health_monitor", "label": "Health Monitor", "status": "warn",
                               "message": f"Stale ({int(age/60)}min) — triggered new check", "auto_fixed": True})
        else:
            threading.Thread(target=_run_health_checks, daemon=True).start()
            report.append({"check": "health_monitor", "label": "Health Monitor", "status": "warn",
                           "message": "No records — triggered first check", "auto_fixed": True})
    except Exception as e:
        report.append({"check": "health_monitor", "label": "Health Monitor", "status": "error",
                       "message": str(e)[:100], "auto_fixed": False})

    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT MAX(generated_at) as last_gen FROM suggestions")
        row = cur.fetchone()
        last = row["last_gen"] if row else None
        cur.close(); conn.close()
        if last:
            age = (datetime.now(timezone.utc) - last).total_seconds()
            status = "ok" if age < 86400 else "warn"
            report.append({"check": "suggestions_engine", "label": "Suggestions Engine", "status": status,
                           "message": f"Last generated {int(age/3600)}h ago", "auto_fixed": False})
        else:
            report.append({"check": "suggestions_engine", "label": "Suggestions Engine", "status": "warn",
                           "message": "No suggestions yet — first run in progress", "auto_fixed": False})
    except Exception as e:
        report.append({"check": "suggestions_engine", "label": "Suggestions Engine", "status": "error",
                       "message": str(e)[:100], "auto_fixed": False})

    try:
        import shutil as _sh
        usage = _sh.disk_usage("/")
        pct = (usage.used / usage.total) * 100
        free_gb = usage.free // (1024**3)
        status = "ok" if pct < 80 else "warn" if pct < 90 else "error"
        report.append({"check": "disk", "label": "Disk Usage", "status": status,
                       "message": f"{pct:.1f}% used, {free_gb}GB free", "auto_fixed": False})
    except Exception:
        report.append({"check": "disk", "label": "Disk Usage", "status": "warn",
                       "message": "Cannot read disk info", "auto_fixed": False})

    try:
        with open("/proc/meminfo") as f:
            lines = {l.split(":")[0]: int(l.split()[1]) for l in f.readlines() if ":" in l}
        total = lines.get("MemTotal", 1); avail = lines.get("MemAvailable", total)
        pct = ((total - avail) / total) * 100
        status = "ok" if pct < 80 else "warn" if pct < 90 else "error"
        report.append({"check": "memory", "label": "Memory Usage", "status": status,
                       "message": f"{pct:.1f}% used", "auto_fixed": False})
    except Exception:
        report.append({"check": "memory", "label": "Memory Usage", "status": "warn",
                       "message": "Cannot read memory info", "auto_fixed": False})

    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM system_events")
        row = cur.fetchone()
        total_events = row["c"] if row else 0
        cur.close(); conn.close()
        report.append({"check": "system_sync", "label": "System Sync (Events)", "status": "ok",
                       "message": f"{total_events} events logged across all features", "auto_fixed": False})
    except Exception as e:
        report.append({"check": "system_sync", "label": "System Sync", "status": "error",
                       "message": str(e)[:100], "auto_fixed": False})

    overall = "ok" if all(r["status"] == "ok" for r in report) else "error" if any(r["status"] == "error" for r in report) else "warn"
    auto_fixed = [r["label"] for r in report if r.get("auto_fixed")]
    _log_event("doctor", "diagnostic", f"Overall: {overall} | {len(report)} checks | Auto-fixed: {auto_fixed}", overall)
    return {"overall": overall, "checks": report, "auto_fixed": auto_fixed}


@api_router.post("/admin/doctor/lock-in")
async def doctor_lock_in():
    import subprocess as _sp
    _chat_rate_tracker.clear()
    try:
        compile_result = _sp.run(
            ["python3", "-m", "py_compile", "backend/app/main.py"],
            capture_output=True, text=True, timeout=120, cwd=WORKSPACE_ROOT
        )

        tests_dir = Path(WORKSPACE_ROOT) / "backend" / "tests"
        if tests_dir.exists():
            test_result = _sp.run(
                ["python3", "-m", "pytest", "backend/tests", "-v", "--tb=short"],
                capture_output=True, text=True, timeout=120, cwd=WORKSPACE_ROOT
            )
            output = (compile_result.stdout + compile_result.stderr + "\n" + test_result.stdout + test_result.stderr).strip()
            passed = compile_result.returncode == 0 and test_result.returncode == 0
            returncode = test_result.returncode if test_result.returncode != 0 else compile_result.returncode
        else:
            output = (compile_result.stdout + compile_result.stderr).strip() or "py_compile passed; no backend/tests directory found"
            passed = compile_result.returncode == 0
            returncode = compile_result.returncode

        lines = output.split("\n")
        summary_line = next((l for l in reversed(lines) if l.strip()), "No summary found")
        _log_event("doctor", "lock_in", f"{summary_line}", "ok" if passed else "error")
        return {"passed": passed, "summary": summary_line, "output": output[-4000:], "returncode": returncode}
    except Exception as e:
        _log_event("doctor", "lock_in_failed", str(e)[:200], "error")
        raise HTTPException(500, f"Test runner failed: {e}")

# ============ MY CODE — Code Export ============

_CODE_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", ".pythonlibs",
    "venv", ".venv", "build", ".next", "coverage", "uploads",
    ".local", ".cache", "tmp",
}
_CODE_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".avif",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".map", ".pyc", ".pyo", ".so", ".dylib", ".dll",
    ".pdf", ".zip", ".tar", ".gz",
}

def _walk_code(root_path: str, rel_prefix: str = "") -> list:
    items = []
    root = Path(root_path)
    if not root.exists():
        return items
    for fpath in sorted(root.rglob("*")):
        if not fpath.is_file():
            continue
        parts = fpath.relative_to(root).parts
        if any(p in _CODE_SKIP_DIRS for p in parts):
            continue
        rel = str(fpath.relative_to(root))
        display = f"{rel_prefix}/{rel}" if rel_prefix else rel
        ext = fpath.suffix.lower()
        try:
            size = fpath.stat().st_size
            if ext in _CODE_BINARY_EXTS or size > 800_000:
                items.append({"path": display, "content": None, "size": size, "binary": True})
            else:
                content = fpath.read_text(errors="replace")
                items.append({"path": display, "content": content, "size": size, "binary": False})
        except Exception:
            pass
    return items

def _make_zip_bytes(roots: list) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root_path, prefix in roots:
            root = Path(root_path)
            if not root.exists():
                continue
            for fpath in sorted(root.rglob("*")):
                if not fpath.is_file():
                    continue
                parts = fpath.relative_to(root).parts
                if any(p in _CODE_SKIP_DIRS for p in parts):
                    continue
                rel = str(fpath.relative_to(root))
                arc = f"{prefix}/{rel}" if prefix else rel
                try:
                    zf.write(fpath, arc)
                except Exception:
                    pass
    buf.seek(0)
    return buf.read()

@api_router.get("/admin/code/files")
async def get_code_files():
    frontend = _walk_code(SITE_ROOT, "frontend")
    backend  = _walk_code(BACKEND_ROOT, "backend")
    return {"frontend": frontend, "backend": backend}

@api_router.get("/admin/code/frontend.zip")
async def download_frontend_zip():
    data = _make_zip_bytes([(SITE_ROOT, "frontend")])
    return StreamingResponse(
        io.BytesIO(data), media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=nba-vault-frontend.zip"}
    )

@api_router.get("/admin/code/backend.zip")
async def download_backend_zip():
    data = _make_zip_bytes([
        (BACKEND_ROOT, "backend"),
    ])
    return StreamingResponse(
        io.BytesIO(data), media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=nba-vault-backend.zip"}
    )

@api_router.get("/admin/code/fullstack.zip")
async def download_fullstack_zip():
    data = _make_zip_bytes([
        (SITE_ROOT,       "frontend"),
        (BACKEND_ROOT,    "backend"),
    ])
    return StreamingResponse(
        io.BytesIO(data), media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=nba-vault-fullstack.zip"}
    )

# ============ MOUNT & RUN ============

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    # Railway/Render/etc. inject PORT; keep PYTHON_PORT as local fallback.
    port = int(os.environ.get("PORT", os.environ.get("PYTHON_PORT", 8000)))
    uvicorn.run(app, host="0.0.0.0", port=port)
