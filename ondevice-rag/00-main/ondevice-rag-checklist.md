# 온디바이스 RAG 구현 체크리스트

> 각 항목은 `[ ]` 대기 / `[x]` 확인 가능한 단위.
> "왜"는 case 문서에 있다. 여기선 "무엇을 체크하는가"만 적는다.

---

## A. 지식 원천 준비

- [ ] 마크다운 위키 경로가 `.env`의 `WIKI_DIR`에 잡혀 있다
- [ ] 위키는 UTF-8로 저장되어 있다
- [ ] MOC/entity/concepts 경로를 식별할 수 있다 (청크 필터 대상)

## B. 서버 (개발 전용)

- [ ] Python 가상환경에 `sentence-transformers>=3.0` 설치
- [ ] `python ingest.py` 실행 시 `mobile.db`가 생성된다
- [ ] 생성된 `mobile.db`의 청크 수가 예상치(93 내외)와 일치한다
- [ ] `python main.py` 로 FastAPI가 `0.0.0.0:8600`에 기동된다
- [ ] `GET /health` → 200
- [ ] `GET /sync` → ETag 헤더 포함, 두 번째 요청은 304

## C. 평가 하네스

- [ ] `server/scripts/embed_eval.py` 로 22 쿼리 평가 실행
- [ ] MRR ≥ 0.9, R@3 ≥ 1.0 확인
- [ ] 실패 쿼리의 top-k 원문을 수동 점검

## D. 임베딩 모델 경량화

- [ ] `optimum-cli export onnx` 로 `model.onnx` (~448MB) 생성
- [ ] `onnxruntime.quantize_dynamic` 으로 INT8 (~113MB)
- [ ] 원본 vs INT8 cosine similarity 한국어 5쿼리 ≥ 0.97
- [ ] Top-1 문서 일치 5/5

## E. 토크나이저 동봉

- [ ] `onnxruntime-extensions` SentencepieceTokenizer 를 `tokenizer.onnx` 로 변환
- [ ] HuggingFace Fast ↔ ONNX byte-exact parity 24/24 검증

## F. 폰 빌드

- [ ] `adb devices` 로 기기 연결 확인
- [ ] `assets/model.onnx`, `assets/tokenizer.onnx` 배치
- [ ] LiteRT-LM 모델(~2.4GB)을 내부 저장소에 배치
- [ ] `./scripts/run.sh --clean` 으로 빌드 + 설치 + 기동 성공

## G. 폰 런타임 검증

- [ ] 앱 상태 바: DB✓ / Embed✓ / LLM✓
- [ ] 서버 연결 상태에서 `/sync` 동작, 최초 다운로드 성공
- [ ] 비행기 모드에서 쿼리 입력 → 40초 내 답변
- [ ] 답변 문장마다 `[#n]` 인용 표시
- [ ] `[#n]` 클릭 시 원본 블로그 URL로 이동
- [ ] `local (d1, d2, d3)` 형태로 Top-3 cosine distance 표시

## H. 프롬프트 품질

- [ ] 자연어 시스템 프롬프트 사용 (JSON 스키마 강제 금지)
- [ ] `renderAnswer()` 파서와 raw/rendered 로그 훅 유지
- [ ] 답변 붕괴 샘플(`"질문 제목 한 줄"`) 발생 시 즉시 롤백 수단 있음

## I. 동기화

- [ ] 위키 커밋 후 재인제스트 → `/sync` ETag 변경
- [ ] 폰 재기동 시 새 DB 자동 다운로드
- [ ] 위키 변경 없을 때 304 반환 (전송량 0)

---

## 완료 기준

위 A~I가 모두 `[x]` 되어 있으면 **최소 온디바이스 RAG가 재현 가능한 상태**다.

- main 구조 한계: 폰 LLM 2B / 청크 < 100 / 한국어 특화
- 확장 시 재검토 대상:
  - 청크 > 수만 개 → sqlite-vec 인덱스 도입 고려 (retrieval case 참고)
  - 4B+ LLM 폰 진입 시 JSON 프롬프트 재활성화 (llm case 참고)
  - 다국어 확장 시 임베딩 재벤치마크 필요 (embedding case 참고)
