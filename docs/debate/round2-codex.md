# Round 2 (Codex): Claude/Gemini의 Codex 비평에 대한 응답 (구현 관점)

작성일: 2026-02-09  
읽은 문서:
- `docs/debate/round1-claude.md`
- `docs/debate/round1-gemini.md`

작성 원칙:
- “맞다/틀리다”보다 **MVP에서 실제로 구현/운영 가능한지**를 기준으로 응답한다.
- 각 논점의 결론은 `[수용] / [부분 수용] / [반박]` 중 하나로 명시한다.
- 각 논점마다 최소 1개 이상의 **코드 예시 또는 구현 시나리오**로 근거를 붙인다.

---

## 논점 1: NER 모델 선택

### 받은 비평 요약
- Claude: “MVP는 NER 베타”는 동의. 다만 **Base를 기본으로 잡는 건 배포/운영 비용이 크니 Small로 시작 + 파일럿에서 A/B로 결론** 내자. (`docs/debate/round1-claude.md`)
- Gemini: KoELECTRA-Small INT8에 강하게 동의. 추가로 **모델 파일 암호화(디스크 at-rest) 보호를 필수**로 보자. (`docs/debate/round1-gemini.md`)

### Codex의 응답
- [부분 수용] “Small 기본 + Base는 옵션(정밀/유휴)”로 정리하는 게 맞다. 다만 “Base vs Small”은 논쟁으로 끝내지 말고, **정책 기반 A/B**로 쉽게 바꿀 수 있게 설계해야 한다.

구현 시나리오(정책으로 모델 스위칭 + A/B):
1. 서버가 `model_policy`를 배포한다. 예: Pilot 200대 중 20대(10%)만 Base 사용.
2. 에이전트는 로컬 벤치(지연/CPU) 결과를 보고 정책을 “거부”할 수 있다(최저 사양 보호).
3. 결과는 “NER 호출 수/평균 지연/FP rate 변화”만 집계(원문 미전송 유지).

```rust
// 정책에 의해 모델을 선택하되, 로컬 하드웨어/지연 가드레일을 우선한다.
#[derive(Clone, Debug)]
pub enum ScanMode { Realtime, Scheduled }

#[derive(Clone, Debug)]
pub enum ModelTier { SmallInt8, BaseInt8 }

#[derive(Clone, Debug)]
pub struct NerPolicy {
    pub enabled: bool,
    pub tier: ModelTier,
    pub max_inferences_per_minute: u32, // "AI budget"
    pub max_latency_ms_p95: u32,        // fail closed: 초과하면 NER 자동 비활성화
}

pub fn choose_ner_policy(mode: ScanMode, policy: NerPolicy, hw_low_end: bool) -> NerPolicy {
    if !policy.enabled {
        return policy;
    }
    // 저사양 + 실시간이면 무조건 Small로 강등
    if hw_low_end && matches!(mode, ScanMode::Realtime) {
        return NerPolicy { tier: ModelTier::SmallInt8, ..policy };
    }
    policy
}
```

모델 파일 암호화(“필수” 주장)에 대한 답:
- [부분 수용] “암호화 at-rest”는 **IP 보호 효과가 제한적**이다(어차피 메모리에 로드되면 덤프 가능). 대신 MVP에서 현실적으로 얻는 이득은 “디스크 상 평문 노출 최소화” 정도다.
- MVP 권장 우선순위는 `서명 검증(무결성)` > `배포/업데이트 체인` > `옵션으로 at-rest 보호`다.

```rust
// MVP에서 가장 값싼 '보호'는 암호화보다 "서명 검증 + 해시 고정"이다.
pub struct SignedArtifact {
    pub bytes: Vec<u8>,      // model.onnx
    pub sha256: [u8; 32],    // metadata.json에 포함
    pub sig: Vec<u8>,        // vendor key로 서명
}

pub fn verify_artifact(a: &SignedArtifact, pubkey: &[u8]) -> anyhow::Result<()> {
    let digest = sha2::Sha256::digest(&a.bytes);
    anyhow::ensure!(digest.as_slice() == a.sha256, "hash mismatch");
    verify_detached_signature(pubkey, &a.sha256, &a.sig)?;
    Ok(())
}
```

