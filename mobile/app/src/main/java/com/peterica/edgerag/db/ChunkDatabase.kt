package com.peterica.edgerag.db

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import java.io.File

/**
 * 모바일 SQLite DB 관리.
 * server GET /sync에서 다운로드한 mobile.db를 로드하여 청크 검색에 사용.
 */
class ChunkDatabase(private val context: Context) {

    private var db: SQLiteDatabase? = null

    val isReady: Boolean get() = dbFile.exists()

    private val dbFile: File
        get() = File(context.filesDir, "mobile.db")

    fun open() {
        if (db?.isOpen == true) return
        if (!dbFile.exists()) error("mobile.db not found. Run sync first.")
        db = SQLiteDatabase.openDatabase(dbFile.path, null, SQLiteDatabase.OPEN_READONLY)
    }

    fun close() {
        db?.close()
        db = null
    }

    /**
     * 모든 청크의 텍스트와 메타데이터를 로드.
     * 118 청크 규모에서는 전체 로드가 실용적.
     */
    fun loadAllChunks(): List<Chunk> {
        val database = db ?: error("DB not opened")
        val chunks = mutableListOf<Chunk>()

        database.rawQuery(
            "SELECT id, doc_path, title, heading, ord, text FROM chunks ORDER BY id",
            null
        ).use { cursor ->
            while (cursor.moveToNext()) {
                chunks.add(
                    Chunk(
                        id = cursor.getInt(0),
                        docPath = cursor.getString(1),
                        title = cursor.getString(2),
                        heading = cursor.getString(3),
                        ord = cursor.getInt(4),
                        text = cursor.getString(5),
                    )
                )
            }
        }
        return chunks
    }

    /**
     * chunk_vec에서 임베딩 벡터를 로드.
     * sqlite-vec 없이 raw blob을 float 배열로 변환.
     */
    fun loadEmbeddings(): Map<Int, FloatArray> {
        val database = db ?: error("DB not opened")
        val embeddings = mutableMapOf<Int, FloatArray>()

        database.rawQuery(
            "SELECT chunk_id, embedding FROM chunk_embeddings",
            null
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val chunkId = cursor.getInt(0)
                val blob = cursor.getBlob(1)
                embeddings[chunkId] = blobToFloatArray(blob)
            }
        }
        return embeddings
    }

    /** /sync에서 받은 DB 파일을 저장 */
    fun saveDbFile(bytes: ByteArray) {
        dbFile.writeBytes(bytes)
    }

    /**
     * 로컬 mobile.db의 meta.wiki_commit (P2-14 ETag 비교용).
     * DB 파일이 없거나 meta 테이블이 없는 구버전이면 null.
     * 본 함수는 short-lived read-only 커넥션을 새로 열어 메인 open()과 독립.
     */
    fun getLocalWikiCommit(): String? {
        if (!dbFile.exists()) return null
        return try {
            SQLiteDatabase.openDatabase(
                dbFile.path, null, SQLiteDatabase.OPEN_READONLY,
            ).use { conn ->
                conn.rawQuery(
                    "SELECT value FROM meta WHERE key = 'wiki_commit' LIMIT 1", null,
                ).use { c ->
                    if (c.moveToFirst()) c.getString(0) else null
                }
            }
        } catch (_: Exception) {
            // meta 테이블 없음(구버전) / DB 파손 등 → null 처리해 전체 다운로드 유도
            null
        }
    }

    companion object {
        fun blobToFloatArray(blob: ByteArray): FloatArray {
            val buffer = java.nio.ByteBuffer.wrap(blob).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            val floats = FloatArray(blob.size / 4)
            buffer.asFloatBuffer().get(floats)
            return floats
        }
    }
}

data class Chunk(
    val id: Int,
    val docPath: String,
    val title: String?,
    val heading: String?,
    val ord: Int,
    val text: String,
)
