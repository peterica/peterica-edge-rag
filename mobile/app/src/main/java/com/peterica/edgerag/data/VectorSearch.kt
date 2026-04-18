package com.peterica.edgerag.data

import com.peterica.edgerag.db.Chunk
import kotlin.math.sqrt

/**
 * Brute-force cosine similarity 검색.
 * 118 청크 규모에서는 <1ms로 충분히 빠름.
 */
class VectorSearch {

    private var chunks: List<Chunk> = emptyList()
    private var embeddings: Map<Int, FloatArray> = emptyMap()

    val isLoaded: Boolean get() = chunks.isNotEmpty()

    fun load(chunks: List<Chunk>, embeddings: Map<Int, FloatArray>) {
        this.chunks = chunks
        this.embeddings = embeddings
    }

    /**
     * 쿼리 벡터로 top-k 검색.
     * @return (chunk, cosine distance) 쌍 리스트, distance 오름차순
     */
    fun search(queryVec: FloatArray, topK: Int = 3, maxDistance: Float = 0.65f): List<SearchResult> {
        val scored = chunks.mapNotNull { chunk ->
            val vec = embeddings[chunk.id] ?: return@mapNotNull null
            val distance = cosineDistance(queryVec, vec)
            SearchResult(chunk, distance)
        }.sortedBy { it.distance }

        // doc_path 중복 제거 (출처 다양성)
        val seen = mutableSetOf<String>()
        val unique = scored.filter { result ->
            if (result.chunk.docPath in seen) false
            else { seen.add(result.chunk.docPath); true }
        }

        // distance 필터 + min-k 보장
        val passing = unique.filter { it.distance <= maxDistance }
        val source = if (passing.size >= 3) passing else unique.take(3)
        return source.take(topK)
    }

    companion object {
        fun cosineSimilarity(a: FloatArray, b: FloatArray): Float {
            var dot = 0f
            var normA = 0f
            var normB = 0f
            for (i in a.indices) {
                dot += a[i] * b[i]
                normA += a[i] * a[i]
                normB += b[i] * b[i]
            }
            val denom = sqrt(normA) * sqrt(normB)
            return if (denom == 0f) 0f else dot / denom
        }

        fun cosineDistance(a: FloatArray, b: FloatArray): Float =
            1f - cosineSimilarity(a, b)
    }
}

data class SearchResult(
    val chunk: Chunk,
    val distance: Float,
)
