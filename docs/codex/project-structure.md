# 프로젝트 구조 (Rust Cargo Workspace) 제안

이 문서는 **Windows PC 에이전트(클라이언트)** 중심의 개인정보(PII) 탐지 제품을 Rust로 구현하기 위한 Cargo workspace 구조와 모듈 간 인터페이스(핵심 trait), 테스트/벤치마크, CI/CD 파이프라인을 제안한다.

핵심 목표(오탐/과탐 감소, 사용자 업무 방해 최소화, 실시간 감지, 비정형 PII 탐지, CPU-only, 상용 보안/라이선스)를 구조적으로 담기 위해 다음 원칙을 따른다.

- “값싼 판단(cheap) → 비싼 판단(expensive)” 파이프라인을 강제한다. (정규식/체크섬/휴리스틱 → NER 검증)
- 증분 스캔(변경분 중심)과 실시간 이벤트(파일 생성/변경) 경로를 같은 엔진으로 수렴시킨다.
- PII 자체를 로그/전송/저장하지 않는 것을 기본값으로 둔다. (증거는 해시/마스킹/정책 기반)
- 무거운 의존(ONNX Runtime, PDF 파서, gRPC 등)은 **구현(crate)** 로 격리하고, 핵심 엔진/도메인은 가볍게 유지한다.

---

## 1. Cargo workspace 구조 제안 (crate 분리와 의존 관계)

### 1.1 분리 기준 (권장)

- **도메인 타입과 계약(interfaces)** 는 매우 안정적이므로 `pii-types`, `pii-interfaces` 로 분리한다.
- **엔진(조립/오케스트레이션)** 은 구현에 의존하지 않고 interface에만 의존한다. (테스트와 교체 용이)
- OS/파일 포맷/추론 런타임처럼 변동이 큰 구현은 개별 crate로 격리한다.
- Windows 전용 코드는 `cfg(windows)` 로 가두고, 가능한 한 “Windows 구현(crate)” 내부에 머물게 한다.

### 1.2 권장 workspace 레이아웃

아래는 “클라이언트+서버를 같은 repo에서 관리할 수 있는” 형태다. 서버 스택이 바뀌더라도 클라이언트 구조는 그대로 유지된다.

```text
pii-scanner/
  Cargo.toml                  # [workspace]
  crates/
    pii-types/                # 순수 도메인 타입/에러/정책 스키마
    pii-interfaces/           # 핵심 trait(Extractor/Detector/Store/Reporter/Policy 등)
    pii-engine/               # 스캔 파이프라인 오케스트레이션(구현에 비의존)

    pii-extract/              # 텍스트 추출 프레임워크 + 공통 유틸
    pii-extract-ooxml/        # (옵션) docx/xlsx/pptx 등 OOXML
    pii-extract-pdf/          # (옵션) PDF 텍스트 추출
    pii-extract-plain/        # txt/csv/log 등 라인 기반
    pii-extract-drm/          # (옵션) DRM 감지/분류(추출 불가 보고 포함)

    pii-detect-regex/         # 정규식 + 체크섬/검증(주민번호/카드 등)
    pii-detect-heuristic/     # (옵션) 컨텍스트 휴리스틱(양식/라벨/패턴)
    pii-detect-ner/           # (옵션) ONNX 기반 NER(KoELECTRA 등), CPU 추론
    pii-score/                # (옵션) 결과 융합/스코어링/오탐 억제 규칙

    pii-fs-windows/           # 파일 열거/실시간 감지(Windows 구현)
    pii-store-sqlite/         # 증분 스캔 상태 + outbox(전송 큐) + 로컬 캐시
    pii-transport/            # 클라이언트-서버 전송(HTTP/gRPC 등 구현)
    pii-crypto/               # (옵션) 로컬 암호화/서명/증거 해시(PII 최소화)
    pii-license/              # 라이선스 검증/디바이스 바인딩(상용)
    pii-telemetry/            # 로깅/메트릭/tracing (PII-safe 로깅 규칙 포함)
    pii-defaults/             # “권장 조합” wiring(컴포넌트 생성/설정 로딩)

  apps/
    pii-agent/                # Windows 에이전트(서비스/백그라운드)
    pii-admin-cli/            # 로컬 점검/디버그/벤치 실행용 CLI
    pii-server/               # (옵션) 서버(정책 배포/리포트 수집)

  tools/
    xtask/                    # 코드젠/패키징/MSI/릴리스 자동화(권장)
    pii-eval/                 # 오탐/정탐 벤치마크 러너(데이터셋 평가)
```

