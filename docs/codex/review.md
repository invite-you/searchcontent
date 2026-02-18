# 설계 리뷰 (Teammate 4, Devil's Advocate)

작성일: 2026-02-09  
리뷰 범위(열람 허용 3개 문서만): `docs/codex/detection-engine.md`, `docs/codex/security.md`, `docs/codex/system-architecture.md`

## 핵심 요약(Executive Summary)

- 방향성은 합리적이다: 하이브리드 파이프라인(Hybrid pipeline: 규칙/검증/컨텍스트 + 제한적 NER), USN 기반 증분 스캔(Incremental scan), 리소스 거버너(Resource governor), 최소 수집(Data minimization), 서명 기반 정책/업데이트(Signed artifacts).
- 다만 “3~4개월 MVP” 관점에서는 **스코프 과다**다. 특히 일정/품질 리스크는 `텍스트 추출(Extractor)`과 `NER 정확도/성능`, `PKI(mTLS)·업데이트·라이선스 운영`에서 폭발하기 쉽다.
- Devil’s Advocate 결론: **MVP는 ‘정형 PII + 증분 + 업무방해 방지 + 최소 서버/콘솔’로 수렴**시키고, `IFilter/PDF/아카이브/DRM 심화/자동 업데이트/지속학습/멀티테넌시 SaaS`는 후순위로 미는 것이 현실적이다. 비정형 PII(NER)는 “베타(beta)”로 제한적 탑재가 맞다.

---

## Q1) 5만 대 운영 경험 문제(오탐/업무방해/비정형 미탐/실시간/DRM/증분/인사이트)가 정말 해결되는가?

판정 기준:
- **해결**: 현재 설계만으로도 MVP에서 일관되게 달성 가능(명확한 SLO/가드레일 포함)
- **부분 해결**: 메커니즘은 있으나 품질/운영 증명이 필요하거나 범위 제한이 있음
- **미해결**: 설계상 다루지 않거나, 다루더라도 현실적 대안이 부족

