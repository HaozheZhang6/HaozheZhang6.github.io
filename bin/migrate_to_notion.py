#!/usr/bin/env python3
"""
One-shot: push every Jekyll _posts/*.md into the Notion 'Blog Posts' DB.

Skips files whose slug already exists in the DB (Slug property) — re-runs are safe.
Uses Title to dedupe if Slug is unset on a Notion page.

Usage: uv run python bin/migrate_to_notion.py
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
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
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ---------- frontmatter ----------

def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    fm_text = text[4:end]
    body = text[end + 4:].lstrip("\n")
    fm = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        fm[k] = v
    return fm, body


# ---------- inline rich_text parser ----------

INLINE_RE = re.compile(
    r"(\$\$.+?\$\$)"
    r"|(`[^`\n]+`)"
    r"|(\*\*[^*\n]+\*\*)"
    r"|(\*[^*\n]+\*)"
    r"|(\[[^\]\n]+\]\([^)\n]+\))",
    re.UNICODE,
)


def encode_url(url):
    """Notion rejects #anchors and {% post_url %}. Encode them as placeholder
    https URLs that sync_notion.py decodes back to the original markdown."""
    if url.startswith("#"):
        return f"https://anchor.local/{url[1:]}"
    m = re.match(r"\{%\s*post_url\s+(\S+)\s*%\}", url)
    if m:
        return f"https://post-url.local/{m.group(1)}"
    if re.match(r"^(https?://|mailto:|/)", url):
        return url
    return f"https://raw.local/{url}"


def rt_text(content, bold=False, italic=False, code=False, href=None):
    obj = {"type": "text", "text": {"content": content}}
    if href:
        obj["text"]["link"] = {"url": href}
    ann = {}
    if bold:
        ann["bold"] = True
    if italic:
        ann["italic"] = True
    if code:
        ann["code"] = True
    if ann:
        obj["annotations"] = ann
    return obj


def parse_inline(text):
    """Markdown inline → Notion rich_text array."""
    rich = []
    pos = 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            plain = text[pos:m.start()]
            if plain:
                rich.append(rt_text(plain))
        if m.group(1):  # equation
            expr = m.group(1)[2:-2]
            rich.append({"type": "equation", "equation": {"expression": expr}})
        elif m.group(2):  # code
            rich.append(rt_text(m.group(2)[1:-1], code=True))
        elif m.group(3):  # bold
            rich.append(rt_text(m.group(3)[2:-2], bold=True))
        elif m.group(4):  # italic
            rich.append(rt_text(m.group(4)[1:-1], italic=True))
        elif m.group(5):  # link
            lm = re.match(r"\[([^\]]+)\]\(([^)]+)\)", m.group(5))
            if lm:
                link_text, link_url = lm.group(1), lm.group(2)
                rich.append(rt_text(link_text, href=encode_url(link_url)))
        pos = m.end()
    if pos < len(text):
        rich.append(rt_text(text[pos:]))
    # Notion enforces 2000-char limit on text.content. Split if needed.
    return chunk_rich(rich)


def chunk_rich(rich):
    out = []
    for r in rich:
        if r["type"] == "text" and len(r["text"]["content"]) > 1800:
            content = r["text"]["content"]
            for i in range(0, len(content), 1800):
                chunk = dict(r)
                chunk["text"] = dict(r["text"], content=content[i:i + 1800])
                out.append(chunk)
        else:
            out.append(r)
    return out


# ---------- block-level parser ----------

def block(t, **payload):
    return {"object": "block", "type": t, t: payload}


def parse_markdown(body):
    lines = body.splitlines()
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # ATX heading: # / ## / ### (optionally with trailing {#anchor})
        m = re.match(r"^(#{1,3})\s+(.+?)\s*$", stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2)
            t = f"heading_{level}" if level <= 3 else "heading_3"
            blocks.append(block(t, rich_text=parse_inline(text)))
            i += 1
            continue

        # Fenced code block
        if stripped.startswith("```"):
            lang = stripped[3:].strip() or "plain text"
            i += 1
            code_lines = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # closing ```
            code_text = "\n".join(code_lines)
            blocks.append(block(
                "code",
                rich_text=[rt_text(code_text)],
                language=normalize_lang(lang),
            ))
            continue

        # Display math block: line is exactly "$$" → collect until next "$$"
        if stripped == "$$":
            i += 1
            math_lines = []
            while i < n and lines[i].strip() != "$$":
                math_lines.append(lines[i])
                i += 1
            i += 1  # closing $$
            expr = "\n".join(math_lines).strip()
            blocks.append(block("equation", expression=expr))
            continue

        # Single-line display math: $$...$$ as the entire line (no other text)
        m = re.match(r"^\$\$(.+)\$\$$", stripped)
        if m:
            blocks.append(block("equation", expression=m.group(1).strip()))
            i += 1
            continue

        # Bullet list
        if re.match(r"^[-*]\s+", stripped):
            while i < n:
                lm = re.match(r"^[-*]\s+(.+)$", lines[i].strip())
                if lm and lines[i].strip():
                    blocks.append(block("bulleted_list_item", rich_text=parse_inline(lm.group(1))))
                    i += 1
                else:
                    break
            continue

        # Numbered list
        if re.match(r"^\d+\.\s+", stripped):
            while i < n:
                lm = re.match(r"^\d+\.\s+(.+)$", lines[i].strip())
                if lm and lines[i].strip():
                    blocks.append(block("numbered_list_item", rich_text=parse_inline(lm.group(1))))
                    i += 1
                else:
                    break
            continue

        # Table: current line starts with | and next line is a separator row
        if stripped.startswith("|") and i + 1 < n and _is_table_sep(lines[i + 1]):
            header_cells = _parse_table_row(lines[i])
            i += 2
            rows = [header_cells]
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_parse_table_row(lines[i]))
                i += 1
            width = max(len(r) for r in rows)
            for r in rows:
                while len(r) < width:
                    r.append([rt_text("")])
            blocks.append({
                "object": "block",
                "type": "table",
                "table": {
                    "table_width": width,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": [
                        {"object": "block", "type": "table_row", "table_row": {"cells": r}}
                        for r in rows
                    ],
                },
            })
            continue

        # Block quote
        if stripped.startswith(">"):
            quote_lines = []
            while i < n and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").lstrip())
                i += 1
            text = " ".join(quote_lines)
            blocks.append(block("quote", rich_text=parse_inline(text)))
            continue

        # Divider
        if stripped == "---" or stripped == "***":
            blocks.append(block("divider"))
            i += 1
            continue

        # Paragraph — collect until blank line
        para_lines = []
        while i < n and lines[i].strip():
            para_lines.append(lines[i].strip())
            i += 1
        text = " ".join(para_lines)
        blocks.append(block("paragraph", rich_text=parse_inline(text)))

    return blocks


NOTION_LANGS = {
    "python", "javascript", "typescript", "bash", "shell", "ruby", "go", "rust",
    "java", "c", "c++", "c#", "html", "css", "json", "yaml", "sql", "markdown",
    "plain text", "diff", "kotlin", "swift", "scala", "perl", "r", "lua",
}


def _is_table_sep(line):
    s = line.strip().strip("|")
    if not s:
        return False
    for cell in s.split("|"):
        if not re.match(r"^\s*:?-+:?\s*$", cell):
            return False
    return True


def _parse_table_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [parse_inline(c.strip()) for c in s.split("|")]


def normalize_lang(lang):
    lang = lang.lower().strip()
    aliases = {"js": "javascript", "ts": "typescript", "py": "python", "sh": "bash", "yml": "yaml"}
    lang = aliases.get(lang, lang)
    return lang if lang in NOTION_LANGS else "plain text"


# ---------- migration ----------

def _slugify(s):
    if " / " in s:
        s = s.split(" / ", 1)[1]
    s = s.lower().strip()
    s = "".join(c for c in s if ord(c) < 128)
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-")


def existing_slugs(token, db_id):
    slugs = {}
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = notion_request("POST", f"/databases/{db_id}/query", token, body)
        for r in data.get("results", []):
            props = r.get("properties", {})
            slug_prop = props.get("Slug", {})
            slug = "".join(x.get("plain_text", "") for x in slug_prop.get("rich_text", []))
            title_prop = props.get("Title", {})
            title = "".join(x.get("plain_text", "") for x in title_prop.get("title", []))
            for key in {slug, _slugify(title)}:
                if key:
                    slugs[key] = r["id"]
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return slugs


def filename_slug(path):
    name = path.stem  # 2025-04-18-svi-vs-sabr
    m = re.match(r"^\d{4}-\d{2}-\d{2}-(.+)$", name)
    return m.group(1) if m else name


def split_list(s):
    if not s:
        return []
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):  # YAML flow sequence: [a, b, c]
        s = s[1:-1]
    if "," in s:
        return [x.strip() for x in s.split(",") if x.strip()]
    return [x.strip() for x in s.split() if x.strip()]


def create_page(token, db_id, properties, children):
    first_batch = children[:100]
    rest = children[100:]
    body = {
        "parent": {"database_id": db_id},
        "properties": properties,
        "children": first_batch,
    }
    page = notion_request("POST", "/pages", token, body)
    while rest:
        chunk = rest[:100]
        rest = rest[100:]
        notion_request("PATCH", f"/blocks/{page['id']}/children", token, {"children": chunk})
    return page


def migrate_file(token, db_id, path, taken_slugs):
    slug = filename_slug(path)
    if slug in taken_slugs:
        return False, f"already in Notion ({slug})"

    raw = path.read_text()
    fm, body = parse_frontmatter(raw)
    title = fm.get("title", path.stem)
    date = fm.get("date", "").split(" ")[0] or "2025-01-01"
    cats = split_list(fm.get("categories", ""))
    tags = split_list(fm.get("tags", ""))
    description = fm.get("description", "")
    last_updated = fm.get("last_updated", "").split(" ")[0]

    props = {
        "Title": {"title": [rt_text(title)]},
        "Status": {"status": {"name": "Published"}},
        "Publish Date": {"date": {"start": date}},
        "Slug": {"rich_text": [rt_text(slug)]},
        "Description": {"rich_text": [rt_text(description)] if description else []},
        "Categories": {"multi_select": [{"name": c} for c in cats]},
        "Tags": {"multi_select": [{"name": t} for t in tags]},
    }
    if last_updated:
        props["Last Edited"] = {"date": {"start": last_updated}}

    children = parse_markdown(body)
    page = create_page(token, db_id, props, children)
    return True, page["id"]


def main():
    env = load_env(ENV_FILE)
    token = env.get("NOTION_TOKEN") or os.environ.get("NOTION_TOKEN")
    db_id = env.get("NOTION_DB_ID") or os.environ.get("NOTION_DB_ID")
    if not token or not db_id:
        print("Missing NOTION_TOKEN or NOTION_DB_ID", file=sys.stderr)
        sys.exit(1)

    taken = existing_slugs(token, db_id)
    print(f"Existing slugs in Notion: {sorted(taken.keys())}")
    print()

    files = sorted(POSTS_DIR.glob("*.md"))
    for path in files:
        slug = filename_slug(path)
        try:
            ok, info = migrate_file(token, db_id, path, taken)
            print(f"[{'OK ' if ok else 'SKIP'}] {path.name} → {info}")
            if ok:
                taken[slug] = info
        except urllib.error.HTTPError as e:
            print(f"[FAIL] {path.name}: HTTP {e.code} {e.read().decode()[:300]}")
        except Exception as e:
            print(f"[FAIL] {path.name}: {e}")


if __name__ == "__main__":
    main()
