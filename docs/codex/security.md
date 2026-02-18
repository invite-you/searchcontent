# PII Scanner 보안(Security) & 라이선스(Licensing) 상세 설계 (Draft)

작성일: 2026-02-09  
역할: Teammate 2 (Security Engineer)  
대상: Windows PC Client Agent + Server (Multi-tenant SaaS/On-Prem 모두 고려)  

## 1. 목표(Goals)

본 문서는 Windows PC에서 파일 내 개인정보(PII)를 탐지하여 서버로 보고하는 솔루션에 대해, “실제 구현 가능한” 보안(Security)과 라이선스(Licensing) 체계의 상세 설계를 정의한다.

핵심 목표:
- 전송/저장/접근 과정에서 개인정보(PII) 노출 리스크를 최소화
- 수만 대 단말 규모에서 인증/키관리/운영이 가능한 통신 보안 체계 제공
- 크랙(Reverse Engineering/Crack) 내성을 “현실적으로” 확보: 클라이언트 단독 방어가 아니라 서버 측 집행(Enforcement)으로 수익 모델 방어
- 안전한 자동 업데이트(Secure Auto Update)로 공급망(Supply Chain) 공격에 대한 방어
- 한국 개인정보보호법(PIPA) 관점에서 설계 원칙을 제품 기능으로 구체화

## 2. 원칙(Principles)

P1. 최소 수집(Data Minimization) 우선:
- 기본값(Default)으로 원문 PII를 서버로 전송하지 않는다.
- 업무 필요 시에만(옵션) 증거(Evidence)를 제한적으로 수집하며, 강력한 접근통제와 감사로그(Audit Log)를 전제로 한다.

P2. 제로 트러스트(Zero Trust) 전제:
- 클라이언트 단말은 “침해될 수 있다”고 가정한다.
- 따라서 비밀(Secret)과 집행(Enforcement)은 가능한 서버에 둔다.

P3. 공개키 기반(Public-Key) 설계:
- 클라이언트에는 공개키(Public Key)만 상주시켜 위변조 방지를 “서명 검증(Signature Verification)”으로 구현한다.
- 공유 비밀(Shared Secret) 기반 라이선스는 리버싱에 취약하므로 피한다.

P4. 방어 심층(Defense in Depth):
- mTLS(mutual TLS) + 요청 재전송/리플레이 방지(Anti-replay) + 서버 측 권한검사(AuthZ) + 감사로그를 조합한다.
- 난독화(Obfuscation)는 보조 수단으로만 사용한다.

P5. 운영 가능성(Operability):
- 수만 대 규모에서 인증서 발급/회수/갱신이 자동화되어야 한다.
- 키 회전(Key Rotation)과 사고 대응(Incident Response)이 절차로 구현되어야 한다.

## 3. 위협 모델(Threat Model)

### 3.1 공격자(Attackers)

- A1. 외부 공격자(External Attacker): 네트워크 도청/중간자(MITM), 서버 API 악용, 계정 탈취 시도
- A2. 악성 내부자(Malicious Insider): 테넌트 관리자/운영자 권한을 악용해 PII 접근 또는 설정 변경
- A3. 침해된 단말(Compromised Endpoint): 로컬 관리자 권한 획득, 프로세스 메모리 덤프, 파일/설정 변조, 트래픽 재전송
- A4. 경쟁사/크래커(Reverser/Cracker): 바이너리 리버싱, 라이선스 우회 패치, 모델/룰 추출
- A5. 공급망 공격자(Supply Chain Attacker): 업데이트 채널/빌드 파이프라인/서명 키를 노림

### 3.2 보호 자산(Assets)

- S1. 탐지 결과(Findings): PII 유형, 위치(파일/경로), 스코어, 증거(옵션)
- S2. 원문 PII(원문/스니펫): 가장 민감(Highest Sensitivity)
- S3. 단말 인증 자격(Identity Material): mTLS 클라이언트 인증서/개인키, 디바이스 식별자(Device ID)
- S4. 라이선스 집행 자격(License Material): 라이선스 리스(Lease) 토큰, 기능 플래그(Feature Flags)
- S5. 업데이트/릴리즈 무결성(Release Integrity): 업데이트 매니페스트(Manifest), 바이너리 서명 키(Code Signing Key)
- S6. 서버 데이터/키(Key Material): KMS/HSM 키, DB 데이터, 감사로그

### 3.3 신뢰경계(Trust Boundaries)

TB1. 엔드포인트(Endpoint) 경계:
- 사용자 PC는 신뢰할 수 없다(관리자 권한 탈취/악성코드/EDR 우회 가능).
- 로컬 저장소는 “유출될 수 있음”을 전제로 암호화(At Rest Encryption) 및 최소 저장을 적용한다.

