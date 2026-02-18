# 한국어 NER 모델 비교 및 PII 탐지 최적화 보고서

**작성일:** 2026년 2월 9일
**작성자:** Gemini (NLP/NER Researcher)
**관련 문서:** `GEMINI.md` (프로젝트 개요 및 요구사항)

## 1. 개요
본 문서는 Windows PC 기반의 대규모(50,000대+) 에이전트 환경에서 개인정보(PII)를 효율적으로 탐지하기 위한 자연어 처리(NLP) 모델을 비교 분석하고, 하드웨어 환경(CPU Only vs CPU+GPU)에 따른 최적의 기술 스택을 제안한다.

---

## 2. 2024~2025년 기준 한국어 NER 모델 비교

PC 백그라운드 서비스로 동작해야 하므로 거대 언어 모델(LLM)보다는 경량화된 **Encoder-only 모델(BERT 계열)**이 적합하다. 최신 트렌드를 포함한 주요 후보군은 다음과 같다.

| 모델명 | 아키텍처 | 특징 | 장점 | 단점 | 적합성 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **KoELECTRA v3** | ELECTRA | 토큰을 생성하는 대신 교체된 토큰을 구별하는 학습 방식(RTD) 사용. | **작은 크기 대비 높은 성능.** 학습 속도 빠름. 한국어 문맥 이해도 우수. | RoBERTa 대비 매우 복잡한 문장 추론은 약할 수 있음. | **매우 높음** (Base/Small) |
| **KLUE-RoBERTa** | RoBERTa | BERT의 학습 최적화 버전. 한국어 NLP 벤치마크(KLUE) 기준 모델. | 전반적인 정확도가 가장 안정적이고 높음. | ELECTRA 대비 모델 사이즈가 크고 추론 속도가 상대적으로 느림. | 보통 (리소스 여유 시) |
| **GLiNER (Korean)** | Bi-Encoder | 2024년 부상한 모델. 모든 엔티티 타입을 텍스트 프롬프트로 정의하여 추출. | **Zero-shot 가능.** 새로운 PII 유형 추가 시 재학습 없이 태그만 추가하면 됨. | 전통적인 NER(Token Classification)보다 추론 비용이 높을 수 있음. | 연구 필요 (확장성 우수) |
| **Pororo / spaCy-ko** | Hybrid | 규칙 기반 + 통계적 모델 / Transformer 래핑. | 사용이 간편하고 다양한 NLP 태스크 통합 지원. | 라이브러리 의존성이 크고 무거움(Python 종속성). 단일 바이너리 배포(Rust)에 부적합. | 낮음 |

---

## 3. 개인정보 탐지 특화 오픈소스 (Presidio) 현황

Microsoft의 **Presidio**는 PII 탐지의 사실상 표준(De Facto) 오픈소스 솔루션이다.

### 3.1. 아키텍처 특징
*   **Recognizer Registry:** 정규식(Pattern), 체크섬(Checksum), 모델(Model), 문맥(Context)을 조합하여 점수(Score)를 산출.
*   **Logic:** 단순 매칭이 아니라, 주변 단어(예: "전화번호:", "H.P")를 Context로 활용하여 신뢰도를 높임.

### 3.2. 한국어 지원 현황 및 한계
*   **기본 지원 미흡:** 한국어 모델(spaCy 기반)을 연결할 수 있으나, 기본 탑재된 한국어 Recognizer(주민번호 등)가 약함.
*   **Python 종속:** Presidio는 Python/Go 기반이며, Windows 에이전트(Rust)에 직접 임베딩하기엔 무겁다.
*   **적용 전략:** Presidio를 그대로 쓰기보다, **Presidio의 탐지 로직(Regex + Context + Model Ensemble)을 Rust로 포팅**하고, 모델 부분만 ONNX로 교체하는 것이 타당하다.

---

## 4. 환경별 최적화 및 제안

PC 환경은 크게 일반 사무용(CPU Only)과 고성능 워크스테이션(CPU + GPU)으로 나뉜다. 각 환경에 맞는 차별화된 전략이 필요하다.

