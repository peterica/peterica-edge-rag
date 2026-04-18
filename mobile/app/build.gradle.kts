plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.peterica.edgerag"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.peterica.edgerag"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        // 서버 URL (Mac Mini)
        buildConfigField("String", "SERVER_URL", "\"http://192.168.0.10:8600\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    // Compose
    val composeBom = platform("androidx.compose:compose-bom:2025.04.00")
    implementation(composeBom)
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.0")
    debugImplementation("androidx.compose.ui:ui-tooling")

    // Core
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.9.0")

    // LiteRT-LM (Gemma 4 E2B on-device LLM)
    // TODO: 실제 공개된 버전 확인 후 활성화
    // implementation("com.google.ai.edge.litertlm:litertlm-android:0.1.0")

    // ONNX Runtime (e5-small-ko-v2 embedding)
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.24.3")

    // DJL Tokenizer (for embedding model)
    implementation("ai.djl.huggingface:tokenizers:0.25.0")

    // Networking (server fallback)
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
}