TB2. 네트워크(Network) 경계:
- 사내망/인터넷/프록시 환경 모두에서 MITM 가능성을 가정한다.
- 전송 보안(Encryption in Transit)은 TLS 1.3 + 서버 인증 + 클라이언트 인증(mTLS)으로 강제한다.

TB3. 서버/클라우드(Server) 경계:
- 서버는 신뢰 대상이지만, 내부자/취약점으로 침해될 수 있다.
- “테넌트 간 격리(Tenant Isolation)”, “키관리 분리(Key Separation)”, “감사(Audit)”를 필수로 한다.

TB4. 관리 콘솔(Admin Console) 경계:
- 인적 계정(Human Identity)은 탈취될 수 있다.
- MFA, 최소권한(RBAC), 감사로그, 위험행동 탐지를 적용한다.

### 3.4 주요 위협(대표 시나리오)

- T1. MITM/프록시에서 트래픽 도청 및 변조
- T2. 침해된 단말에서 결과 위조/재전송(Replay)로 서버 데이터 오염 또는 과금/라이선스 우회
- T3. 라이선스 크랙: 오프라인에서 무제한 사용, 유효기간 우회, 좌석(Seat) 제한 우회
- T4. 업데이트 채널 하이재킹으로 악성 바이너리 배포
- T5. 서버/관리자 권한 남용으로 원문 PII 대량 열람/유출

## 4. 프로토콜 및 통신 보안(Client-Server Security)

### 4.1 결정: mTLS(mutual TLS) 기반 단말 인증 + TLS 1.3 강제

- 위협/가정: T1(MITM), T2(침해 단말의 위조), A1~A3
- 결정:
  - 모든 API 통신은 TLS 1.3을 사용한다.
  - 단말은 mTLS로 인증한다(클라이언트 인증서(Client Certificate) 기반).
  - 서버는 테넌트/디바이스 식별을 클라이언트 인증서의 SAN(Subject Alternative Name) 또는 커스텀 확장에 포함된 `tenant_id`, `device_id`로 수행한다.
- 근거:
  - 패스워드/토큰만으로는 단말 위장(Impersonation) 방어가 약하다.
  - 수만 대 규모에서 “디바이스 정체성(Device Identity)”을 가장 운영 가능하게 제공하는 방식이 PKI 기반 mTLS이다.
  - TLS 1.3은 최신 보안 표준이며 다운그레이드/취약한 암호군을 줄인다.
- 트레이드오프:
  - 기업 프록시/SSL Inspection 환경에서 연결 문제가 생길 수 있다.
  - PKI 운영(발급/회수/갱신/키보관) 비용이 든다.
  - 대응: “프록시 CONNECT 통과”를 지원하고, 고객사 네트워크에서 서버 도메인 allowlist 가이드를 제공한다.

### 4.2 PKI/인증서(Certificate) 수명주기

#### 4.2.1 인증서 유형

- Device Client Certificate (X.509):
  - 용도(EKU): Client Authentication
  - 키 알고리즘(Key Algorithm): ECDSA P-256 권장(성능/보안 균형)
  - 만료(Validity): 90일 권장(오프라인/운영 균형)
  - 저장(Store): Windows CNG Key Storage + LocalMachine Certificate Store
- Server Certificate:
  - 공용 CA(Public CA) 또는 고객사 환경에 따른 사설 CA(Private CA)
  - 서버 인증(Server Authentication)

#### 4.2.2 발급(Enrollment) 플로우

목표: “설치 직후 자동”으로 디바이스 인증서를 발급하고, 이후 모든 통신을 mTLS로 전환한다.

사전 조건(Provisioning):
- Bootstrap Token(Enrollment Token): 단말 배포 채널(MDM/Intune, GPO, 소프트웨어 배포 시스템)에 의해 안전하게 전달
- Token 특성:
  - 짧은 TTL(Time-to-live): 예) 24시간
  - Scope 제한: enroll 전용, 특정 tenant에만 유효
  - 사용 횟수 제한(Replay 저감): 예) 1회 또는 N회

Enrollment 단계:
1. 단말에서 키쌍(Key Pair) 생성:
   - 가능하면 TPM 기반(Non-exportable key) 사용
   - TPM 미지원 시 Windows Software KSP + DPAPI 보호
2. CSR(Certificate Signing Request) 생성:
   - `tenant_id`, `device_id`를 SAN URI 형태로 포함 권장
3. `POST /v1/device/enroll` 호출:
   - 서버 인증만 적용(이 시점에는 mTLS 불가)
   - Bootstrap Token으로 인증(AuthN)
4. 서버는 Token 검증 + 정책 확인 후 클라이언트 인증서 발급:
   - 발급된 인증서 + 체인(chain) 반환
5. 이후 모든 API는 mTLS로 접속:
   - `device_id`는 인증서 기반으로 확정(신뢰원천, Source of Truth)

