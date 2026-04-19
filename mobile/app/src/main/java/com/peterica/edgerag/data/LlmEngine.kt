package com.peterica.edgerag.data

import android.content.Context
import android.util.Log
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.LogSeverity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Gemma 4 E2B 온디바이스 LLM 엔진 (LiteRT-LM).
 *
 * 모델 위치 정책:
 *   - 런타임: `context.filesDir/gemma-4-E2B-it.litertlm` (internal, JNI open() 가능)
 *   - 스테이징: `context.getExternalFilesDir(null)/...` (adb push로 넣기 편함)
 *   - 최초 부팅 시 external → internal로 이동하고 external 삭제.
 *   - Scoped storage의 fuse mount는 native open()에서 PERMISSION_DENIED.
 *
 * Backend는 CPU 고정 (Snapdragon 8 Gen 2 GPU delegate 이슈 회피).
 */
class LlmEngine(private val context: Context) {

    enum class State { NOT_READY, LOADING, READY, ERROR }

    var state: State = State.NOT_READY
        private set
    var errorMessage: String? = null
        private set

    private val modelFile: File get() = File(context.filesDir, MODEL_FILENAME)
    private val stagingFile: File get() = File(context.getExternalFilesDir(null), MODEL_FILENAME)

    val isModelDownloaded: Boolean get() = modelFile.exists()

    private var engine: Engine? = null

    suspend fun initialize() = withContext(Dispatchers.IO) {
        ensureModelFile()
        if (!modelFile.exists()) {
            state = State.NOT_READY
            return@withContext
        }
        state = State.LOADING
        try {
            Engine.setNativeMinLogSeverity(LogSeverity.ERROR)
            val config = EngineConfig(
                modelPath = modelFile.absolutePath,
                backend = Backend.CPU(),
            )
            val e = Engine(config)
            e.initialize()  // ~10s on SoC
            engine = e
            state = State.READY
        } catch (e: Exception) {
            Log.e("EdgeRag", "LlmEngine.initialize failed", e)
            state = State.ERROR
            errorMessage = "${e.javaClass.simpleName}: ${e.message ?: "(no msg)"}"
        }
    }

    /** 스테이징(external) 경로의 모델을 internal filesDir로 이동 (최초 1회). */
    private fun ensureModelFile() {
        if (modelFile.exists()) return
        val src = stagingFile
        if (!src.exists()) return
        try {
            Log.i("EdgeRag", "Moving model to internal: ${src.length()} bytes")
            src.copyTo(modelFile, overwrite = false)
            src.delete()
            Log.i("EdgeRag", "Model moved to ${modelFile.path}")
        } catch (e: Exception) {
            Log.e("EdgeRag", "Model move failed", e)
        }
    }

    /**
     * systemPrompt + userMessage로 답변 생성. 스트림을 accumulate하여 문자열 반환.
     */
    suspend fun generate(systemPrompt: String, userMessage: String): String =
        withContext(Dispatchers.IO) {
            val e = engine
            if (state != State.READY || e == null) {
                return@withContext "[LLM 미준비] 모델 파일이 없거나 초기화 실패: ${errorMessage ?: "(unknown)"}"
            }
            try {
                val convConfig = ConversationConfig(
                    systemInstruction = Contents.of(systemPrompt),
                )
                e.createConversation(convConfig).use { conv ->
                    val sb = StringBuilder()
                    conv.sendMessageAsync(userMessage).collect { chunk ->
                        sb.append(chunk.toString())
                    }
                    sb.toString().trim()
                }
            } catch (ex: Exception) {
                Log.e("EdgeRag", "LlmEngine.generate failed", ex)
                "로컬 LLM 오류: ${ex.javaClass.simpleName}: ${ex.message ?: "(no msg)"}"
            }
        }

    fun release() {
        try { engine?.close() } catch (_: Exception) {}
        engine = null
        state = State.NOT_READY
    }

    companion object {
        const val MODEL_FILENAME = "gemma-4-E2B-it.litertlm"
    }
}