| 항목 | 판정 | 근거(설계에 포함된 장치) | Devil’s Advocate 리스크 | 수정 제안(대안 포함) |
|---|---|---|---|---|
| 오탐/과탐(False positive) | 부분 해결 | 체크섬/형식 검증(Checksum/Luhn 등), 컨텍스트 룰(Context rule)·부정 키워드(negative context), allow/deny list, 스코어링(Scoring)·임계값(Threshold), dedup, 회귀/온라인 검증(Regression/Online validation) | “오탐률 6%” 목표가 **정의가 흔들리면 실패**한다(파일 단위 vs 엔티티 단위 vs 알림 단위). IFilter/PDF 추출 노이즈·로그/코드/키(license key)류 하드 네거티브가 실제 오탐의 대부분인데, 초기 데이터셋/골든 코퍼스(golden corpus) 준비 없으면 튜닝 불가. NER은 잘못 넣으면 오탐을 오히려 올릴 수 있음(확률적 모델). | MVP에서 **알림 단위(Alert-level precision)** 를 우선 KPI로 고정하고, 타입별 목표(예: RRN/CARD는 99%+, PHONE/ADDR은 90%+)로 쪼갠다. IFilter는 MVP 기본 경로에서 제외하거나 “격리 프로세스 + 하드 타임아웃(hard timeout)” 전제. 오탐 상위 원인 자동 집계는 “알림 폭증 지표(alert rate spike)”로 롤백 트리거를 잡고, 오탐 여부 판정은 인간 검수 기반으로 분리한다. |
| 사용자 업무 방해(User disruption) | 부분 해결 | Job Object로 CPU/메모리 제한, IO 제한(동시성/샘플링), EcoQoS·낮은 우선순위, debounce/backoff, idle 기반 스캔, silent UX 기본, 배치 업로드(batching) | 가장 위험한 구간은 “텍스트 추출”이다. COM 기반 IFilter는 **행(hang)·메모리 폭주·환경 편차**가 잦고, 아카이브(zip bomb)·대용량 파일·네트워크 드라이브에서 IO 폭증이 쉽게 발생한다. 또한 “기준선 풀스캔(baseline full scan)”은 한번 삐끗하면 사용자 체감이 크게 나빠져 에이전트 삭제로 이어진다. | MVP는 **파일 포맷/경로를 강하게 제한**하고, “유지보수창(maintenance window) + idle에서만 공격적”을 기본값으로 한다. 모든 추출기는 “별도 워커 프로세스 격리 + 단계별 타임아웃 + 부분 스캔(degraded mode)”를 강제. 초기에는 baseline을 “전체”가 아니라 “핵심 폴더(문서/바탕화면/다운로드)”로 제한해 성공 경험을 만든다. |
| 비정형 PII 미탐(False negative, unstructured) | 부분 해결 | 트리거 기반 의심 구간(suspect span) + 샘플링 NER(sampling NER), PER/ADDR 조합 승격, 모델 버전/카나리 배포 | 비정형은 결국 **학습 데이터와 라벨링(ground truth)** 싸움이다. 그런데 기본값이 원문 미전송이라면 “지속학습(continual learning) 루프”가 실제로 돌아가려면 (1) 증거(Evidence) 업로드 옵션을 켜거나 (2) 엔드포인트에서 라벨링을 수행해야 한다. 이 연결이 아직 설계상 불명확하다. OCR 비범위라 스캔된 PDF/이미지 문서는 구조적으로 미탐. | MVP는 NER을 “베타”로 두고, 먼저 **정형 PII + ‘이름/주소 라벨-값’ 형태** 같은 고정밀 케이스부터 커버한다(컨텍스트 룰로). 학습 루프는 “증거 업로드 활성화 고객” 또는 “로컬 증거 뷰어(local evidence viewer)”가 준비된 후에 제품 기능으로 약속한다. OCR은 ‘Later’로 명확히 문서화한다. |
| 실시간 탐지(Real-time) | 부분 해결 | ReadDirectoryChangesW + USN Journal 조합, debounce, 누락 보정(reconciliation) | “실시간”은 정의가 필요하다. USN 폴링 기반은 본질적으로 **지연(latency)** 이 있고, ReadDirectoryChangesW는 감시 범위 확대 시 리소스/누락 문제가 있다. 따라서 “전 볼륨 즉시 감지”는 MVP에서 불가능에 가깝다. | SLO를 두 단계로 쪼갠다: “핵심 경로(정책 지정)는 30초 이내”, “그 외는 N분 이내 eventual” 같은 식. MVP는 watcher 범위를 제한하고, USN은 증분/보정 중심으로 둔다. ‘진짜 실시간’이 필요하면 Phase 2+에서 Minifilter(커널 드라이버) 옵션으로 간다. |
| DRM 파일 탐지(DRM) | 부분 해결 | 추출 불가 시 `UNSCANNABLE_ENCRYPTED`로 분류/리포트, Minifilter는 로드맵(향후) | “DRM 내부 내용 탐지”는 현 설계로는 불가하다. 현재는 “스캔 불가 분류”까지만 가능하며, 이 자체는 인사이트지만 ‘미탐 해결’로 보긴 어렵다. | MVP 목표를 “DRM 파일의 **가시화(visibility)**”로 명확히 하고, 고객 요구가 크면 DRM 벤더 연동(API/SDK) 또는 Minifilter 기반 식별을 별도 옵션 제품으로 분리한다. DRM 비율이 높은 고객에겐 “DRM 영역 제외/경고” 같은 정책 UX를 먼저 제공한다. |
| 증분 스캔(Incremental scan) | 해결(단, 로컬 NTFS 중심) | 파일 ID + USN + fast fingerprint + scan_state(SQLite), 결과 digest로 재보고 억제, USN 리셋/누락 보정 전략 | 네트워크 공유(UNC), 클라우드 동기화 폴더(OneDrive 등), 비-NTFS, USN 비활성 환경은 “해결”로 보기 어렵다. 또한 fast hash는 파일 중간만 바뀌는 케이스에서 충돌/누락 가능(USN이 있으면 상쇄되지만 폴백 환경이 문제). | MVP 지원 범위를 명시한다: “로컬 NTFS는 완전 지원”, “비-NTFS/네트워크는 제한 지원(주기 스캔/샘플링)”. 설치 시 사전 점검(health check)으로 USN 가능 여부를 진단하고 정책을 자동 조정한다. |
| 관리 인사이트(Insights) | 부분 해결 | 파일 위험도(risk) 산정, dedup/집계, UNSCANNABLE 리포팅, observability(OpenTelemetry)·감사(Audit) | “인사이트”는 기능이 아니라 **운영 워크플로우(workflow)** 다. 현재 문서는 데이터 원칙과 수집 구조는 있으나, 관리자에게 무엇을 어떻게 보여줘야 “조치(remediation)”가 되는지(우선순위, 담당자, 추적 상태)가 약하다. 원문 미전송이면 더더욱 “조치 UX”가 중요해진다. | MVP 인사이트를 5개 KPI로 고정한다: “위험도 상위 파일/경로/디바이스”, “새로 발견된 고위험(HIGH)”, “UNSCANNABLE 비율”, “정책 변경 전후 탐지율 변화”, “에이전트 건강도(health)”. 조치 트래킹(remediation tracking)은 Later가 아니라 MVP에 최소 형태(상태: open/ack/resolved)라도 넣는 것이 운영에 유리하다. |