---

## 논점 2: 탐지 파이프라인 구조

### 받은 비평 요약
- Claude:
  - “저비용→고비용 깔때기”는 합의.
  - Codex의 **YAML DSL/trait/다수 crate 분해는 MVP에 과잉**일 수 있음.
  - **NER을 별도 자식 프로세스로 격리**하는 게 안정성에 유리. (`docs/debate/round1-claude.md`)
- Gemini:
  - 4단계 파이프라인 동의.
  - Aho-Corasick으로 **키워드 없으면 즉시 스킵** 같은 공격적 게이팅을 강조. (`docs/debate/round1-gemini.md`)

### Codex의 응답
- [부분 수용] “형식화(DSL/추상화)는 MVP에서 ‘스키마 고정 + 기능 제한’으로만” 가져가고, **미니 언어(표현식)로 확장하지 않는다.**  
  - 즉, YAML/JSON은 “규칙 데이터”이지 “규칙 코드”가 아니다.

DSL(스키마) 최소화 예시: “표현식 금지, 열거형만 허용”
```rust
#[derive(serde::Deserialize)]
pub struct Rule {
    pub id: String,
    pub kind: PiiKind,
    pub regex: String,
    pub validators: Vec<ValidatorId>, // 문자열이 아니라 enum
    pub context: ContextRule,         // window, 키워드 리스트만
    pub threshold: f32,
}

#[derive(serde::Deserialize)]
pub enum ValidatorId { RrnChecksum, Luhn, BrnChecksum }

#[derive(serde::Deserialize)]
pub struct ContextRule {
    pub window_chars: usize,
    pub positive_keywords: Vec<String>,
    pub negative_keywords: Vec<String>,
}
```

키워드 “없으면 스킵”에 대한 답:
- [반박] “키워드 없으면 **전체 스킵**”은 구조화 PII(주민/카드/이메일/전화)를 놓친다.  
  - 키워드는 **NER 게이팅**에만 쓰는 게 안전하다.

구현 시나리오(구조화는 항상 스캔, NER만 키워드로 제한):
1. Regex/Checksum은 스트리밍으로 항상 수행(비용 낮음).
2. NER은 `키워드 근접` 또는 `MEDIUM 후보` 또는 `샘플링`만 수행(비용 상한).

```rust
fn should_run_ner(window: &str, has_medium_candidate: bool, keyword_hit: bool, budget_ok: bool) -> bool {
    if !budget_ok { return false; }
    has_medium_candidate || keyword_hit || sampling_trigger(window)
}
```

NER 격리(자식 프로세스) 관련:
- [수용] 텍스트 추출기와 NER은 **워커 프로세스(또는 별도 워커)** 에서만 실행하는 것이 맞다.
- 구현은 “FFI”가 아니라 **IPC + Job Object + 하드 타임아웃**으로 간다.

```text
pii-agent-svc (service)
  - USN/Watcher ingest
  - queue + backpressure
  - spawn worker in Job Object
  - watchdog + quarantine

pii-scan-worker (process)
  - extract -> regex/validate -> (optional) ner
  - write result spool file
```

---

## 논점 3: 기술 스택 (Rust vs 대안)

### 받은 비평 요약
- Claude: 클라이언트는 Rust 확정. **C#/.NET 하이브리드는 최악**(FFI/빌드/배포 이중화/런타임 의존). 서버는 Go가 적합. (`docs/debate/round1-claude.md`)
- Gemini: Client Rust + Server Go로 확정. (`docs/debate/round1-gemini.md`)