근거/트레이드오프:
- 위협/가정: A1이 네트워크에서 Token 탈취 가능
- 대응:
  - Token은 짧은 TTL + 1회성(또는 제한) + 테넌트 스코프
  - Token 유출 시 피해 범위를 “일시적”으로 제한

#### 4.2.3 회수/폐기(Revocation) 및 갱신(Renewal)

- 갱신: 만료 14일 전부터 자동 갱신 시도(백오프 포함)
- 회수:
  - 서버에서 Device 상태를 `revoked`로 표시하면, 해당 인증서의 요청은 즉시 거부
  - CRL/OCSP는 “필수”가 아니라 “보조”로 취급:
    - 이유: 단말/서버 환경에서 CRL 배포/OCSP 조회는 운영 부담이 큼
    - 대신: 짧은 인증서 수명(예: 90일) + 서버 측 차단으로 실효성 확보

### 4.3 인증/인가(AuthN/AuthZ)

#### 4.3.1 단말(Device) AuthN

- AuthN 수단: mTLS 클라이언트 인증서
- 서버는 인증서에서 `tenant_id`, `device_id`를 추출해 요청 컨텍스트(Context)에 주입한다.

결정 근거:
- 위협/가정: 토큰 기반은 탈취/재사용 위험이 크다(A1).
- 트레이드오프: 인증서 운영 부담 증가. 하지만 수만 대에서 가장 표준적이며 자동화 가능.

#### 4.3.2 단말(Device) AuthZ

- 원칙: “자기 자신 리소스만(Self-Only)” 접근
- 예:
  - `/v1/device/{device_id}/report`는 인증서의 `device_id`와 URL 파라미터가 일치할 때만 허용
  - 테넌트 경계(Tenant Boundary)는 모든 API에서 강제

#### 4.3.3 관리자(Admin) AuthN/AuthZ

- AuthN: OIDC(OpenID Connect) / SSO(SAML 연계 가능), MFA 필수 권장
- AuthZ: RBAC(Role-Based Access Control) + 테넌트 스코프
- 권한 분리(Separation of Duties) 기본 제공:
  - Security Admin: 정책/권한/키 설정
  - Operations Admin: 단말 관리/배포
  - Auditor: 읽기 전용 + 로그 열람

### 4.4 재전송/리플레이 방지(Anti-replay) 및 무결성

결정: TLS 외에 “애플리케이션 레벨”의 재전송/중복 방지 장치를 둔다.

- 위협/가정: A3(침해 단말) 또는 네트워크 재전송으로 동일 보고가 반복되어 서버 데이터가 오염(T2)
- 설계:
  - 모든 요청에 `request_id`(UUID) 포함
  - 보고(Report)에는 `device_seq`(단말 단조 증가 시퀀스) 포함
  - 서버는 `(device_id, request_id)`를 TTL 캐시(예: 7일)로 저장해 중복을 거부
  - 서버는 `device_seq`가 이전 값 이하이면 기본 거부(단, 재시도/순서 뒤바뀜을 고려해 `request_id` 기반의 idempotency를 우선)

트레이드오프:
- 서버에 캐시/저장 비용 발생
- 하지만 “오프라인 큐/재시도”가 존재하는 에이전트에서 필수적인 안정성/보안 장치

### 4.5 키관리(Key Management)

#### 4.5.1 클라이언트 측 키 저장

결정: 개인키(Private Key)는 가능하면 TPM Non-exportable로 생성/보관한다.

- 근거:
  - 디바이스 바인딩(Device Binding)과 자격증명 탈취 저감에 가장 효과적
- 구현:
  - TPM 가능: CNG KSP(Platform Crypto Provider)로 ECDSA 키 생성, export 금지
  - TPM 불가: Software KSP + DPAPI(Windows Data Protection API)로 키/토큰/설정 보호

트레이드오프:
- TPM 미탑재/비활성 환경에서 보안 강도가 낮아짐
- 대응: 라이선스/토큰은 “추가 바인딩(하드웨어 핑거프린트)”를 병행하고, 서버에서 이상 징후 탐지

#### 4.5.2 서버 측 키 보호

- 저장: HSM(Hardware Security Module) 또는 KMS(Key Management Service) 사용 권장
- 키 분리:
  - K1. Device CA(단말 인증서 발급용)
  - K2. License Signing Key(라이선스 리스 서명용)
  - K3. Update Metadata Signing Key(업데이트 매니페스트 서명용)
  - K4. Data Encryption Keys(테넌트 데이터 암호화용, Envelope Encryption)
- 회전(Rotation):
  - 서명 키는 `kid`(Key ID) 기반 다중 키 동시 허용(Overlap)으로 무중단 회전

## 5. 라이선스 시스템(Licensing) 설계

### 5.1 목표 및 위협

