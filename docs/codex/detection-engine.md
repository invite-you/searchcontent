# 한국어 PII 탐지 엔진(Detection Engine) 상세 설계안 (Client-side, CPU-only)

## 1. 요약(Summary)
본 문서는 Windows PC 클라이언트에서 파일 내 개인정보(PII)를 **CPU-only 환경**에서 **고정확도**로 탐지하고, **실시간 감지 + 증분 스캔(incremental scan)** 을 통해 **사용자 업무 방해를 최소화**하는 탐지 엔진(Detection Engine)의 구현 가능한 상세 설계안을 제시한다.

핵심 설계 결론(Design Decisions)
1. **하이브리드 파이프라인(Hybrid Pipeline)**: 정규식(Regex)+검증(Validation)+컨텍스트 룰(Context Rule)로 1차 후보를 고정밀로 만들고, **의심 구간에만 NER**(Named Entity Recognition)를 적용한다.
근거: NER를 전체 텍스트에 적용하면 CPU 비용과 지연이 커지고, 오탐도 증가할 수 있다. 반대로 Regex만으로는 한국어 비정형 PII(이름/주소/조합) 미탐이 크다. 하이브리드는 비용과 정확도의 균형이 가장 좋다.
2. **오탐률 6% 이하 목표**: 후보 생성 단계에서 **엄격한 검증(Checksum/Luhn 등)** + **부정 컨텍스트(negative context) 필터** + **화이트/블랙리스트(allow/deny list)** + **중복 제거(dedup)** 를 결합한다.
근거: 오탐은 “숫자 패턴이 우연히 맞는 경우”와 “예시/샘플/로그/테스트 데이터”에서 대량 발생한다. 체크섬과 컨텍스트 필터는 비용 대비 오탐 감소 효과가 크다.
3. **CPU 성능 전략**: 텍스트 추출(Text Extraction)을 스트리밍/청크(chunk) 기반으로 하고, NER는 ONNX Runtime 기반 + INT8 양자화(Quantization) + 윈도우링(windowing) + 캐시(cache)로 제한한다.
근거: 파일은 대체로 대용량/다양 포맷이며, “전체 추출 후 전체 NER”는 현실적으로 불가능하다. 비용이 큰 구간을 좁히고, 동일 텍스트 재추론을 막는 것이 필수다.
4. **기업 확장성(Extensibility)**: 룰(Rule)을 YAML 기반 DSL로 패키징하고, 서명(Signature)·버전(Version)·배포/롤백(Deploy/Rollback)을 제공한다. Regex 엔진은 기본적으로 **안전한 엔진(safe regex)** 을 사용한다.
근거: 고객사 요구는 “패턴 추가/예외 처리”가 대부분이다. 코드 배포 없이 룰 업데이트로 대응해야 운영 비용이 낮아지고, ReDoS(Regex DoS) 위험도 줄일 수 있다.

범위(Goals)
- 파일 생성/변경 시점의 실시간 감지(Real-time Detection) + 주기적 증분 스캔
- 한국어 PII: 정형(주민등록번호 등) + 비정형(이름/주소/조합)
- 엔드포인트(PC) 내 탐지 결과를 관리자 서버로 보고(Reporting)

비범위(Non-Goals)
- 데이터 유출 방지(DLP) 차단/암호화/격리 정책 자체
- OCR(Optical Character Recognition)은 옵션(선택 모듈)으로 두고, 기본 설계는 텍스트 기반에 집중

### 1.1 운영 정의 및 MVP 스코프(Operational Definitions & MVP Scope)
초기 MVP(예: 3-4개월)에서 목표/지표가 흔들리면 “오탐 6%” 같은 수치가 의미를 잃는다. 따라서 아래를 제품 레벨 정의로 고정한다.

- 실시간(Real-time) SLO:
  - 정책으로 지정된 핵심 경로(예: 문서/바탕화면/다운로드)는 파일 생성/수정 이벤트 발생 후 30초 이내 스캔 작업 큐잉(queueing), 5분 이내 1차 규칙 기반 탐지(Regex/Validator) 완료를 목표로 한다.
  - 그 외 경로는 USN 기반 증분 스캔(incremental scan)으로 `N`분(예: 5-15분) 내 eventual 처리로 정의한다.
  - 근거: “전 볼륨 즉시 감지”는 워처(Watcher) 확장 시 리소스/누락 리스크가 커져 CPU-only/업무방해 목표와 충돌한다.
- 오탐률(false positive) 6% 이하의 정의:
  - 기본 KPI는 알림 단위(alert-level) Precision으로 정의한다: `FP_rate = FP_alerts / total_alerts` (관리자 오탐 처리 액션 기준).
  - 보조 KPI로 파일 단위(file-level) Precision/Recall을 함께 본다(문서 8.2).
  - 근거: 운영에서 실패를 만드는 것은 “탐지 자체”보다 “알림 신뢰도”이며, 엔티티 F1만으로는 운영 품질을 보장하기 어렵다.
- 파일 포맷 지원(MVP):
  - 기본 지원: `txt/csv/log` + `OOXML(docx/xlsx/pptx)` 내장 추출기(built-in extractor)
  - 후순위(Phase 2+ 옵션): IFilter, PDF 고품질 추출, 아카이브(archive) 심화, OCR
  - 근거: 포맷 커버리지 확장은 오탐/업무방해/불안정성(hang/폭주) 리스크를 동시에 올리므로, MVP에서는 “안정성/예측 가능성”을 우선한다.