### Codex의 응답
- [부분 수용] “Rust↔C# FFI 하이브리드”는 나도 비추천으로 정리한다. 다만 “하이브리드”를 쓴다면 FFI가 아니라 **프로세스 경계(IPC)** 로만 가능하다.

현실적 선택지(팀 역량/일정 기준):
1. 기본안: Client 전부 Rust(서비스 + 워커) / Server Go
2. 예외안: “C# 서비스 + Rust 워커” (FFI 금지, Named Pipe IPC만)

IPC 예시(FFI 없이 protobuf over named pipe):
```proto
message ScanJob {
  string job_id = 1;
  string file_path = 2;
  bytes policy_bundle_hash = 3;
}

message ScanResultSummary {
  string job_id = 1;
  repeated Finding findings = 2;
  string status = 3; // OK | UNSCANNABLE | ERROR
}
```

crate 분해 관련:
- [수용] MVP에서는 “20개 crate”까지 쪼개지 않는다. 대신 “프로세스 2개 + 내부 모듈”로 시작하고, 병목/교체 필요가 확인된 부분만 crate로 분리한다.

---

## 논점 4: MVP 범위

### 받은 비평 요약
- Claude: Codex의 단계적 MVP 정의는 매우 현실적. 다만 **Phase 0에서 HWP/추출/NER 지연을 강하게 검증하고 Kill/Pivot 기준을 못 박아야** 한다. 또 MVP에서 실시간/NER을 빼는 게 안전하다. (`docs/debate/round1-claude.md`)
- Gemini: 대폭 축소에 동의. 다만 NER은 Labs로 opt-in, 실시간은 핵심 경로만, HWP는 실험적, 에이전트 자동 업데이트는 제외. (`docs/debate/round1-gemini.md`)

### Codex의 응답
- [부분 수용] MVP에서 “실시간/NER을 완전히 제외”는 선택지지만, 최소한의 가치는 유지할 수 있게 **(1) 실시간은 ‘감지/큐잉’까지만, (2) NER은 Labs opt-in**으로 둔다.

Phase 0의 Kill/Pivot 기준(예시):
```text
HWP 텍스트 추출 성공률 < 90%  -> MVP에서 HWP 제외(UNSCANNABLE로 보고) + 대체 전략 결정
i3/4GB에서 NER p95 > 200ms    -> NER는 MVP 기본 OFF, Scheduled/Labs에서만
ReadDirectoryChangesW 누락률 높음 -> “eventual” 문구 고정 + USN catch-up을 primary로
```

구현 시나리오(MVP의 “실시간”을 기능이 아니라 SLO로 제한):
- Watcher는 핵심 폴더만: Desktop/Documents/Downloads.
- 실시간 이벤트는 “즉시 스캔”이 아니라 “큐잉”까지만 보장.
- 실제 스캔은 리소스 거버너가 “사용자 활동/CPU” 보고 실행한다.

---

## 논점 5: 보안/라이선스 설계

### 받은 비평 요약
- Claude:
  - Codex의 PKI/리스 설계는 포괄적이지만 MVP에는 과잉.
  - MVP에서는 Join Token 등록 + JWT(Access/Refresh)로 단순화, mTLS는 옵션/후순위.
  - 라이선스도 MVP에서는 단순 JWT + 온라인 활성화로 충분.
  - HW fingerprinting(퍼지)은 고객 불만(부품 교체) 대응에 유효. (`docs/debate/round1-claude.md`)
- Gemini:
  - mTLS는 유지하되, 등록은 Join Token으로 단순화하고 갱신 실패 시 토큰 폴백을 둔다. (`docs/debate/round1-gemini.md`)
  - (문서 내에서 Codex 입장 해석이 일부 섞여 있음: “mTLS 운영 지옥”을 Codex가 전면 부정한 것으로 읽었는데, 실제 Codex 문서는 ‘운영 리스크를 인정하되 자동화로 간다’에 더 가깝다.)

