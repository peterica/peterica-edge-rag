"""마크다운 파싱 + 청킹 (peterica-blog-chat lib/chunk.ts 포팅)"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import frontmatter


@dataclass
class ParsedDoc:
    title: str
    frontmatter: dict
    sections: list[dict] = field(default_factory=list)  # {"heading": str, "body": str}


def parse_markdown(raw: str, fallback_title: str) -> ParsedDoc:
    """마크다운 파싱: YAML frontmatter + h1-h3 기준 섹션 분리"""
    post = frontmatter.loads(raw)
    title = post.metadata.get("title", fallback_title)
    content = post.content

    sections: list[dict] = []
    lines = content.split("\n")
    current_heading = title
    buf: list[str] = []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            sections.append({"heading": current_heading, "body": body})
        buf.clear()

    heading_re = re.compile(r"^(#{1,3})\s+(.+?)\s*$")

    for line in lines:
        m = heading_re.match(line)
        if m:
            flush()
            current_heading = m.group(2).strip()
        else:
            buf.append(line)

    flush()

    if not sections:
        sections.append({"heading": title, "body": content.strip()})

    return ParsedDoc(
        title=title,
        frontmatter=dict(post.metadata),
        sections=sections,
    )


def chunk_section(heading: str, body: str, target: int = 800) -> list[str]:
    """섹션을 ~800자 청크로 분할. 코드블록 보존."""
    paragraphs = re.split(r"\n{2,}", body)
    chunks: list[str] = []
    cur = ""

    for p in paragraphs:
        combined = f"{cur}\n\n{p}" if cur else p
        if len(combined) > target and cur:
            chunks.append(cur.strip())
            cur = p
        else:
            cur = combined

    if cur.strip():
        chunks.append(cur.strip())

    return [f"## {heading}\n\n{c}" for c in chunks]
