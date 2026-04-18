package com.peterica.edgerag.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Gemma 4 E2B 온디바이스 LLM 엔진 (LiteRT-LM).
 *
 * 모델 파일(.litertlm)은 앱 내부 저장소에 다운로드하여 사용.
 * GPU delegate는 Snapdragon 8 Gen 2에서 버그가 있으므로 CPU fallback.
 */
class LlmEngine(private val context: Context) {

    // LiteRT-LM은 실제 라이브러리 연동 시 구현.
    // 현재는 인터페이스만 정의하여 앱 구조를 확립.

    enum class State { NOT_READY, LOADING, READY, ERROR }

    var state: State = State.NOT_READY
        private set

    var errorMessage: String? = null
        private set

    private val modelFile get() = context.filesDir.resolve("gemma4-e2b.litertlm")

    val isModelDownloaded: Boolean get() = modelFile.exists()

    /**
     * LLM 엔진 초기화.
     * 모델 파일이 존재하면 로드, 없으면 NOT_READY 유지.
     */
    suspend fun initialize() = withContext(Dispatchers.IO) {
        if (!modelFile.exists()) {
            state = State.NOT_READY
            return@withContext
        }

        state = State.LOADING
        try {
            // TODO: LiteRT-LM 실제 초기화
            // val engineConfig = EngineConfig(
            //     modelPath = modelFile.absolutePath,
            //     backend = Backend.CPU()
            // )
            // engine = Engine(engineConfig)
            // engine.initialize()
            state = State.READY
        } catch (e: Exception) {
            state = State.ERROR
            errorMessage = e.message
        }
    }

    /**
     * 시스템 프롬프트 + 사용자 질문으로 답변 생성.
     * @param systemPrompt RAG 검색 결과가 포함된 시스템 프롬프트
     * @param userMessage 사용자 질문
     * @return 생성된 답변 텍스트
     */
    suspend fun generate(systemPrompt: String, userMessage: String): String =
        withContext(Dispatchers.IO) {
            if (state != State.READY) {
                return@withContext "[LLM 미준비] 모델이 로드되지 않았습니다."
            }

            // TODO: LiteRT-LM 실제 생성
            // engine.createConversation().use { conversation ->
            //     conversation.setSystemInstruction(systemPrompt)
            //     conversation.sendMessage(userMessage)
            // }

            "[LLM 미연동] Gemma 4 E2B 연동 대기 중. 시스템 프롬프트가 정상 구성되었습니다."
        }

    fun release() {
        // TODO: engine?.close()
        state = State.NOT_READY
    }
}
