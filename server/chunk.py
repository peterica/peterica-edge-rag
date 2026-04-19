"""마크다운 파싱 + 청킹 (peterica-blog-chat lib/chunk.ts 포팅)"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import frontmatter

# 청킹 로직이 바뀌면 bump. 모바일 /sync ETag에 포함되어 위키 해시가 같아도 강제 재다운로드 유도.
CHUNKER_VERSION = "v2-weak-filter"


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


# MOC/entity/concepts 파일에서 위키링크 목록뿐이라 RAG 근거로 약한 섹션.
# 이런 청크가 top-k를 독점해 답변이 "관련 포스트에 언급되어 있습니다" 식 회피로 수렴.
_WEAK_HEADINGS_EXACT = {"관련 포스트", "관련 개념", "주요 태그", "개념", "기술/도구"}
_WEAK_HEADING_YEAR_RE = re.compile(r"^\d{4}\s*\(\d+\)$")


def is_weak_section(doc_path: str, heading: str) -> bool:
    if not doc_path.startswith(("moc/", "entities/", "concepts/")):
        return False
    if heading in _WEAK_HEADINGS_EXACT:
        return True
    return bool(_WEAK_HEADING_YEAR_RE.match(heading))


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