목표:
- 구독형(Subscription) 모델에서 좌석/기능/기간을 서버 중심으로 집행(Enforcement)
- 오프라인에서도 일정 기간 동작(Offline Grace) 제공
- 크랙 내성: “서명 기반 토큰 + 서버 집행”으로 우회 난이도를 상승

대표 위협:
- L1. 바이너리 패치로 만료/좌석 제한 우회
- L2. 토큰 복사로 다른 PC에서 재사용(Cloning)
- L3. 시간 조작(Time Tampering)으로 오프라인 유효기간 우회

### 5.2 결정: “서명된 라이선스 리스( Signed License Lease )” + 서버 측 집행(Enforcement)

- 위협/가정: 클라이언트는 패치될 수 있음(A3, A4)
- 결정:
  - 서버는 단말에 “짧은 수명의 라이선스 리스(Lease)”를 발급한다.
  - 리스는 비대칭 서명(Asymmetric Signature)으로 보호되고, 클라이언트는 공개키로만 검증한다.
  - 서버는 모든 주요 API에서 구독 상태를 재검증하고, 미라이선스 단말의 보고/업데이트/정책수신을 차단한다.
- 근거:
  - 공유 비밀(Shared Secret) 기반 라이선스는 리버싱 후 위조가 가능하다.
  - 서명(Signature)은 “위조 방지”를 제공하고, 키가 유출되지 않는 한 임의 발급이 불가능하다.
  - 서버 집행은 클라이언트 패치 우회를 “기능적으로 무력화”한다(콘솔/업데이트/보고 불가).
- 트레이드오프:
  - 오프라인 환경에서 서버 집행이 불가하므로 리스 기반의 그레이스 설계가 필요
  - 이에 따라 오프라인 사용 기간이 길수록 크랙 우회 여지가 증가

### 5.3 데이터 모델(서버)

- Tenant Subscription:
  - `tenant_id`
  - `plan_id`
  - `starts_at`, `ends_at`
  - `seat_limit`
  - `features`(예: realtime, incremental, evidence_upload)
  - `offline_grace_days`(상한: 예 30일)
- Device Registry:
  - `device_id`
  - `tenant_id`
  - `cert_fingerprint`(mTLS cert thumbprint)
  - `hw_fingerprint`(선택, 해시)
  - `status`(active, revoked, quarantined)
  - `last_checkin_at`

### 5.4 라이선스 리스(Lease) 포맷(예시)

결정: JSON Canonicalization(정렬/고정 인코딩) + 서명(Detached Signature) 방식.

예시(개념):
```json
{
  "kid": "licsign-2026-01",
  "tenant_id": "t_123",
  "device_id": "d_abc",
  "entitlements": {
    "realtime": true,
    "incremental": true,
    "evidence_upload": false
  },
  "issued_at": "2026-02-09T00:00:00Z",
  "checkin_deadline": "2026-02-16T00:00:00Z",
  "hard_deadline": "2026-02-23T00:00:00Z",
  "bind": {
    "cert_pubkey_sha256": "BASE64URL(...)",
    "hw_fingerprint_sha256": "BASE64URL(...)"
  }
}
```

서명:
- `sig = Sign(license_signing_private_key, SHA-256(canonical_json))`
- 클라이언트는 내장된 `license_signing_public_keys[kid]`로 검증

근거/트레이드오프:
- 위협/가정: L1(위조 토큰)
- 서명 기반으로 위조 불가
- 트레이드오프: 클라이언트 패치로 “검증 스킵”은 가능
- 대응: 서버 집행으로 제품 가치를 구성하는 기능(콘솔/보고/업데이트)을 서버에서 차단

### 5.5 오프라인 그레이스(Offline Grace)

결정:
- 리스는 “짧은 체크인 기한(checkin_deadline)”과 “긴 하드 데드라인(hard_deadline)”을 함께 포함한다.
- 체크인 기한 경과 시: 제한 모드(Degraded Mode)
- 하드 데드라인 경과 시: 차단 모드(Blocked Mode)

제한 모드(예):
- 탐지는 계속하되, 서버 업로드/정책 수신을 중지하고 로컬 큐에만 저장(로컬 큐는 암호화)
- 사용자 방해 최소화를 위해 팝업은 최소화(관리 콘솔에만 경고)

차단 모드(예):
- 신규 탐지 실행 중지 또는 탐지 기능을 최소 기능(예: 파일 감시 중지)으로 축소
- 단, 고객사 업무 영향이 큰 경우 “정책 기반 예외”를 제공할 수 있으나, 기본값은 차단

근거/트레이드오프:
- 위협/가정: L2/L3(오프라인 장기 사용, 시간 조작)
- 오프라인 허용 기간을 명시하고 상한을 둬 수익 모델 방어
- 트레이드오프: 폐쇄망/장기 오프라인 고객에서 운영 이슈
- 대응: 계약/정책에서 최대 오프라인 기간을 명확히 하고, 예외는 서버에서 서명된 정책으로만 허용