- NER 범위(MVP):
  - NER은 “베타(beta)”로 제공하고, 트리거 기반 의심 구간(suspect span)에만 실행한다. 파일당 NER 호출 상한(hard cap)과 타임아웃(timeout)을 강제한다.
  - 근거: NER은 확률적 모델이며 CPU 비용이 크다. 호출 조건을 보수적으로 두지 않으면 오탐/업무방해가 동시에 악화될 수 있다.

---

## 2. 아키텍처(Architecture)
### 2.1 구성 요소(Modules)
- `FileEventIngestor`: 파일 이벤트 수집(실시간) + 스케줄 기반 증분 스캔 트리거
- `ScanScheduler`: 우선순위/리소스 제어(CPU/IO), 디바운스(debounce), 백오프(backoff)
- `TypeDetector`: 파일 유형 판별(확장자+매직바이트)
- `TextExtractor`: 파일별 텍스트 추출기(Extractor) 라우팅
- `TextNormalizer`: 정규화(normalization) 및 청크 생성(chunking)
- `RuleEngine`: Regex 룰 + 컨텍스트 룰 평가
- `Validator`: 체크섬(checksum)·형식·사전 기반 검증
- `CandidateScorer`: 후보 스코어링(scoring) 및 임계값(threshold) 판단
- `NerRunner`: NER 추론(ONNX Runtime) 및 후처리(post-processing)
- `ResultAggregator`: 엔티티 병합(merge)·중복 제거(dedup)·파일 위험도(risk) 산정
- `PolicyManager`: 룰/모델 패키지 버전 관리, 서명 검증, 롤백
- `LocalStateStore`: 로컬 상태 DB(예: SQLite)로 파일 지문(fingerprint)·스캔 이력 저장
- `Reporter`: 서버 보고(PII 최소전송 원칙), 재시도(retry), 배치 전송(batch)

근거: 모듈 분리는 (1) 룰/모델 업데이트의 독립성, (2) 포맷별 추출기의 교체 가능성, (3) 성능 이슈 발생 시 병목 지점의 분리/튜닝을 가능하게 한다.

### 2.2 데이터 흐름(Data Flow)
```text
[File Events / Incremental Scan]
        |
        v
  ScanScheduler (debounce, priority, throttle)
        |
        v
   TypeDetector ---> (unsupported/drm) ---> Result: "UNSCANNABLE"
        |
        v
   TextExtractor (stream) -> TextNormalizer (chunks/windows)
        |
        v
 RuleEngine + Validator -> CandidateScorer
        |                       |
        | (needs NER?)           | (high confidence structured)
        v                       v
     NerRunner --------------> ResultAggregator
                (entities)         |
                                   v
                           Reporter (masked/hashed)
```

---

## 3. 세부 설계(Detailed Design)
요구된 “텍스트 추출 -> 후보 생성 -> 검증/스코어링 -> NER 적용 -> 결과 통합” 파이프라인을 실제 구현 관점에서 단계별로 정의한다.

### 3.1 파일 이벤트/증분 스캔(File Triggering)
#### 3.1.1 실시간 감지(Real-time)
권장 구현
- 기본: `ReadDirectoryChangesW` 기반 디렉터리 감시(Watch)로 생성/수정/이름변경 이벤트 수집
- 보강: NTFS `USN Journal` 기반 증분 스캔으로 누락 이벤트 보완 및 대규모 변경 처리

근거 및 트레이드오프
- `ReadDirectoryChangesW`는 실시간성이 좋지만, 버퍼 오버플로/재부팅/대량 이벤트에서 누락 가능성이 있다.
- `USN Journal`은 안정적으로 변경 파일 목록을 회수할 수 있으나, “즉시성”은 스케줄러 폴링에 의존한다.
- 둘을 결합하면 실시간/정확성을 동시에 얻을 수 있다(복잡도는 증가).

#### 3.1.2 디바운스(Debounce)와 파일 잠금 처리
정책(Policy)
- 파일 이벤트 수신 후 `N`초(예: 3~10초) 디바운스(동일 파일 이벤트를 묶음) 후 스캔 시작
- 파일이 열려 있어 읽기 실패 시(락/권한): 지수 백오프(exponential backoff)로 재시도(예: 1m, 5m, 30m)

근거: 파일 저장 중(Office 임시파일/부분쓰기) 스캔하면 텍스트 추출 실패/부분 텍스트로 오탐이 증가한다.

#### 3.1.3 증분 스캔(Incremental Scan) 상태 저장
로컬 상태(LocalStateStore)에 저장할 최소 정보
- `file_id`: 경로(path)+파일 ID(FileId) 조합(이름 변경/이동 대응)
- `mtime`, `size`
- `fast_hash`: 파일 앞/뒤 일부 블록을 합친 빠른 해시(예: xxh3)로 “변경 여부” 1차 판단
- `last_scan_time`, `last_scan_policy_version`, `last_scan_model_version`
- `last_findings_digest`: 결과 요약 해시(중복 보고 방지)

근거: 전체 파일 해시(sha256)를 매번 계산하면 IO 비용이 커진다. “빠른 변경 감지(fast fingerprint)”로 대부분을 거르고, 필요 시에만 전체 추출/정밀 스캔을 한다.

---

