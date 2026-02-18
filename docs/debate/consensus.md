# Debate Consensus — 3 AI, 2 Rounds

**Date:** 2026-02-10
**Participants:** Claude, Gemini, Codex
**Sources:** round1-*.md, round2-*.md (총 6개 문서)

---

## 논점 1: NER 모델 선택

- **결론:** KoELECTRA-Small v3 (INT8 양자화, ~14MB)를 기본 모델로 확정. MVP에서 NER은 **베타(기본 비활성화, Opt-in)**로만 제공하며, 판정이 아닌 **"승격 보조 신호"** 역할로 제한한다. "AI 예산(분당 N회)" 하드캡을 도입하여 CPU 독점을 방지한다.
- **합의 수준:** ⭐⭐⭐ 전원 동의
- **근거 요약:**
  - Gemini: 크기(14MB)/속도 대비 유일한 현실적 선택지. CPU Only 환경에서 대안 없음.
  - Codex: 공개 벤치마크 F1은 PII 성능이 아님. 토크나이저 병목, INT8 엔티티별 민감도, CPU ISA 편차를 감안하면 하드캡 필수.
  - Claude: Small로 시작 + 파일럿 A/B 테스트로 Base와 비교 후 GA 모델 결정. 공개 F1을 설계 근거로 사용하지 않음.
- **조건/유보사항:**
  - Phase 0에서 PII 전용 평가셋 구축 + i3/4GB 실측이 전제.
  - 토크나이저 포함 end-to-end 지연이 P95 200ms를 초과하면 NER은 MVP 기본 OFF로 전환.
  - INT8 양자화 후 엔티티 타입별 threshold 재캘리브레이션 필수.

---

## 논점 2: 탐지 파이프라인 구조

- **결론:** **저비용→고비용 깔때기(Funnel)** 구조 확정. Metadata → Regex/Checksum → (선택적) NER 순서. 텍스트 추출과 NER은 **별도 워커 프로세스에서 격리** 실행. USN Journal이 증분 스캔의 **본체(backbone)**이며, ReadDirectoryChangesW는 핵심 폴더 한정 보조 수단. 정책/룰 업데이트는 **서명 + 카나리 + 롤백** 필수.
- **합의 수준:** ⭐⭐⭐ 전원 동의
- **근거 요약:**
  - Gemini: Aho-Corasick 키워드 프리필터로 NER 도달 데이터 최소화. 의심 구간(Suspicious Span)만 NER에 전달.
  - Codex: 파이프라인의 핵심은 "단계 수"가 아니라 가드레일/격리/백프레셔. ReadDirectoryChangesW는 이벤트를 놓치므로 USN catch-up이 본체. ZIP bomb 대응(깊이/크기/개수/타임아웃/경로 트래버설) 필수.
  - Claude: 이산 판정(CONFIRMED/SUSPECT/DISMISSED) 3단계로 스코어링 단순화. 연속 가중치(x1.2 등)는 평가셋 없이 무너짐.
- **조건/유보사항:**
  - 스코어링 고도화(연속 가중치)는 Phase 2에서 평가셋 축적 후 도입.
  - YAML DSL은 MVP에서 "스키마 고정 + 열거형만"으로 최소화. 표현식(미니 언어)으로 확장하지 않음.
  - **USN 불가 시 폴백 규칙 필수** *(Round 3 Codex 피드백 반영)*: USN 비활성/권한 부족/저널 롤오버/볼륨 비-NTFS 시나리오에 대해 폴백(주기적 느린 스캔 또는 해당 볼륨 Limited/Unsupported 처리) 규칙을 설계에 포함해야 한다.

---

## 논점 3: 기술 스택

