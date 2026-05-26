#!/usr/bin/env python3
"""
Sync Notion 'Blog Posts' database to Jekyll _posts/ folder.

Usage:  uv run python bin/sync_notion.py
        (reads NOTION_TOKEN and NOTION_DB_ID from .env at repo root)

Only pages with Status=Published are written out. Each file gets a
`notion_id:` frontmatter line so this script can recognize files it owns.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "_posts"
ENV_FILE = ROOT / ".env"
NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"


def load_env(path):
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def notion_request(method, path, token, body=None):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def query_published(token, db_id):
    pages, cursor = [], None
    while True:
        body = {
            "filter": {"property": "Status", "status": {"equals": "Published"}},
            "page_size": 100,
        }
        if cursor:
            body["start_cursor"] = cursor
        data = notion_request("POST", f"/databases/{db_id}/query", token, body)
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return pages


def fetch_children(token, block_id):
    blocks, cursor = [], None
    while True:
        path = f"/blocks/{block_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        data = notion_request("GET", path, token)
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return blocks


def prop_text(p):
    if not p:
        return ""
    t = p.get("type")
    if t == "title":
        return "".join(x.get("plain_text", "") for x in p.get("title", []))
    if t == "rich_text":
        return "".join(x.get("plain_text", "") for x in p.get("rich_text", []))
    if t == "status":
        return (p.get("status") or {}).get("name", "")
    if t == "select":
        return (p.get("select") or {}).get("name", "")
    if t == "multi_select":
        return [x.get("name", "") for x in p.get("multi_select", [])]
    if t == "date":
        return (p.get("date") or {}).get("start", "")
    if t == "people":
        return [x.get("name", "") for x in p.get("people", [])]
    if t == "last_edited_time":
        return p.get("last_edited_time", "")
    return ""


def decode_url(url):
    """Inverse of migrate_to_notion.encode_url."""
    if not url:
        return url
    if url.startswith("https://anchor.local/"):
        return "#" + url[len("https://anchor.local/"):]
    if url.startswith("https://post-url.local/"):
        return "{% post_url " + url[len("https://post-url.local/"):] + " %}"
    if url.startswith("https://raw.local/"):
        return url[len("https://raw.local/"):]
    return url


def rich_to_md(rt_list):
    out = []
    for rt in rt_list:
        t = rt.get("type")
        if t == "equation":
            out.append(f"$${rt.get('equation', {}).get('expression', '')}$$")
            continue
        text = rt.get("plain_text", "")
        ann = rt.get("annotations", {}) or {}
        href = decode_url(rt.get("href"))
        if ann.get("code"):
            text = f"`{text}`"
        if ann.get("bold"):
            text = f"**{text}**"
        if ann.get("italic"):
            text = f"*{text}*"
        if ann.get("strikethrough"):
            text = f"~~{text}~~"
        if href and not ann.get("code"):
            text = f"[{text}]({href})"
        out.append(text)
    return "".join(out)


def block_to_md(block, token, indent=0):
    t = block.get("type")
    pad = "  " * indent
    body = block.get(t, {}) or {}
    rich = body.get("rich_text", [])
    text = rich_to_md(rich) if rich else ""
    lines = []

    if t == "paragraph":
        lines.append(pad + text if text else "")
    elif t == "heading_1":
        lines.append(f"{pad}# {text}")
    elif t == "heading_2":
        lines.append(f"{pad}## {text}")
    elif t == "heading_3":
        lines.append(f"{pad}### {text}")
    elif t == "bulleted_list_item":
        lines.append(f"{pad}- {text}")
    elif t == "numbered_list_item":
        lines.append(f"{pad}1. {text}")
    elif t == "to_do":
        check = "x" if body.get("checked") else " "
        lines.append(f"{pad}- [{check}] {text}")
    elif t == "quote":
        for ln in (text or "").splitlines() or [""]:
            lines.append(f"{pad}> {ln}")
    elif t == "callout":
        emoji = (body.get("icon") or {}).get("emoji", "")
        prefix = f"{emoji} " if emoji else ""
        for ln in (text or "").splitlines() or [""]:
            lines.append(f"{pad}> {prefix}{ln}")
    elif t == "code":
        lang = body.get("language", "") or ""
        code = "".join(x.get("plain_text", "") for x in body.get("rich_text", []))
        lines.append(f"{pad}```{lang}")
        for ln in code.splitlines() or [""]:
            lines.append(f"{pad}{ln}")
        lines.append(f"{pad}```")
    elif t == "equation":
        expr = body.get("expression", "")
        lines.append(f"{pad}$${expr}$$")
    elif t == "divider":
        lines.append(f"{pad}---")
    elif t == "image":
        src = ""
        kind = body.get("type")
        if kind == "external":
            src = (body.get("external") or {}).get("url", "")
        elif kind == "file":
            src = (body.get("file") or {}).get("url", "")
        cap = rich_to_md(body.get("caption", []))
        lines.append(f"{pad}![{cap}]({src})")
    elif t == "bookmark":
        url = body.get("url", "")
        lines.append(f"{pad}[{url}]({url})")
    elif t == "toggle":
        lines.append(f"{pad}<details><summary>{text}</summary>")
        lines.append("")
    elif t == "table":
        rows = fetch_children(token, block["id"])
        has_header = body.get("has_column_header", True)
        row_idx = 0
        for child in rows:
            if child.get("type") != "table_row":
                continue
            cells = child.get("table_row", {}).get("cells", [])
            row_md = f"{pad}| " + " | ".join(rich_to_md(c) for c in cells) + " |"
            lines.append(row_md)
            if row_idx == 0 and has_header:
                lines.append(f"{pad}|" + "|".join(["---"] * len(cells)) + "|")
            row_idx += 1
        return "\n".join(lines)
    else:
        # Fallback: skip unknown block types silently
        if text:
            lines.append(pad + text)

    # Recurse into children for list items, toggles, quotes, callouts
    if block.get("has_children"):
        children = fetch_children(token, block["id"])
        child_indent = indent + 1 if t in {
            "bulleted_list_item", "numbered_list_item", "to_do", "toggle"
        } else indent
        for c in children:
            sub = block_to_md(c, token, child_indent)
            if sub:
                lines.append(sub)
        if t == "toggle":
            lines.append(f"{pad}</details>")

    return "\n".join(lines)


def slugify(s):
    # If the title has " / " (bilingual), use only the part after the slash (English half).
    if " / " in s:
        s = s.split(" / ", 1)[1]
    s = s.lower().strip()
    # Strip non-ASCII first so Chinese characters don't end up in URLs.
    s = "".join(c for c in s if ord(c) < 128)
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-") or "untitled"


def detect_bilingual(body):
    return bool(re.search(r"^##\s+(中文|English)(\s+\{#(cn|en)\})?\s*$", body, re.MULTILINE))


def frontmatter(page, title, date, categories, tags, description, bilingual, last_updated):
    fm = {
        "layout": "post",
        "title": title,
        "date": date,
        "description": description or "",
        "tags": tags or [],
        "categories": categories or [],
        "notion_id": page["id"],
        "last_updated": last_updated or page.get("last_edited_time", "")[:10],
    }
    if bilingual:
        fm["bilingual"] = True
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, list):
            if v:
                lines.append(f"{k}: [{', '.join(v)}]")
            else:
                lines.append(f"{k}: []")
        else:
            val = str(v).replace('"', '\\"')
            lines.append(f'{k}: "{val}"' if any(c in val for c in ":#") else f"{k}: {val}")
    lines.append("---")
    return "\n".join(lines)


def find_existing_file(notion_id):
    for f in POSTS_DIR.glob("*.md"):
        head = f.read_text(errors="ignore")[:600]
        if f"notion_id: {notion_id}" in head or f'notion_id: "{notion_id}"' in head:
            return f
    return None


def render_page(page, token):
    props = page.get("properties", {})
    title = prop_text(props.get("Title")) or "Untitled"
    date = prop_text(props.get("Publish Date")) or datetime.utcnow().strftime("%Y-%m-%d")
    cats = prop_text(props.get("Categories")) or []
    tags = prop_text(props.get("Tags")) or []
    description = prop_text(props.get("Description")) or ""
    slug_prop = prop_text(props.get("Slug")) or ""
    last_edited = prop_text(props.get("Last Edited")) or page.get("last_edited_time", "")[:10]
    if isinstance(cats, str):
        cats = [cats] if cats else []
    if isinstance(tags, str):
        tags = [tags] if tags else []
    slug = slug_prop if slug_prop else slugify(title)
    filename = f"{date}-{slug}.md"

    blocks = fetch_children(token, page["id"])
    LIST_TYPES = {"bulleted_list_item", "numbered_list_item", "to_do"}
    body_parts = []
    for b in blocks:
        md = block_to_md(b, token)
        if md is None:
            continue
        body_parts.append((b.get("type"), md))
    out = []
    for i, (t, md) in enumerate(body_parts):
        if i > 0:
            prev_t = body_parts[i - 1][0]
            sep = "\n" if prev_t == t and t in LIST_TYPES else "\n\n"
            out.append(sep)
        out.append(md)
    body = "".join(out)

    bilingual = detect_bilingual(body)
    content = frontmatter(page, title, date, cats, tags, description, bilingual, last_edited) + "\n\n" + body + "\n"

    existing = find_existing_file(page["id"])
    target = existing if existing else POSTS_DIR / filename
    if existing and existing.name != filename:
        existing.unlink()
        target = POSTS_DIR / filename
    target.write_text(content)
    return target


def main():
    env = load_env(ENV_FILE)
    token = env.get("NOTION_TOKEN") or os.environ.get("NOTION_TOKEN")
    db_id = env.get("NOTION_DB_ID") or os.environ.get("NOTION_DB_ID")
    if not token or not db_id:
        print("Missing NOTION_TOKEN or NOTION_DB_ID in .env or environment.", file=sys.stderr)
        sys.exit(1)

    pages = query_published(token, db_id)
    print(f"Found {len(pages)} published post(s) in Notion.")
    POSTS_DIR.mkdir(exist_ok=True)
    for page in pages:
        try:
            path = render_page(page, token)
            print(f"  wrote {path.relative_to(ROOT)}")
        except urllib.error.HTTPError as e:
            print(f"  FAILED {page['id']}: HTTP {e.code} {e.read()[:200]}", file=sys.stderr)
        except Exception as e:
            print(f"  FAILED {page['id']}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