### 1.3 Crate 책임과 의존 방향

의존 방향은 단방향으로 유지한다. “도메인/인터페이스 → 구현 → 앱” 흐름이 깨지면 테스트/교체 비용이 급증한다.

```text
pii-types
  ↓
pii-interfaces
  ↓
pii-engine
  ↓
(impl crates: extract/*, detect-*, fs-windows, store-sqlite, transport, license, telemetry, crypto)
  ↓
apps (pii-agent, pii-admin-cli, pii-server)
```

권장 의존 매핑(요약):

| crate | 역할 | 주요 의존 |
|---|---|---|
| `pii-types` | 도메인/정책/결과 타입 | 최소 의존(serde/thiserror 등) |
| `pii-interfaces` | 핵심 trait(계약) | `pii-types` |
| `pii-engine` | 스캔 파이프라인(구현 비의존) | `pii-interfaces`, `pii-types` |
| `pii-extract-*` | 파일별 텍스트 추출 구현 | `pii-interfaces`, `pii-types` |
| `pii-detect-regex` | 정규식/체크섬 기반 탐지 | `pii-interfaces`, `pii-types` |
| `pii-detect-ner` | NER 추론(ONNX) | `pii-interfaces`, `pii-types` |
| `pii-score` | 결과 융합/스코어/오탐 억제 | `pii-types` (가능하면 `pii-interfaces` 없이) |
| `pii-fs-windows` | 파일 이벤트/열거(Windows) | `pii-interfaces`, `pii-types` |
| `pii-store-sqlite` | 상태/증분/전송 큐 | `pii-interfaces`, `pii-types` |
| `pii-transport` | 서버 통신 | `pii-types` (DTO), `pii-crypto` |
| `pii-license` | 라이선스 | `pii-types`, `pii-crypto` |
| `pii-defaults` | 권장 조립(wiring) | 구현 crate들 + `pii-engine` |
| `apps/pii-agent` | 에이전트 실행물 | `pii-defaults` |

### 1.4 Feature 플래그(성능/배포 유연성)

에이전트는 고객사 환경에 따라 구성 변경이 필요하므로 feature 플래그로 “무거운 옵션”을 제어한다.

- `pii-detect-ner`: 기본은 `off`, 정책으로 “의심 텍스트에만” 실행되도록 엔진에서 강제
- `pii-extract-pdf`, `pii-extract-ooxml`: 고객사 문서 유형에 따라 on/off
- `transport-grpc` vs `transport-http`: 서버 스택에 맞춰 선택

---

## 2. 모듈 간 핵심 trait/interface 설계

핵심은 “스캔 파이프라인을 구성하는 부품 계약”을 명확히 정의해, 구현 교체(새 모델/새 포맷/새 전송) 시 엔진을 고치지 않도록 하는 것이다.

아래 코드는 **인터페이스 형태를 설명하기 위한 스케치** 이며, 실제 타입/에러는 `pii-types` 중심으로 정리한다.

### 2.1 도메인 타입(요지)

`pii-types`는 “클라이언트/서버/테스트”가 공유하는 최소 타입을 제공한다.

```rust
/// PII 종류(예: 주민등록번호, 전화번호, 이메일, 주소, 이름 등)
pub enum PiiKind { /* ... */ }

/// 탐지 근거가 되는 텍스트의 위치(추출 단계에서 제공)
pub struct TextSpan {
    pub offset: u32,     // chunk 내 시작 오프셋
    pub len: u32,
}

/// 텍스트 조각. 파일 전체가 아니라 "청크" 기반 처리로 CPU/메모리 제어.
pub struct TextChunk {
    pub text: String,
    pub origin: ChunkOrigin,   // 파일 경로, 페이지, 시트명 등
}

pub enum DetectionMethod { Regex, Checksum, Ner, Heuristic, Fusion }

pub struct DetectionHit {
    pub kind: PiiKind,
    pub span: TextSpan,
    pub confidence: f32,        // 0.0..=1.0
    pub method: DetectionMethod,
    pub evidence: EvidenceRef,  // 기본은 해시/마스킹
}

pub struct ScanReport {
    pub file: FileRef,
    pub fingerprint: FileFingerprint,
    pub hits: Vec<DetectionHit>,
    pub risk_score: f32,
    pub scan_reason: ScanReason, // Initial, Scheduled, RealtimeEvent
}
```

