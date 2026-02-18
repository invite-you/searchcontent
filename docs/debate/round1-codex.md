# Round 1 (Codex): Claude vs Gemini vs Codex 비교/비평 (구현 관점)

작성일: 2026-02-09  
비교 대상:
- Claude: `docs/claude/detection-engine.md`, `docs/claude/system-architecture.md`, `docs/claude/security.md`, `docs/claude/review.md`
- Gemini: `docs/gemini/detection-engine.md`, `docs/gemini/system-architecture.md`, `docs/gemini/security.md`, `docs/gemini/review.md`, `docs/gemini/ner-model-comparison.md`, `docs/gemini/rust-tech-research.md`, `docs/gemini/market-analysis.md`
- Codex(내 설계): `docs/codex/detection-engine.md`, `docs/codex/system-architecture.md`, `docs/codex/security.md`, `docs/codex/review.md`, `docs/codex/feasibility-review.md`, `docs/codex/project-structure.md`

목적: 7개 논점에 대해 **입장을 명확히** 하고, “문서상으로는 좋아 보이지만 실제 코드로 옮기면 깨지는 지점”을 중심으로 비평한다.

---

## 요약 (내 결론)

- NER은 넣되 **기본값은 보수적(베타 + 하드캡 + 엄격한 게이팅)** 이 맞다. “전 파일 NER”은 운영에서 터진다. (`docs/gemini/review.md`의 “AI on Endpoint” 경고가 유효)
- “실시간 100%”는 금지어다. **eventual consistency**를 제품 문구/SLO로 고정해야 한다. USN은 “보완”이 아니라 **신뢰성의 본체**다. (`docs/gemini/review.md`, `docs/claude/review.md`, `docs/codex/review.md`)
- mTLS는 이론적으로 가장 깔끔한 단말 ID지만, 5만 대에서 PKI 운영은 진짜 일이다. **핀닝(pinning)은 기본값에서 빼고**, 기업 프록시/TLS inspection 대응을 1급 설정으로 둬야 한다. (`docs/claude/security.md`의 pinning, `docs/codex/security.md`의 mTLS 선택은 “운영 런북”까지 포함돼야 성립)
- MVP는 “정형 PII + 증분 + 업무방해 방지 + 최소 서버/콘솔”로 수렴해야 한다. HWP/DRM/완전 실시간/자동 업데이트/고급 컴플라이언스는 분리하지 않으면 일정이 무너진다. (`docs/claude/review.md` MVP 축소 제안에 대체로 동의)
- 차별화는 “NER”이 아니라 **(1) 조용한 에이전트(가드레일/격리/복구), (2) 증분 백본(USN), (3) 안전한 룰 업데이트(서명/롤백), (4) 원문 미전송 기본값에서도 돌아가는 조치 UX**에 있다. (`docs/claude/review.md`의 차별점 재정의가 현실적)

---

## 논점 1: NER 모델 선택

### 입장 (Codex)
**기본 모델은 `KoELECTRA-Small(INT8)`로 고정**하고, `Base`는 “정밀 스캔(야간/유휴)” 옵션으로 둔다. NER은 MVP에서 **베타**이며, “확정 판정(Confirmed)”이 아니라 “점수 보정/승격 보조 신호”로 시작한다.

### Claude/Gemini/Codex 비교
- Claude: `KoELECTRA-Small v3 (INT8)`을 주력, `Base`를 정밀 스캔 옵션으로 제안. (`docs/claude/detection-engine.md`)
- Gemini: `KoELECTRA-Small` 주력, GPU 가능 시 `KLUE-RoBERTa-Base` 옵션까지 제안. (`docs/gemini/detection-engine.md`, `docs/gemini/ner-model-comparison.md`)
- Codex: 모델 선택 프레임을 제시하면서 초기 권장으로 “KoELECTRA-base 수준”을 적어뒀지만, MVP/엔드포인트 현실을 감안하면 **Small 기본이 더 안전**하다. (`docs/codex/detection-engine.md`)

### 구현에서 깨지는 지점 (이론 vs 코드)
- “벤치마크 F1”은 PII 성능이 아니다.
  - Claude가 제시한 F1(Naver NER/KLUE-NER)은 **일반 NER** 성능이고, PII에서 핵심인 hard negative(이상/박수/김밥 등)와 “라벨 없는 문서”에서의 FP/FN 비용 모델이 다르다. (`docs/claude/review.md` 지적이 타당)