### 5.6 디바이스 바인딩(Device Binding)

결정: “mTLS 개인키”를 1차 바인딩으로 사용하고, 하드웨어 핑거프린트(HW Fingerprint)를 2차로 사용한다.

- 1차 바인딩: `cert_pubkey_sha256`
  - TPM Non-exportable 키면 복제가 사실상 어려움
- 2차 바인딩: `hw_fingerprint_sha256`
  - 예: Windows Machine GUID, BIOS UUID, TPM EKPub hash 등(가용한 항목 중 선택)
  - 수집 시 원문을 저장하지 않고 해시로만 저장(Privacy)

근거/트레이드오프:
- 위협/가정: L2(클론), A4(라이선스 토큰 복사)
- 트레이드오프: HW 변경(메인보드 교체 등) 시 오탐(재등록 필요)
- 대응: “허용 가능한 변경” 정책(예: N개 중 M개 일치)을 서버 정책으로 구성하고, 콘솔에서 재바인딩 절차 제공

### 5.7 서버 측 집행(Enforcement) 포인트

필수 집행:
- 보고 수신(Report Ingest): 미라이선스 단말 거부
- 정책 배포(Policy Fetch): 미라이선스 단말 거부 또는 최소 정책만 제공
- 업데이트 다운로드(Update Download): 미라이선스 단말 거부
- 인증서 갱신(Cert Renew): 미라이선스 단말 거부(단, 갱신을 막으면 복구가 어려울 수 있으므로 “단계적 차단” 권장)

단계적 차단 권장:
- 1단계: 보고/업데이트 차단
- 2단계: 정책 수신 차단
- 3단계: 인증서 갱신 차단(마지막 수단)

근거:
- 침해 단말/패치 단말도 “서버 기능”을 못 쓰면 상용 가치가 급감한다.

## 6. 바이너리 보호 및 리버싱 대응(Binary Protection / Anti-Reversing)

### 6.1 결정: 코드서명(Code Signing) 필수 + 설치/업데이트 시 서명 검증

- 위협/가정: T4(업데이트 하이재킹), A5(공급망), A4(변조 배포)
- 결정:
  - 모든 배포 바이너리는 Authenticode(Code Signing)로 서명한다.
  - 업데이트는 “코드서명 + 매니페스트 서명” 이중 검증을 통과해야 설치한다.
- 근거:
  - Windows 생태계에서 배포 무결성의 표준
  - 고객사 보안 정책(실행 파일 신뢰)과 EDR 연동에 유리
- 트레이드오프:
  - 서명 키 보호(특히 EV 코드서명)와 운영 비용 증가
  - 대응: 서명 키는 HSM/KMS에 보관하고, CI에서 직접 키 파일을 다루지 않는 “서명 서비스(Signing Service)” 형태 권장

### 6.2 난독화(Obfuscation)의 한계와 현실적 대응

현실:
- 로컬 관리자/커널 권한을 가진 공격자는 결국 디버깅/패치/메모리 덤프가 가능하다.
- 과도한 안티디버그(Anti-debug)는 호환성/오탐(보안 제품 탐지) 문제를 유발한다.

결정: 난독화는 “지연(Delay)” 목적에 한정하고, 핵심은 서버 집행으로 둔다.

현실적 대응(우선순위):
- R1. 클라이언트에 비밀(Secret) 최소화: 공유 비밀 기반 라이선스 금지, 공개키 검증만
- R2. 모델/룰 파일 무결성: 서명된 아티팩트(artifact)만 로드
- R3. 릴리즈 식별: 빌드 ID + 해시를 서버에 등록, 비정상 버전은 서버에서 제한
- R4. 기초 하드닝: 심볼 제거(Strip), 디버그 로그에서 PII 제거

선택(고객 환경/요구 시):
- R5. 경량 안티탬퍼(Anti-tamper): 실행 시 핵심 파일 해시 검증, 프로세스 인젝션 탐지(기본 제공은 보수적으로)
- R6. 모델 파일 암호화: 라이선스 리스에 포함된 키(또는 디바이스 공개키로 래핑된 키)로 복호화

트레이드오프:
- R5/R6는 “우회 가능”하지만 크랙 난이도 상승에 기여
- 대신 안정성과 운영 편의가 떨어질 수 있으므로 옵션화 권장

## 7. 탐지 결과(PII) 보호 설계(Data Protection)

### 7.1 데이터 분류(Data Classification)

D0. Telemetry(비식별 운영 데이터):
- 성능 지표, 스캔 상태, 에러 코드

D1. Findings(탐지 결과, 최소 정보):
- 파일 식별자, PII 유형, 토큰(Token), 마스킹된 프리뷰(Masked Preview), 신뢰도(Score)

