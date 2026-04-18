package com.peterica.edgerag.data

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import ai.djl.huggingface.tokenizers.HuggingFaceTokenizer
import java.nio.LongBuffer

/**
 * ONNX Runtime 기반 온디바이스 임베딩 엔진.
 *
 * Phase 1: multilingual-e5-small-ko-v2 (384차원, ~30MB INT8)
 * Phase 2: EmbeddingGemma-300M (768차원, LiteRT 전환)
 *
 * assets/에 model.onnx와 tokenizer.json을 포함해야 함.
 */
class EmbeddingEngine(private val context: Context) {

    private var ortEnv: OrtEnvironment? = null
    private var session: OrtSession? = null
    private var tokenizer: HuggingFaceTokenizer? = null

    val isReady: Boolean get() = session != null && tokenizer != null

    fun initialize() {
        ortEnv = OrtEnvironment.getEnvironment()

        // assets에서 ONNX 모델 로드
        val modelBytes = context.assets.open("model.onnx").readBytes()
        session = ortEnv!!.createSession(modelBytes)

        // assets에서 토크나이저 로드
        val tokenizerBytes = context.assets.open("tokenizer.json").readBytes()
        val tokenizerStream = tokenizerBytes.inputStream()
        tokenizer = HuggingFaceTokenizer.newInstance(tokenizerStream, mapOf())
    }

    /**
     * 텍스트를 임베딩 벡터로 변환.
     * e5 모델은 쿼리에 "query: " 프리픽스 필요.
     */
    fun embed(text: String, isQuery: Boolean = true): FloatArray {
        val tokenizer = this.tokenizer ?: error("EmbeddingEngine not initialized")
        val session = this.session ?: error("EmbeddingEngine not initialized")
        val env = this.ortEnv ?: error("EmbeddingEngine not initialized")

        // e5 계열 프리픽스
        val input = if (isQuery) "query: $text" else "passage: $text"

        // 토크나이즈
        val encoding = tokenizer.encode(input)
        val inputIds = encoding.ids
        val attentionMask = encoding.attentionMask

        // ONNX 텐서 생성
        val inputIdsTensor = OnnxTensor.createTensor(
            env, LongBuffer.wrap(inputIds), longArrayOf(1, inputIds.size.toLong())
        )
        val attentionMaskTensor = OnnxTensor.createTensor(
            env, LongBuffer.wrap(attentionMask), longArrayOf(1, attentionMask.size.toLong())
        )

        // 추론 (XLM-RoBERTa 기반 e5는 token_type_ids 불필요)
        val inputs = mapOf(
            "input_ids" to inputIdsTensor,
            "attention_mask" to attentionMaskTensor,
        )

        val results = session.run(inputs)

        // 출력: [1, seq_len, 384] → mean pooling → [384]
        @Suppress("UNCHECKED_CAST")
        val output = results[0].value as Array<Array<FloatArray>>
        val tokenEmbeddings = output[0] // [seq_len, 384]

        // Mean pooling (attention mask 적용)
        val dim = tokenEmbeddings[0].size
        val pooled = FloatArray(dim)
        var validTokens = 0f

        for (i in tokenEmbeddings.indices) {
            if (attentionMask[i] == 1L) {
                for (j in 0 until dim) {
                    pooled[j] += tokenEmbeddings[i][j]
                }
                validTokens += 1f
            }
        }

        // 정규화
        if (validTokens > 0) {
            for (j in 0 until dim) pooled[j] /= validTokens
        }

        // L2 normalize
        var norm = 0f
        for (v in pooled) norm += v * v
        norm = kotlin.math.sqrt(norm)
        if (norm > 0f) {
            for (j in pooled.indices) pooled[j] /= norm
        }

        // 리소스 정리
        inputIdsTensor.close()
        attentionMaskTensor.close()
        results.close()

        return pooled
    }

    fun release() {
        session?.close()
        ortEnv?.close()
        tokenizer = null
        session = null
        ortEnv = null
    }
}
