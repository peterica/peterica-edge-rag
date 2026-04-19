package com.peterica.edgerag.data

import com.peterica.edgerag.BuildConfig
import okhttp3.OkHttpClient
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Streaming
import java.util.concurrent.TimeUnit

/**
 * Mac Mini 서버 API 클라이언트.
 * /query: RAG 응답 (서버 fallback)
 * /sync: 모바일 DB 다운로드
 */

data class QueryRequest(val question: String)

data class Citation(
    val index: Int,
    val doc_path: String,
    val heading: String?,
)

data class QueryResponse(
    val answer: String,
    val citations: List<Citation>,
    val system_prompt: String,
)

data class SearchResultDto(
    val doc_path: String,
    val heading: String?,
    val distance: Float,
    val preview: String,
)

/** /sync/meta 응답 — P3-5 서버 계약과 동일 */
data class SyncMetaDto(
    val wiki_commit: String,
    val ingested_at: String,
    val db_size_bytes: Long,
)

interface ServerApiService {
    @POST("/query")
    suspend fun query(@Body request: QueryRequest): QueryResponse

    @GET("/search")
    suspend fun search(
        @retrofit2.http.Query("q") query: String,
        @retrofit2.http.Query("k") k: Int = 3,
    ): List<SearchResultDto>

    /** wiki HEAD commit + DB 크기 조회 (다운로드 없이 캐시 검증용) */
    @GET("/sync/meta")
    suspend fun syncMeta(): SyncMetaDto

    /**
     * mobile.db 다운로드. If-None-Match 헤더에 현재 로컬 ETag를 넣으면
     * 서버가 같은 버전일 때 304 Not Modified를 반환 → body 없음.
     * Retrofit 기본 호출은 non-2xx에서 예외를 던지므로 Response wrapper로 상태 코드 접근.
     */
    @GET("/sync")
    @Streaming
    suspend fun syncDb(
        @Header("If-None-Match") ifNoneMatch: String? = null,
    ): Response<ResponseBody>

    @GET("/health")
    suspend fun health(): Map<String, String>
}

object ServerApi {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    val service: ServerApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BuildConfig.SERVER_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ServerApiService::class.java)
    }

    /** 서버 연결 가능 여부 확인 */
    suspend fun isServerReachable(): Boolean = try {
        service.health()
        true
    } catch (e: Exception) {
        // P2-17: silent catch가 디버깅을 막아 원인 파악 불가했음. 진단 로그 추가
        android.util.Log.w(
            "EdgeRag",
            "isServerReachable failed: ${e.javaClass.simpleName} — ${e.message}",
        )
        false
    }
}