### 3.2 텍스트 추출(Text Extraction)
#### 3.2.1 파일 유형별 추출기(Extractor) 전략
권장 전략(MVP -> 확장)
- MVP 기본: **내장 추출기(built-in extractor)** 로 `txt/csv/log` + `OOXML(docx/xlsx/pptx)`를 안정적으로 지원한다.
  - 근거: 포맷 커버리지를 무리하게 넓히면 hang/메모리 폭주/품질 편차가 업무 방해로 직결된다. MVP에서는 “안정성/예측 가능성”이 더 중요하다.
- Phase 2+ 옵션: **Windows IFilter(IFilter)** 를 플러그인(plugin)으로 추가해 커버리지를 확장한다(PDF/메일 등).
  - 전제: IFilter는 워커 프로세스 격리 + 하드 타임아웃(hard timeout) + hang 감지 + 자동 quarantine을 필수로 한다.
  - 근거: 현장 PC마다 IFilter 설치/품질이 다르고 COM hang이 발생할 수 있어, 기본 경로로 두면 운영 리스크가 크다.

핵심 포맷에 대한 내장 추출기(built-in extractor) 범위
- 텍스트(txt, csv, log): 인코딩 감지(UTF-8/UTF-16/CP949 등) 후 스트리밍
- OOXML(docx, xlsx, pptx): zip+XML 파싱(공유 문자열 sharedStrings, 셀 값, 슬라이드 텍스트)
- PDF: 내장 구현은 비용이 크므로 MVP에서는 제외하고 Phase 2+에서 “제한적(guardrailed) 추출”부터 검토한다.
  - 근거: CPU-only에서 PDF 전량 고품질 추출은 난이도가 높고, 실패 시 사용자 불만이 크다.

DRM/암호화 파일 처리
- 암호화/DRM로 본문 추출 불가 시: `UNSCANNABLE_ENCRYPTED`로 분류하고 별도 리포트(스캔 불가 사유)
근거: 미탐으로 조용히 넘어가면 보안 리스크가 커진다. 탐지 불가 자체도 관리 인사이트다.

#### 3.2.2 추출 시 리소스 상한(Guardrails)
정책(Policy)
- 파일 크기 상한: 예) 200MB 이상은 “부분 스캔” 또는 “야간 전용”
- 압축 파일(archive): 재귀 깊이 제한(예: 3), 총 압축 해제 용량 제한(예: 500MB), 파일 수 제한
- 페이지 문서(PDF/PPT): 첫 `P`페이지 + 균등 샘플링(예: 1, 5, 10, …)으로 비용 제어

근거: 극단적으로 큰 파일/압축 폭탄(zip bomb)은 CPU/디스크를 고갈시켜 업무 방해를 유발한다. 상한은 “정확도”보다 “안정성”을 우선한다.

#### 3.2.3 정규화(Normalization)
정규화 규칙(예)
- 숫자 구분자 통일: `-`, `·`, 공백, 탭을 표준 구분자로 매핑
- 전각(Fullwidth) 숫자/문자 -> 반각(Halfwidth) 변환
- 제로폭 문자(Zero-width) 제거
- 유니코드 정규화(NFKC) 적용(단, 원문 오프셋 매핑을 유지하기 위해 “원문-정규화 매핑 테이블”을 유지)

근거: 한국어 문서에는 복사/붙여넣기 과정에서 다양한 구분자와 유니코드 변형이 들어온다. 정규화는 미탐 감소에 효과적이다.
트레이드오프: 오프셋(offset) 추적이 어려워진다. 따라서 정규화는 “원문 좌표로 복원 가능”해야 한다.

#### 3.2.4 청크 생성(Chunking)
청크 단위
- 기본: 문단(paragraph) 단위 + 길이 제한(예: 2~4KB 텍스트)
- 표/셀 기반 문서(xlsx): 셀 단위 또는 행(row) 단위
- 길이가 긴 텍스트는 슬라이딩 윈도우(sliding window)로 분할(예: 256~512 토큰 대응)

근거: 후보 생성/NER 모두 “지역적 컨텍스트(local context)”가 중요하고, 전체 텍스트는 비용이 너무 크다.

---

### 3.3 후보 생성(Candidate Generation)
후보 생성은 (1) 정형 PII(Structured)와 (2) 비정형 PII(Unstructured)를 분리하여 접근한다.

#### 3.3.1 정형 PII: Regex 기반 후보
대상 예시
- 주민등록번호(RRN): `######-#######` 변형 포함
- 사업자등록번호(BRN)
- 신용카드(Credit Card)
- 전화번호(Phone Number)
- 이메일(Email)
- 여권번호(Passport) 등(국가별 상이, 기업 요구에 따라 룰로 확장)

Regex 엔진 선택(중요 결정)
- 기본 엔진: Rust `regex` 계열(유한 오토마타 기반, backtracking 없음)
근거: 고객이 룰을 확장할 수 있는 구조에서 가장 큰 운영 리스크는 ReDoS이다. 안전한 엔진은 “최악의 경우에도” CPU를 폭발시키지 않는다.
트레이드오프: lookbehind 등 일부 고급 기능이 없다. 대신 DSL에서 “전후 컨텍스트 조건”을 별도 룰로 표현해 해결한다(3.3.3 참조).