### 2.2 정책/구성 흐름

정책은 “무엇을 스캔/어떤 탐지기/어떤 임계값”을 결정하며, 엔진은 정책을 받아 동작만 한다.

```rust
pub trait PolicyProvider: Send + Sync {
    fn current(&self) -> PolicySnapshot;
    fn etag(&self) -> Option<String>; // 정책 버전 추적
}
```

권장: 에이전트는 정책 업데이트를 폴링하거나(간단) 장기적으로는 서버에서 푸시(고급)할 수 있게 `PolicyProvider` 구현을 교체 가능하게 둔다.

### 2.3 파일 이벤트(실시간)와 열거(초기/증분) 인터페이스

실시간 감지와 초기 스캔을 다른 코드로 만들면 오탐 억제 로직이 분기되기 쉽다. “입력만 다르고 엔진은 동일”하게 설계한다.

```rust
pub enum FileEventKind { Created, Modified, Renamed, Deleted }

pub struct FileEvent {
    pub kind: FileEventKind,
    pub path: std::path::PathBuf,
}

pub trait FileEventSource: Send + Sync {
    fn next_event(&mut self) -> Option<FileEvent>;
}

pub trait FileEnumerator: Send + Sync {
    fn enumerate(&self, policy: &PolicySnapshot) -> Vec<std::path::PathBuf>;
}
```

`pii-fs-windows`는 위 trait을 구현한다. 내부 구현은 `ReadDirectoryChangesW` 또는 USN Journal 등을 선택할 수 있지만, 엔진/앱에는 노출하지 않는다.

### 2.4 증분 스캔을 위한 상태 저장소(StateStore)

증분 스캔은 “파일 지문(fingerprint)”을 저장해 변경 없으면 스킵한다. 또한 전송 실패 시 보고(outbox)를 보존해야 한다.

```rust
pub trait StateStore: Send + Sync {
    fn last_fingerprint(&self, file: &FileRef) -> Option<FileFingerprint>;
    fn put_fingerprint(&self, file: &FileRef, fp: &FileFingerprint);

    fn enqueue_report(&self, report: &ScanReport);
    fn dequeue_reports(&self, max: usize) -> Vec<ScanReport>;
}
```

권장: `StateStore`는 “SQLite 기반 단일 파일 DB”로 시작한다. 대규모 배포에서 장애 조사/포렌식에 유리하며, outbox 패턴을 적용하기 쉽다.

### 2.5 텍스트 추출(Extract) 인터페이스

추출기는 파일 형식별로 교체 가능해야 한다. 또한 “청크 단위”로 흘려보내 NER 적용 범위를 줄이기 쉽도록 한다.

```rust
pub trait TextExtractor: Send + Sync {
    fn can_handle(&self, file: &FileRef) -> bool;

    /// 실패해도 에이전트가 죽지 않도록 "오류를 보고 가능한 범위에서 계속"을 기본으로 한다.
    fn extract(&self, file: &FileRef, policy: &PolicySnapshot) -> Result<Vec<TextChunk>, ExtractError>;
}

pub trait ExtractorRegistry: Send + Sync {
    fn pick(&self, file: &FileRef) -> Option<&dyn TextExtractor>;
}
```

DRM 파일은 “추출 불가” 자체가 중요한 이벤트가 될 수 있으므로, `pii-extract-drm` 같은 감지기를 통해 `ScanReport`에 “DRM 보호로 분석 제한” 상태를 기록할 수 있게 한다.

### 2.6 탐지(Detect) 인터페이스: Cheap → Expensive

오탐/과탐을 낮추려면 “후보 생성(cheap) + 검증(expensive)”를 구조로 강제하는 것이 효과적이다.

```rust
/// 1차: 빠른 후보 생성(정규식/체크섬/라벨 휴리스틱 등)
pub trait CandidateDetector: Send + Sync {
    fn detect_candidates(&self, chunk: &TextChunk, policy: &PolicySnapshot) -> Vec<DetectionHit>;
}

/// 2차: 비싼 검증(NER 등). 의심 구간만 입력으로 받도록 설계한다.
pub trait Verifier: Send + Sync {
    fn verify(&self, chunk: &TextChunk, candidates: &[DetectionHit], policy: &PolicySnapshot)
        -> Vec<DetectionHit>;
}

/// 3차: 결과 융합/스코어링(오탐 억제 규칙을 중앙집중화)
pub trait Fusion: Send + Sync {
    fn fuse(&self, primary: Vec<DetectionHit>, verified: Vec<DetectionHit>, policy: &PolicySnapshot)
        -> Vec<DetectionHit>;
}
```

