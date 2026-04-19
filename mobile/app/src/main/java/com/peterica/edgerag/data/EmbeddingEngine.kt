package com.peterica.edgerag.data

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import ai.onnxruntime.extensions.OrtxPackage
import android.content.Context
import java.nio.LongBuffer

/**
 * ONNX Runtime 기반 온디바이스 임베딩 엔진.
 *
 * 토크나이저도 ONNX 그래프로 내장 (P2-16, onnxruntime-extensions).
 * DJL HuggingFaceTokenizer는 Android arm64 native 미배포로 제거 (P2-15 원인).
 *
 * assets/model.onnx:     e5-small-ko-v2 (INT8, 118MB, 384차원 XLM-RoBERTa)
 * assets/tokenizer.onnx: SentencepieceTokenizer custom op + Cast (5MB)
 *
 * 파이프라인:
 *   text → tokenizer session → input_ids (flat) → [1, L] reshape
 *        → model session → token embeddings [1, L, 384]
 *        → mean pool + L2 normalize → FloatArray(384)
 */
class EmbeddingEngine(private val context: Context) {

    private var ortEnv: OrtEnvironment? = null
    private var tokenizerSession: OrtSession? = null
    private var modelSession: OrtSession? = null

    val isReady: Boolean
        get() = tokenizerSession != null && modelSession != null

    fun initialize() {
        ortEnv = OrtEnvironment.getEnvironment()

        // 토크나이저 session — ORT-extensions 커스텀 op 등록 필요
        val tokOpts = OrtSession.SessionOptions().apply {
            registerCustomOpLibrary(OrtxPackage.getLibraryPath())
        }
        val tokBytes = context.assets.open("tokenizer.onnx").readBytes()
        tokenizerSession = ortEnv!!.createSession(tokBytes, tokOpts)

        // 임베딩 모델 session — 커스텀 op 불필요
        val modelBytes = context.assets.open("model.onnx").readBytes()
        modelSession = ortEnv!!.createSession(modelBytes)
    }

    /**
     * 텍스트를 임베딩 벡터로 변환.
     * e5 계열은 쿼리/패시지 프리픽스 비대칭이 필수.
     */
    fun embed(text: String, isQuery: Boolean = true): FloatArray {
        val env = ortEnv ?: error("EmbeddingEngine not initialized")
        val tokSess = tokenizerSession ?: error("EmbeddingEngine not initialized")
        val modelSess = modelSession ?: error("EmbeddingEngine not initialized")

        val prefixed = if (isQuery) "query: $text" else "passage: $text"

        // --- 1) 토크나이즈 (ORT-extensions) ---
        // 입력: string tensor [1], 출력: tokens_cast int64 [L] (flat, BOS/EOS 포함)
        val textTensor = OnnxTensor.createTensor(
            env,
            arrayOf(prefixed),
            longArrayOf(1L),
        )
        val tokResults = tokSess.run(mapOf("inputs" to textTensor))
        @Suppress("UNCHECKED_CAST")
        val tokensFlat = (tokResults["tokens_cast"].get().value as LongArray)
        tokResults.close()
        textTensor.close()

        // 512 토큰 초과 시 tail truncation (모델 max_length)
        val seqLen = minOf(tokensFlat.size, MAX_SEQ_LEN)
        val inputIds = if (seqLen == tokensFlat.size) tokensFlat else tokensFlat.copyOf(seqLen)
        val attentionMask = LongArray(seqLen) { 1L }  // SentencepieceTokenizer는 패딩 없음

        // --- 2) 임베딩 모델 ---
        val shape = longArrayOf(1L, seqLen.toLong())
        val inputIdsTensor = OnnxTensor.createTensor(env, LongBuffer.wrap(inputIds), shape)
        val attentionMaskTensor = OnnxTensor.createTensor(env, LongBuffer.wrap(attentionMask), shape)

        val inputs = mapOf(
            "input_ids" to inputIdsTensor,
            "attention_mask" to attentionMaskTensor,
        )
        val results = modelSess.run(inputs)

        @Suppress("UNCHECKED_CAST")
        val output = results[0].value as Array<Array<FloatArray>>
        val tokenEmbeddings = output[0]  // [seq_len, 384]
        val dim = tokenEmbeddings[0].size
        val pooled = FloatArray(dim)
        var validTokens = 0f

        for (i in tokenEmbeddings.indices) {
            if (attentionMask[i] == 1L) {
                for (j in 0 until dim) pooled[j] += tokenEmbeddings[i][j]
                validTokens += 1f
            }
        }
        if (validTokens > 0f) {
            for (j in 0 until dim) pooled[j] /= validTokens
        }

        var norm = 0f
        for (v in pooled) norm += v * v
        norm = kotlin.math.sqrt(norm)
        if (norm > 0f) {
            for (j in pooled.indices) pooled[j] /= norm
        }

        inputIdsTensor.close()
        attentionMaskTensor.close()
        results.close()

        return pooled
    }

    fun release() {
        modelSession?.close()
        tokenizerSession?.close()
        ortEnv?.close()
        modelSession = null
        tokenizerSession = null
        ortEnv = null
    }

    companion object {
        private const val MAX_SEQ_LEN = 512  // XLM-RoBERTa base
    }
}
