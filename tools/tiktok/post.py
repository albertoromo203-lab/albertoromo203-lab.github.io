#!/usr/bin/env python3
"""Send a finished carousel to the academy's TikTok inbox as a photo post draft.

    py -3 tiktok/post.py send <slug> [--title "..."] [--src DIR] [--caption FILE] [--repo DIR]
    py -3 tiktok/post.py status <publish_id>

This script never decides WHAT to post. The tiktok-poster skill (laptop) and the cloud
routine pick the Notion rows; this only sends the one it is given.

`send`:
 1. reads the slides NN.jpg (content slides plus the end slide) from --src, default output/<slug>/,
    and the caption from --caption, default output/<slug>/caption.md;
 2. makes 1080px-wide copies (TikTok accepts at most 1080p): into site/slides/<slug>/ on the
    laptop, into a temporary folder in the cloud;
 3. pushes them to the GitHub Pages repo in one commit and waits until they are served: through
    the GitHub API on the laptop, or with git from the checkout given by --repo in the cloud
    (the cloud's GitHub proxy refuses API writes but allows git push);
 4. asks TikTok to pull them from the verified URL prefix (MEDIA_UPLOAD = inbox draft);
 5. waits for TikTok's answer and prints one JSON line: slug, publish_id, status, fail_reason.

Settings come from .env on the laptop, or from environment variables in the cloud:
TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, SITE_URL, and GITHUB_TOKEN, GITHUB_REPO when there is no --repo.
The TikTok login comes from tiktok/token.json (laptop, made by connect.py) or, when that file
does not exist, from TIKTOK_REFRESH_TOKEN (cloud). If TikTok hands back a different refresh
token, it is written to tiktok/refresh_token.new and the line REFRESH_TOKEN_ROTATED is printed;
the caller must store the new value, because the old one stops working.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import connect  # noqa: E402  (settings and token requests live there)

ROOT = connect.ROOT
ROTATED = HERE / "refresh_token.new"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/content/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
GH_API = "https://api.github.com"
MAX_W = 1080


def call(url, body=None, headers=None, method=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"raw": raw[:300].decode("utf-8", "replace")}


# ---------- slides ----------

def prepare(slug, src):
    files = sorted(p for p in src.glob("*.jpg") if re.fullmatch(r"\d{2}\.jpg", p.name))
    if not files:
        sys.exit(f"STOP no slides named 01.jpg, 02.jpg ... in {src}")
    if len(files) > 35:
        sys.exit(f"STOP {len(files)} slides; TikTok allows at most 35")
    site = ROOT / "site"
    dest = (site / "slides" / slug) if site.is_dir() else Path(tempfile.mkdtemp()) / slug
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        im = Image.open(f).convert("RGB")
        if im.width > MAX_W:
            im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
        p = dest / f.name
        im.save(p, "JPEG", quality=90, optimize=True)
        out.append(p)
    return out


def push(cfg, slug, paths):
    """One commit with every slide, through the Git Data API, so Pages builds once."""
    repo, h = cfg["GITHUB_REPO"], {"Authorization": f"Bearer {cfg['GITHUB_TOKEN']}",
                                   "Accept": "application/vnd.github+json", "Content-Type": "application/json"}
    code, ref = call(f"{GH_API}/repos/{repo}/git/ref/heads/main", headers=h)
    if code != 200:
        sys.exit(f"STOP GitHub refused access to {repo} ({code}): {ref.get('message')}")
    head = ref["object"]["sha"]
    _, commit = call(f"{GH_API}/repos/{repo}/git/commits/{head}", headers=h)
    tree = []
    for p in paths:
        code, blob = call(f"{GH_API}/repos/{repo}/git/blobs", {"content": base64.b64encode(p.read_bytes()).decode(),
                                                               "encoding": "base64"}, h)
        if code != 201:
            sys.exit(f"STOP GitHub blob upload failed ({code}): {blob.get('message')}")
        tree.append({"path": f"slides/{slug}/{p.name}", "mode": "100644", "type": "blob", "sha": blob["sha"]})
    _, new_tree = call(f"{GH_API}/repos/{repo}/git/trees", {"base_tree": commit["tree"]["sha"], "tree": tree}, h)
    if new_tree["sha"] == commit["tree"]["sha"]:
        return False  # identical slides are already published
    _, new_commit = call(f"{GH_API}/repos/{repo}/git/commits",
                         {"message": f"slides: {slug}", "tree": new_tree["sha"], "parents": [head]}, h)
    code, upd = call(f"{GH_API}/repos/{repo}/git/refs/heads/main", {"sha": new_commit["sha"]}, h, "PATCH")
    if code != 200:
        sys.exit(f"STOP GitHub could not update main ({code}): {upd.get('message')}")
    return True


def push_git(repo, slug, paths):
    """Same single commit, made with git in a checkout of the Pages repo (the cloud routine's way)."""
    def git(*a):
        r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"STOP git {' '.join(a[:2])} failed: {(r.stderr or r.stdout).strip()[-300:]}")
        return r.stdout

    git("fetch", "-q", "origin", "main")
    git("checkout", "-q", "-B", "tiktok-slides", "FETCH_HEAD")
    dest = Path(repo) / "slides" / slug
    dest.mkdir(parents=True, exist_ok=True)
    for p in paths:
        shutil.copyfile(p, dest / p.name)
    git("add", "--", f"slides/{slug}")
    if not git("status", "--porcelain", "--", f"slides/{slug}").strip():
        return False  # identical slides are already published
    git("-c", "user.name=Potochino TikTok poster", "-c", "user.email=albertoromo203-lab@users.noreply.github.com",
        "commit", "-q", "-m", f"slides: {slug}")
    git("push", "-q", "origin", "HEAD:main")
    return True