---

## Q2) 소규모 팀이 현실적으로 구현 가능한가? 가장 큰 일정/품질 리스크 Top N과 완화책

결론: “가능은 하지만” 현재 설계 범위를 그대로 다 잡으면 3~4개월 MVP는 위험하다. 아래 Top 리스크를 줄이는 방향으로 MVP를 재정렬해야 한다.

### Top 리스크(일정/품질)와 완화책

### 리스크 1: 텍스트 추출(Text extraction) 커버리지/안정성

- 리스크: IFilter(COM) 기반은 환경 편차가 크고 hang/메모리 폭주 가능. PDF/아카이브는 비용이 크고 품질 편차가 큼.
- 완화: MVP는 `txt/csv/log + OOXML(docx/xlsx/pptx)` 내장 추출기 중심으로 고정한다. IFilter/PDF/아카이브는 “옵션 + 격리 프로세스 + 하드 타임아웃”을 전제로 Phase 2로 내린다.

### 리스크 2: NER 성능/정확도(모델 선택, CPU 추론, 양자화)

- 리스크: ONNX/INT8 최적화, 토크나이저(tokenizer) 병목, 정확도 저하(quantization drop) 검증이 필요. 데이터/라벨 없으면 품질을 증명할 수 없음.
- 완화: MVP에서 NER은 “베타 + 엄격한 호출 조건(when to run)”으로 제한하고, 실패해도 제품 가치가 유지되도록 정형 PII를 먼저 강하게 만든다. NER은 “파일당 K개 샘플링” 같은 상한을 하드코딩해 업무 방해를 막는다.

### 리스크 3: “최소 수집”과 “지속학습 루프”의 충돌

- 리스크: 원문 미전송이 기본이면, 오탐/미탐을 개선할 라벨 데이터 확보가 막힌다(학습/검증 파이프라인이 기능적으로 성립하지 않을 수 있음).
- 완화: 옵션 기능으로 “증거(Evidence) 업로드”를 둔다면, MVP에 그 정책/권한/RBAC/감사/보관기간까지 함께 넣어야 한다(그 자체가 큰 일). 대안은 “로컬 라벨링 + 라벨만 업로드”인데 UX/개발 난도가 높다. 따라서 MVP에서는 “지속학습은 로드맵”으로 명확히 하고, 초기 품질은 규칙/검증/컨텍스트로 확보한다.

### 리스크 4: PKI(mTLS) 수명주기 + 기업 프록시 환경

- 리스크: 인증서 발급/갱신/회수, 프록시/SSL inspection 환경에서의 장애 대응은 운영 난도가 높다.
- 완화: MVP는 “단일 고객(on-prem 또는 전용 SaaS)”을 전제로 운영 변수를 줄인다. mTLS는 유지하되 CRL/OCSP는 생략(문서와 동일)하고, 연결 실패 시 HTTPS 폴백/프록시 설정을 제품의 1급 설정(First-class config)으로 둔다.

