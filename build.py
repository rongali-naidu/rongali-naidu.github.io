"""Build the static website from the blogs repo.

Only posts whose front matter says `publish: true` are included.

Usage: python build.py [--content ../blogs] [--out dist]
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import posixpath
import re
import shutil
import sys
from email.utils import format_datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "_deps"))  # local installs (markdown-it-py etc.)

import yaml  # noqa: E402
from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402
from markdown_it import MarkdownIt  # noqa: E402
from mdit_py_plugins.anchors import anchors_plugin  # noqa: E402
from pygments import highlight  # noqa: E402
from pygments.formatters import HtmlFormatter  # noqa: E402
from pygments.lexers import get_lexer_by_name  # noqa: E402
from pygments.util import ClassNotFound  # noqa: E402

TOPIC_NAMES = {
    "aws": "AWS", "genai": "GenAI", "sql": "SQL", "sqlserver": "SQL Server",
    "postgresql": "PostgreSQL", "duckdb": "DuckDB", "spark": "Spark", "python": "Python",
    "data_architecture": "Data Architecture", "data_governance": "Data Governance",
    "data_lineage": "Data Lineage", "data_processing": "Data Processing",
    "table_formats": "Table Formats", "streaming": "Streaming", "analytics": "Analytics",
    "software": "Software Engineering", "interview_prep": "Interview Prep",
    "career_and_strategy": "Career & Strategy", "linux": "Linux",
    "modelling": "Data Modelling", "performance_tuning": "Performance Tuning",
    # sub-folders
    "athena": "Athena", "redshift": "Redshift", "glue": "Glue", "s3_tables": "S3 Tables",
    "dms": "DMS", "bedrock": "Bedrock", "kinesis": "Kinesis", "flink": "Flink",
    "containers": "Containers", "cloudwatch": "CloudWatch", "security": "Security",
    "developer_tools": "Developer Tools", "data_mesh": "Data Mesh", "arrow": "Apache Arrow",
    "iceberg": "Apache Iceberg", "kafka": "Kafka", "knowledge_base": "Knowledge Bases",
    "statistics": "Statistics", "networking": "Networking", "system_design": "System Design",
}


def topic_name(folder):
    return TOPIC_NAMES.get(folder, folder.replace("_", " ").title())


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


# ---------------------------------------------------------------- markdown

def _highlight(code, lang, _attrs):
    try:
        lexer = get_lexer_by_name((lang or "").strip() or "text")
    except ClassNotFound:
        lexer = get_lexer_by_name("text")
    return highlight(code, lexer, HtmlFormatter(nowrap=True))


md = (MarkdownIt("gfm-like", {"html": True, "linkify": True, "highlight": _highlight})
      .use(anchors_plugin, min_level=2, max_level=3, slug_func=slugify))


def split_front_matter(text):
    if not text.startswith("---"):
        return None, text
    _, fm, body = text.split("---", 2)
    return yaml.safe_load(fm) or {}, body.lstrip("\r\n")


def strip_title_heading(body, title):
    """Drop the post's leading heading when it just repeats the title."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if line.lstrip().startswith("#") or line.strip().startswith("**"):
            nh, nt = norm(re.sub(r"[#*\\`]", "", line)), norm(title)
            if len(nh) > 3 and (nt in nh or nh in nt):
                return "\n".join(lines[i + 1:])
        break
    return body