- 추론 시간은 모델만의 문제가 아니라 **토크나이저가 병목**이 되기 쉽다.
  - Rust에서 HF tokenizer를 붙이면 문자열 정규화/분절/IDs 변환이 실제로 CPU를 꽤 먹는다. “모델 추론 10ms”라고 해도 end-to-end는 2~5배로 튀는 경우가 흔하다.
- INT8 양자화는 “0.5~1% F1 하락” 같은 평균치로 끝나지 않는다.
  - 엔티티 타입별로(특히 `PER`, `ADDR`) 민감하게 흔들리고, threshold를 같이 재캘리브레이션하지 않으면 FP가 늘 수 있다.
  - CPU ISA(AVX2/VNNI) 차이로 지연이 기기별로 크게 벌어진다. `i3/4GB` 같은 하한을 진짜로 맞추려면 “AI 예산(분당 최대 N회)”이 필요하다. (`docs/gemini/review.md`의 “AI Budget”이 실무적)
- “NER로 phone vs product code 구분”은 라벨 설계가 없으면 불가능하다.
  - Gemini 문서의 “Product Code/IP Address로 분류하면 discard”는 현재 제안된 NER 라벨(PER/LOC/ORG/TEL/ID)로는 구현 불가다. (`docs/gemini/detection-engine.md`)
  - 이건 NER이 아니라 별도의 **컨텍스트 분류기** 또는 규칙 엔진(negative context)로 풀어야 한다.
- Lazy load/unload는 thrashing 위험이 크다.
  - Claude의 “5분 미사용 시 언로드”는 실시간 이벤트가 잦은 환경에서 로드/언로드 반복으로 오히려 지연/메모리 파편화/캐시 미스가 늘 수 있다. (`docs/claude/detection-engine.md`, `docs/claude/review.md`)

### 결론/권장 결정
- MVP: `KoELECTRA-Small INT8` 단일 + “파일당 NER 호출 상한 K + 타임아웃 + 분당 AI 예산”을 하드코딩.
- Phase 2+: `Base`를 “스케줄(Idle) 정밀 모드”에서만 선택적으로 사용.
- NER 출력은 초기에는 “승격 보조 신호”로 두고, FP/FN 데이터가 쌓인 후에만 판정에 더 깊게 관여.

---

## 논점 2: 탐지 파이프라인 구조

### 입장 (Codex)
파이프라인은 “단계”보다 **가드레일/격리/백프레셔**가 제품 품질을 결정한다. 따라서 구조의 핵심은:
1) Cheap -> Expensive 강제, 2) 이벤트 폭주에도 안 죽는 큐/스케줄러, 3) 추출기/NER의 프로세스 격리, 4) USN 기반 증분 백본 + 워처는 제한된 경로만.

### Claude/Gemini/Codex 비교
- 공통: Regex/검증 -> (필요 시) NER의 funnel 구조는 3자 모두 동의. (`docs/claude/detection-engine.md`, `docs/gemini/detection-engine.md`, `docs/codex/detection-engine.md`)
- 차이: “무거운 단계(추출/NER)를 어디까지 MVP에 넣는가”와 “실시간 신뢰성의 정의”.
  - Claude는 포맷 커버리지가 넓고(EML/MSG/HWP/PDF 등), 실시간 파이프라인도 상세히 적어 “스코프 폭발” 위험이 크다. (`docs/claude/detection-engine.md`, `docs/claude/system-architecture.md`)
  - Gemini는 funnel 개념은 좋지만, “무슨 라벨로 어떤 결정을” 같은 구현 제약을 놓친 부분이 있다(위 논점 1의 라벨 문제).
  - Codex는 운영 정의(SLO/지원 매트릭스/하드캡)와 “오프셋/정규화 매핑” 같은 구현 난점을 더 강하게 전제했다. (`docs/codex/detection-engine.md`)

### 구현에서 깨지는 지점 (이론 vs 코드)
- 텍스트 추출은 파이프라인의 Stage 0이 아니라 “프로덕션 장애의 80%”다.
  - 파일 포맷 파서는 입력이 조금만 깨져도 hang/폭주/크래시가 난다. 특히 COM/IFilter/PDF/MSG/DRM은 더하다.
  - 해결은 “좋은 설계”가 아니라 **타임아웃 + 프로세스 격리 + Quarantine 큐**다. 문서에 이 3종 세트를 강제하지 않으면 현장에서는 반드시 죽는다. (`docs/codex/system-architecture.md`의 worker 격리, `docs/claude/system-architecture.md`의 NER/DRM 격리 제안은 방향이 맞음)
