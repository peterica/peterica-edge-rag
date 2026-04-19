package com.peterica.edgerag.ui

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.peterica.edgerag.data.*
import com.peterica.edgerag.db.ChunkDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class ChatMessage(
    val text: String,
    val isUser: Boolean,
    val citations: List<Citation> = emptyList(),
    val source: String = "",  // "local" | "server"
)

data class ChatUiState(
    val messages: List<ChatMessage> = emptyList(),
    val isLoading: Boolean = false,
    val dbReady: Boolean = false,
    val embeddingReady: Boolean = false,
    val llmReady: Boolean = false,
    val serverReachable: Boolean = false,
    val statusText: String = "초기화 중...",
    val isSyncing: Boolean = false,
)

class ChatViewModel(app: Application) : AndroidViewModel(app) {

    private val _state = MutableStateFlow(ChatUiState())
    val state: StateFlow<ChatUiState> = _state.asStateFlow()

    private val chunkDb = ChunkDatabase(app)
    private val vectorSearch = VectorSearch()
    private val embeddingEngine = EmbeddingEngine(app)
    private val llmEngine = LlmEngine(app)

    init {
        viewModelScope.launch { initialize() }
    }

    private suspend fun initialize() {
        _state.value = _state.value.copy(statusText = "DB 확인 중...")

        // DB 로드
        if (chunkDb.isReady) {
            chunkDb.open()
            val chunks = chunkDb.loadAllChunks()
            val embeddings = chunkDb.loadEmbeddings()
            vectorSearch.load(chunks, embeddings)
            _state.value = _state.value.copy(
                dbReady = true,
                statusText = "DB 로드 완료 (${chunks.size} 청크)"
            )
        } else {
            _state.value = _state.value.copy(statusText = "DB 없음 — 동기화 필요")
        }

        // 임베딩 엔진 초기화
        try {
            embeddingEngine.initialize()
            _state.value = _state.value.copy(
                embeddingReady = true,
                statusText = "임베딩 엔진 준비 완료"
            )
        } catch (e: Exception) {
            _state.value = _state.value.copy(
                statusText = "임베딩 모델 없음 (assets/model.onnx 필요)"
            )
        }

        // LLM 초기화
        llmEngine.initialize()
        _state.value = _state.value.copy(
            llmReady = llmEngine.state == LlmEngine.State.READY,
        )

        // 서버 연결 확인
        val reachable = ServerApi.isServerReachable()
        _state.value = _state.value.copy(
            serverReachable = reachable,
            statusText = buildStatusText(),
        )
    }

    /** 서버에서 mobile.db 다운로드 */
    fun syncDatabase() {
        viewModelScope.launch {
            _state.value = _state.value.copy(isSyncing = true, statusText = "DB 동기화 중...")
            try {
                val chunkCount = withContext(Dispatchers.IO) {
                    val response = ServerApi.service.syncDb()
                    val bytes = response.bytes()
                    chunkDb.saveDbFile(bytes)
                    chunkDb.open()
                    val chunks = chunkDb.loadAllChunks()
                    val embeddings = chunkDb.loadEmbeddings()
                    vectorSearch.load(chunks, embeddings)
                    chunks.size
                }
                _state.value = _state.value.copy(
                    dbReady = true,
                    isSyncing = false,
                    statusText = "동기화 완료 ($chunkCount 청크)",
                )
            } catch (e: Exception) {
                Log.e("EdgeRag", "syncDatabase failed", e)
                val kind = e.javaClass.simpleName
                val msg = e.message ?: "(no msg)"
                _state.value = _state.value.copy(
                    isSyncing = false,
                    statusText = "동기화 실패: $kind — $msg",
                )
            }
        }
    }

    /** 로컬 RAG 검색 + LLM 응답 */
    fun sendMessage(text: String) {
        val userMsg = ChatMessage(text = text, isUser = true)
        _state.value = _state.value.copy(
            messages = _state.value.messages + userMsg,
            isLoading = true,
        )

        viewModelScope.launch {
            val response = if (_state.value.dbReady && _state.value.embeddingReady) {
                localSearch(text)
            } else if (_state.value.serverReachable) {
                serverQuery(text)
            } else {
                ChatMessage(
                    text = "오프라인 상태이며 로컬 DB가 준비되지 않았습니다. 동기화를 먼저 실행해주세요.",
                    isUser = false,
                    source = "system",
                )
            }

            _state.value = _state.value.copy(
                messages = _state.value.messages + response,
                isLoading = false,
            )
        }
    }

    /** 서버 fallback 요청 */
    fun sendToServer(text: String) {
        val userMsg = ChatMessage(text = "[서버 요청] $text", isUser = true)
        _state.value = _state.value.copy(
            messages = _state.value.messages + userMsg,
            isLoading = true,
        )

        viewModelScope.launch {
            val response = serverQuery(text)
            _state.value = _state.value.copy(
                messages = _state.value.messages + response,
                isLoading = false,
            )
        }
    }

    private suspend fun localSearch(query: String): ChatMessage {
        return try {
            // 쿼리 임베딩
            val queryVec = embeddingEngine.embed(query, isQuery = true)

            // 벡터 검색
            val results = vectorSearch.search(queryVec, topK = 3)

            if (results.isEmpty()) {
                return ChatMessage(
                    text = "로컬 검색 결과가 없습니다. 서버에 질문해보세요.",
                    isUser = false,
                    source = "local",
                )
            }

            // 시스템 프롬프트 구성
            val ctx = results.mapIndexed { i, r ->
                "[#${i + 1}] source=${r.chunk.docPath} heading=${r.chunk.heading ?: ""}\n${r.chunk.text}"
            }.joinToString("\n\n---\n\n")

            val systemPrompt = buildString {
                appendLine("당신은 peterica-blog-wiki 지식베이스를 근거로 답하는 한국어 기술 어시스턴트입니다.")
                appendLine()
                appendLine("CONTEXT:")
                append(ctx)
            }

            // LLM 생성
            val answer = llmEngine.generate(systemPrompt, query)

            val citations = results.mapIndexed { i, r ->
                Citation(
                    index = i + 1,
                    doc_path = r.chunk.docPath,
                    heading = r.chunk.heading,
                )
            }

            ChatMessage(
                text = answer,
                isUser = false,
                citations = citations,
                source = "local (${results.map { "%.2f".format(it.distance) }.joinToString()})",
            )
        } catch (e: Exception) {
            ChatMessage(
                text = "로컬 검색 오류: ${e.message}",
                isUser = false,
                source = "local-error",
            )
        }
    }

    private suspend fun serverQuery(query: String): ChatMessage {
        return try {
            val resp = ServerApi.service.query(QueryRequest(query))
            ChatMessage(
                text = resp.answer,
                isUser = false,
                citations = resp.citations,
                source = "server",
            )
        } catch (e: Exception) {
            ChatMessage(
                text = "서버 연결 실패: ${e.message}",
                isUser = false,
                source = "server-error",
            )
        }
    }

    private fun buildStatusText(): String {
        val parts = mutableListOf<String>()
        if (_state.value.dbReady) parts.add("DB✓") else parts.add("DB✗")
        if (_state.value.embeddingReady) parts.add("Embed✓") else parts.add("Embed✗")
        if (_state.value.llmReady) parts.add("LLM✓") else parts.add("LLM✗")
        if (_state.value.serverReachable) parts.add("Server✓") else parts.add("Server✗")
        return parts.joinToString(" | ")
    }

    override fun onCleared() {
        super.onCleared()
        embeddingEngine.release()
        llmEngine.release()
        chunkDb.close()
    }
}