def first_paragraph(body):
    for block in re.split(r"\n\s*\n", body):
        b = block.strip()
        if not b or b[0] in "#!|<>-*`[" or b.startswith("```") or b[:2].isdigit():
            continue
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", b)
        text = re.sub(r"[*_`#>]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 60:
            return text if len(text) <= 200 else text[:197].rsplit(" ", 1)[0] + "…"
    return ""


# ---------------------------------------------------------------- loading

class Post:
    def __init__(self, rel, meta, body):
        self.rel = rel                                  # aws/athena/foo.md
        self.key = rel[:-3]                             # aws/athena/foo
        parts = rel.split("/")
        self.folders = parts[:-1]
        self.top = self.folders[0] if self.folders else "misc"
        self.title = str(meta["title"])
        d = meta["date"]
        self.date = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))
        self.tags = meta.get("tags") or []
        self.url = "/blog/" + "/".join(slugify(p) for p in parts[:-1] + [parts[-1][:-3]]) + "/"
        self.body = strip_title_heading(body, self.title)
        self.words = len(re.findall(r"\w+", self.body))
        self.minutes = max(1, round(self.words / 220))
        self.summary = first_paragraph(self.body)
        self.topic_label = " · ".join(topic_name(f) for f in self.folders) or "Misc"
        self.html = ""
        self.toc = []


def load_posts(content):
    posts, hidden = [], 0
    for p in sorted(content.rglob("*.md")):
        rel = p.relative_to(content).as_posix()
        if rel.startswith(".") or "/." in rel or rel == "README.md":
            continue
        meta, body = split_front_matter(p.read_text(encoding="utf-8-sig"))
        if not meta or meta.get("publish") is not True:
            hidden += 1
            continue
        posts.append(Post(rel, meta, body))
    posts.sort(key=lambda x: (x.date, x.title), reverse=True)
    return posts, hidden


# ---------------------------------------------------------------- rendering

IMG_SRC = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")')
A_HREF = re.compile(r'(<a\b[^>]*?\bhref=")([^"]+)(")')
GH_PREFIX = re.compile(r"^https://github\.com/rongali-naidu/blogs/(?:blob|raw)/main/")