- ReadDirectoryChangesW는 이벤트를 놓친다.
  - 버퍼 오버플로, 네트워크 드라이브 제약, watch handle 한계 등은 구현하면 바로 만난다. “USN으로 보완”이 아니라 **USN catch-up이 본체**라는 운영 정의가 필요하다. (`docs/gemini/review.md`, `docs/claude/review.md`)
- 점수 가중치(x1.2, x0.5 등)는 “코드가 아닌 운영”이 필요하다.
  - Claude의 스코어링은 구체적이지만, 실제로는 타입별/고객사별로 튜닝이 필요해서 “고정 가중치”는 빠르게 무너진다.
  - 결국 필요한 건 “평가셋 + 회귀 테스트 + 카나리/롤백”이다. (`docs/codex/detection-engine.md`의 평가/롤백 전제)
- 화이트리스트/블랙리스트는 기능이 아니라 “정책 배포 시스템”이다.
  - 로컬 반영(즉시) + 전사 반영(승인/서명) + 롤백까지 이어지지 않으면, 고객은 “오탐 줄이려다 장애”를 경험한다. (`docs/claude/detection-engine.md`의 hot reload는 가능하지만, 안전장치가 빠지면 사고가 난다)
- 아카이브/ZIP은 zip bomb 대응이 없으면 치명적이다.
  - “zip 지원”은 한 줄로 끝나지 않는다: 재귀 깊이, 총 해제 용량, 파일 수, 타임아웃, 임시 디스크 공간, 권한, 경로 트래버설 등.

### 결론/권장 결정
- USN 기반 증분을 “신뢰성 백본”으로 문구/SLO에 박는다.
- 워처는 “핵심 폴더만” + 이벤트 폭주 시 “eventual mode로 자동 전환”.
- 추출/NER는 워커 프로세스에서만 실행 + 하드 타임아웃 + Quarantine(반복 실패 파일).
- 정책/룰 업데이트는 반드시 서명 + 카나리 + 롤백을 붙인다(“hot reload”만으로는 부족).

---

## 논점 3: 기술 스택 (Rust vs 대안)

### 입장 (Codex)
클라이언트 에이전트는 Rust가 장점이 크지만, **팀 숙련도가 낮으면 MVP 속도가 크게 떨어진다.** “Rust 고집”이 목적이 되면 실패한다.

### Claude/Gemini/Codex 비교
- Claude/Gemini: 클라이언트 Rust 선호, 서버는 Go, UI는 React 계열. (`docs/claude/system-architecture.md`, `docs/gemini/system-architecture.md`)
- Codex: Rust 유지하되 “무거운 의존을 crate/프로세스로 격리”, 팀이 .NET 강하면 C# MVP 후 병목만 Rust로 뽑는 하이브리드도 현실적. (`docs/codex/project-structure.md`, `docs/codex/feasibility-review.md`)

### 구현에서 깨지는 지점 (이론 vs 코드)
- Windows 서비스/업데이트/인스톨러/MSI/서명은 언어와 무관하게 “운영 기술”이다.
  - Rust로도 가능하지만 레퍼런스/라이브러리 갭이 있어 삽질 비용이 커질 수 있다.
- Rust에서 Windows API/COM/FFI(특히 DRM SDK, IFilter)는 난도가 급상승한다.
  - 크래시 격리/메모리 관리/ABI/스레딩 모델을 모두 직접 다뤄야 한다. 작은 팀에서 병목이 된다.
- 서버에 Kafka/Elasticsearch는 MVP에 과하다.
  - Gemini/Claude 아키텍처는 “50k 최종 형태”로는 의미가 있지만, MVP에서는 운영 복잡도를 먼저 올려 개발 속도를 죽일 수 있다. (`docs/gemini/system-architecture.md`, `docs/claude/system-architecture.md`)

### 결론/권장 결정
- 클라이언트는 Rust로 가되, “워크스페이스 분리 + 워커 프로세스 격리 + feature flag”로 속도와 안정성을 확보한다. (`docs/codex/project-structure.md` 방향)
- 서버는 팀 주력 스택(Go/.NET/Rust 중 택1)으로 **단순 모놀리스**부터 시작한다.
- 초기에는 Postgres 단일 + (필요 시) Redis 정도로 제한하고, 큐/검색 엔진은 Later로 미룬다.

---

## 논점 4: MVP 범위

### 입장 (Codex)
MVP는 “기술 데모”가 아니라 “파일럿 운영”이다. 따라서 MVP 범위는 기능보다 **안정성/가드레일/지원 매트릭스**가 우선이다.