- **결론:** **클라이언트 = Rust 단일 언어(기본안). 서버 = Go. MVP 서버 인프라 = PostgreSQL 단일 + 선택적 Redis.** Kafka/Elasticsearch/NATS는 MVP에서 제외.
- **합의 수준:** ⭐⭐⭐ 전원 동의 (기본안). Codex는 극단적 .NET 편향 팀에 한해 IPC 예외안 유보.
- **근거 요약:**
  - 3팀 모두: 50,000대 상주 에이전트에서 메모리 안전성/GC 없는 예측 가능한 성능은 협상 불가. Rust가 유일한 합리적 선택.
  - Gemini/Claude: Go 서버는 고루틴 기반 동시성 + 빠른 개발 속도. Rust 서버는 이 프로젝트에서 과잉.
  - Codex: MVP 서버에 큐/검색엔진 올리면 운영 복잡도가 개발 속도를 죽임. PostgreSQL 단일 모놀리스로 시작. 단, 팀 역량이 극단적으로 .NET 편향인 경우에 한해 **FFI가 아닌 프로세스 경계(IPC, Named Pipe)로만** "C# 서비스 + Rust 워커" 예외안을 열어둘 수 있다는 입장. *(Round 3 Codex 피드백 반영)*
- **조건/유보사항:**
  - Phase 2+ 에이전트 1,000대 초과 시 NATS 도입 검토.
  - Phase 3+ 로그 검색/분석 필요 시 Elasticsearch 도입 검토.
  - Cargo workspace는 MVP에서 10-12개 이하 crate. 필요 시에만 분리.

---

## 논점 4: MVP 범위

- **결론:** MVP = **구조화 PII(주민/사업자/카드/이메일/전화) + Checksum 검증 + USN 기반 증분 스캔 + 핵심 폴더(3개) 한정 이벤트 워처(큐잉까지만, 즉시 스캔 아님) + 최소 서버 콘솔 + 워커 격리 + Panic Mode.** Phase 0(2-4주) PoC로 Kill/Pivot 기준 검증 후 Phase 1 MVP(6-10주) 진행. 대상 100-500대 파일럿.
  > **참고** *(Round 3 Codex 피드백 반영)*: "실시간 워처"는 이벤트 수신 후 큐 적재까지만을 의미한다. 실제 스캔 타이밍은 리소스 거버너가 CPU/사용자 활동 기반으로 결정하며, "Quiet Agent" 목표와 충돌하지 않도록 한다.
- **합의 수준:** ⭐⭐⭐ 전원 동의
- **근거 요약:**
  - Codex: MVP는 "기술 데모"가 아니라 "파일럿 운영". 기능보다 안정성/가드레일/지원 매트릭스 우선.
  - Claude: NER은 독립 R&D 트랙. MVP 가치는 NER 없이도 성립. Phase 0에서 HWP 파싱/텍스트 추출/NER 지연 실측 필수.
  - Gemini: "꿈의 스펙"에서 "현실의 제품"으로. MVP 목표 = "죽지 않는 에이전트" + "거짓말하지 않는 탐지".
- **MVP에서 제외 확정:**

  | 항목 | 상태 | 비고 |
  |:---|:---|:---|
  | NER | 바이너리 포함, 기본 OFF (Labs/Opt-in) | 서버 정책으로 활성화 제어 |
  | HWP/PDF/MSG | Phase 2 | Phase 0에서 성공률 검증 |
  | DRM 내용 스캔 | Phase 2 | MVP는 DRM 감지(UNSCANNABLE)만 |
  | 자동 업데이트 | Phase 2 | MVP는 MSI + PMS/AD 배포 |
  | Kafka/ES/NATS | Phase 2-3 | MVP는 PostgreSQL 단일 |
  | 멀티테넌시 SaaS | Phase 3 | |
  | OCR (스캔 PDF) | Phase 3 | |

---

## 논점 5: 보안/라이선스 설계

- **결론:** MVP 인증 = **Join Token(1회 등록) + JWT Access/Refresh Token.** mTLS는 서버 간 통신에만 적용, 클라이언트 mTLS는 MVP 스코프 외(Phase 2 도입 예정). **Certificate Pinning은 기본 OFF(옵션).** Anti-replay = request_id + device_seq. **원문 PII 미전송**을 기본 원칙으로 확정. Path Privacy Mode 도입(파일명도 민감할 수 있음).
  > **참고** *(Round 3 Codex 피드백 반영)*: 클라이언트 mTLS를 "Phase 2"로 미루는 것은 합의된 기술적 결론이 아니라 **MVP 스코프 선택**이다. 설계 단계에서는 Token-only 모드와 mTLS+Token 모드를 모두 수용할 수 있도록 인터페이스를 잡아야 하며, 고객 환경에 따라 단계적으로 올릴 수 있어야 한다.