D2. Evidence(증거, 옵션):
- 제한 길이 스니펫, 문맥 일부(최대 N bytes), 원문 가능(정책에 따라)

### 7.2 결정: 기본값은 “원문 미전송” + 토큰화(Tokenization) (상관분석은 옵션)

- 위협/가정: T5(서버/관리자에 의한 과도한 열람), 데이터 유출 사고
- 결정:
  - 서버로 전송되는 기본 결과는 D1까지만 포함한다.
  - 원문 PII는 토큰(Token)으로 치환한다(결정적 토큰화, Deterministic Tokenization).
  - 기본 토큰은 “디바이스 스코프(device-scoped)”로 생성한다(MVP 기본값). 테넌트 스코프(tenant-scoped) 토큰(교차 디바이스 상관분석)은 옵션으로 제공한다.
  - 증거(Evidence, D2)는 테넌트 정책으로 명시적으로 활성화될 때만 전송한다.
- 근거:
  - PII의 원문을 보관/전송하지 않으면 유출 시 피해 규모가 현저히 줄어든다.
  - 결정적 토큰화는 “동일 PII 재등장” 추적, 중복 제거, 통계에 유용하다.
  - 다만 테넌트 스코프 토큰은 “한 대의 침해 단말에서 키가 유출될 경우(또는 서버 DB 유출과 결합될 경우) 상관분석 범위가 커질 수 있음”을 인정하고 옵션으로 분리한다.
- 트레이드오프:
  - 관리자가 원문 확인 없이 대응이 어려울 수 있다.
  - 대응: 증거 업로드는 옵션으로 제공하고, 강력한 RBAC/감사로그/보관기간 제한을 전제로 한다.

### 7.3 토큰화(Tokenization) 및 마스킹(Masking)

#### 7.3.1 토큰화 알고리즘(권장)

권장 구현은 2단계로 나눈다.

- 모드 A(기본, MVP): 디바이스 스코프 토큰(device-scoped token)
  - `device_token = Base64Url(HMAC-SHA256(device_token_key, normalize(pii_value)))`
  - `device_token_key`는 디바이스별로 생성하고 TPM/CNG 비내보내기(non-exportable) 키를 우선 사용한다(불가 시 DPAPI 보호).
  - 용도: “동일 디바이스 내” 중복 제거(dedup), 재보고 억제, 로컬/서버에서의 장기 저장 리스크 완화.
  - 근거: 디바이스 침해(A3)를 가정하면 원문 자체는 이미 노출 가능하므로, 우선순위는 “서버 대량 유출 시 피해 범위 축소”다. 디바이스 스코프는 교차 디바이스 상관분석을 포기하는 대신 키 유출의 외연을 줄인다.

- 모드 B(옵션): 테넌트 스코프 토큰(tenant-scoped token, 교차 디바이스 상관분석)
  - `tenant_token = Base64Url(HMAC-SHA256(tenant_token_key, normalize(pii_value)))`
  - `tenant_token_key`는 서버에서 생성/회전한다.
  - 단말 배포 방식은 2가지가 있다.
    - B1(현실적, 단기): `tenant_token_key`를 디바이스 공개키로 래핑(wrap)하여 배포. 단, 침해 단말에서 키가 유출될 수 있음을 인정하고 “상관분석 기능”을 보안 옵션으로 분리한다.
    - B2(권장, 장기): OPRF/VOPRF 같은 “서버 보조 토큰화(server-assisted tokenization)”로 단말에 `tenant_token_key`를 직접 배포하지 않는다.
  - 근거/트레이드오프:
    - 비밀키 없는 해시(SHA-256)는 주민번호/전화번호 등 구조적 PII에서 사전대입(Dictionary) 위험이 크다.
    - HMAC는 키 없이는 대규모 사전대입을 어렵게 하지만, 테넌트 키가 유출되면(단말 침해 + 서버 DB 유출 결합 시) 재식별 리스크가 커진다.

토큰 메타데이터(운영 필수)
- 모든 토큰에는 `token_kid`(키 식별자, key id)를 함께 저장해 키 회전(key rotation) 시 재토큰화(re-tokenization) 범위를 추적 가능하게 한다.

#### 7.3.2 마스킹 규칙(예)

- 주민등록번호(RRN): `******-*******` 또는 `******-1******`(정책에 따라)
- 전화번호(Phone): `***-****-1234`(끝 4자리만)
- 이메일(Email): `a***@domain.com`

### 7.4 파일 경로/파일명 보호(Path Protection)

결정: 고객 요구와 개인정보 리스크를 모두 고려해 2가지 모드를 제공한다.

- 모드 A(표준, Standard): 전체 경로 전송
  - 장점: 관리자가 즉시 조치 가능
  - 리스크: 경로에 사용자명 등 PII가 포함될 수 있음
  - 대응: 저장 암호화 + RBAC + 감사로그 + 마스킹 뷰 제공