권장 구현 흐름:

- `pii-detect-regex`: 주민번호/카드번호/전화번호/이메일 같은 “형식 기반”은 정규식 이후 체크섬/검증으로 오탐을 크게 줄인다.
- `pii-detect-ner`: 이름/주소 같은 비정형은 NER로 “검증”하되, 기본은 후보 주변 텍스트만 넣는다.
- `pii-score`: “이름 단독은 약함, 이름+주소 조합은 강함” 같은 결합 규칙을 정책화한다.

### 2.7 스캔 엔진(오케스트레이션) 계약

`pii-engine`는 입력(파일 경로, 이벤트 사유)만 받으면 동일한 파이프라인으로 처리한다.

```rust
pub struct Scanner<'a> {
    pub policy: &'a dyn PolicyProvider,
    pub store: &'a dyn StateStore,
    pub extractors: &'a dyn ExtractorRegistry,
    pub candidate: &'a dyn CandidateDetector,
    pub verifier: Option<&'a dyn Verifier>,
    pub fusion: &'a dyn Fusion,
}

impl<'a> Scanner<'a> {
    pub fn scan_file(&self, file: &FileRef, reason: ScanReason) -> ScanOutcome { /* ... */ }
}
```

엔진 레벨에서 지켜야 할 제약:

- NER는 **후보가 있을 때만** 실행하거나, 정책이 명시적으로 허용하는 경우에만 제한적으로 실행한다.
- 텍스트 추출 실패는 “실패 보고 + 다음 파일 진행”이 기본이다. (업무 방해 최소화)
- 동일 파일 재스캔은 `StateStore`의 fingerprint로 스킵한다. (증분 스캔)

### 2.8 보고(Reporting)와 PII 최소화

관리자에게 “무엇이 발견되었는지”는 필요하지만, 원문 PII를 서버로 보내는 것은 리스크가 크다. 기본값은 “해시/마스킹/요약”이며, 정책으로만 완화한다.

```rust
pub trait ReportSink: Send + Sync {
    fn send(&self, batch: &[ScanReport]) -> Result<(), TransportError>;
}
```

권장: `pii-store-sqlite` outbox에서 `ReportSink`로 전송한다. 네트워크 장애 시에도 로컬 큐가 보존되어야 한다.

---

## 3. 테스트 전략 (단위, 통합, 오탐 벤치마크)

### 3.1 단위 테스트(Unit)

목표: “오탐 억제 규칙”과 “검증 로직(체크섬/정규식/스코어)”이 회귀하지 않도록 한다.

- `pii-detect-regex`: 패턴별 테스트 케이스를 **데이터 구동**(예: `tests/cases/*.jsonl`)으로 관리한다.
- 체크섬/검증(주민번호, 카드번호 등)은 경계값/오탐 유발 문자열을 집중 테스트한다.
- `pii-score`: 결합 규칙(이름+주소, 라벨 근접성 등)은 “입력 hits → 기대 risk_score / filtered hits” 형태로 테스트한다.
- `pii-types`: 직렬화/역직렬화(정책 스키마) 호환성 테스트를 둔다.

권장 도구:

- `proptest`: 형식 기반 탐지기의 랜덤 변형(공백/하이픈/유니코드 변형)으로 내구성 테스트

### 3.2 통합 테스트(Integration)

목표: “실제 스캔 파이프라인이 끝까지 돈다”를 보장한다.

- `pii-engine` + `pii-defaults` 조합으로 임시 디렉터리에 파일을 생성하고 스캔 결과를 검증한다.
- 증분 스캔: 같은 파일을 2회 스캔했을 때 2회차가 스킵되는지(fingerprint 기반) 테스트한다.
- outbox: 전송 실패를 가정하고 큐에 쌓였다가 재시도 시 배치 전송되는지 테스트한다.
- Windows 파일 이벤트는 CI에서 flaky해지기 쉬우므로 “짧은 타임아웃 + 재시도”를 적용하고, 핵심 로직은 `FileEventSource` mock으로 검증한다.

### 3.3 오탐(과탐) 벤치마크(정량 평가)

목표: “오탐/과탐을 획기적으로 낮춘다”를 주장하려면, PR 단위로 추적 가능한 지표가 필요하다.

권장 구성:

