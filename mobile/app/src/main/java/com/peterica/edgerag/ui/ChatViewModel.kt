package com.peterica.edgerag.ui

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.peterica.edgerag.data.*
import com.peterica.edgerag.db.ChunkDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
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
    /** 상시 아이콘 라인 (DB✓ | Embed✓ | ...). 준비 상태 플래그 변화 시 자동 갱신. */
    val statusIcons: String = "초기화 중...",
    /** 일시 메시지 (동기화 완료/실패/에러). null이면 두 번째 줄 숨김. auto-clear 로직으로 수 초 후 사라짐. */
    val transientMessage: String? = null,
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

    private suspend fun initialize() = withContext(Dispatchers.IO) {
        refreshIcons()  // "초기화 중..." → 첫 아이콘 라인

        // DB 로드 (SQLite open + 쿼리는 IO 작업)
        if (chunkDb.isReady) {
            chunkDb.open()
            val chunks = chunkDb.loadAllChunks()
            val embeddings = chunkDb.loadEmbeddings()
            vectorSearch.load(chunks, embeddings)
            _state.value = _state.value.copy(dbReady = true)
        } else {
            _state.value = _state.value.copy(transientMessage = "DB 없음 — 동기화 필요")
        }
        refreshIcons()

        // 임베딩 엔진 초기화
        try {
            embeddingEngine.initialize()
            _state.value = _state.value.copy(embeddingReady = true)
        } catch (e: Exception) {
            Log.e("EdgeRag", "EmbeddingEngine.initialize failed", e)
            _state.value = _state.value.copy(
                transientMessage = "Embed 실패: ${e.javaClass.simpleName} — ${e.message ?: "(no msg)"}"
            )
        }
        refreshIcons()

        // LLM 초기화
        llmEngine.initialize()
        _state.value = _state.value.copy(
            llmReady = llmEngine.state == LlmEngine.State.READY,
        )
        refreshIcons()

        // 서버 연결 확인 (P2-17: 1회 retry)
        var reachable = ServerApi.isServerReachable()
        if (!reachable) {
            delay(2000)
            reachable = ServerApi.isServerReachable()
        }
        _state.value = _state.value.copy(serverReachable = reachable)
        refreshIcons()
    }

    /** 준비 플래그 → 아이콘 라인 갱신 (상시 표시). transientMessage는 건드리지 않음. */
    private fun refreshIcons() {
        _state.value = _state.value.copy(statusIcons = buildStatusText())
    }

    /** 일시 메시지 표시 + auto-clear (기본 2.5s). coroutine scope는 호출처에서 보장. */
    private fun showTransient(message: String, clearAfterMs: Long = 2500L) {
        _state.value = _state.value.copy(transientMessage = message)
        viewModelScope.launch {
            delay(clearAfterMs)
            // 그 사이 다른 메시지로 덮였으면 건드리지 않음
            if (_state.value.transientMessage == message) {
                _state.value = _state.value.copy(transientMessage = null)
            }
        }
    }

    /**
     * 서버에서 mobile.db 동기화.
     * P2-14: 로컬 wiki_commit을 If-None-Match로 보내면 서버가 304로 응답 → 다운로드 스킵.
     * 200 응답이면 새 DB로 교체. 대역폭·시간 절약 (118 청크 ~1.7MB 스케일에서도 의미 있음).
     */
    fun syncDatabase() {
        viewModelScope.launch {
            _state.value = _state.value.copy(isSyncing = true, transientMessage = "DB 동기화 중...")
            try {
                val result = withContext(Dispatchers.IO) {
                    val localEtag = chunkDb.getLocalSyncEtag()
                    val etag = localEtag?.let { "\"$it\"" }

                    val resp = ServerApi.service.syncDb(ifNoneMatch = etag)
                    when (resp.code()) {
                        304 -> SyncResult.NotModified
                        200 -> {
                            val body = resp.body() ?: error("/sync 200 without body")
                            val bytes = body.bytes()
                            chunkDb.saveDbFile(bytes)
                            chunkDb.open()
                            val chunks = chunkDb.loadAllChunks()
                            val embeddings = chunkDb.loadEmbeddings()
                            vectorSearch.load(chunks, embeddings)
                            SyncResult.Downloaded(chunks.size)
                        }
                        else -> error("/sync unexpected status: ${resp.code()}")
                    }
                }

                _state.value = _state.value.copy(
                    dbReady = chunkDb.isReady,
                    isSyncing = false,
                    serverReachable = true,
                )
                refreshIcons()
                when (result) {
                    is SyncResult.NotModified -> {
                        Log.i("EdgeRag", "sync: already up to date (304)")
                        showTransient("이미 최신 (304)")
                    }
                    is SyncResult.Downloaded -> {
                        Log.i("EdgeRag", "sync: downloaded ${result.chunkCount} chunks")
                        showTransient("동기화 완료 (${result.chunkCount} 청크)")
                    }
                }
            } catch (e: Exception) {
                Log.e("EdgeRag", "syncDatabase failed", e)
                val kind = e.javaClass.simpleName
                val msg = e.message ?: "(no msg)"
                _state.value = _state.value.copy(isSyncing = false)
                showTransient("동기화 실패: $kind — $msg", clearAfterMs = 5000L)
            }
        }
    }

    private sealed interface SyncResult {
        data object NotModified : SyncResult
        data class Downloaded(val chunkCount: Int) : SyncResult
    }

    /** 로컬 RAG 검색 + LLM 응답 */
    fun sendMessage(text: String) {
        val userMsg = ChatMessage(text = text, isUser = true)
        _state.value = _state.value.copy(
            messages = _state.value.messages + userMsg,
            isLoading = true,
        )

        viewModelScope.launch {
            // 로컬 경로가 전부 준비됐을 때만 localSearch, 아니면 서버 시도.
            // serverReachable 플래그는 startup 시점의 스냅샷이라 신뢰하지 않고
            // 항상 서버 호출 → 실패 시 serverQuery 내부 catch가 에러 메시지 반환.
            val response = if (_state.value.dbReady && _state.value.embeddingReady) {
                localSearch(text)
            } else {
                serverQuery(text)
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

            // 시스템 프롬프트 — v4-lite-v2 (Step B-1).
            // P2-18에서 서버 v4 JSON을 이식해봤지만 E2B(2B)에서 역효과 — JSON 제약에 신경쓰다
            // 답변이 질문 제목 반복 수준까지 축소됨. 품질로는 자연어 v4-lite-v2가 우수해 롤백.
            // renderAnswer + Log는 남겨둠 — raw가 JSON 아니면 폴백으로 그대로 통과하므로 무해.
            // 4B 모델로 스케일업 시 프롬프트만 v4 JSON으로 다시 바꾸면 즉시 재활성.
            val ctx = results.mapIndexed { i, r ->
                "[#${i + 1}] source=${r.chunk.docPath} heading=${r.chunk.heading ?: ""}\n${r.chunk.text}"
            }.joinToString("\n\n---\n\n")

            val systemPrompt = buildString {
                appendLine("당신은 peterica-blog-wiki 지식베이스를 근거로 답하는 한국어 기술 어시스턴트입니다.")
                appendLine()
                appendLine("규칙:")
                appendLine("1) CONTEXT의 내용을 직접 인용하거나 요약해 한국어로 설명하세요. CONTEXT 텍스트를 근거 삼아 답을 구성하세요.")
                appendLine("2) 답변은 1~3문장으로 CONTEXT의 핵심 내용을 전달하세요.")
                appendLine("3) 각 문장 끝에 근거 청크 번호를 [#n] 형태로 붙이세요 (예: \"쿠버네티스의 graceful shutdown은 … 입니다. [#1]\").")
                appendLine("4) CONTEXT가 질문 주제와 완전히 무관한 경우에만 \"문서에 근거 없음\" 한 줄로 답하세요. 부분적으로라도 관련 내용이 있으면 그 내용을 근거로 답변을 구성하세요.")
                appendLine("5) CONTEXT에 전혀 없는 외부 지식은 더하지 마세요.")
                appendLine("6) \"일반적으로\", \"대체로\", \"아마\", \"추측하면\", \"커뮤니티에서\", \"경험상\" 같은 표현을 쓰지 마세요.")
                appendLine()
                appendLine("CONTEXT:")
                append(ctx)
            }

            // LLM 생성 + renderAnswer(JSON이면 포맷, 아니면 폴백으로 원문 통과).
            val raw = llmEngine.generate(systemPrompt, query)
            val answer = renderAnswer(raw)
            Log.i("EdgeRag", "localSearch Q: $query")
            Log.i("EdgeRag", "localSearch raw: $raw")
            Log.i("EdgeRag", "localSearch rendered: $answer")

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
            if (!_state.value.serverReachable) {
                _state.value = _state.value.copy(serverReachable = true)
                refreshIcons()
            }
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

    /**
     * v4 JSON 스키마 응답을 사람 가독 텍스트로 렌더. 서버 `rag.render_answer`와 동치.
     * - grounded=false → "문서에 근거 없음"
     * - grounded=true  → "문장1 [#c]. 문장2 [#c][#c]." 형식
     * - JSON 파싱 실패 → 원문 그대로 (폴백 — E2B가 스키마 깨뜨린 경우 사용자에게라도 뭔가 보여줌)
     */
    private fun renderAnswer(raw: String): String {
        var cleaned = raw.trim()
        if (cleaned.startsWith("```")) {
            cleaned = cleaned.removePrefix("```json").removePrefix("```").trimStart()
            val fenceEnd = cleaned.lastIndexOf("```")
            if (fenceEnd >= 0) cleaned = cleaned.substring(0, fenceEnd).trimEnd()
        }
        return try {
            val data = org.json.JSONObject(cleaned)
            if (!data.optBoolean("grounded", false)) return "문서에 근거 없음"
            val sentences = data.optJSONArray("sentences") ?: return "문서에 근거 없음"
            val parts = mutableListOf<String>()
            for (i in 0 until sentences.length()) {
                val s = sentences.optJSONObject(i) ?: continue
                var text = s.optString("text", "").trim()
                if (text.isEmpty()) continue
                val citeArr = s.optJSONArray("cite")
                val cites = mutableListOf<Int>()
                if (citeArr != null) {
                    for (j in 0 until citeArr.length()) cites.add(citeArr.optInt(j))
                }
                var trailing = ""
                while (text.isNotEmpty() && text.last() in ".?!".toSet()) {
                    trailing = text.last() + trailing
                    text = text.dropLast(1)
                }
                if (trailing.isEmpty()) trailing = "."
                val citeStr = cites.joinToString("") { "[#$it]" }
                parts.add("${text.trimEnd()} $citeStr$trailing".trim())
            }
            if (parts.isEmpty()) "문서에 근거 없음" else parts.joinToString(" ")
        } catch (_: org.json.JSONException) {
            raw
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