### Claude/Gemini/Codex 비교
- Claude 리뷰: NER/실시간/HWP/복잡 보안은 MVP에서 과감히 빼고 정형+예약 스캔 중심으로 가야 한다. (`docs/claude/review.md`)
- Gemini: 기능 의지가 강하고(allowlist, zip, hwp 포함), 리뷰에서는 그 낙관을 강하게 비판한다. (`docs/gemini/detection-engine.md`, `docs/gemini/review.md`)
- Codex: “정형 + 증분 + 조용함 + 최소 서버”를 MVP로, NER은 베타로 제한. Updater도 Later. (`docs/codex/review.md`, `docs/codex/system-architecture.md`)

### 구현에서 깨지는 지점 (이론 vs 코드)
- “포맷 지원”을 MVP에 많이 넣으면 QA가 무한정 늘어난다.
  - HWP/MSG/PDF/DRM은 각각이 서브프로젝트다.
- “실시간”을 MVP에서 강하게 약속하면, 드롭 이벤트/락 파일/대용량 복사에서 바로 신뢰를 잃는다.
- “자동 업데이트”는 구현보다 운영이 어렵다(서명 키, 롤아웃, 롤백, 사고 대응 런북).

### 결론/권장 MVP (3~4개월 파일럿 기준)
- In:
  - 탐지: 정형 PII(주민/사업자/카드/이메일/전화) + checksum/형식 + 컨텍스트 룰 + allow/deny + dedup
  - 스캔: USN 기반 증분 + 핵심 폴더 한정 워처 + eventual SLO
  - 포맷: `txt/csv/log` + `docx/xlsx/pptx`(OOXML)만
  - 안정성: 워커 격리 + 하드 타임아웃 + Quarantine + Panic mode(안전 모드)
  - 서버: 디바이스 등록/헬스, 정책 배포(서명), 결과 수집(배치/압축), 최소 콘솔(목록/필터/조치 상태)
- Out(표시만):
  - DRM: “스캔 불가(UNSCANNABLE)” 분류/집계까지만
  - NER: 베타(옵션) + 하드캡(파일당 K) + 승격 보조 신호
- Out:
  - HWP/PDF/MSG/아카이브 심화/OCR
  - 자동 업데이트 전체(에이전트 바이너리)
  - 멀티테넌시 SaaS 완성형, Kafka/ES, 고급 컴플라이언스(정보주체 요청 API 등)

---

## 논점 5: 보안/라이선스 설계

### 입장 (Codex)
보안 설계는 “암호 알고리즘”보다 **운영 가능성**이 먼저다. MVP에서는 “최소 수집 + 서명된 아티팩트 + 서버 집행 기반 라이선스”를 우선하고, mTLS/핀닝/안티디버깅 같은 고난도/고운영 기능은 “고객 환경”을 보고 단계적으로 올린다.

### Claude/Gemini/Codex 비교
- mTLS:
  - Claude/Gemini/Codex 모두 mTLS를 선호. (`docs/claude/security.md`, `docs/gemini/security.md`, `docs/codex/security.md`)
  - Gemini 리뷰는 mTLS를 강하게 문제 삼고 JWT 기반 세션을 제안. (`docs/gemini/review.md`)
- Pinning:
  - Claude/Gemini는 pinning을 적극 언급. (`docs/claude/security.md`, `docs/gemini/security.md`)
  - Codex는 “기업 프록시/TLS inspection” 리스크를 더 강하게 전제. (`docs/codex/review.md`, `docs/codex/system-architecture.md`)
- 라이선스:
  - Claude/Gemini는 JWT 기반 라이선스 토큰/파일을 제시.
  - Codex는 “서명된 license lease + 서버 측 집행”을 명시. (`docs/codex/security.md`)

### 구현에서 깨지는 지점 (이론 vs 코드)
- Certificate pinning은 엔터프라이즈에서 “연결 불가”를 만든다.
  - TLS inspection(프록시) 환경에서 pinning은 정상 트래픽도 MITM으로 간주해 차단한다.
  - 제품이 “보안 때문에 안 됨”으로 비치면 도입이 막힌다. 기본값은 pinning OFF, 고객 옵션이 현실적이다.