#### 3.3.2 비정형 PII: 트리거 기반 후보(의심 구간 추출)
NER에 넣을 “의심 구간(suspect span)”을 만들기 위한 트리거(trigger) 설계
- 키워드 트리거: `이름/성명/성함/고객명/주소/거주지/연락처/휴대폰/주민번호/생년월일/우편번호` 등
- 주소 형태 트리거: `시`, `도`, `구`, `군`, `동`, `읍`, `면`, `리`, `로`, `길`, `번지`, `호`, `층` 같은 접미 토큰(suffix token) 조합
- 표/폼(form) 구조 트리거: `라벨(label): 값(value)` 패턴(예: `이름: 홍길동`)

근거: 한국어 이름/주소는 형태가 다양하여 Regex만으로 고정밀 탐지가 어렵다. 대신 “NER가 잘 동작하는 구간”을 좁히는 것이 비용과 정확도 모두에 유리하다.
트레이드오프: 트리거가 누락되면 미탐이 발생한다. 이를 보완하기 위해 3.5.2의 “부분 샘플링 NER”를 추가한다.

#### 3.3.3 컨텍스트 룰(Context Rule)로 후보 정제
Regex의 표현력 한계를 룰 엔진에서 보완한다.
- 긍정 컨텍스트(positive context): `주민번호`, `RRN`, `신용카드`, `Card No`, `주소`, `우편번호`, `전화`, `mobile` 등 근접 키워드
- 부정 컨텍스트(negative context): `예시`, `샘플`, `테스트`, `dummy`, `XXXX`, `0000`, `1234`, `abcdef`, `license key`, `serial` 등
- 거리/범위: 키워드와 후보 간 거리(window) 제한(예: 0~30자)
- 포맷 위치: 라벨-값 구조에서 값(value) 위치만 인정

근거: 동일 패턴이라도 “문맥”에 따라 실제 PII일 확률이 크게 달라진다. 컨텍스트 룰은 오탐 감소에 직접적이다.

---

### 3.4 검증/스코어링(Validation & Scoring)
#### 3.4.1 체크섬/형식 검증(Checksum/Format Validation)
주요 검증 알고리즘(예)
- 신용카드(Luhn)
  - 숫자열을 오른쪽부터 번갈아 2배 후 자리수 합산, 총합이 10으로 나누어 떨어지면 유효
  - 근거: Regex만으로는 카드번호 유사 문자열 오탐이 많다. Luhn은 비용이 매우 낮고 오탐을 크게 줄인다.
- 주민등록번호(RRN, 13자리)
  - 가중치: `[2,3,4,5,6,7,8,9,2,3,4,5]`
  - `s = sum(d[i] * w[i])` (i=0..11), `c = (11 - (s % 11)) % 10`
  - `c == d[12]`이면 체크 통과
  - 추가 형식 검증: 생년월일(YYMMDD) 가능 범위, 7번째 자리(성별/세대) 범위 등(정책으로 조절)
  - 근거: RRN 형태는 우연히 매칭될 수 있으나 체크섬 통과 확률은 낮아 오탐 감소 효과가 매우 큼.
- 사업자등록번호(BRN, 10자리)
  - 가중치 예: `[1,3,7,1,3,7,1,3,5]` (마지막은 특수 처리)
  - `s = sum(d[i] * w[i])` (i=0..8) + `floor((d[8]*5)/10)` (구현 정책에 따라 정확 수식 고정)
  - `c = (10 - (s % 10)) % 10`, `c == d[9]`
  - 근거: 기업 문서에서 BRN은 흔하고, 숫자열 오탐을 줄이기 위한 강력한 신호다.
- 전화번호(Phone)
  - 유효 접두(prefix): `010`, `011`, `016`, `017`, `018`, `019`, 지역번호 `02`, `031` 등(룰 패키지로 관리)
  - 길이 검증: 하이픈 포함/미포함 변형 허용, 자리수 범위 제한
  - 근거: 단순 `\d{3,4}-\d{4}`는 거의 모든 숫자열을 오탐으로 만든다. prefix/길이 검증이 필수다.

트레이드오프
- 체크섬/접두 검증을 너무 엄격히 하면 “실제지만 형식이 깨진 데이터”를 미탐할 수 있다.
- 해결: “엄격(Strict)”과 “완화(Relaxed)” 프로필을 제공하고, 기업 정책/부서별로 선택 가능하게 한다.

#### 3.4.2 화이트/블랙리스트(Allow/Deny List)
형태
- `allowlist`: 조직 내부에서 “PII로 취급하지 않기로 한” 예외(예: 특정 대표번호, 테스트 계정)
- `denylist`: 흔한 더미 값(예: `000000-0000000`, `123456-1234567`, `1111-1111-1111-1111`)
- 리스트는 원문 저장 대신 **해시(hash) 기반** 저장 지원(예: canonicalize 후 SHA-256)

근거: 현장 운영에서 오탐의 상당 비율은 “업무상 반복되는 가짜 데이터”에서 나온다. 리스트는 매우 저렴한 비용으로 큰 효과를 낸다.
트레이드오프: allowlist는 악용될 수 있다(실제 PII를 예외 처리). 따라서 정책 패키지 서명/승인 워크플로우가 필요(5장 참조).

#### 3.4.3 중복 제거(Deduplication)
단계
- 동일 파일 내 중복: 동일 엔티티(정규화 후)가 여러 번 등장하면 1건으로 합치고 `count`만 증가
- 동일 PC 내 중복: 같은 파일 재스캔 시 동일 결과면 재보고 억제
- (선택) 조직 전체 중복: 서버에서 엔티티 해시 기준으로 “이미 알려진 PII”는 알림 노이즈를 줄이기 위해 집계 중심으로 표시