### 리스크 5: 업데이트(Updater) 보안/롤아웃 운영

- 리스크: “매니페스트 서명 + 코드서명 검증 + anti-rollback + staged rollout”은 구현뿐 아니라 운영 체계(키 보관, 런북)가 필요.
- 완화: MVP에서는 “에이전트 자동 업데이트”를 과감히 빼고, 고객의 기존 배포 체계(MDM/SCCM/MSI)로 버전 업데이트를 처리한다. 대신 “정책/룰 번들(policy bundle)” 업데이트만 먼저 안전하게 만든다(서명 검증은 비교적 작은 스코프).

### 리스크 6: 서버/콘솔 범위 과다(멀티테넌시, 검색, 분석)

- 리스크: PostgreSQL + Object storage + Queue + (OpenSearch/ClickHouse)까지 깔면 소규모 팀이 운영/개발 모두 잡기 어렵다.
- 완화: MVP는 PostgreSQL 단일로 시작하고(필요하면 대용량 blob만 object storage), 큐도 “한 가지”만 선택한다. 검색/대시보드는 단순 리스트/필터로 시작하고, 고급 검색/집계는 Later.

### 리스크 7: Windows 파일 감지 엣지 케이스(USN 리셋, 권한, 비-NTFS, 네트워크 공유)

- 리스크: 현장에서는 USN이 비활성/권한 제한/볼륨 정책으로 막힐 수 있다. 네트워크 공유는 근본적으로 다르다.
- 완화: 설치 시 health check로 모드 자동 선택(USN 가능/불가)을 하고, 불가 환경은 “주기 스캔 + 제한된 watcher”로 degrade한다. 지원 범위를 문서/계약에 명확히 한다.

### 리스크 8: 토큰화(Tokenization) 키 분배/회전과 ‘상관분석(correlation)’ 트레이드오프

- 리스크: 결정적 토큰화(deterministic tokenization)로 테넌트 단위 dedup/집계를 하려면 `tenant_token_key`가 결국 엔드포인트로 내려가야 한다. 단말 침해(A3) 1대로 키가 유출되면, 구조적 PII(RRN/PHONE 등)는 사전대입(dictionary)로 토큰 역추정이 가능해져 “서버 저장 데이터의 2차 위험”이 생긴다. 또한 키 회전(key rotation) 시 과거 토큰과의 호환/재토큰화(re-tokenization) 문제가 운영 복잡도를 올린다.
- 완화: MVP에서는 “교차 디바이스(cross-device) PII 상관분석”을 낮추고, 우선 `file-level`/`device-level` 집계와 조치 workflow를 만든다. 상관분석이 꼭 필요하면 Later에 OPRF/VOPRF 같은 서버-보조 토큰화(서버가 키를 노출하지 않으면서 토큰을 발급) 또는 “증거 업로드 승인 워크플로우” 기반의 제한적 재식별 흐름을 검토한다.

### 리스크 9: 정규화(Normalization)로 인한 오프셋(offset) 깨짐과 ‘증거(Evidence)’ UX

- 리스크: NFKC/구분자 통일/제로폭 제거 같은 정규화는 탐지 품질에는 유리하지만, “원문 위치(정확한 좌표)”를 잃기 쉽다. 원문 미전송 기본 정책에서는 오프셋/스니펫 정확도가 곧 신뢰도다. 이게 흔들리면 오탐 처리/조치가 느려지고 제품 신뢰가 깨진다.
- 완화: MVP는 “정확 오프셋 보장”을 과도하게 약속하지 말고, 먼저 “파일 단위 조치” 중심 UX로 간다(예: 파일 경로 + 탐지 타입 + 마스킹 프리뷰). 오프셋이 필요해지는 시점(Later)에는 정규화 매핑 테이블을 실제로 검증 가능한 형태로 구현하고, 로컬 증거 뷰어(local evidence viewer) 같은 안전한 확인 경로를 같이 제공한다.

---

## Q3) 기존 상용 솔루션 대비 실질적 차별점은 무엇인가? (구현/운영 관점)