- `tools/pii-eval` (또는 `apps/pii-admin-cli eval`) 형태의 러너를 만든다.
- 데이터셋은 다음 2개로 나눈다.
- `negative_corpus`: **PII가 없어야 하는** 일반 업무 문서/로그/가짜 데이터(합법적/비식별)
- `positive_corpus`: **PII가 포함된** 합성/샘플(주민번호/전화/주소/이름 조합 등) + 라벨

권장 지표:

- `False Positive Rate (FPR)`: negative에서 “hit가 1개 이상 나온 문서 비율”
- `FP per MB`: 용량 대비 오탐 발생률(대규모 PC에서 예측이 쉬움)
- `Precision/Recall`(가능하면): positive/negative 라벨이 있는 경우
- `NER invocation rate`: 전체 스캔 중 NER가 호출된 비율(사용자 업무 방해 지표의 대리변수)
- `p95 scan latency`: 파일 1개 처리 p95(정책/파일 크기별)

운영 방식:

- PR CI에서는 “소규모 스모크 벤치”만 수행한다. (수 초~수 분)
- Nightly(스케줄)에서는 “전체 벤치”를 수행하고 결과를 아티팩트로 저장한다.
- 오탐 회귀를 막기 위해 “Known FP regression set”을 별도로 유지한다. (과거 오탐 사례의 텍스트를 비식별/합성해 재현)

### 3.4 성능/안정성 테스트

- `criterion` 벤치: regex 후보 생성 처리량, NER 추론 p50/p95, 추출기별 처리량
- `cargo fuzz`(선택): 파일 포맷 파서/추출기에 대한 크래시 방지(상용 안정성)

---

## 4. CI/CD 파이프라인

여기서는 “GitHub Actions 기준”으로 설명하지만, GitLab CI/Jenkins로도 동일한 단계로 옮길 수 있다.

### 4.1 CI (PR/Push)

필수 게이트:

- `cargo fmt --check`
- `cargo clippy --all-targets --all-features -D warnings`
- `cargo test --workspace`
- Windows 빌드/테스트: `windows-latest` 러너에서 `apps/pii-agent` 최소 빌드 확인

권장(속도/신뢰성):

- `cargo nextest`로 테스트 실행 시간 단축
- 캐시: `~/.cargo/registry`, `target/` 캐시
- MSRV(최소 지원 Rust 버전)를 정하고 `rust-toolchain.toml`로 고정(재현성)

### 4.2 보안/컴플라이언스(상용 요구)

- `cargo audit`: 취약점 점검
- `cargo deny`: 라이선스/금지 의존성 정책
- SBOM 생성: CycloneDX 등(`cargo-cyclonedx` 또는 사내 표준)
- 바이너리 서명 준비: Windows 코드사이닝(릴리스 단계)

### 4.3 벤치마크 파이프라인

- PR: 스모크 벤치(작은 negative/positive)만 수행, 결과를 PR 코멘트 또는 아티팩트로 첨부
- Nightly: 전체 오탐 벤치 + 성능 벤치 수행, 결과를 시계열로 보관(대시보드/아티팩트)

### 4.4 CD / 릴리스

클라이언트(Windows 에이전트):

- 태그(`vX.Y.Z`) 생성 시 릴리스 워크플로 실행
- `--release` 빌드 산출물 생성
- MSI/설치 패키징(권장: `tools/xtask`로 WiX/NSIS 등 자동화)
- 코드사이닝(Secrets/인증서 필요)
- 아티팩트 업로드(GitHub Release 또는 사내 배포 서버)
- (선택) 단계적 배포(링 채널): canary → pilot → broad

서버(옵션):

- Docker 이미지 빌드/푸시(레지스트리)
- 마이그레이션 실행(선행 단계)
- 스테이징 배포 후 헬스체크
- 프로덕션 배포(블루/그린 또는 롤링)

---

## 부록: “오탐을 구조로 줄이는” 설계 체크리스트

- 후보 생성은 싸게(정규식) 하되 반드시 검증(체크섬/문맥 규칙)을 붙였는가
- NER는 전체 텍스트에 무차별 적용하지 않고 “의심 구간”에만 적용되는가
- 결과 융합 규칙이 흩어져 있지 않고(`pii-score`) 한 곳에서 관리되는가
- PII 원문이 로그/전송/저장 기본 경로에 섞이지 않게 타입/정책으로 막았는가
- 증분 스캔과 실시간 이벤트가 같은 엔진 경로로 수렴하는가