- **합의 수준:** ⭐⭐⭐ 전원 동의 (MVP 스코프 한정)
- **근거 요약:**
  - Codex: Pinning은 TLS inspection 프록시 환경에서 장애 유발. 타임스탬프 anti-replay는 NTP 미정렬 PC에서 실패. "보안 기능이 장애 원인"이 되는 것이 가장 위험.
  - Gemini: 50k 인증서 관리는 운영 지옥(자체 비판). Join Token 등록 + JWT로 복잡도 축소. 원문 미전송은 고객 도입 설득의 핵심 논리.
  - Claude: Anti-replay를 UUID v7 + device_seq로 변경. 파일명 민감성 대응으로 Path Privacy Mode(3단계) 추가.
- **조건/유보사항:**
  - mTLS 도입(Phase 2) 시 Bootstrap Token → CSR → 짧은 수명 cert(90일) + 서버 denylist 방식.
  - CRL/OCSP는 "필수"로 약속하지 않음.
  - 라이선스: 서명된 JWT Lease + 서버 집행. 오프라인 grace period(30일) 제공.

---

## 논점 6: 구현 실현 가능성

- **결론:** **Phase 0(2-4주) → Phase 1 MVP(6-10주) → Phase 2 Beta(8-12주)** 단계적 접근. 텍스트 추출/NER은 **워커 프로세스 격리가 아키텍처 원칙**. 제품화 작업(MSI/서비스 복구/AV 대응/프록시 테스트)이 기술보다 큰 일정 리스크. 4-5명 팀이 최소 현실적 규모.
- **합의 수준:** ⭐⭐ 다수 동의
- **근거 요약:**
  - Codex: 3-5명이 3-4개월에 "상용급"은 불가능. "파일럿 운영 가능(MVP)"이 정의. 가장 큰 리스크는 기술이 아니라 제품화.
  - Claude: 전체 제품은 30-45 인월(제품화 버퍼 +30% 포함). 4-5명 + 6-9개월(MVP까지).
  - Gemini: 모든 파싱 로직은 샌드박스된 워커 프로세스에서. Phase 0에서 HWP/추출/NER 검증 실패 시 과감히 드랍.
- **조건/유보사항:**
  - Phase 0 Kill/Pivot 기준:
    - HWP 추출 성공률 < 90% → MVP 제외
    - i3/4GB NER P95 > 200ms → NER 기본 OFF
    - OOXML 추출 성공률 < 95% → 라이브러리 교체 검토
  - EV 코드 서명 인증서 사전 확보 필요(AV/EDR 오탐 방지).
  - Windows QA 매트릭스(Win10 21H2/Win11/저사양) 구축 1-2주 소요.

---

## 논점 7: 경쟁 차별화 전략

- **결론:** Day 1 USP = **4개 축: (1) Quiet Agent, (2) Privacy by Default, (3) Explainable Detection, (4) Safe Updates.** AI(NER)는 Day 1 USP가 아니라 **로드맵의 성장 스토리(옵션/베타)**로 포지셔닝. "완전 실시간"이나 "제로 오탐"을 약속하지 않는다.
- **합의 수준:** ⭐⭐⭐ 전원 동의
- **근거 요약:**
  - Claude: Fasoo가 AI-R Privacy로 F1 93.1%를 이미 선점. AI로 싸우면 후발주자가 동일 전장에서 불리. "업무 무중단 + 개인정보 미전송"이 체감 가능한 차별점.
  - Codex: 차별점은 "구현 결정" 수준의 것들(하드캡, USN, 서명 번들, 원문 미전송, fault isolation). "업데이트 후 장애가 없냐"를 고객은 본다.
  - Gemini: "데이터를 가져가지 않는 안전함" + "오탐 근거를 보여주는 투명함" + "PC를 느리게 하지 않는 조용함".