- 모드 B(프라이버시, Privacy): 경로 토큰화(컴포넌트별 HMAC)
  - 장점: 서버에 경로 원문이 남지 않음
  - 트레이드오프: 관리 조치가 단말 측 확인 절차를 필요로 함

### 7.5 전송/저장 암호화(Encryption in Transit / at Rest)

전송(Transit):
- 모든 전송은 mTLS(TLS 1.3)로 암호화

클라이언트 저장(At Rest, Client):
- 로컬 큐/캐시/리스 토큰은 DPAPI(기기 범위, machine scope)로 암호화
- 가능하면 TPM 키로 추가 보호(키 export 금지)
- 로컬 로그는 PII를 포함하지 않도록 기본값에서 마스킹/토큰만 기록

서버 저장(At Rest, Server):
- DB/오브젝트 스토리지 모두 Envelope Encryption 적용
  - 테넌트별 DEK(Data Encryption Key) + KMS로 래핑(KEK)
  - 민감 컬럼(예: Evidence)은 애플리케이션 레벨 AES-256-GCM으로 추가 암호화
- 키 접근은 최소 서비스 계정(Least Privilege)만 허용

### 7.6 접근 통제(RBAC) 및 감사로그(Audit Log)

#### 7.6.1 RBAC(권장 역할)

- Tenant Owner: 결제/계약/테넌트 설정
- Security Admin: PII 정책, Evidence 활성화, 키/로그 설정
- Operator: 단말 등록/해제, 배포/업데이트 관리
- Analyst: Findings 조회(토큰/마스킹), 리포트 생성
- Auditor: 감사로그 열람 전용

결정 근거:
- 위협/가정: A2(내부자), 계정 탈취
- 최소권한 + 권한분리로 대량 열람/유출을 어렵게 한다.

#### 7.6.2 감사로그 설계

필수 이벤트:
- Findings/Evidence 조회, 다운로드/내보내기(Export)
- RBAC 변경, Evidence 정책 변경, 보관기간 변경
- 디바이스 등록/해제, 인증서 회수, 라이선스 상태 변경
- 키 회전/서명키 변경, 업데이트 키 변경

로그 특성:
- 변조 방지(Tamper-evident): 각 로그에 `prev_hash`를 포함한 해시 체인(Hash Chain)
- 저장 분리: 운영 DB와 분리된 스토리지(권한 분리)
- 보관기간(Retention): 테넌트 정책으로 설정(기본 1년 권장, 법무/고객 요구에 맞게 조정)

## 8. 업데이트/배포 보안(Secure Update & Distribution)

### 8.1 결정: “서명된 업데이트 매니페스트 + 코드서명된 바이너리” 이중 검증

- 위협/가정: T4(업데이트 하이재킹), A5(공급망)
- 결정:
  - 업데이트는 매니페스트(Manifest)를 통해 배포한다.
  - 매니페스트는 별도 서명키(Update Metadata Signing Key)로 서명한다.
  - 실제 설치 파일은 코드서명(Code Signing)되어야 한다.
  - 클라이언트는 1) 매니페스트 서명 검증 2) 파일 해시 검증 3) 코드서명 검증을 모두 통과해야만 설치한다.
- 근거:
  - 업데이트 서버가 침해되어도(또는 CDN 변조) 서명 없이는 악성 업데이트가 배포되지 않는다.
  - 코드서명은 Windows 실행 신뢰 체인과 연동된다.
- 트레이드오프:
  - 서명 키 운영이 복잡
  - 대응: 키 분리 + 오프라인 루트/온라인 서브키 구조로 운영

### 8.2 업데이트 매니페스트(예시)

```json
{
  "kid": "updmeta-2026-01",
  "channel": "stable",
  "version": "1.4.2",
  "published_at": "2026-02-09T00:00:00Z",
  "min_supported_version": "1.3.0",
  "artifacts": [
    {
      "os": "windows",
      "arch": "x86_64",
      "url": "https://updates.example.com/agent/1.4.2/agent.msi",
      "sha256": "HEX..."
    }
  ],
  "metadata_expiry": "2026-02-16T00:00:00Z"
}
```

추가 방어:
- 롤백 방지(Anti-rollback): 클라이언트는 설치된 최대 버전(max version)을 저장하고, `min_supported_version` 미만으로 다운그레이드 거부
- 단계적 배포(Staged Rollout): 테넌트/디바이스 그룹에 순차 배포(장애/침해 확산 방지)

### 8.3 업데이트 전송 채널

- 업데이트 다운로드도 mTLS로 보호(가능하면 동일 API 도메인)
- 라이선스 미유효 단말은 업데이트 다운로드 차단(Enforcement)

## 9. 운영(Operations)

### 9.1 보안 운영 체크리스트(구현 항목)

