package com.peterica.edgerag.data

import com.peterica.edgerag.BuildConfig
import okhttp3.OkHttpClient
import okhttp3.ResponseBody
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
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

interface ServerApiService {
    @POST("/query")
    suspend fun query(@Body request: QueryRequest): QueryResponse

    @GET("/search")
    suspend fun search(
        @retrofit2.http.Query("q") query: String,
        @retrofit2.http.Query("k") k: Int = 3,
    ): List<SearchResultDto>

    @GET("/sync")
    @Streaming
    suspend fun syncDb(): ResponseBody

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
    } catch (_: Exception) {
        false
    }
}
