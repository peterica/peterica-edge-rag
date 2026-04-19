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
     * 로컬 mobile.db의 sync ETag (P2-14 /sync If-None-Match 용).
     * `sync_etag` 우선, 없으면 `wiki_commit` 폴백(구 ingest 호환).
     * DB 파일/meta 미존재 → null → phone이 ETag 없이 요청해 서버가 200으로 응답(강제 재다운로드).
     */
    fun getLocalSyncEtag(): String? {
        if (!dbFile.exists()) return null
        return try {
            SQLiteDatabase.openDatabase(
                dbFile.path, null, SQLiteDatabase.OPEN_READONLY,
            ).use { conn ->
                conn.rawQuery(
                    "SELECT value FROM meta WHERE key IN ('sync_etag','wiki_commit') " +
                        "ORDER BY CASE key WHEN 'sync_etag' THEN 0 ELSE 1 END LIMIT 1",
                    null,
                ).use { c ->
                    if (c.moveToFirst()) c.getString(0) else null
                }
            }
        } catch (_: Exception) {
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