근거: 중복 알림은 사용자/관리자 피로도를 유발하며 “업무 방해”의 핵심 원인이다.
트레이드오프: dedup이 과도하면 신규 파일에 대한 가시성이 떨어진다. 따라서 “신규 파일/경로 변화”는 별도 이벤트로 유지한다.

#### 3.4.4 스코어링(Scoring)과 임계값(Threshold)
후보 스코어 = 가중치 합(Weighted Sum) + 규칙 기반 보정(rule-based calibration)
예시 피처(feature)
- `checksum_ok` (강한 +)
- `has_label_keyword_nearby` (중간 +)
- `negative_context` (강한 -)
- `format_strength` (중간 +)
- `entropy`/`digit_pattern` (단순 반복/순차는 -)
- `source_type` (예: 폼/인사 서식은 +, 코드 파일은 -)

출력 등급
- `HIGH`: 즉시 보고(Report)
- `MEDIUM`: NER/추가 검증 후 보고
- `LOW`: 로컬 보관만(옵션) 또는 샘플링 검수 대상

근거: 단일 임계값은 운영에서 튜닝이 어렵다. 등급화는 정책 변경과 A/B 테스트에 유리하다.

---

### 3.5 NER 적용(NER Application)
#### 3.5.1 NER 호출 조건(When to Run NER)
NER는 “항상”이 아니라 “필요할 때만” 호출한다.
- `MEDIUM` 후보가 포함된 청크
- 트리거 키워드 주변 윈도우(예: ±200~500자)
- 라벨-값 구조에서 값(value)로 추정되는 짧은 구간

근거: NER는 CPU 비용이 가장 크다. 호출 조건을 명시해야 “업무 방해 최소화” 목표를 달성한다.

#### 3.5.2 미탐 방지용 샘플링(Sampling NER)
트리거가 없는 문서에 대한 보완 장치
- 파일당 최대 `K`개 청크를 균등 샘플링(예: 2~5개)하여 NER 실행
- 결과가 “이름+주소 조합” 같은 강한 신호를 보이면, 해당 파일은 추가 청크를 더 스캔(점진 확대)

근거: 트리거 기반만 쓰면 “라벨 없는 서술형 문서”에서 미탐이 발생한다. 소량 샘플링은 비용을 크게 늘리지 않고 미탐을 줄인다.
트레이드오프: 샘플링은 확률적이므로 완전 탐지는 아니다. 대신 정기(full) 스캔(야간/주말)과 결합한다.

#### 3.5.3 모델 선택 프레임(Model Selection Frame)
비교 대상 예
- KoELECTRA 계열(추천 후보)
- KLUE-RoBERTa
- XLM-R
- DeBERTa 계열

평가 기준(선정 근거에 반드시 사용)
- 정확도(Accuracy): 한국어 이름/주소/기관명/직책 등 엔티티 구분 성능(토큰 F1, 엔티티 F1)
- CPU 지연(Latency): 1청크 추론 시간 + 토크나이저(tokenizer) 비용
- 모델 크기(Model Size): 배포/업데이트 비용, 메모리 압박
- 양자화 친화성(Quantization-friendliness): INT8 적용 시 정확도 하락 폭
- 도메인 적합성(Domain Fit): 기업 문서(인사/고객/계약/민원) 텍스트 특성
- 다국어 요구(Multilingual): 영어/숫자 혼합, 약어, 외래어 처리
- 라이선스/운영(License/Ops): 상용 배포 가능성, 모델 업데이트 절차

권장 선택(초기)
- **KoELECTRA-base 수준 + Token Classification(NER) 파인튜닝(fine-tuning)** 을 1차 권장
근거: 한국어 중심 사전학습 모델은 형태소/띄어쓰기 변형에 상대적으로 강하고, base급은 CPU에서 현실적인 지연을 기대할 수 있다.
대안 판단
- KLUE-RoBERTa: 한국어 성능이 좋을 수 있으나 토크나이저/추론 비용과 배포 크기를 비교해야 한다.
- XLM-R: 다국어 혼합 문서가 많다면 유리하지만 보통 더 무겁고 CPU 비용이 증가한다.
- DeBERTa: 성능 잠재력은 있으나 CPU 추론 최적화/양자화 안정성을 검증해야 한다.

#### 3.5.4 학습/지속학습(Training & Continual Learning)
라벨 스키마(Label Schema)
- BIO/IOB2 태깅: `B-PER`, `I-PER`, `B-ADDR`, `I-ADDR`, `B-ORG`, `I-ORG`, `B-POST` 등
- 조합 엔티티(예: 이름+주소): 모델 출력은 분리(PER/ADDR)로 두고, 후처리에서 조합 룰로 “강한 PII 이벤트”로 승격

데이터 전략(실제 구현 가능)
- 초기: 합성 데이터(synthetic) + 공개 가능한 내부 예제(사내 승인)로 부트스트랩
- 운영: “검수 루프(review loop)”로 라벨 확장
  - `LOW/MEDIUM` 중 일부를 샘플링해(정책 기반) 관리자 검수
  - 검수 결과를 학습 데이터로 적재

지속학습 방식
- 주기적 재학습(batch retraining) + 모델 버전 관리(model registry)
- 망각 방지(anti-forgetting): 과거 데이터 리플레이(replay) 세트 유지
- 배포 안전장치: 새 모델은 소규모 엔드포인트에 카나리(canary) 배포 후 전체 확산