마케팅 문구가 아니라 “구현 결정” 기준으로 보면, 차별점 후보는 아래와 같다(실제로 구현돼야 의미가 있음).

### 차별점 1: CPU 비용을 통제한 하이브리드 탐지(Hybrid detection with tight gating)

- 포인트: NER을 “의심 구간(suspect span)에만” 적용하고, 정형 PII는 체크섬/형식 검증으로 고정밀(High precision) 처리한다.
- 운영 관점: “업무 방해(UX)”를 줄이면서도 비정형을 단계적으로 확대할 수 있는 구조다.

### 차별점 2: NTFS USN Journal 기반 증분 스캔(Incremental scan backbone)

- 포인트: 풀스캔 중심 제품 대비 재스캔 비용과 서버/네트워크 노이즈를 줄인다.
- 운영 관점: 스캔 상태를 SQLite로 관리하고, 결과 digest로 재보고를 억제하는 설계는 50k 운영에서 비용 절감으로 직결된다.

### 차별점 3: 안전한 룰 확장(Policy DSL + Safe regex + Signed bundle)

- 포인트: 고객 커스텀 정규식으로 인한 ReDoS(Regex DoS) 및 성능 사고를 구조적으로 줄인다.
- 운영 관점: 룰/모델/리스트를 “서명된 번들(signed bundle)”로 배포/롤백하면, 정책 변경이 곧 장애가 되는 문제를 줄일 수 있다.

### 차별점 4: 기본값이 ‘원문 미전송’인 데이터 최소화(Data minimization by default)

- 포인트: 탐지 솔루션이 “PII 중앙 수집 시스템”이 되는 리스크를 낮춘다.
- 운영 관점: “조치 UX(원문 없이 remediation)”를 같이 설계하지 않으면 오히려 제품 사용성이 떨어질 수 있으므로, UI/워크플로우가 차별점의 성패를 좌우한다.

### 차별점 5: Fault isolation 중심의 에이전트 구조(Service + Worker + Job Object)

- 포인트: 파서/모델 크래시가 서비스 전체 장애로 전파되는 것을 막는다.
- 운영 관점: 엔드포인트 제품에서 “안정적 실패(fail-safe)”는 도입/확산의 전제 조건이 될 수 있다.

---

## Q4) MVP 범위와 후순위 범위 경계를 명확히. 3~4개월 기준 MVP 제안(기능/비기능 포함)

### 제안하는 MVP 목표(3~4개월)

MVP는 “비정형까지 100%”가 아니라, 다음의 **제품 가설 검증**에 집중하는 것이 현실적이다.

- 가설 A: 정형 PII(Structured PII)를 낮은 오탐과 낮은 업무방해로 안정적으로 탐지/집계할 수 있다.
- 가설 B: USN 기반 증분 스캔으로 “운영 가능한” 스캔 비용과 결과 노이즈를 만들 수 있다.
- 가설 C: 원문 미전송 기본값에서도 관리자 조치(remediation)가 가능한 최소 UX를 만들 수 있다.
- 가설 D: 비정형(NER)은 “베타”로 제한적으로 넣어도 운영에 도움이 된다(또는 나중에 넣는 게 맞다는 결론을 빠르게 낸다).

### MVP 범위(In Scope)

클라이언트(Agent):
- Windows Service + Worker 프로세스 분리(IPC는 Named Pipe/Protobuf 등 간단한 형태)
- 파일 감지: `USN Journal` 기반 증분 + “핵심 경로만” ReadDirectoryChangesW 병행
- 스케줄러: debounce/backoff, idle 모드, 유지보수창(maintenance window)
- 로컬 상태: SQLite `scan_state` + 업로드 스풀(spool), DPAPI 기반 at-rest 암호화
- 리소스 제어: Job Object 기반 CPU/메모리 제한 + 동시성 제한 + 대용량 파일 상한(guardrails)
- 텍스트 추출(포맷 제한): `txt/csv/log` + `OOXML(docx/xlsx/pptx)` 내장 추출기
- 탐지(정형 중심): RRN/BRN/CARD/PHONE/EMAIL 규칙 + checksum/형식 검증 + 컨텍스트 룰 + allow/deny list + dedup + 파일 위험도(risk) 산정
- 보고: 기본값 “원문 미전송”, 마스킹(masking)된 프리뷰 + 파일 메타데이터 + 정책/모델 버전 + 결과 digest
- 비정형(NER): 옵션(베타). 트리거 주변 소량만 실행, 파일당 상한 K개 샘플링(하드캡). PER/ADDR “참고 신호”로만 사용(알림 승격은 보수적으로).