- 단말:
  - 개인키 Non-exportable 우선(TPM)
  - 로컬 큐/캐시/리스 토큰 DPAPI 암호화
  - 로컬 로그 PII 미기록(토큰/마스킹만)
  - 설정/모델/룰 파일 서명 검증
- 서버:
  - mTLS 강제, 인증서 기반 디바이스 식별
  - RBAC + MFA + 감사로그
  - KMS/HSM 기반 키보관, 키 분리 및 회전 절차
  - 테넌트 격리(최소한 논리적 격리: tenant_id 강제)
  - 알림/탐지:
    - 비정상 enroll 급증
    - 동일 디바이스에서 hw_fingerprint 급변
    - license lease 갱신 실패 급증

### 9.2 사고 대응(Incident Response) 시나리오

- 단말 침해 의심:
  - 디바이스 상태 `quarantined`로 전환
  - 보고/업데이트/정책 수신 차단 또는 제한
  - 클라이언트 인증서 회수(서버 차단)
- 서명 키/업데이트 키 침해 의심:
  - 즉시 키 회전(새 `kid`) 및 이전 키 폐기
  - 매니페스트 만료(expiry) 짧게 설정하여 빠른 무효화
  - 고객사 공지 및 강제 업데이트 정책 적용

## 10. 법적/규제 고려(PIPA 관점의 설계 반영)

주의: 아래는 법적 자문이 아니라 “제품 설계에 반영할 원칙”이다. 세부 요건은 법무/고객사 내부 규정 검토가 필요하다.

반영 원칙:
- 목적 제한(Purpose Limitation): “탐지/보호” 목적 외 사용 금지, 콘솔에 목적/근거 표시
- 최소 수집(Data Minimization): 기본값 원문 미전송, 증거 업로드는 명시적 옵션 + 최소 범위
- 접근통제(Access Control): 최소권한, 권한분리, MFA
- 접속기록(Access Log): PII 조회/다운로드 등 중요 행위는 상세 로그, 보관기간 정책화(기본 1년 권장)
- 암호화(Encryption): 전송/저장 암호화, 키관리 분리
- 보관기간(Retention) 및 파기(Deletion): 테넌트별 정책(기본값 제공) + 자동 파기 + 증빙 로그
- 위탁/제3자 제공: 멀티테넌트 서비스일 경우 위탁 관리 항목(로그, 접근권한, 키관리)을 운영 문서/계약에 반영

## 11. 리스크 및 잔여 위험(Residual Risks)과 대응

RISK-1. 침해된 단말에서 로컬 PII 유출:
- 한계: 단말이 침해되면 파일 원문은 공격자가 접근 가능
- 대응: 본 제품은 “서버로의 2차 유출”을 최소화(원문 미전송 기본), 로컬 캐시 최소화/암호화

RISK-2. 클라이언트 패치로 라이선스 검증 우회:
- 한계: 로컬에서 완벽 방지는 불가
- 대응: 서버 집행(보고/업데이트/콘솔 기능)으로 상용 가치 방어, 이상 징후 탐지로 대응

RISK-3. 시간 조작(Time Tampering)으로 오프라인 유효기간 우회:
- 대응:
  - 리스에 서버 시간 포함, 마지막 서버 시간(last_seen_server_time)을 DPAPI로 저장
  - 로컬 시간이 과거로 급격히 이동하면 제한 모드로 전환(오탐 가능성 있으므로 정책화)

RISK-4. 서명 키 침해(최대 리스크):
- 대응:
  - 키 분리(K1~K4) 및 HSM/KMS 보관
  - 서명 키 회전 절차/런북(Runbook) 사전 준비
  - 업데이트 매니페스트 만료(expiry)를 짧게 운영해 침해 확산 시간 단축

## 12. 구현 우선순위(MVP -> Hardened)

MVP(출시 필수):
- TLS 1.3 + mTLS 디바이스 인증
- Bootstrap enroll + 자동 인증서 갱신
- Signed License Lease + 서버 집행(보고/업데이트 차단)
- 기본값: 원문 미전송, 토큰화 + 마스킹
- RBAC + MFA + 감사로그(핵심 이벤트)
- 서명된 정책/룰/모델 번들(artifact) 검증 + 코드서명(Code Signing)된 에이전트 배포
  - 에이전트 “자동 업데이트(Updater)”는 MVP에서는 고객의 기존 배포 체계(MDM/SCCM/MSI)를 우선 활용하고, 제품 내 Updater는 Phase 2+로 둘 수 있다.

Hardened(2단계):
- TPM 우선 바인딩 강화 및 원격 증명(Remote Attestation) 검토
- 프라이버시 모드(경로 토큰화) 정식 지원
- 감사로그 WORM 저장소 연동 및 외부 SIEM 연동
- 모델 파일 암호화/서명 검증 강화