### Codex의 응답
- [부분 수용] MVP에서는 “mTLS 강제”가 아니라 **Auth 모듈을 2가지 모드로 설계**한다.
  - Mode A: Token-only (TLS server-auth + Access/Refresh) = 도입 장벽 낮음
  - Mode B: mTLS + Token (Join Token -> cert 발급) = 보안 강함, 단 운영 준비 필요

등록/갱신 플로우(Join Token 공통, mTLS는 선택):
```text
Install
  -> Join Token 입력/배포(1회성)
  -> /enroll 호출(서버 TLS만)
  -> (선택) CSR 제출 -> Device cert 발급
  -> Access/Refresh 발급

Runtime
  -> API는 Bearer token 기본
  -> mTLS 모드면 채널 인증도 병행
  -> cert 갱신 실패 시 token-only로 degrade(정책 기반)
```

“서명된 lease”는 JWT로 최소 구현 가능:
```rust
#[derive(serde::Deserialize)]
struct LicenseLease {
    tenant_id: String,
    device_id: String,
    features: Vec<String>,
    checkin_deadline_unix: i64,
    hard_deadline_unix: i64,
}

fn license_mode(now: i64, l: &LicenseLease) -> &'static str {
    if now <= l.checkin_deadline_unix { return "NORMAL"; }
    if now <= l.hard_deadline_unix { return "DEGRADED"; }
    "BLOCKED"
}
```

퍼지 HW fingerprinting에 대한 답:
- [부분 수용] “부품 교체로 라이선스가 풀리는 문제”는 실무적으로 중요하다.
- 다만 WMI 기반 값은 공백/중복/권한 이슈가 많아 **오탐/오차**가 잦다. 따라서 우선순위는:
  1) TPM Non-exportable key(또는 mTLS 개인키)로 1차 바인딩
  2) TPM 불가 환경에서만 “퍼지 fingerprint + 콘솔 재바인딩 UX”를 제공

---

## 논점 6: 현실적 구현 가능성 (팀 규모, 기간)

### 받은 비평 요약
- Claude:
  - Codex 분석이 가장 현실적이나, 서버/대시보드 공수는 더 클 수 있다(23~35 인월 추정).
  - HWP 파싱/NER 데이터/Windows 서비스 QA 매트릭스가 핵심 리스크. (`docs/debate/round1-claude.md`)
- Gemini:
  - 텍스트 추출/NER은 워커 프로세스로 격리해야 3~5명 팀이 “안정성”을 만들 수 있다. (`docs/debate/round1-gemini.md`)

### Codex의 응답
- [수용] “서버/대시보드 공수 과소평가 가능성”과 “HWP/데이터/QA”는 핵심 리스크로 인정한다. 따라서 MVP 정의를 “기능”이 아니라 **운영 가능한 최소 워크플로우**로 고정한다.

구현 시나리오(서버/콘솔 공수 줄이는 방법):
1. 서버 1개(모놀리스) + Postgres 1개로 시작, 큐/ES는 금지.
2. 콘솔은 “리스트/필터/조치 상태(open/ack/resolved)”만.
3. 에이전트 디버깅/진단은 웹 UI보다 CLI/로그 수집부터.

Windows QA 매트릭스(최소):
```text
Win10 21H2 x64 / Win11 x64 / 저사양(i3/4GB)
 - 이벤트 폭주: unzip 50k files, git checkout, build output
 - 포맷 회귀: docx/xlsx 샘플 코퍼스 200개
 - 워커 크래시/행: 타임아웃/재시작/Quarantine 동작 확인
```

---

## 논점 7: 경쟁 차별화 전략

### 받은 비평 요약
- Claude: Fasoo가 이미 AI 성능을 공개/선점. “AI가 USP”는 위험. 대신 “경량 에이전트 + Privacy by Design + 운영 효율(Panic/복구/정책)”이 현실적. (`docs/debate/round1-claude.md`)
- Gemini: “투명하고 안전한 경량 에이전트(Explainable detection + privacy)” 메시지에 집중. (`docs/debate/round1-gemini.md`)

