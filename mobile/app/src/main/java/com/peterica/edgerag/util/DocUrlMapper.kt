package com.peterica.edgerag.util

/**
 * 위키 doc_path → 피테리카 티스토리 블로그 URL 매핑.
 *
 * 규칙: 위키 `posts/YYYY/NNNN-...md`의 `NNNN`(zero-padded 4자리)이
 * 프론트매터 `id`·`url` 필드와 일치함을 검증 완료 (peterica-blog-wiki 전수 샘플).
 *
 * - `posts/2022/0183-Kubernetes-...md`  → `https://peterica.tistory.com/183`
 * - `concepts/…md`·`entities/…md`·`moc/…md`·`_index.md` → null
 *   (블로그 포스트가 아니라 지식 지도 / 개념 노트 → 외부 링크 없음)
 */
object DocUrlMapper {
    private val POST_REGEX = Regex("""^posts/\d{4}/(\d+)-.*\.md$""")
    private const val BLOG_BASE = "https://peterica.tistory.com"

    fun toBlogUrl(docPath: String): String? {
        val match = POST_REGEX.matchEntire(docPath) ?: return null
        val id = match.groupValues[1].trimStart('0').ifEmpty { "0" }
        return "$BLOG_BASE/$id"
    }
}