- **조건/유보사항:**
  - "Explainable Detection"은 탐지 결과에 `detection_reason` 필드(regex 패턴, checksum 결과, context 키워드)를 포함하여 구현. 원문 없이도 판단 근거 전달 가능.
  - MVP 관리 콘솔에 최소 조치 워크플로우(OPEN → ACK → RESOLVED) + 마스킹된 증거 스냅샷 필수.

---

## 논점 8: 텍스트 추출 전략

- **결론:** 텍스트 추출은 "기능"이 아니라 **"제품 리스크"로 관리**. MVP 지원 포맷 = **txt/csv/log/tsv + docx/xlsx/pptx(OOXML).** 모든 추출은 워커 프로세스에서 실행. **타임아웃(30초) + 메모리 상한(200MB) + Quarantine(2회 실패 시 24시간 스킵)** 강제. Phase 0에서 포맷별 성공률 정량 측정.
- **합의 수준:** ⭐⭐⭐ 전원 동의
- **근거 요약:**
  - Codex: 파일 포맷 파서는 "프로덕션 장애의 80%". 타임아웃 + 프로세스 격리 + Quarantine이 해법. 포맷별 성공률을 숫자로 관리.
  - Gemini: Rust 문서 파싱 생태계는 Python/Java 대비 미성숙. MVP는 자체 처리 가능한 포맷에 집중.
  - Claude: 포맷 지원 매트릭스를 Supported/Experimental/Unsupported 3단계로 분류. 계약 문구와 일치시킴.
- **조건/유보사항:**
  - HWP: Phase 0에서 `hwp-rs` 성공률 95% 미달 시 FFI 래퍼(libhwp) 또는 Python 헬퍼 검토.
  - PDF: 텍스트 레이어만 Phase 2 실험적 지원. 스캔 PDF(OCR)는 Phase 3.
  - 외부 헬퍼 바이너리 사용 시 서명/AV 오탐/업데이트 관리 비용 동반.

---

## 논점 9: DRM 연동 전략

- **결론:** MVP에서는 **알려진 DRM 벤더/시그니처에 한해** 헤더/매직넘버 기반으로 DRM 파일 여부를 감지하고 **"SUSPECTED_DRM" 분류로 보고**한다. 벤더 SDK/필터 드라이버 없이 모든 DRM 파일을 확실히 판별하는 것은 불가능하므로, 탐지 실패 가능성을 계약/지원 매트릭스에 명시한다. 내용 스캔은 Phase 2에서 주요 벤더(Fasoo, SoftCamp) SDK 연동으로 시작. SDK 연동은 **별도 헬퍼 프로세스로 격리**. *(Round 3 Codex 피드백 반영)*
- **합의 수준:** ⭐⭐⭐ 전원 동의
- **근거 요약:**
  - Claude: 한국 대기업/공공기관 80%+가 문서 DRM 사용. DRM 파일을 못 보면 솔루션 신뢰도 치명적 손상. 가시성(visibility)이라도 제공해야.
  - Codex: DRM SDK 연동은 NDA/계약이 먼저. 코드만으로 해결 안 됨. MVP는 "UNSCANNABLE_DRM" 분류/집계.
  - Gemini: DRM 연동 난이도 "매우 높음" 동의. MVP 제외 합의.
- **조건/유보사항:**
  - Phase 2 DRM 연동 시 벤더당 4-8주 소요 예상.
  - Rust에서 DRM SDK(COM/FFI)는 unsafe 코드 불가피 → 워커 프로세스 격리 필수.

---

## 논점 10: 운영 안전장치