- mTLS 5만 대 운영은 PKI “프로젝트”다.
  - 발급/갱신/회수 자동화, 오프라인 노트북(장기 미접속), 만료로 인한 브릭(brick) 복구 플로우가 문서에 없으면 실제 운영에서 터진다. (`docs/gemini/review.md`의 “50,000 Certificate Problem”은 과장 아니다)
  - Codex의 “짧은 수명 + 서버 차단(Revocation은 보조)”는 현실적이지만, 그만큼 “갱신 실패 시 복구”가 제품 기능이 돼야 한다.
- 타임스탬프 기반 anti-replay는 시계 틀어지면 장애를 만든다.
  - Claude의 ±30초 같은 정책은 NTP 미정렬 PC에서 바로 실패한다. (`docs/claude/security.md`, `docs/claude/review.md`)
  - 실무에서는 request_id/idempotency + device_seq가 더 안전하고 단순하다. (`docs/codex/security.md`)
- 하드웨어 핑거프린팅은 WMI 현실 때문에 오탐이 많다.
  - 메인보드/디스크 시리얼이 비어있거나 중복되는 PC가 생각보다 많다(가상화/벤더 구현/권한).
  - 퍼지 매칭은 “정당한 교체인데 차단”과 “복제인데 허용” 둘 다를 만든다. 결국 콘솔 재바인딩 UX가 필수다.
- “모델 파일 암호화/키 샤딩/anti-debug”는 지원 비용을 올린다.
  - 메모리 zeroize, mlock, honey-pot 오동작 등은 제품 지원/장애 분석을 어렵게 만든다.
  - 상용 제품에서 가장 위험한 건 “보안 기능이 원인인 장애”다. 옵션화가 맞다. (`docs/codex/security.md`의 난독화 절제 노선이 타당)
- “원문 미전송”을 하려면 경로/파일명도 민감해질 수 있다.
  - Claude는 파일명은 보내고 경로는 해시로 처리했는데, 파일명 자체가 민감한 고객이 있다. (`docs/claude/security.md`)
  - 해결: Path privacy mode(경로/파일명 토큰화), 또는 로컬에서만 노출되는 “증거 뷰어” UX.

### 결론/권장 결정
- MVP 보안:
  - TLS 1.3, 서버 인증, 결과 최소 수집(D1), 정책/룰 번들 서명 검증
  - anti-replay는 request_id/idempotency 중심
  - pinning은 기본 OFF(옵션)
- mTLS는 고객사 환경(프록시/폐쇄망) 확인 후 단계 도입:
  - 도입 시: Bootstrap token -> CSR -> 짧은 수명 cert(예: 90일) + 서버 denylist 기반 차단
  - CRL/OCSP는 “필수”로 약속하지 않는다
- 라이선스:
  - “서명된 lease + 서버 집행”을 기본으로 두고, 오프라인은 grace(제한 모드)로 커버

---

## 논점 6: 현실적 구현 가능성 (팀 규모, 기간)

### 입장 (Codex)
3~5명 팀이 3~4개월에 “상용급”은 불가능하다. 3~4개월의 정의는 **파일럿 운영 가능(MVP)** 이어야 하고, 그 조건은 “스코프 축소 + 위험 영역 격리 + 측정/롤백”이다.

### Claude/Gemini/Codex 비교
- Claude 리뷰: 현 설계 전체는 2년+로 봐야 한다(스택 폭, HWP/DRM/보안/업데이트/대시보드). (`docs/claude/review.md`)
- Gemini 리뷰: NER 성능을 즉시 프로토타이핑해서 전략을 검증하라고 강하게 권고. (`docs/gemini/review.md`)
- Codex: Phase 0(2~4주)에서 정의/벤치/프로토를 끝내고, Phase 1 MVP(6~10주)로 파일럿 가치를 증명하는 로드맵. (`docs/codex/feasibility-review.md`)

### 구현에서 깨지는 지점 (이론 vs 코드)
- 가장 큰 일정 리스크는 “기술”이 아니라 “제품화 작업”이다.
  - MSI 배포, 서비스 복구, 로그/진단, AV/EDR 오탐 대응, 정책 배포 실패 복구, 고객 네트워크 프록시, 권한 이슈 등.
- 작은 팀은 “넓은 스택”에서 무너진다.
  - Rust+Go+React+ML+PKI+MSI+WinAPI를 동시에 제대로 하려면, 범위를 줄이지 않으면 품질이 희생된다.

### 결론/권장 일정 운영
- Phase 0(2~4주): “i3/4GB” 타겟에서 추출/규칙/NER(하드캡) 벤치 + USN 증분 POC + 이벤트 폭주 시나리오(압축/빌드/복사) 재현.
- Phase 1(6~10주): 포맷 제한 MVP + 정책/결과 수집 + 최소 콘솔 + 가드레일/격리/복구.
- Phase 2(8~12주): 실시간 범위 확대, NER 베타 확장, 파일럿 고객 데이터 기반 튜닝 루프.