### 시나리오 A: CPU Only (일반 사무용 PC)
대부분의 기업 PC 환경(90% 이상)에 해당한다. 사용자 경험(UX) 저하 방지가 최우선이다.

#### 기술 전략
1.  **모델 경량화:** `KoELECTRA-Small` 모델 사용.
2.  **Int8 양자화 (Quantization):** FP32 가중치를 Int8로 변환하여 모델 크기 4배 감소, 추론 속도 2~3배 향상.
3.  **하이브리드 필터링 (Funneling):**
    *   **1단계 (Regex):** `aho-corasick` 등으로 의심 키워드/패턴 초고속 스캔.
    *   **2단계 (Light NER):** 필터링된 문장에 대해서만 NER 수행.
4.  **스레드 제어:** 백그라운드 스레드 우선순위를 `Low` 또는 `Idle`로 설정하여 사용자 작업 간섭 최소화.

### 시나리오 B: CPU + GPU (고성능 PC/개발자/디자이너)
NVIDIA GeForce/RTX 등이 장착된 PC. 더 높은 정확도와 처리 속도를 확보할 수 있다.

#### 기술 전략
1.  **고성능 모델:** `KoELECTRA-Base` 또는 `KLUE-RoBERTa-Base` 사용 가능. Small 모델 대비 복잡한 문맥 인식률 향상.
2.  **하드웨어 가속 (DirectML / CUDA):**
    *   Windows 환경 특성상 특정 벤더(NVIDIA)에 종속되지 않는 **DirectML**을 활용하면 AMD, Intel GPU 가속도 지원 가능 (ONNX Runtime 지원).
    *   NVIDIA 전용 환경이라면 **CUDA Execution Provider** 사용 시 압도적 성능.
3.  **FP16 정밀도:** 양자화 대신 FP16(Half Precision)을 사용하여 속도와 정확도 균형 유지.
4.  **배치 처리 (Batch Processing):** GPU 메모리를 활용하여 여러 파일을 동시에 스캔하거나, 하나의 파일 내 여러 문단을 한 번에 추론하여 처리량(Throughput) 극대화.

---

## 5. 결론 및 최종 권장 스택

프로젝트 목표(오탐 감소, 실시간 감지)를 달성하기 위해 다음과 같은 이원화 전략을 제안한다.

### 5.1. 추천 모델
*   **기본 모델 (Default):** **KoELECTRA-Small-v3 (Fine-tuned)**
    *   *이유:* 모든 환경에서 구동 가능하며, 이름/주소 등 비정형 PII 탐지에 충분한 성능 제공.
*   **고성능 옵션 (Optional):** **KLUE-RoBERTa-Base**
    *   *이유:* GPU 가용 시 선택적으로 다운로드/로드하여 오탐률을 극한으로 낮춤.

### 5.2. 구현 아키텍처 (Rust Client)
| 구분 | CPU Only 모드 | CPU + GPU 모드 |
| :--- | :--- | :--- |
| **추론 엔진** | `ort` (ONNX Runtime) + CPU EP | `ort` + DirectML / CUDA EP |
| **모델 포맷** | ONNX (Int8 Quantized) | ONNX (FP16 or FP32) |
| **전처리** | Regex 필터링 필수 (부하 감소) | Regex 필터링 권장 (선택적 Batch) |
| **탐지 전략** | 의심 문장만 핀포인트 추론 | 대량 텍스트 고속 일괄 추론 |

### 5.3. 실행 계획 (Action Items)
1.  **데이터셋 구축:** PII 특화 말뭉치 확보 및 `KoELECTRA-Small` 학습.
2.  **ONNX 변환:** 학습된 모델을 Int8(CPU용)과 FP16(GPU용) 두 가지 버전으로 변환.
3.  **에이전트 로직 구현:** 시작 시 하드웨어 사양을 감지하여 적절한 모델 및 실행 공급자(Execution Provider)를 동적으로 선택하는 로직 개발.