def render_post(post, by_key, image_names):
    html_out = md.render(post.body)
    base = posixpath.dirname(post.rel)

    def fix_img(m):
        src = html.unescape(m.group(2))
        local = GH_PREFIX.sub("", src)
        if local != src or not re.match(r"^[a-z]+:", src):
            name = posixpath.basename(local.split("?")[0])
            if name in image_names:
                return f"{m.group(1)}/images/{name}{m.group(3)}"
        return m.group(0)

    def fix_link(m):
        href = html.unescape(m.group(2))
        local = GH_PREFIX.sub("", href)
        if re.match(r"^[a-z]+:", local) or not local.split("#")[0].endswith(".md"):
            return m.group(0)
        path, _, frag = local.partition("#")
        target = posixpath.normpath(posixpath.join(base if local == href else "", path))[:-3]
        if target in by_key:
            return f"{m.group(1)}{by_key[target].url}{'#' + frag if frag else ''}{m.group(3)}"
        return m.group(0)

    html_out = IMG_SRC.sub(fix_img, html_out)
    html_out = A_HREF.sub(fix_link, html_out)
    html_out = html_out.replace("<img ", '<img loading="lazy" ')
    html_out = re.sub(r"<table>", '<div class="table-wrap"><table>', html_out)
    html_out = re.sub(r"</table>", "</table></div>", html_out)
    post.html = html_out
    post.toc = [
        {"level": int(m.group(1)), "id": m.group(2),
         "text": html.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()}
        for m in re.finditer(r'<h([23]) id="([^"]+)">(.*?)</h\1>', html_out, re.S)
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", default=str(HERE.parent / "blogs"))
    ap.add_argument("--out", default=str(HERE / "dist"))
    args = ap.parse_args()
    content, out = Path(args.content).resolve(), Path(args.out).resolve()
    if os.name == "nt" and not str(out).startswith("\\\\?\\"):
        out = Path("\\\\?\\" + str(out))  # allow paths longer than 260 chars on Windows
    cfg = yaml.safe_load((HERE / "site.yaml").read_text(encoding="utf-8"))

    posts, hidden = load_posts(content)
    by_key = {p.key: p for p in posts}
    image_dir = content / "images"
    image_names = {f.name for f in image_dir.iterdir() if f.is_file()} if image_dir.exists() else set()
    for p in posts:
        render_post(p, by_key, image_names)

    # topics (top-level folders, with sub-groups)
    topics = {}
    for p in posts:
        t = topics.setdefault(p.top, {"slug": slugify(p.top), "name": topic_name(p.top),
                                      "posts": [], "groups": {}})
        t["posts"].append(p)
        sub = topic_name(p.folders[1]) if len(p.folders) > 1 else ""
        t["groups"].setdefault(sub, []).append(p)
    topic_list = sorted(topics.values(), key=lambda t: (-len(t["posts"]), t["name"]))
    for t in topic_list:
        t["url"] = f"/topics/{t['slug']}/"
        t["groups"] = sorted(t["groups"].items(), key=lambda g: (g[0] != "", g[0]))

    # output
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(HERE / "static", out / "static")
    if image_dir.exists():
        shutil.copytree(image_dir, out / "images", ignore=shutil.ignore_patterns("*.txt"))
    fmt = HtmlFormatter()
    (out / "static" / "code.css").write_text(
        fmt.get_style_defs(".prose pre") + "\n"
        + "\n".join(f"html[data-theme=dark] {line}" if line.startswith(".") else line
                    for line in HtmlFormatter(style="github-dark").get_style_defs(".prose pre").splitlines()),
        encoding="utf-8")

    env = Environment(loader=FileSystemLoader(HERE / "templates"),
                      autoescape=select_autoescape(["html", "xml"]))
    year = dt.date.today().year
    projects = cfg.get("projects") or []
    for pr in projects:
        pr["url"] = f"/projects/{pr['slug']}/"
        pr["overview_html"] = md.render(pr.get("overview", ""))
    # cache-busting version for CSS/JS, so browsers pick up style changes right away
    asset_v = hashlib.sha1(b"".join(
        f.read_bytes() for f in sorted((out / "static").glob("*.*")))).hexdigest()[:8]
    common = {"site": cfg, "year": year, "topics": topic_list, "post_count": len(posts),
              "projects": projects, "v": asset_v}

    def write(url, template, **ctx):
        dest = out / url.strip("/") / "index.html" if url != "/" else out / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(env.get_template(template).render(**common, **ctx, url=url),
                        encoding="utf-8")

    write("/", "home.html", recent=posts[:8])
    write("/blog/", "blog.html", posts=posts)
    write("/guides/", "guides.html")
    write("/projects/", "projects.html")
    for pr in projects:
        write(pr["url"], "project.html", project=pr)
    write("/topics/", "topics.html")
    write("/about/", "about.html", about_html=md.render(cfg.get("about", "")))
    for t in topic_list:
        write(t["url"], "topic.html", topic=t)
    for p in posts:
        siblings = [q for q in topics[p.top]["posts"] if q is not p][:5]
        write(p.url, "post.html", post=p, related=siblings, topic=topics[p.top])
    (out / "404.html").write_text(env.get_template("404.html").render(**common, url="/404"),
                                  encoding="utf-8")

    # search index + RSS
    (out / "search.json").write_text(json.dumps([
        {"t": p.title, "u": p.url, "s": p.summary, "g": p.topic_label,
         "d": p.date.isoformat(), "m": p.minutes} for p in posts
    ], ensure_ascii=False), encoding="utf-8")
    items = "".join(
        f"<item><title>{html.escape(p.title)}</title><link>{cfg['url']}{p.url}</link>"
        f"<guid>{cfg['url']}{p.url}</guid>"
        f"<pubDate>{format_datetime(dt.datetime.combine(p.date, dt.time(), dt.timezone.utc))}</pubDate>"
        f"<description>{html.escape(p.summary)}</description></item>"
        for p in posts[:30])
    (out / "feed.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>{html.escape(cfg['name'])}</title><link>{cfg['url']}</link>"
        f"<description>{html.escape(cfg['tagline'])}</description>{items}</channel></rss>",
        encoding="utf-8")
    (out / ".nojekyll").write_text("")

    print(f"Built {len(posts)} posts ({hidden} hidden), {len(topic_list)} topics -> {out}")


if __name__ == "__main__":
    main()
