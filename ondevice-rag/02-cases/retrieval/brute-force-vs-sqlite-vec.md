# Case · 폰에서의 벡터 검색 — brute-force vs sqlite-vec

## 문제

폰에서 top-K 청크를 어떻게 찾아낼 것인가.

서버(Mac Mini)는 `sqlite-vec` 확장으로 HNSW 인덱스를 태워 쓰고 있다.
같은 방식을 폰에 이식하는 게 기본 후보였다.

제약:
- 대상 플랫폼: Android arm64
- 청크 규모: 93개 × 384차원
- 검색 응답 시간: UI 대기 가능한 수 밀리초 이내
- 추가 네이티브 의존성 최소화

## 초기 가정

1. 서버와 동일한 `sqlite-vec`를 폰에도 쓰면 구현 복잡도가 줄어든다
2. 인덱스 기반 검색(HNSW)이 brute-force보다 항상 빠르다

## 실험/검증

### sqlite-vec on Android

- `sqlite-vec`의 **arm64 Android용 네이티브 바이너리가 공식 배포되지 않음**
- 경로: 직접 크로스 컴파일 → AAR 패키징 → 앱 모듈에 포함
- 비용: NDK 빌드 체인 설정, 버전 업 시 재빌드, 메모리 풋프린트 증가
- **판정**: 이론적으로 가능하나 93청크 규모엔 과함

### Brute-force cosine (대안)

- 저장: sqlite에 `vector BLOB` 컬럼으로 float32 정규화 벡터만 저장
- 로딩: 앱 기동 시 전체 벡터를 메모리로 load (float32 배열)
- 검색: Kotlin에서 dot product 전수 스캔 → 상위 K개 추출

### 메모리 · 성능 측정

| 항목 | 값 |
|---|---|
| 벡터 총량 | 93 × 384 × 4B = **143 KB** |
| 메모리 상주 비용 | 무시 가능 |
| 전수 스캔 시간 | **< 1 ms** (S23 Ultra, 캐시 친화적 선형 액세스) |

### 서버에서 A/B 확인

- 서버(x86_64)에서 `sqlite-vec HNSW` vs 순수 `brute-force`를 같은 청크 셋으로 비교
- 수백 청크 수준에선 top-K 결과 · 지연 시간 유의한 차이 **없음**
- HNSW의 이점은 수만 청크 이상에서 본격화 (인덱스 구축·유지 비용을 검색 이득이 넘는 구간)

## 결과

- 93청크 규모에서는 인덱스 자료구조의 오버헤드가 선형 스캔보다 크다
- brute-force는 쿼리 임베딩 1회 + 벡터 N개 dot product → O(N·d), N·d = 35,712 곱셈
- UI 체감 시간에서 벡터 검색은 **사실상 무비용** (LLM 추론 40s 대비 < 0.0025%)

## 최종 선택

**sqlite에 float32 BLOB만 저장하고, 앱 Kotlin 코드에서 brute-force cosine으로 전 청크를 훑는다.**

구현 위치:
- 저장: `ChunkDatabase` (sqlite · `vector` 컬럼 BLOB)
- 검색: `VectorSearch.cosine(query, allChunks)` → top-K + distance

## 왜 이 선택이 최소 구현에 적합한가

1. **네이티브 의존성 0**: sqlite-vec AAR 빌드·관리 불필요. 앱 빌드 체인이 단순해진다.
2. **93청크 규모에서 선형 스캔이 최적**: 인덱스의 유지·구축 오버헤드가 이익보다 크다. "작은 규모 + 비지원 플랫폼"은 가장 얕은 알고리즘이 정답.
3. **디버깅 쉬움**: 검색 결과가 예상과 다를 때 확인 경로가 짧다 — "코사인 계산 한 줄". HNSW 파라미터 조정·재인덱싱 필요 없음.
4. **확장 경계가 명확**: 청크가 수만 개 이상으로 늘어나면 이 선택을 재검토하면 된다. 재검토 트리거(청크 수, 응답 시간)를 수치로 기록해두면 된다.
5. **UI 체감 시간 지배 요인이 LLM임을 드러냄**: 벡터 검색 최적화는 현재 병목이 아님을 확정해, 자원을 LLM·프롬프트 최적화로 집중시킬 근거가 된다.

## 재검토 트리거

아래 조건 중 하나라도 걸리면 sqlite-vec 또는 앱 내 HNSW 라이브러리 재도입을 검토.

- 청크 수 > **10,000**
- 벡터 검색 > **50 ms** (UI 체감 시작 구간)
- 전체 벡터 메모리 상주 비용 > **50 MB**

## 관련 문서

- 최소 구현 가이드: [../../00-main/ondevice-rag-minimal-guide.md](../../00-main/ondevice-rag-minimal-guide.md)
- 임베딩 모델·차원 선택: [../embedding/embedding-benchmark-ko.md](../embedding/embedding-benchmark-ko.md)
- 청크 필터링: [../chunking/moc-entity-filter.md](../chunking/moc-entity-filter.md)
- 참고: [sqlite-vec](https://github.com/asg017/sqlite-vec)