근거: 고객사 문서 스타일은 매우 다양해 “한 번 학습으로 끝”이 아니다. 검수 루프를 제품 기능으로 설계해야 오탐/미탐이 지속적으로 줄어든다.
트레이드오프: 검수는 비용(사람)이 든다. 따라서 “샘플링”과 “고위험 후보 우선”으로 최소화한다.

---

### 3.6 결과 통합(Result Aggregation)
#### 3.6.1 엔티티 병합(Merge) 규칙
- 동일 타입 + 오버랩(overlap) + 근접 거리(예: 3~10자 이내)면 하나로 병합
- Regex와 NER가 같은 범위를 가리키면 “더 높은 신뢰도(high confidence)” 출처를 채택하고, 다른 출처는 `evidence`로 기록
- 주소(ADDR)는 종종 분절된다. 연속 엔티티들을 룰로 결합(예: `서울특별시` + `강남구` + `테헤란로` + `123`)

근거: 사용자는 “수십 개 파편 엔티티”가 아니라 “하나의 의미 있는 PII”를 원한다. 병합은 관리자 UX와 중복 알림 감소에 필수다.

#### 3.6.2 파일 위험도(Risk) 산정
예시 정책
- `RRN` 또는 `CARD` 발견: 기본 HIGH
- `PER + ADDR` 동시 발견(근접): HIGH로 승격
- `PER` 단독 다수 발견: MEDIUM (문맥에 따라 조정)
- `ADDR` 단독: MEDIUM/LOW (조직 정책)

근거: 엔티티 타입별 위험도는 다르며, 조합일 때 위험이 커진다. 파일 단위로 우선순위를 정해야 대규모 운영에서 대응이 가능하다.

#### 3.6.3 서버 보고 시 개인정보 최소화(PII Minimization)
원칙
- 원문 전송 금지(기본). `snippet`은 마스킹(masking) 후 전송
  - 예: 주민번호 `######-*******`, 카드 `************1234`
- 엔티티 값은 canonicalize 후 해시(hash)로 전송(동일 PII dedup 및 집계용)
- 보고 데이터: `file metadata + counts + hashed entities + confidence + policy/model version`

근거: 탐지 솔루션 자체가 “PII 수집 시스템”이 되면 보안/법무 리스크가 커진다. 최소 수집이 제품 경쟁력이다.
트레이드오프: 서버에서 원문 검증이 어렵다. 해결: 필요 시에만 “승인된 워크플로우”로 원문 열람(엔드포인트 로컬 뷰) 제공.

---

## 4. 오탐률 6% 이하를 위한 단계별 장치(Precision Controls)
오탐을 체계적으로 줄이기 위해 “단계별 게이트(gate)”를 둔다.

### 4.1 1차(Regex)에서의 오탐 억제
- 안전한 Regex 엔진(safe regex) 사용으로 성능 리스크 제거
- 패턴을 넓게 잡지 말고 “경계(boundary)”를 명확히(숫자 앞뒤 문자인접 제한 등)
- 포맷 변형은 정규화에서 흡수하고, Regex는 단순화
근거: Regex가 복잡해질수록 유지보수/오탐이 늘어난다.

### 4.2 2차(검증)에서의 오탐 억제
- 체크섬(Checksum) 필수 적용(RRN/BRN/Card)
- 날짜/범위 검증(예: 생년월일 불가능 값 필터)
- 전화번호 prefix/자리수 검증
근거: 계산 비용이 매우 낮고 효과가 큼.

### 4.3 3차(컨텍스트)에서의 오탐 억제
- 라벨 키워드 기반(예: `주민번호:`) 가중치 부여
- 부정 컨텍스트(예: `예시`, `샘플`, `dummy`) 강한 감점
- 파일 유형 기반(예: `.rs`, `.js` 등 코드 파일은 감점)
근거: 문맥은 “진짜 PII” 확률을 직접적으로 바꾼다.

### 4.4 4차(화이트/블랙리스트)에서의 오탐 억제
- 조직별 테스트 값/대표번호 allowlist
- 흔한 더미값 denylist
- 리스트는 서명된 정책 패키지로만 업데이트 허용
근거: 운영에서 가장 즉효성 높은 조치가 리스트이며, 동시에 남용 위험도 높아 통제가 필요하다.

### 4.5 5차(중복 제거)로 알림 피로도 감소
- 동일 파일 내 중복 병합
- 동일 결과 재보고 억제(결과 digest 비교)
- 서버 집계 기반 중복 억제 옵션
근거: “오탐”이 아니더라도 “알림 노이즈”는 업무 방해로 인식된다.

### 4.6 6차(샘플링/검수 루프)로 지속 개선
- `LOW/MEDIUM` 후보 중 일부를 샘플링해 검수 데이터로 확보
- “오탐 상위 원인”을 자동 집계해 룰/모델 개선 우선순위로 사용
근거: 현장 문서 스타일 변화와 예외 케이스는 지속적으로 발생한다. 학습/룰 개선 루프가 없으면 목표 오탐률을 유지하기 어렵다.

---

## 5. CPU-only 현실 성능 설계(Performance on CPU-only)
### 5.1 ONNX Runtime + 양자화(Quantization)
권장
- NER 모델은 ONNX 변환 후 ONNX Runtime으로 추론
- INT8 양자화(INT8 quantization) 적용(정적(static) 또는 동적(dynamic) 방식은 실측 후 선택)