### Codex의 응답
- [수용] Day 1 USP를 AI로 잡지 않는다. AI는 “성장 스토리/옵션 기능”로 두고, **조용함 + 프라이버시 + 운영 안전장치**를 1차 USP로 고정한다.

구현 관점(“Explainable”을 실제 UI/데이터로 보장):
```rust
pub struct FindingEvidence {
    pub detector: &'static str,      // "regex", "checksum", "ner"
    pub rule_id: Option<String>,     // 어떤 규칙이 매치됐는지
    pub validators: Vec<&'static str>,
    pub context_hits: Vec<String>,   // "이름", "주소" 등
    pub confidence: f32,
}
```

관리 콘솔은 “원문 없이도 조치”가 되게:
- 파일 위험도/유형/경로 그룹핑
- 중복 제거(동일 파일 반복 알림 차단)
- 조치 상태(open/ack/resolved) + 담당자 메모

---

## 논점 8: 텍스트 추출 전략 (추가)

### 받은 비평 요약
- Claude/Gemini 모두 “텍스트 추출이 제일 큰 리스크”를 강조. 특히 HWP/PDF/압축/암호화 정책은 MVP에서 범위 선언이 필요. (`docs/debate/round1-claude.md`, `docs/debate/round1-gemini.md`)

### Codex의 응답
- [수용] 텍스트 추출은 “지원 여부”가 아니라 **성공률/품질을 숫자로 관리**해야 한다.

구현 시나리오(포맷별 성공률 계측 + 자동 제외):
1. Phase 0에서 포맷별 샘플 코퍼스 구축(고정).
2. 각 extractor는 `coverage`, `empty_rate`, `timeout_rate`를 리포트.
3. 정책에서 “성공률 < 90% 포맷은 MVP 제외(UNSCANNABLE)”를 자동 적용.

워커 타임아웃 예시:
```rust
// extractor는 반드시 타임아웃으로 감싼다.
let extracted = tokio::time::timeout(Duration::from_secs(30), extract(file_path)).await;
match extracted {
    Ok(Ok(text)) => { /* continue */ }
    Ok(Err(_e)) => { /* UNSCANNABLE_FORMAT */ }
    Err(_elapsed) => { /* UNSCANNABLE_TIMEOUT + quarantine */ }
}
```

외부 도구/바이너리 래핑에 대해:
- [부분 수용] “외부 helper”는 실무적으로 빠른 길이지만, 공급망/서명/AV 오탐/업데이트를 같이 떠안는다.
- MVP에서는 `txt/csv/ooxml` 같은 “자체 구현 가능한 포맷”에 집중하고, 어려운 포맷은 **연기 + 격리된 helper(서명된 번들)** 로만 확장한다.

---

## 논점 9: DRM 연동 전략 (추가)

### 받은 비평 요약
- Claude: 한국 시장에서 DRM 비중이 커서 “DRM 파일을 못 보면 신뢰가 깨진다”. 다만 MVP에서는 “DRM 여부 감지 + 스캔 불가 보고”까지만 하고, 내용 스캔은 Phase 2 이후. (`docs/debate/round1-claude.md`)

### Codex의 응답
- [수용] MVP 목표는 “DRM 내용 탐지”가 아니라 **DRM 가시화(visibility)** 다.

구현 시나리오:
1. 헤더/매직넘버/확장자/벤더 시그니처로 DRM 가능성을 분류한다.
2. 분류되면 즉시 `UNSCANNABLE_DRM`으로 결과를 보고한다(미탐처럼 조용히 넘기지 않는다).
3. Phase 2에서 벤더별 SDK 연동을 “별도 helper 프로세스”로 추가한다.

```rust
pub enum ScanStatus {
    Ok,
    UnscannableDrm { vendor: Option<String> },
    UnscannableEncrypted,
    UnscannableFormat,
    Error { code: String },
}
```