서버/콘솔(Server/Admin):
- 모놀리스 + 비동기 워커(가능하면 1개 큐) 형태의 최소 구성
- Device registry + Heartbeat
- Policy distribution(버전/해시) + 정책 번들 서명 검증(클라이언트에서)
- Ingestion API(배치/압축) + 멱등 키(idempotency key)
- Admin UI: 디바이스 목록/상태(health)
- Admin UI: 탐지 결과 목록/필터(PII type, risk, device)
- Admin UI: 조치 상태 트래킹 최소 형태(open/ack/resolved)
- Admin UI: UNSCANNABLE(암호화/DRM/미지원) 집계
- RBAC 최소 2역할(Admin/Viewer) + 핵심 감사로그(Audit: 로그인, 정책 변경, 결과 조회/내보내기)

### MVP 비기능 요구(Non-functional) 제안(SLO/Guardrails)

- 업무방해: 워커 CPU cap을 정책으로 강제, 사용자 활동 시 자동 감속(throttle), 파일당 하드 타임아웃(예: 추출 30초, 전체 스캔 60초 등)
- 지연(latency): 핵심 경로 변경은 30초 내 처리(Watcher), 그 외는 USN 폴링 주기 내(예: 5~15분) eventual
- 안정성: 워커 크래시 시 자동 재시작, 반복 실패 파일은 quarantine 큐로 이동
- 보안: TLS 1.3, 최소 수집 기본값, 서버 저장은 at-rest 암호화(가능하면 envelope encryption), 감사로그 변조 방지(tamper-evident)

### 후순위(Later, Out of MVP)

- IFilter 기반 광범위 포맷 커버리지(환경 편차/안정성 리스크 큼)
- PDF 고품질 추출기, 아카이브(archive) 심화 스캔(재귀/폭탄 대응 포함)
- OCR(이미지/스캔 PDF)
- Minifilter(커널 드라이버) 기반 “진짜 실시간” 및 DRM/안티탬퍼(Anti-tamper)
- 지속학습(continual learning) 파이프라인과 라벨링 UX(원문 미전송 원칙과의 정합성 포함)
- 멀티테넌트 SaaS 완성형(테넌트 격리 고도화, 대규모 검색/분석 엔진 도입)
- 자동 업데이트(Updater) 전체 기능(스테이지 롤아웃/anti-rollback/서명키 운영 런북 포함)
- 라이선스 집행(License lease) 완성형(상용화 직전 단계에서 넣는 것이 합리적)
- 경로 프라이버시 모드(Path tokenization) 및 고급 토큰화(OPRF/VOPRF 등) 같은 고난도 프라이버시 기능

---

## 추가로 문서에 반영하면 좋은 “명시적 결정” (빠진 부분)

- “실시간(Real-time)” 정의(SLO): 어떤 경로/볼륨에서 몇 초/분 이내를 목표로 하는지.
- “오탐률 6%”의 **정확한 정의**(alert/file/entity, 분모/분자)와 타입별 목표.
- NER 학습/개선 루프가 “원문 미전송” 원칙과 어떻게 양립하는지(증거 업로드 옵션을 MVP에 넣을지, Later로 뺄지).
- 토큰화(Tokenization) 키 전략: 테넌트 키 vs 디바이스 키, 키 회전/유출 가정, 상관분석(correlation) 요구 수준.
- 정규화/청크(Normalization/Chunking) 이후에도 원문 좌표(Offset)와 증거 UX를 어떻게 보장할지(또는 MVP에서 포기할지).
- 지원 파일 타입/경로/드라이브 범위(로컬 NTFS, 네트워크 공유, OneDrive 등)의 MVP 선언.