def wait_served(urls, paths, timeout=600):
    """Pages can lag a few minutes; TikTok must find every file, byte for byte, with no redirect."""
    deadline, pending = time.time() + timeout, dict(zip(urls, paths))
    while pending and time.time() < deadline:
        for url, p in list(pending.items()):
            try:
                req = urllib.request.Request(url + f"?v={int(time.time())}", headers={"Cache-Control": "no-cache"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    if r.read() == p.read_bytes():
                        del pending[url]
            except urllib.error.URLError:
                pass
        if pending:
            time.sleep(15)
    if pending:
        sys.exit(f"STOP GitHub Pages still does not serve {len(pending)} slide(s) after {timeout // 60} min")


# ---------- TikTok ----------

def access_token():
    if connect.TOKEN.exists():
        tok = json.loads(connect.TOKEN.read_text(encoding="utf-8"))
    else:
        rt = os.environ.get("TIKTOK_REFRESH_TOKEN", "").strip()
        if not rt:
            sys.exit("STOP no tiktok/token.json and no TIKTOK_REFRESH_TOKEN: reconnect with connect.py")
        tok = {"refresh_token": rt, "access_token": "", "obtained_at": 0, "expires_in": 0}
    if tok["obtained_at"] + tok["expires_in"] - time.time() < 600:
        cfg = connect.env()
        old = tok["refresh_token"]
        connect.save(connect.post_form(connect.TOKEN_URL, {
            "client_key": cfg["TIKTOK_CLIENT_KEY"], "client_secret": cfg["TIKTOK_CLIENT_SECRET"],
            "grant_type": "refresh_token", "refresh_token": old}))
        tok = json.loads(connect.TOKEN.read_text(encoding="utf-8"))
        if tok["refresh_token"] != old:
            ROTATED.write_text(tok["refresh_token"], encoding="utf-8")
            print("REFRESH_TOKEN_ROTATED", flush=True)
    return tok["access_token"]


def fit(text, limit):
    """Trim to TikTok's limit, counted in UTF-16 units, on a word boundary."""
    if len(text.encode("utf-16-le")) // 2 <= limit:
        return text
    while len((text + "…").encode("utf-16-le")) // 2 > limit:
        text = text[:text.rstrip().rfind(" ")] if " " in text.strip() else text[:-1]
    return text.rstrip(" ,.;:") + "…"


def status(publish_id, token=None):
    h = {"Authorization": f"Bearer {token or access_token()}", "Content-Type": "application/json; charset=UTF-8"}
    _, r = call(STATUS_URL, {"publish_id": publish_id}, h)
    d = r.get("data") or {}
    return {"publish_id": publish_id, "status": d.get("status") or r.get("error", {}).get("code"),
            "fail_reason": d.get("fail_reason") or ""}


def send(slug, title=None, src=None, caption_file=None, repo=None):
    cfg = connect.env()
    for k in ("SITE_URL",) if repo else ("GITHUB_TOKEN", "GITHUB_REPO", "SITE_URL"):
        if not cfg.get(k):
            sys.exit(f"STOP missing setting {k}")
    src = Path(src) if src else ROOT / "output" / slug
    caption_file = Path(caption_file) if caption_file else src / "caption.md"
    caption = caption_file.read_text(encoding="utf-8").strip()
    title = fit((title or caption.splitlines()[0]).strip(), 90)
    description = fit(caption, 4000)

    paths = prepare(slug, src)
    if repo:
        push_git(repo, slug, paths)
    else:
        push(cfg, slug, paths)
    base = cfg["SITE_URL"].rstrip("/") + f"/slides/{slug}/"
    urls = [base + p.name for p in paths]
    wait_served(urls, paths)

    token = access_token()
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    code, r = call(INIT_URL, {
        "post_info": {"title": title, "description": description},
        "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": urls},
        "post_mode": "MEDIA_UPLOAD", "media_type": "PHOTO"}, h)
    err = r.get("error", {})
    if err.get("code") != "ok":
        print(json.dumps({"slug": slug, "publish_id": "", "status": "FAILED",
                          "fail_reason": f"{err.get('code')}: {err.get('message')}"}))
        sys.exit(1)
    pid = r["data"]["publish_id"]

    result = {"publish_id": pid, "status": "PROCESSING_DOWNLOAD", "fail_reason": ""}
    for _ in range(36):  # up to 3 minutes
        time.sleep(5)
        result = status(pid, token)
        if result["status"] in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "FAILED"):
            break
    print(json.dumps({"slug": slug, **result}))
    sys.exit(0 if result["status"] != "FAILED" else 1)


def opt(args, name):
    return args[args.index(name) + 1] if name in args else None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "send":
        send(args[1], opt(args, "--title"), opt(args, "--src"), opt(args, "--caption"), opt(args, "--repo"))
    elif len(args) == 2 and args[0] == "status":
        print(json.dumps(status(args[1])))
    else:
        sys.exit(__doc__)
