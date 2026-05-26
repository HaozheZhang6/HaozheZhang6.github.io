#!/usr/bin/env python3
"""
Push intro paragraphs from local _posts/*.md back to their Notion pages.

Targets a curated list of posts where only the intro paragraphs changed
(between `## 中文`/`## English` and the first `### ...` subheading), plus an
optional pre-heading block (NVDA's removed quote).

Usage:
    uv run python bin/update_intros.py            # dry-run, prints plan
    uv run python bin/update_intros.py --apply    # actually mutate Notion
"""

import argparse
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

sys.path.insert(0, str(ROOT / "bin"))
from migrate_to_notion import parse_inline, parse_frontmatter  # noqa: E402

TARGETS = [
    "2026-04-09-leveraged-etf-decay.md",
    "2026-05-21-diversifier-matrix.md",
    "2026-04-23-covered-call-ablation.md",
    "2026-03-26-nvda-iron-condor.md",
]


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
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode()[:500]
        raise RuntimeError(f"HTTP {e.code} for {method} {path}: {body_txt}")


_MD_STRIP_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)|\*\*|\*|`")


def strip_md(s):
    """Strip light markdown so we can compare to Notion plain_text."""
    return _MD_STRIP_RE.sub(lambda m: m.group(1) or "", s)


def fetch_top_blocks(token, page_id, n=12):
    """Top-level blocks only; we never touch deeper than the first heading_3."""
    blocks, cursor = [], None
    while len(blocks) < n:
        path = f"/blocks/{page_id}/children?page_size=50"
        if cursor:
            path += f"&start_cursor={cursor}"
        data = notion_request("GET", path, token)
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return blocks


def is_heading(block, level):
    return block.get("type") == f"heading_{level}"


def heading_text(block):
    t = block.get("type")
    if not t or not t.startswith("heading_"):
        return ""
    return "".join(r.get("plain_text", "") for r in block[t].get("rich_text", []))


def split_md_sections(body):
    """Return dict: section_key → list of paragraph texts (each a single string).
    Sections we care about:
      cn_pre   — content before `## 中文` (only quote/paragraphs, ignored if empty)
      cn_intro — paragraphs after `## 中文` heading until next `### ...`
      en_intro — paragraphs after `## English` heading until next `### ...`
    """
    lines = body.splitlines()
    idx = {"cn_h2": -1, "en_h2": -1, "cn_next_h3": -1, "en_next_h3": -1}
    for i, ln in enumerate(lines):
        s = ln.strip()
        if re.match(r"^##\s+中文(\s+\{#cn\})?\s*$", s) and idx["cn_h2"] < 0:
            idx["cn_h2"] = i
        elif re.match(r"^##\s+English(\s+\{#en\})?\s*$", s) and idx["en_h2"] < 0:
            idx["en_h2"] = i
        elif s.startswith("### ") and idx["cn_h2"] >= 0 and idx["cn_next_h3"] < 0 and i > idx["cn_h2"]:
            if idx["en_h2"] < 0 or i < idx["en_h2"]:
                idx["cn_next_h3"] = i
        elif s.startswith("### ") and idx["en_h2"] >= 0 and idx["en_next_h3"] < 0 and i > idx["en_h2"]:
            idx["en_next_h3"] = i

    def collect_paragraphs(lo, hi):
        """Collect blank-line-separated paragraph blocks between lo (exclusive) and hi (exclusive).
        Only returns plain paragraphs — bails out (returns None) if it sees ``` or | tables or > quotes."""
        paras = []
        i = lo + 1
        while i < hi:
            s = lines[i].strip()
            if not s:
                i += 1
                continue
            if s.startswith("```") or s.startswith("|") or s.startswith(">") or s.startswith("#"):
                return None  # Not a simple paragraph region — refuse to touch.
            buf = []
            while i < hi and lines[i].strip():
                buf.append(lines[i].strip())
                i += 1
            paras.append(" ".join(buf))
        return paras

    cn_pre_lines = lines[:idx["cn_h2"]] if idx["cn_h2"] > 0 else []
    cn_pre_has_content = any(ln.strip() for ln in cn_pre_lines)

    cn_intro = collect_paragraphs(idx["cn_h2"], idx["cn_next_h3"]) if idx["cn_h2"] >= 0 else None
    en_intro = collect_paragraphs(idx["en_h2"], idx["en_next_h3"]) if idx["en_h2"] >= 0 else None

    return {
        "cn_pre_has_content": cn_pre_has_content,
        "cn_intro": cn_intro,
        "en_intro": en_intro,
    }


def plan_section(notion_blocks, h2_idx, new_paras):
    """Given the top-blocks list and the index of the `## 中文`/`## English`
    heading, plus the desired new paragraphs, return a plan:
      [(action, block_id_or_None, new_text), ...]
    where action ∈ {patch, delete, append_after}.
    """
    plan = []
    end = h2_idx + 1
    # Schedule deletion of any quote block sitting between the heading and the first paragraph
    # (NVDA had a per-language disclaimer quote we now want gone).
    while end < len(notion_blocks):
        b = notion_blocks[end]
        t = b.get("type")
        if t == "quote":
            plan.append(("delete", b["id"], None))
            end += 1
            continue
        break

    old_para_blocks = []
    while end < len(notion_blocks):
        b = notion_blocks[end]
        t = b.get("type")
        if t and t.startswith("heading_"):
            break
        if t == "paragraph":
            old_para_blocks.append(b)
            end += 1
        else:
            # Stop at first non-paragraph (table, code, etc.) so we don't accidentally clobber data
            break

    n_old = len(old_para_blocks)
    n_new = len(new_paras)
    for i in range(min(n_old, n_new)):
        old_plain = "".join(
            r.get("plain_text", "")
            for r in old_para_blocks[i].get("paragraph", {}).get("rich_text", [])
        )
        new_plain = strip_md(new_paras[i])
        if old_plain.strip() == new_plain.strip():
            plan.append(("skip", old_para_blocks[i]["id"], new_paras[i]))
            continue
        plan.append(("patch", old_para_blocks[i]["id"], new_paras[i]))
    if n_old > n_new:
        for b in old_para_blocks[n_new:]:
            plan.append(("delete", b["id"], None))
    elif n_new > n_old:
        # Append remaining after the last existing paragraph (or after the heading itself).
        anchor = old_para_blocks[-1]["id"] if old_para_blocks else notion_blocks[h2_idx]["id"]
        for txt in new_paras[n_old:]:
            plan.append(("append_after", anchor, txt))
            # Note: the anchor will shift to the just-inserted block at exec time.
    return plan