근거: Transformer 계열은 FP32로는 CPU 비용이 너무 크다. INT8은 일반적으로 지연/CPU 사용량을 크게 줄인다.
트레이드오프: 양자화는 정확도 하락을 유발할 수 있다. 따라서 “엔티티 타입별 임계값”과 “후처리 룰”로 보정한다.

### 5.2 배치/윈도우링(Batching & Windowing)
전략
- 청크를 토큰 길이 기준(예: 256 tokens)으로 윈도우링
- 이벤트성(실시간)은 **작은 배치**(latency 우선), 백그라운드 스캔은 **큰 배치**(throughput 우선)

근거: 배치는 CPU 효율을 높이지만 지연을 늘린다. 실시간과 백그라운드는 목표가 다르므로 모드를 분리한다.

### 5.3 캐시(Cache)
캐시 키
- `window_hash = hash(normalized_text_window)`
- 값: NER 결과(엔티티 + 확률)

적용 범위
- 동일 파일 재스캔(수정 없을 때)
- 문서 템플릿(서식) 반복(예: 동일 인사 양식)

근거: 기업 문서에는 템플릿 반복이 많다. 캐시는 CPU 비용을 선형이 아닌 부분적으로 상수화한다.
트레이드오프: 캐시는 메모리/디스크를 사용한다. LRU(Least Recently Used) + 크기 상한으로 제어한다.

### 5.4 스레딩(Threading)과 리소스 거버너(Resource Governor)
권장 정책
- 스캔 워커(worker) 스레드 풀: `min(논리코어-1, 상한)` 등으로 제한
- 프로세스 우선순위(priority) 낮춤 + 유휴(idle) 시 가속, 사용자 활동 시 감속
- IO 스로틀(throttle): 대용량 파일은 읽기 속도 제한 또는 야간 전용

근거: “업무 방해 최소화”가 제품 핵심 목표다. 성능은 최대 처리량보다 “최악의 경우에도 PC를 망치지 않는 것”이 중요하다.

### 5.5 파일 유형별 비용 모델(Cost Model)
대략적 비용 특성(정성적)
- 텍스트(txt/log/csv): 추출 저렴, Regex/검증 위주
- OOXML(docx/xlsx/pptx): 압축 해제 + XML 파싱 비용, 하지만 구조적 텍스트라 후보/컨텍스트가 유리
- PDF: 추출 비용/품질 편차 큼(엔진 의존), 페이지 제한/샘플링 필요
- 아카이브(zip): 폭발 위험, 상한/재귀 제한 필수

근거: 모든 포맷에 동일 정책을 적용하면 비용이 폭증한다. 포맷별 정책 차등이 필수다.

---

## 6. 기업 패턴 확장 구조(Extensibility & Operations)
### 6.1 룰 DSL/YAML 설계
목표
- 고객사가 “코드 수정 없이” 패턴/예외를 추가
- 룰의 안전성(Regex 안전, 리소스 제한) 보장

권장 스키마(예시)
```yaml
version: 1
rule_set_id: "corp-default"
rules:
  - id: "rrn_strict"
    type: "regex"
    entity: "RRN"
    pattern: "\\b\\d{6}[- ]?\\d{7}\\b"
    validators: ["rrn_checksum", "rrn_date_range"]
    context:
      positive_keywords: ["주민번호", "주민등록번호", "RRN"]
      negative_keywords: ["예시", "샘플", "dummy", "테스트"]
      window_chars: 30
    score:
      base: 0.6
      checksum_bonus: 0.3
      negative_penalty: 0.7
    threshold: 0.85
```

근거: (1) 사람이 읽고 검토 가능, (2) CI에서 정적 검증 가능, (3) 서명/버전 관리와 궁합이 좋다.
트레이드오프: YAML은 표현력이 제한된다. 대신 “조건(condition)”의 종류를 제한해 안전성과 예측가능성을 확보한다.

### 6.2 룰/모델 패키지 버전, 서명, 배포/롤백
패키지 구성(권장)
- `policy_bundle.zip`
  - `rules.yaml`
  - `allowlist.hashes`
  - `denylist.hashes`
  - `model.onnx` (선택)
  - `metadata.json` (버전, 호환성, 릴리즈 노트, 해시)
  - `signature.sig`

정책
- 클라이언트는 번들을 다운로드 후 서명 검증(signature verification) 통과 시에만 활성화
- 문제 발생 시 자동 롤백(auto rollback): “오탐 폭증/성능 악화” 탐지 시 이전 버전으로 되돌림

근거: 수만 대 배포에서는 “안전한 업데이트”가 기능만큼 중요하다.
트레이드오프: 서명/롤백은 운영 복잡도를 올린다. 하지만 상용 제품 수준 보안 요구를 충족하려면 필수다.

### 6.3 안전한 Regex 확장(Regex Safety)
정책
- 엔진 제한: backtracking 기반 PCRE를 기본 비허용
- 룰 정적 검사(static check): 패턴 길이, 반복자, 대안(alternation) 개수 제한
- 실행 제한: 각 청크당 Regex 매칭 시간/횟수 제한(실행 카운터)

근거: 고객 커스텀 Regex는 ReDoS 및 성능 사고의 주 원인이다. 제한은 제품 안정성의 핵심이다.

### 6.4 플러그인/모듈화(Plugin/Modularization)
현실적 권장
- 단일 바이너리(single binary) 유지: 동적 플러그인(DLL)보다는 “기능 플래그(feature flag) + 정책 패키지” 중심 확장
- 다만, 텍스트 추출기는 예외적으로 “외부 프로세스(external helper)”로 분리 가능

