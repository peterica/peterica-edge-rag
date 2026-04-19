package com.peterica.edgerag.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mikepenz.markdown.m3.Markdown
import com.peterica.edgerag.util.DocUrlMapper

@Composable
fun ChatScreen(viewModel: ChatViewModel) {
    val state by viewModel.state.collectAsState()
    var inputText by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

    // 새 메시지 시 자동 스크롤
    LaunchedEffect(state.messages.size) {
        if (state.messages.isNotEmpty()) {
            listState.animateScrollToItem(state.messages.size - 1)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .imePadding()
    ) {
        // 상단 바
        TopBar(state = state, onSync = { viewModel.syncDatabase() })

        // 메시지 리스트
        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            contentPadding = PaddingValues(vertical = 8.dp),
        ) {
            if (state.messages.isEmpty()) {
                item { EmptyState() }
            }

            items(state.messages) { message ->
                MessageBubble(message)
            }

            if (state.isLoading) {
                item {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Start,
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(24.dp),
                            strokeWidth = 2.dp,
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("검색 중...", color = Color.Gray, fontSize = 14.sp)
                    }
                }
            }
        }

        // 입력 영역
        InputBar(
            text = inputText,
            onTextChange = { inputText = it },
            onSend = {
                if (inputText.isNotBlank()) {
                    viewModel.sendMessage(inputText.trim())
                    inputText = ""
                }
            },
            onServerSend = {
                if (inputText.isNotBlank()) {
                    viewModel.sendToServer(inputText.trim())
                    inputText = ""
                }
            },
            isLoading = state.isLoading,
            serverReachable = state.serverReachable,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TopBar(state: ChatUiState, onSync: () -> Unit) {
    TopAppBar(
        title = {
            Column {
                Text("Peterica Edge RAG", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                // 상시 상태 아이콘 라인
                Text(state.statusIcons, fontSize = 11.sp, color = Color.Gray)
                // 일시 메시지 (있을 때만, 3번째 줄) — 동기화 결과/에러 auto-clear
                state.transientMessage?.let {
                    Text(
                        text = it,
                        fontSize = 10.sp,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
        },
        actions = {
            if (state.isSyncing) {
                CircularProgressIndicator(
                    modifier = Modifier.size(20.dp).padding(end = 8.dp),
                    strokeWidth = 2.dp,
                )
            } else {
                TextButton(onClick = onSync) {
                    Text("동기화", fontSize = 12.sp)
                }
            }
        },
    )
}

@Composable
private fun EmptyState() {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Peterica Edge RAG", fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Spacer(modifier = Modifier.height(8.dp))
        Text("블로그 지식 기반 AI 어시스턴트", color = Color.Gray)
        Spacer(modifier = Modifier.height(24.dp))
        Text("질문 예시:", fontWeight = FontWeight.Medium)
        Spacer(modifier = Modifier.height(8.dp))

        listOf(
            "Kubernetes Probe 종류는?",
            "APM 모니터링이란?",
            "RAG 시스템 구조 설명해줘",
        ).forEach { example ->
            Text(
                text = "\"$example\"",
                color = MaterialTheme.colorScheme.primary,
                fontSize = 14.sp,
                modifier = Modifier.padding(vertical = 2.dp),
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun MessageBubble(message: ChatMessage) {
    val context = LocalContext.current
    val isUser = message.isUser
    val bgColor = if (isUser) MaterialTheme.colorScheme.primary
                  else MaterialTheme.colorScheme.surfaceVariant
    val textColor = if (isUser) Color.White
                    else MaterialTheme.colorScheme.onSurface

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = if (isUser) Alignment.End else Alignment.Start,
    ) {
        Box(
            modifier = Modifier
                .widthIn(max = 300.dp)
                .background(bgColor, RoundedCornerShape(12.dp))
                .padding(12.dp),
        ) {
            if (isUser) {
                // 사용자 입력은 원본 그대로(마크다운 파싱 금지 — 일반 텍스트 보존)
                Text(text = message.text, color = textColor, fontSize = 14.sp)
            } else {
                // LLM 답변은 마크다운 렌더링 (`**bold**`, `* bullet`, `## heading`, code 등)
                Markdown(content = message.text)
            }
        }

        // 인용 표시 — posts/ 경로면 블로그 URL 탭으로 열기
        if (message.citations.isNotEmpty()) {
            FlowRow(
                modifier = Modifier
                    .widthIn(max = 300.dp)
                    .padding(top = 2.dp, start = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                message.citations.forEach { citation ->
                    val url = DocUrlMapper.toBlogUrl(citation.doc_path)
                    val label = "[#${citation.index}] ${citation.heading ?: citation.doc_path}"
                    if (url != null) {
                        Text(
                            text = label,
                            fontSize = 10.sp,
                            color = MaterialTheme.colorScheme.primary,
                            textDecoration = TextDecoration.Underline,
                            modifier = Modifier.clickable {
                                context.startActivity(
                                    Intent(Intent.ACTION_VIEW, Uri.parse(url))
                                )
                            },
                        )
                    } else {
                        Text(text = label, fontSize = 10.sp, color = Color.Gray)
                    }
                }
            }
        }

        // 소스 표시
        if (message.source.isNotBlank() && !isUser) {
            Text(
                text = message.source,
                fontSize = 10.sp,
                color = Color.Gray,
                modifier = Modifier.padding(top = 1.dp, start = 4.dp),
            )
        }
    }
}

@Composable
private fun InputBar(
    text: String,
    onTextChange: (String) -> Unit,
    onSend: () -> Unit,
    onServerSend: () -> Unit,
    isLoading: Boolean,
    serverReachable: Boolean,
) {
    Surface(
        tonalElevation = 2.dp,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier
                .padding(8.dp)
                .fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = text,
                onValueChange = onTextChange,
                modifier = Modifier.weight(1f),
                placeholder = { Text("질문을 입력하세요") },
                maxLines = 3,
                enabled = !isLoading,
            )

            Spacer(modifier = Modifier.width(4.dp))

            Column {
                Button(
                    onClick = onSend,
                    enabled = text.isNotBlank() && !isLoading,
                    modifier = Modifier.height(36.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp),
                ) {
                    Text("검색", fontSize = 12.sp)
                }

                Spacer(modifier = Modifier.height(4.dp))

                OutlinedButton(
                    onClick = onServerSend,
                    enabled = text.isNotBlank() && !isLoading && serverReachable,
                    modifier = Modifier.height(36.dp),
                    contentPadding = PaddingValues(horizontal = 8.dp),
                ) {
                    Text("서버", fontSize = 12.sp)
                }
            }
        }
    }
}