def execute_plan(token, page_id, plan, parent_id, apply):
    current_anchor = None
    for action, ref, text in plan:
        if action == "skip":
            print(f"  SKIP   {ref[:8]}  (unchanged)")
            continue
        if action == "patch":
            payload = {"paragraph": {"rich_text": parse_inline(text)}}
            print(f"  PATCH  {ref[:8]}  ← {text[:80]}{'...' if len(text) > 80 else ''}")
            if apply:
                notion_request("PATCH", f"/blocks/{ref}", token, payload)
        elif action == "delete":
            print(f"  DELETE {ref[:8]}")
            if apply:
                notion_request("DELETE", f"/blocks/{ref}", token)
        elif action == "append_after":
            anchor = current_anchor or ref
            body = {
                "children": [{
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": parse_inline(text)},
                }],
                "after": anchor,
            }
            print(f"  INSERT after {anchor[:8]}  ← {text[:80]}{'...' if len(text) > 80 else ''}")
            if apply:
                resp = notion_request("PATCH", f"/blocks/{parent_id}/children", token, body)
                # Update current_anchor so subsequent inserts go after this one.
                results = resp.get("results", [])
                if results:
                    current_anchor = results[-1]["id"]


def delete_leading_non_heading_blocks(token, blocks, apply):
    """For NVDA: remove anything before the first `## 中文` heading (quote, paragraph)."""
    deleted = []
    for b in blocks:
        if b.get("type") == "heading_2":
            break
        print(f"  DELETE pre-heading {b['id'][:8]} ({b['type']})")
        deleted.append(b["id"])
    if apply:
        for bid in deleted:
            notion_request("DELETE", f"/blocks/{bid}", token)
    return len(deleted)


def process_post(token, post_path, apply):
    raw = post_path.read_text()
    fm, body = parse_frontmatter(raw)
    notion_id = fm.get("notion_id", "").strip()
    if not notion_id:
        print(f"[skip] {post_path.name}: no notion_id")
        return

    sections = split_md_sections(body)
    if sections["cn_intro"] is None or sections["en_intro"] is None:
        print(f"[skip] {post_path.name}: intro region contains non-paragraph content; refusing to touch.")
        return

    print(f"\n=== {post_path.name} ({notion_id}) ===")
    blocks = fetch_top_blocks(token, notion_id, n=20)

    # 1) Pre-heading cleanup (NVDA case)
    if not sections["cn_pre_has_content"]:
        # Local file has nothing before `## 中文`; delete any pre-heading blocks in Notion.
        n_pre = sum(1 for b in blocks if b.get("type") != "heading_2") if blocks and blocks[0].get("type") != "heading_2" else 0
        if n_pre > 0:
            # only count up to first heading_2
            actual = 0
            for b in blocks:
                if b.get("type") == "heading_2":
                    break
                actual += 1
            if actual > 0:
                delete_leading_non_heading_blocks(token, blocks, apply)
                # Re-fetch to get accurate indices after deletion.
                if apply:
                    blocks = fetch_top_blocks(token, notion_id, n=20)

    # 2) Find heading indices in the (possibly re-fetched) block list
    cn_idx = next((i for i, b in enumerate(blocks) if b.get("type") == "heading_2" and "中文" in heading_text(b)), -1)
    en_idx = next((i for i, b in enumerate(blocks) if b.get("type") == "heading_2" and "English" in heading_text(b)), -1)

    if cn_idx >= 0:
        print(f"  -- CN section (heading at index {cn_idx}) --")
        plan_cn = plan_section(blocks, cn_idx, sections["cn_intro"])
        execute_plan(token, notion_id, plan_cn, notion_id, apply)

    # The EN heading might not be in our fetched window if intro+rest pushes it past 20 blocks.
    # Most of our targets keep EN within the first ~20 blocks for the intro region we care about.
    # For safety, fetch a wider window if needed.
    if en_idx < 0:
        blocks_wider = fetch_top_blocks(token, notion_id, n=200)
        en_idx = next((i for i, b in enumerate(blocks_wider) if b.get("type") == "heading_2" and "English" in heading_text(b)), -1)
        blocks = blocks_wider

    if en_idx >= 0:
        print(f"  -- EN section (heading at index {en_idx}) --")
        plan_en = plan_section(blocks, en_idx, sections["en_intro"])
        execute_plan(token, notion_id, plan_en, notion_id, apply)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Actually mutate Notion (default is dry-run).")
    args = ap.parse_args()

    env = load_env(ENV_FILE)
    token = env.get("NOTION_TOKEN") or os.environ.get("NOTION_TOKEN")
    if not token:
        print("Missing NOTION_TOKEN", file=sys.stderr)
        sys.exit(1)

    for name in TARGETS:
        path = POSTS_DIR / name
        if not path.exists():
            print(f"[miss] {name}")
            continue
        process_post(token, path, args.apply)


if __name__ == "__main__":
    main()