근거: 엔드포인트에서 DLL 플러그인은 배포/보안/호환성 비용이 크다. 반면 외부 추출기 프로세스는 샌드박싱/격리(크래시 격리) 장점이 있다.
트레이드오프: 외부 프로세스는 IPC 비용이 있다. PDF/IFilter 같은 무거운 추출에는 오히려 유리할 수 있다.

---

## 7. 리스크(Risks)와 대응(Mitigations)
### 7.1 텍스트 추출 품질 편차
- 리스크: IFilter/PDF 추출 품질이 환경마다 다름
- 대응: “추출기별 품질 지표(coverage, empty rate)” 텔레메트리(telemetry) 수집, 내장 추출기 백업

### 7.2 오탐 폭증(정책/모델 업데이트)
- 리스크: 룰/모델 업데이트 후 특정 포맷에서 오탐 폭증
- 대응: 카나리 배포(canary), 오탐 지표 모니터링, 자동 롤백

### 7.3 CPU/IO 사용량으로 인한 업무 방해
- 리스크: 실시간 대용량 파일 처리 시 PC 체감 성능 저하
- 대응: 리소스 거버너(우선순위/스로틀), 페이지/용량 상한, 야간 스캔 모드 분리

### 7.4 개인정보 최소화 실패(보고 데이터 과다)
- 리스크: 탐지 솔루션 자체가 민감정보를 모으는 시스템으로 전락
- 대응: 마스킹/해시 기본, 원문 미전송, 정책으로 예외 승인 절차 강제

### 7.5 NER 드리프트(도메인 변화)
- 리스크: 문서 스타일 변화로 정확도 하락
- 대응: 샘플링 검수 루프 + 주기적 재학습 + 회귀 테스트

---

## 8. 테스트/평가 계획(Test & Evaluation Plan)
정확도 목표(예): 운영 기준 **오탐률(false positive) 6% 이하**(정의 명확화 필요)

### 8.1 데이터셋 전략(Dataset Strategy)
구성
- 정형 PII 합성 데이터: 체크섬 통과/불통과, 다양한 구분자/유니코드 변형 포함
- 비정형 PII 문서: 실제 서식 기반 템플릿 + 가명처리(pseudonymization) + 라벨링
- 하드 네거티브(hard negative): 로그/코드/라이선스 키/주문번호 등 “오탐 유사 데이터”를 의도적으로 포함

근거: 오탐 6% 목표는 “네거티브 품질”에 달려 있다. 쉬운 음성 데이터만으로는 현장 오탐을 예측할 수 없다.

### 8.2 메트릭(Metrics) 정의
엔티티 레벨(entity-level)
- Precision / Recall / F1 (엔티티 단위 일치 기준은 IoU 또는 오프셋 오버랩 기준으로 정의)
- 타입별 지표: RRN, CARD, PHONE, EMAIL, PER, ADDR 등

파일 레벨(file-level)
- File Precision: “PII 있다고 판정된 파일 중 실제 PII 포함 파일 비율”
- File Recall: “실제 PII 포함 파일 중 탐지된 파일 비율”
- 오탐률(false positive rate) 후보 정의(운영 친화)
  - `FP_rate = FP_files / flagged_files` (알림 기반)
  - 또는 `FP_rate = FP_files / scanned_files` (전체 스캔 기반)

근거: 운영에서 중요한 것은 “알림의 신뢰도”다. 엔티티 F1만 높아도 알림 precision이 낮으면 실패다.

### 8.3 회귀 테스트(Regression)
구성
- 룰 회귀: golden corpus에 대해 “검출 결과 스냅샷(snapshot)” 비교
- 모델 회귀: 모델 버전별 지표 저장, 성능 하락 시 배포 차단(gate)
- 성능 회귀: 포맷별 대표 파일로 추출/스캔 시간 상한 테스트

근거: 룰/모델 업데이트가 잦은 제품에서 회귀 테스트 없이는 품질이 지속적으로 악화된다.

### 8.4 현장 검증(Online Validation)
- 카나리 그룹에서 지표 수집(오탐률, 사용자 영향 지표: CPU/IO, 스캔 지연)
- 알림 피드백(관리자 “오탐 처리” 액션)을 라벨로 활용

근거: 오프라인 데이터셋은 현실을 100% 반영하지 못한다. 온라인 검증은 필수다.

---

## 9. 구현 체크리스트(Implementation Checklist)
1. 이벤트 수집: ReadDirectoryChangesW + USN 증분 보강
2. 상태 저장: 파일 fingerprint + 스캔 이력 + 결과 digest
3. 추출: 핵심 내장 추출기(텍스트/OOXML) 우선, IFilter/PDF는 옵션(격리+타임아웃 전제)
4. 정규화/청크: 오프셋 매핑 포함
5. 룰 엔진: safe regex + 컨텍스트 룰 + validator 연결
6. 검증기: Luhn, RRN, BRN, phone prefix/length 등
7. 스코어링: 타입별 threshold + 등급(H/M/L)
8. NER: ONNX Runtime + INT8 + windowing + cache + sampling
9. 결과 통합: merge/dedup + 파일 risk 산정
10. 보고: 마스킹/해시 + 재시도/배치 + 개인정보 최소화
11. 정책 배포: 서명/버전/롤백 + 정적 룰 검사
12. 평가: 오프라인 지표 + 회귀 + 온라인 카나리