- **결론:** **Panic Mode, Quarantine, Support Matrix, Rollout Discipline**을 아키텍처 문서의 **독립 섹션**으로 격상. 50,000대 제품에서는 기능보다 "망가지지 않는 것"이 가치.
- **합의 수준:** ⭐⭐⭐ 전원 동의
- **근거 요약:**
  - Codex(제안자): 운영 안전장치를 설계 문서에 "명시적 결정"으로 박아야 한다. Panic mode/Quarantine/Support Matrix/Rollout discipline 4가지.
  - Gemini: "죽지 않는 에이전트"가 MVP 핵심 가치. Watchdog + Hard Timeout + Quarantine DB.
  - Claude(수용): "무엇이 깨질 때 어떻게 살아남는가"를 체계적으로 다루지 못했음을 인정. 전면 수용.
- **초기값 사항** *(Phase 0 텔레메트리로 per-device 보정 전제, Round 3 Codex 피드백 반영)*:
  > 아래 수치(CPU%, I/O MB/s, 메모리 상한 등)는 **초기 기본값**이며, 엔드포인트 다양성(코어 수, 디스크 종류, EDR 훅, VDI 등)을 감안하여 Phase 0에서 per-device 기준(코어 수 정규화 등)으로 보정해야 한다. "확정값"이 아니라 "조정 전제의 출발점"이다.

  | 안전장치 | 트리거 (초기값) | 동작 |
  |:---|:---|:---|
  | Panic Mode | 워커 크래시 3회/1h, CPU>15% 5분, I/O>50MB/s 2분 | 실시간 중지, NER OFF, 스캔 간격 2배 |
  | Quarantine | 동일 파일 추출 실패 2회 | 24시간 스킵, 서버 보고 |
  | Support Matrix | (정적) | NTFS=Full, SMB=Limited, FAT32/OneDrive=Unsupported |
  | Rollout Discipline | 룰/모델 업데이트 시 | 서명 필수 + 카나리(1-5%) + 24h 모니터링 + 롤백 |

---

## 추가 원칙: 탐지 로그 배치 전송 *(Round 3 Gemini 피드백 반영)*

- **배경:** 50,000대 PC가 탐지 결과를 실시간으로 서버에 전송하면 PostgreSQL 단일 DB가 부하를 견디지 못할 수 있다. 대규모 배포 시 장애의 주원인이 될 수 있으므로 명시적 원칙이 필요하다.
- **원칙:** 에이전트는 탐지 로그를 **배치 전송(예: 10분 주기 또는 100건 누적 시)**한다. 긴급 알림(CONFIRMED 등급)은 즉시 전송하되, 일반 탐지/텔레메트리는 배치로 묶어 서버 부하를 분산한다.
- **합의 수준:** Round 3에서 Gemini 제안. 서버 아키텍처의 하부 항목으로 설계에 반영 필요.

---

## 합의 요약 매트릭스

| 논점 | 합의 수준 | 핵심 결정 |
|:---|:---|:---|
| 1. NER 모델 | ⭐⭐⭐ | Small INT8 기본 + 베타 + AI 예산 |
| 2. 파이프라인 | ⭐⭐⭐ | Funnel + 워커 격리 + USN 본체 + 서명 정책 |
| 3. 기술 스택 | ⭐⭐⭐ | Rust 클라이언트 + Go 서버 + PostgreSQL |
| 4. MVP 범위 | ⭐⭐⭐ | 정형 PII + 증분 + 3폴더 워처 + Panic Mode |
| 5. 보안 | ⭐⭐⭐ | JWT + Pinning OFF + 원문 미전송 + Path Privacy |
| 6. 실현 가능성 | ⭐⭐ | Phase 0→1→2 + 4-5명 + 워커 격리 원칙 |
| 7. 차별화 | ⭐⭐⭐ | Quiet + Privacy + Explainable + Safe Updates |
| 8. 텍스트 추출 | ⭐⭐⭐ | txt/OOXML만 + 타임아웃/격리/Quarantine |
| 9. DRM | ⭐⭐⭐ | 감지만(UNSCANNABLE) + Phase 2 SDK |
| 10. 운영 안전장치 | ⭐⭐⭐ | Panic/Quarantine/Matrix/Rollout 4종 |