---

## 논점 7: 경쟁 차별화 전략

### 입장 (Codex)
차별점은 “NER 최고 성능”이 아니라 “운영 가능한 엔드포인트 제품”이다. 특히 한국 시장(파수/소만사 등)에서 후발이 NER로만 이기는 건 어렵다. 차별화는 다음 4개에 집중해야 한다.

1) **Quiet by Design**: 워커 격리 + CPU/IO 가드레일 + Panic mode  
2) **Incremental First**: USN 기반 증분 백본 + eventual consistency SLO  
3) **Safe Change Management**: 서명된 룰/모델 번들 + 카나리 + 자동 롤백  
4) **Privacy by Default with Usable Remediation**: 원문 미전송 기본값에서도 조치 가능한 UX/워크플로우

### Claude/Gemini/Codex 비교
- Claude 리뷰: “NER 차별화”는 이미 경쟁사가 앞서며, 경량 에이전트/프라이버시 설계가 더 현실적 차별점. (`docs/claude/review.md`)
- Gemini 시장 분석: Rust+AI가 강한 해자라고 주장하지만, 이는 경쟁사가 못 한다기보다 “제품화/운영”이 더 큰 장벽이다. (`docs/gemini/market-analysis.md`)
- Codex: 차별점을 “구현 결정” 수준(하드캡, USN, 서명 번들, 원문 미전송 기본값, fault isolation)으로 정의. (`docs/codex/review.md`)

### 구현에서 깨지는 지점 (이론 vs 코드)
- 원문을 안 보내면, 관리자 조치가 어려워져 “쓸모 없는 정확도”가 된다.
  - 결국 파일 단위 우선순위, 조치 상태 추적(open/ack/resolved), 로컬 증거 확인(선택) 같은 workflow가 MVP부터 있어야 한다.
- 룰/모델 업데이트가 안전하지 않으면, “오탐률 99% 감소” 같은 약속은 한 번의 업데이트로 무너진다.
  - 고객은 기능보다 “업데이트 후 장애가 없냐”를 본다.

### 결론/권장 포지셔닝
- 마케팅 문구: “완전 실시간/제로 오탐”을 약속하지 말고, “조용함/증분/프라이버시/운영 워크플로우”를 약속한다.
- NER은 “옵션/베타”로 시작해도 된다. 대신 “왜 탐지했는지(근거)”와 “어떻게 줄일지(정책/예외/롤백)”를 제품의 중심에 둔다.

---

## 추가 논점 A: 텍스트 추출(포맷) 지원은 ‘기능’이 아니라 ‘제품 리스크’

### 입장 (Codex)
포맷 커버리지는 로드맵으로 관리하고, MVP는 “내장 추출기로 안정적으로 커버 가능한 것”만 한다. HWP/MSG/PDF/DRM은 Phase 2+에서 “외부 워커/헬퍼 프로세스 + 타임아웃 + 샌드박스” 전제로 확장한다.

### 구현에서 깨지는 지점
- HWP: Rust 생태계 미성숙/엣지 케이스가 많다. (`docs/claude/review.md` 지적)
- MSG/MAPI: 파서 난도 높고 케이스가 방대하다.
- PDF: 텍스트 레이어 품질 편차가 심하고, 레이아웃/오프셋 이슈가 관리자 UX로 직결된다.
- DRM: SDK 연동은 계약/협업이 먼저다. 코드만으로 해결 안 된다.

---

## 추가 논점 B: “운영 안전장치”가 문서의 주인공이어야 한다

### 입장 (Codex)
50,000대 제품은 기능보다 “망가지지 않는 것”이 가치다. 따라서 아래는 설계 문서에 **명시적 결정**으로 박아야 한다.

- Panic mode: 크래시/오류율 임계치 초과 시 실시간 훅/AI 기능 비활성화 후 스케줄 모드로 강등 (`docs/gemini/review.md`와 같은 제안)
- Quarantine: 특정 파일/포맷이 반복 실패하면 자동 격리(재시도 지연)하고 관리자에게 “스캔 불가 사유”로 노출
- Support Matrix: NTFS/비-NTFS/네트워크/OneDrive 등 “지원/제한”을 계약 문구로도 일치시킴
- Rollout discipline: 룰/모델 업데이트는 카나리/롤백이 기본

