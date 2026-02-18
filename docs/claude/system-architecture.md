# PII Scanner 시스템 아키텍처 설계서

## 목차
1. [클라이언트 Agent 모듈 구조](#1-클라이언트-agent-모듈-구조)
2. [실시간 파일 감지](#2-실시간-파일-감지)
3. [리소스 관리](#3-리소스-관리-업무-방해-최소화)
4. [서버 아키텍처](#4-서버-아키텍처-수만-대-pc-관리)
5. [기술 스택 선택과 근거](#5-기술-스택-선택과-근거)
6. [텍스트 추출 전략](#6-텍스트-추출-전략)
7. [클라이언트-서버 통신 프로토콜](#7-클라이언트-서버-통신-프로토콜)

---

## 1. 클라이언트 Agent 모듈 구조

### 1.1 전체 아키텍처 개요

클라이언트 Agent는 **Windows 서비스(Windows Service)**로 동작하며, 단일 프로세스 내에서 멀티스레드로 실행된다. 각 모듈은 독립적인 비동기 태스크로 구동되며, 모듈 간 통신은 Tokio의 MPSC 채널(channel)을 통해 이루어진다.

```
┌─────────────────────────────────────────────────────────┐
│                   Windows Service Host                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │ File Watcher │  │   Scanner   │  │  Policy Manager │ │
│  │   Module     │→ │   Engine    │← │                 │ │
│  └─────────────┘  └──────┬──────┘  └────────┬────────┘ │
│                          │                   │          │
│  ┌─────────────┐  ┌──────▼──────┐  ┌────────▼────────┐ │
│  │  Resource    │  │  Result     │  │    Updater      │ │
│  │  Governor    │  │  Reporter   │  │                 │ │
│  └─────────────┘  └─────────────┘  └─────────────────┘ │
│                                                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │              Local State DB (SQLite)                 ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

### 1.2 프로세스 모델: 단일 프로세스 멀티스레드

**선택: 단일 프로세스, 멀티스레드 (async + thread pool 혼합)**

근거:
- **IPC 오버헤드 제거**: 멀티프로세스 대비 모듈 간 통신이 채널 기반으로 매우 빠름
- **메모리 효율**: 프로세스 간 메모리 복제 없이 `Arc<T>`로 공유 가능
- **배포 단순성**: 단일 바이너리로 설치/업데이트/관리가 용이
- **리소스 제어 용이**: 단일 프로세스에서 전체 CPU/메모리 사용량을 통합 관리

스레드 구조:
- **Main Thread**: Windows 서비스 라이프사이클 관리
- **Tokio Runtime (multi-thread)**: 비동기 I/O 작업 (파일 감시, 네트워크 통신, 정책 수신)
- **Blocking Thread Pool (rayon)**: CPU 집약 작업 (텍스트 추출, 정규식 매칭, NER 추론)

> **예외 격리**: NER 추론 모듈은 별도 자식 프로세스(child process)로 분리하는 것을 권장한다. ONNX Runtime의 메모리 누수나 비정상 종료가 메인 Agent를 크래시시키는 것을 방지하기 위함이다. 메인 프로세스와는 stdin/stdout 파이프 또는 로컬 소켓으로 통신한다.

### 1.3 핵심 모듈 상세

#### 1.3.1 File Watcher Module (파일 감시 모듈)
- 실시간 파일 생성/수정/삭제 이벤트 감지
- 이벤트 디바운싱 및 필터링 후 스캔 큐에 전달
- 상세 내용은 [2. 실시간 파일 감지](#2-실시간-파일-감지) 참조

#### 1.3.2 Scanner Engine (스캔 엔진)
- 스캔 큐에서 파일 경로를 수신하여 PII 탐지 수행
- 파이프라인: 텍스트 추출 → 정규식+체크섬 1차 탐지 → NER 2차 탐지(필요 시)
- 동시 스캔 파일 수는 Resource Governor의 지시에 따라 동적 조절
- 스캔 결과를 Result Reporter에 전달

#### 1.3.3 Policy Manager (정책 관리 모듈)
- 서버로부터 정책(스캔 대상 경로, 제외 경로, 스캔 스케줄, PII 유형별 민감도 등)을 수신
- 정책 변경 시 각 모듈에 새 정책 적용 (watch broadcast channel)
- 로컬 캐시에 정책 저장 (서버 연결 불가 시에도 마지막 정책으로 동작)

#### 1.3.4 Result Reporter (결과 리포터)
- 스캔 결과를 로컬 SQLite에 먼저 저장 (오프라인 내성)
- 배치로 서버에 전송 (5분 간격 또는 결과 100건 누적 시)
- 전송 실패 시 지수 백오프(exponential backoff)로 재시도
- 전송 완료된 결과는 로컬 DB에서 전송 완료 마킹

#### 1.3.5 Resource Governor (리소스 관리 모듈)
- 상세 내용은 [3. 리소스 관리](#3-리소스-관리-업무-방해-최소화) 참조
- 다른 모든 모듈에 리소스 예산(budget)을 공급하고 조절

#### 1.3.6 Updater (업데이트 모듈)
- 서버로부터 새 Agent 버전 알림 수신
- 다운로드 → 무결성 검증(SHA-256) → 코드 서명 검증 → 교체
- Windows 서비스 재시작을 통한 업데이트 적용
- 롤백 메커니즘: 업데이트 실패 시 이전 바이너리로 복원

#### 1.3.7 Local State DB (로컬 상태 DB)
- **SQLite** 사용 (단일 파일, 설치 불요, Rust에서 `rusqlite` 크레이트로 접근)
- 저장 항목:
  - 파일 인벤토리: 경로, 크기, 수정시각, 콘텐츠 해시
  - 미전송 스캔 결과 큐
  - 정책 캐시
  - 스캔 이력 (최근 N일)

### 1.4 모듈 간 통신

```
File Watcher ──[ScanRequest]──→ Scan Queue (bounded MPSC channel)
                                      │
Scanner Engine ←──────────────────────┘
      │
      ├──[ScanResult]──→ Result Reporter
      │
Resource Governor ──[ResourceBudget]──→ broadcast channel → All Modules
Policy Manager ──[PolicyUpdate]──→ broadcast channel → All Modules
```

- **MPSC Channel** (`tokio::sync::mpsc`): 단방향 메시지 전달 (File Watcher → Scanner)
- **Broadcast Channel** (`tokio::sync::broadcast`): 정책 변경, 리소스 예산 등 1:N 브로드캐스트
- **Watch Channel** (`tokio::sync::watch`): 최신 상태 값 공유 (현재 리소스 예산 등)
- 채널 크기는 bounded로 설정하여 메모리 폭주 방지 (backpressure 적용)

### 1.5 Rust 프로젝트 구조

```
pii-scanner-client/
├── Cargo.toml                    # workspace 정의 (virtual manifest)
├── crates/
│   ├── pii-scanner-agent/        # 메인 바이너리 (Windows 서비스 진입점)
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── main.rs           # 서비스 등록/시작
│   │       └── service.rs        # 서비스 라이프사이클
│   │
│   ├── pii-scanner-watcher/      # 파일 감시 모듈
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   │
│   ├── pii-scanner-scanner/      # 스캔 엔진 (정규식 + 체크섬)
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   │
│   ├── pii-scanner-ner/          # NER 추론 (별도 바이너리로도 빌드 가능)
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       └── main.rs           # 별도 프로세스 모드용 진입점
│   │
│   ├── pii-scanner-extractor/    # 텍스트 추출 (파일 형식별 파서)
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   │
│   ├── pii-scanner-policy/       # 정책 관리
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   │
│   ├── pii-scanner-reporter/     # 결과 리포팅 + 서버 통신
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   │
│   ├── pii-scanner-governor/     # 리소스 관리
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   │
│   ├── pii-scanner-updater/      # 자동 업데이트
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   │
│   ├── pii-scanner-db/           # SQLite 로컬 DB 추상화
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   │
│   └── pii-scanner-common/       # 공통 타입, 에러, 설정
│       ├── Cargo.toml
│       └── src/lib.rs
│
├── resources/
│   └── models/                   # ONNX 모델 파일
│
└── installer/                    # WiX 또는 NSIS 설치 스크립트
```

**구조 설계 원칙:**
- **Virtual Manifest**: 루트 `Cargo.toml`에 `[workspace]`만 정의. 루트에 `src/`를 두지 않아 깔끔한 구조 유지
- **크레이트 이름 = 폴더 이름**: 탐색과 리팩토링 편의
- **NER 크레이트는 lib + bin 이중 구조**: 동일 프로세스 내 라이브러리로 호출하거나, 별도 프로세스로 실행 가능
- **공통 크레이트 분리**: `pii-scanner-common`에 공유 타입(`ScanRequest`, `ScanResult`, `PolicyConfig` 등)을 정의하여 순환 의존 방지

---

## 2. 실시간 파일 감지

### 2.1 Windows 파일 감시 API 비교

| 기준 | ReadDirectoryChangesW | USN Journal | ETW (FileIo Provider) |
|------|----------------------|-------------|----------------------|
| **동작 방식** | 디렉토리 핸들에 변경 알림 요청 | NTFS 저널 레코드 순차 읽기 | 커널 이벤트 트레이싱 |
| **이벤트 유실** | 버퍼 오버플로 시 유실 가능 | 저널 래핑 전까지 유실 없음 | 세션 버퍼 오버플로 시 유실 |
| **오프라인 변경 감지** | 불가 (실행 중에만 감지) | **가능** (저널에 기록 남음) | 불가 |
| **성능** | 감시 디렉토리 수에 비례 | 볼륨 단위 일괄 처리 | 오버헤드 있으나 상세 정보 |
| **정보 상세도** | 파일명, 변경 유형 | 파일 참조번호, 변경 유형, 타임스탬프 | 프로세스 ID, I/O 크기 등 매우 상세 |
| **관리자 권한** | 불필요 (해당 디렉토리 접근 권한만) | **필요** (볼륨 핸들 접근) | **필요** (커널 세션) |
| **구현 복잡도** | 낮음 | 중간 | 높음 |
| **NTFS 전용** | 아니오 (FAT32 등도 지원) | 예 (NTFS만) | 아니오 |

### 2.2 추천 전략: 하이브리드 (ReadDirectoryChangesW + USN Journal)

**1차: ReadDirectoryChangesW (실시간 감시)**
- 정책에 정의된 감시 대상 디렉토리에 대해 실시간 이벤트 수신
- Rust `notify` 크레이트(v8.x)가 내부적으로 ReadDirectoryChangesW를 사용
- 사용자 데스크톱, 문서, 다운로드 등 주요 경로를 감시

**2차: USN Journal (보완 + 부팅 후 캐치업)**
- Agent 미실행 시간(재부팅, 업데이트 등) 동안 발생한 변경 감지
- Agent 시작 시 마지막 처리한 USN 번호 이후의 변경 사항을 일괄 수집
- 주기적으로(예: 1시간 간격) USN Journal을 스캔하여 ReadDirectoryChangesW 누락 보완
- `windows-rs` 크레이트를 통해 직접 `DeviceIoControl` + `FSCTL_READ_USN_JOURNAL` 호출

**ETW는 제외하는 이유:**
- 구현 복잡도가 매우 높고, 파일 감시 목적으로는 과도한 정보량
- ReadDirectoryChangesW + USN Journal 조합으로 충분한 커버리지 확보 가능
- 향후 프로세스 감시(어떤 프로세스가 파일을 변경했는지) 필요 시 선택적 도입 고려

### 2.3 이벤트 디바운싱과 큐잉

```
File Event → Debouncer (300ms) → Dedup Filter → Priority Queue → Scanner
```

**디바운싱 전략:**
- 동일 파일에 대해 300ms 내 연속 이벤트는 마지막 이벤트 하나로 합산
- Office 파일 저장 시 임시파일 생성→이름변경→삭제 패턴을 단일 "수정" 이벤트로 정규화
- `~$`로 시작하는 임시 파일, `.tmp` 파일은 자동 필터링

**큐잉 전략:**
- **Bounded Priority Queue**: 최대 10,000건 (메모리 제한)
- 우선순위:
  1. 사용자가 방금 열거나 수정한 파일 (가장 높음)
  2. 실시간 감지된 신규/수정 파일
  3. 증분 스캔 대상 (백그라운드)
  4. 전체 스캔 대상 (가장 낮음)
- 큐 포화 시 낮은 우선순위 항목부터 드롭 (로그 기록)

### 2.4 DRM 파일 처리 방안

DRM(Digital Rights Management) 파일은 암호화되어 일반적인 텍스트 추출이 불가능하다.

**전략: DRM 연동 SDK 또는 복호화 API 활용**
1. **DRM 벤더 SDK 연동**: 국내 주요 DRM 솔루션(Fasoo, SoftCamp, MarkAny 등)의 SDK를 통해 복호화 후 텍스트 추출
2. **구현 방식**: DRM SDK는 대부분 C/C++ 라이브러리이므로 Rust FFI(`bindgen`)를 통해 연동
3. **프로세스 격리**: DRM 복호화는 별도 자식 프로세스에서 수행 (DRM SDK 크래시 격리)
4. **임시 파일 보안**: 복호화된 임시 파일은 메모리 매핑 또는 암호화된 임시 디렉토리에 저장, 스캔 완료 후 즉시 안전 삭제(secure wipe)
5. **미지원 DRM**: SDK 연동이 불가능한 DRM은 "스캔 불가(DRM 보호)" 상태로 결과 리포트

### 2.5 대용량 파일 처리

**파일 크기별 전략:**

| 크기 구간 | 전략 |
|----------|------|
| < 10 MB | 전체 메모리 로드 후 처리 |
| 10 MB ~ 100 MB | 스트리밍 처리 (청크 단위 텍스트 추출) |
| 100 MB ~ 1 GB | 백그라운드 우선순위로 스트리밍 처리, 유휴 시간에만 |
| > 1 GB | 정책 기반 처리 (기본: 스킵, 관리자 설정에 따라 처리 가능) |

**스트리밍 처리 방식:**
- 청크 크기: 1 MB 단위로 텍스트 추출 → PII 탐지
- 청크 간 경계에서 PII가 분할되는 것을 방지하기 위해 256바이트 오버랩(overlap) 적용
- 메모리 사용량: 동시 처리 파일 수 x 청크 크기(1 MB) + 오버헤드

---

## 3. 리소스 관리 (업무 방해 최소화)

기존 솔루션의 가장 큰 불만이 "풀스캔 시 CPU 급증으로 인한 업무 방해"이므로, 리소스 관리는 이 제품의 핵심 차별점이다.

### 3.1 Resource Governor 설계

Resource Governor는 현재 시스템 상태를 모니터링하고, 모든 모듈에 **리소스 예산(Resource Budget)**을 배분한다.

```rust
struct ResourceBudget {
    max_cpu_percent: u8,        // 스캔에 사용할 최대 CPU %
    max_memory_mb: u32,         // 스캔에 사용할 최대 메모리 MB
    max_concurrent_files: u8,   // 동시 스캔 파일 수
    io_priority: IoPriority,    // I/O 우선순위
    scan_mode: ScanMode,        // Active / Idle / Paused
}

enum ScanMode {
    Active,     // 사용자 활동 감지 → 최소 리소스
    Idle,       // 유휴 상태 → 적극적 스캔
    Scheduled,  // 스케줄된 배치 스캔
    Paused,     // 관리자 또는 사용자 일시정지
}
```

### 3.2 CPU 쓰로틀링

**사용자 활동 감지 기반 동적 조절:**

| 사용자 상태 | 감지 방법 | CPU 예산 | 동시 스캔 |
|------------|----------|---------|----------|
| 활발한 사용 | 키보드/마우스 입력 감지 (`GetLastInputInfo`) | 5~10% | 1파일 |
| 비활성 (5분) | 입력 없음 | 25% | 2파일 |
| 유휴 (15분 이상) | 입력 없음 + 스크린세이버/잠금 | 50% | 4파일 |
| 프레젠테이션 모드 | `SHQueryUserNotificationState` | **0% (일시정지)** | 0 |
| 배터리 사용 중 | `GetSystemPowerStatus` | 기본의 50% 감축 | 감축 |

**구현 방식:**
- `rayon` 스레드 풀의 활성 스레드 수를 동적 조절
- 스캔 루프 내 `yield` 포인트에서 슬립 삽입으로 CPU 점유율 제어
- Windows Job Object를 활용한 프로세스 레벨 CPU 제한도 보조적으로 사용

### 3.3 메모리 제한

- **전체 Agent 메모리 상한**: 300 MB (설정 가능)
- NER 모델 로드: ~80 MB (양자화 모델 기준)
- 텍스트 추출 버퍼: ~50 MB
- 로컬 DB 캐시: ~30 MB
- 나머지: 동적 할당
- 메모리 사용량 모니터링 → 상한 근접 시 스캔 일시정지, 캐시 해제
- `jemalloc` 또는 `mimalloc`을 메모리 할당자로 사용하여 조각화(fragmentation) 최소화

### 3.4 I/O 우선순위

- 스캔 관련 파일 읽기는 **Background I/O Priority**로 설정
- Windows API: `SetFileInformationByHandle`의 `FileIoPriorityHintInfo`를 `IoPriorityHintVeryLow`로 설정
- 스캔 스레드의 I/O 우선순위: `SetThreadPriority`로 `THREAD_PRIORITY_LOWEST` 설정
- 결과: 사용자의 파일 I/O가 항상 우선되어 체감 성능 저하 최소화

### 3.5 스캔 스케줄링

```
┌─────────────────────────────────────────────────────────┐
│                  스캔 스케줄링 계층                        │
├─────────────────────────────────────────────────────────┤
│ 1. 실시간 스캔: 파일 변경 즉시 (최우선, 경량)              │
│ 2. 증분 스캔: 변경된 파일만 (매일 유휴 시간)              │
│ 3. 전체 스캔: 모든 대상 파일 (주 1회, 관리자 지정 시간)    │
│ 4. 보정 스캔: USN 캐치업 (부팅 후, 1시간 간격)            │
└─────────────────────────────────────────────────────────┘
```

**유휴 시간 활용:**
- Windows Task Scheduler 연동 또는 자체 스케줄러
- 관리자 정책으로 스캔 시간대 설정 가능 (예: 점심 12~13시, 퇴근 후 18~22시)
- `idle` 조건: 사용자 입력 15분 없음 AND CPU 사용률 20% 미만

### 3.6 증분 스캔

**파일 변경 감지 방식 (증분 스캔 판단 기준):**

1. **파일 메타데이터 비교**: 수정 시각(`mtime`) + 파일 크기
   - 가장 빠른 1차 필터 (I/O 불필요, 메타데이터만 조회)
2. **콘텐츠 해시 비교**: 메타데이터 변경 감지 시에만 `xxHash`(xxh3)로 콘텐츠 해시 계산
   - SHA-256 대비 10배 이상 빠름, 변경 감지 목적으로 충분
3. **로컬 DB 저장**: `(파일경로, mtime, size, xxhash, 마지막_스캔_시각)` 튜플 저장

**증분 스캔 흐름:**
```
파일 목록 수집 → mtime/size 비교 → 변경된 파일만 xxHash → 해시 변경 확인 → 스캔 큐 투입
```

---

## 4. 서버 아키텍처 (수만 대 PC 관리)

### 4.1 전체 서버 아키텍처

```
                    ┌─────────────┐
                    │   CDN/LB    │
                    │  (NGINX)    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼────┐ ┌────▼─────┐
        │ API Server │ │  API   │ │   API    │
        │  (Node 1)  │ │(Node 2)│ │ (Node N) │
        └─────┬──────┘ └───┬────┘ └────┬─────┘
              │            │            │
              └────────────┼────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼────┐ ┌────▼─────┐
        │   Redis    │ │  NATS  │ │PostgreSQL│
        │  (Cache)   │ │  (MQ)  │ │  (Main)  │
        └────────────┘ └────────┘ └──────────┘
                                       │
                                  ┌────▼─────┐
                                  │ TimescaleDB│
                                  │(시계열 확장)│
                                  └──────────┘

        ┌─────────────────────────────────────┐
        │          Admin Dashboard            │
        │         (SPA - React/Vue)           │
        └─────────────────────────────────────┘
```

### 4.2 API 서버 설계

**기술 스택: Go + Fiber (또는 Gin)**

근거:
- **Go를 선택하는 이유**:
  - 정적 바이너리 컴파일 → 배포 단순
  - 뛰어난 동시성(goroutine) → 수만 대 연결 처리에 적합
  - 낮은 메모리 사용량
  - 배우기 쉬운 언어 → 서버 팀 채용 유리
  - Rust 서버도 가능하나, 서버 측은 빠른 개발과 유지보수 용이성이 더 중요
- **Fiber를 선택하는 이유**:
  - Express 스타일 API로 생산성 높음
  - fasthttp 기반으로 Go 표준 라이브러리 대비 높은 성능

**API 엔드포인트 구조:**

```
# Agent 통신 API (gRPC)
/agent.v1.AgentService/Heartbeat          # 에이전트 상태 보고 (30초 간격)
/agent.v1.AgentService/ReportResults      # 스캔 결과 배치 전송
/agent.v1.AgentService/GetPolicy          # 정책 조회/스트리밍
/agent.v1.AgentService/GetUpdate          # 업데이트 확인 및 다운로드
/agent.v1.AgentService/RegisterAgent      # 신규 에이전트 등록

# 관리자 API (REST)
GET    /api/v1/dashboard/summary          # 대시보드 요약 통계
GET    /api/v1/agents                     # 에이전트 목록 (페이지네이션)
GET    /api/v1/agents/:id                 # 에이전트 상세 정보
GET    /api/v1/agents/:id/results         # 특정 에이전트의 스캔 결과
POST   /api/v1/policies                   # 정책 생성
PUT    /api/v1/policies/:id               # 정책 수정
GET    /api/v1/policies                   # 정책 목록
GET    /api/v1/results                    # 스캔 결과 검색/필터
GET    /api/v1/results/statistics         # 통계 데이터
POST   /api/v1/results/export             # 결과 내보내기 (CSV/Excel)
GET    /api/v1/licenses                   # 라이선스 현황
POST   /api/v1/licenses/activate          # 라이선스 활성화
GET    /api/v1/updates                    # 업데이트 패키지 관리
POST   /api/v1/updates                    # 업데이트 패키지 업로드
```

**Agent-Server 통신은 gRPC**, **관리자 대시보드는 REST**로 이원화:
- gRPC: 바이너리 프로토콜로 대역폭 절약, 양방향 스트리밍(정책 푸시) 지원, Protobuf 스키마로 타입 안전성
- REST: 관리자 대시보드(브라우저)에서 접근 용이

### 4.3 데이터베이스 설계

**Primary DB: PostgreSQL 16+**

근거:
- 안정성과 성숙도가 검증된 RDBMS
- JSON 지원으로 유연한 스키마 확장
- 파티셔닝 지원으로 대용량 데이터 관리
- TimescaleDB 확장으로 시계열 데이터(스캔 이력) 효율 처리

**핵심 테이블:**

```sql
-- 에이전트 관리
agents (
    id UUID PRIMARY KEY,
    hostname VARCHAR(255),
    ip_address INET,
    os_version VARCHAR(100),
    agent_version VARCHAR(20),
    last_heartbeat TIMESTAMPTZ,
    status ENUM('online', 'offline', 'error'),
    organization_id UUID REFERENCES organizations(id),
    created_at TIMESTAMPTZ,
    metadata JSONB
)

-- 스캔 결과 (TimescaleDB 하이퍼테이블로 전환)
scan_results (
    id BIGSERIAL,
    agent_id UUID REFERENCES agents(id),
    file_path TEXT,
    file_hash VARCHAR(64),
    pii_type VARCHAR(50),           -- 주민번호, 전화번호, 이메일, 이름, 주소 등
    pii_count INTEGER,
    confidence FLOAT,               -- NER 신뢰도 (0.0~1.0)
    detection_method VARCHAR(20),   -- regex, checksum, ner
    scanned_at TIMESTAMPTZ,
    reported_at TIMESTAMPTZ,
    PRIMARY KEY (id, scanned_at)    -- 파티션 키 포함
)

-- 정책
policies (
    id UUID PRIMARY KEY,
    name VARCHAR(100),
    organization_id UUID REFERENCES organizations(id),
    scan_paths JSONB,               -- 스캔 대상 경로
    exclude_paths JSONB,            -- 제외 경로
    schedule JSONB,                 -- 스캔 스케줄
    pii_rules JSONB,                -- PII 유형별 설정
    resource_limits JSONB,          -- 리소스 제한 설정
    version INTEGER,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
)

-- 조직/테넌트
organizations (
    id UUID PRIMARY KEY,
    name VARCHAR(200),
    license_id UUID REFERENCES licenses(id),
    created_at TIMESTAMPTZ
)
```

**파티셔닝 전략:**
- `scan_results` 테이블: `scanned_at` 기준 월별 파티셔닝 (TimescaleDB 자동 관리)
- 90일 이상 데이터는 압축 → 1년 이상은 아카이브 또는 삭제 (정책 설정 가능)

### 4.4 메시지 큐: NATS

**선택: NATS (with JetStream)**

근거:
- **경량성**: Go로 작성, 단일 바이너리, 메모리 사용량 매우 적음
- **고성능**: 초당 수백만 메시지 처리 가능
- **JetStream**: 영속적 메시지, at-least-once 전송 보장
- Kafka 대비 운영 복잡도가 현저히 낮으면서도 50,000 에이전트 규모에 충분
- RabbitMQ 대비 Go 생태계와의 친화성이 높고 성능 우수

**메시지 큐 사용처:**

| 큐 이름 | 용도 | 컨슈머 |
|---------|------|--------|
| `scan.results` | Agent 스캔 결과 배치 수신 | Result Processor 워커 |
| `policy.updates` | 정책 변경 이벤트 발행 | Agent들 (pub/sub) |
| `agent.events` | Agent 상태 변경 이벤트 | Dashboard 실시간 업데이트 |
| `alerts` | 대량 PII 발견 등 긴급 알림 | Alert Handler |

### 4.5 캐시: Redis

- Agent 인증 토큰 캐시 (JWT 검증 결과)
- 대시보드 통계 캐시 (5분 TTL)
- Rate limiting (Agent별 API 호출 제한)
- Agent 온라인 상태 (heartbeat 기반 TTL 키)

### 4.6 관리자 대시보드

**기술 스택: React + TypeScript (또는 Vue 3 + TypeScript)**

**주요 화면:**

1. **메인 대시보드**
   - 전체 에이전트 수, 온라인/오프라인 비율
   - 최근 24시간 PII 탐지 건수 추이 (시계열 차트)
   - PII 유형별 분포 (도넛 차트)
   - 위험도 높은 PC Top 10

2. **에이전트 관리**
   - 에이전트 목록 (검색, 필터, 정렬)
   - 개별 에이전트 상세: 시스템 정보, 마지막 스캔 시각, 탐지 결과
   - 에이전트 그룹(부서/조직) 관리
   - 에이전트 버전 현황

3. **스캔 결과**
   - 결과 목록 (검색: 파일명, PII 유형, 날짜 범위, 에이전트)
   - 결과 상세: 탐지된 PII 위치(마스킹 처리), 신뢰도
   - CSV/Excel 내보내기
   - 조치 이력 (사용자 확인, 삭제, 암호화 등)

4. **정책 관리**
   - 정책 생성/수정/삭제
   - 정책 할당 (조직/그룹/개별 에이전트)
   - 정책 버전 이력

5. **통계 및 보고서**
   - 기간별 PII 탐지 트렌드
   - 조직/부서별 비교
   - 컴플라이언스 준수율
   - 정기 보고서 자동 생성 (PDF)

6. **시스템 관리**
   - 라이선스 현황 및 관리
   - 업데이트 패키지 관리
   - 시스템 로그
   - 관리자 계정 관리

### 4.7 수평 확장 전략

**50,000대 에이전트 기준 예상 트래픽:**
- Heartbeat: 50,000 x 2/분 = ~1,667 req/s
- 스캔 결과 리포트: ~500 req/s (피크 시)
- 정책 조회: ~100 req/s
- 총: ~2,300 req/s (피크)

**확장 전략:**

```
Phase 1: 단일 서버 (에이전트 ~5,000대)
├── API Server x 1
├── PostgreSQL x 1
├── Redis x 1
└── NATS x 1

Phase 2: 기본 확장 (에이전트 ~20,000대)
├── API Server x 3 (Load Balancer 뒤)
├── PostgreSQL x 1 (Primary) + Read Replica x 1
├── Redis x 1 (Sentinel)
└── NATS x 3 (Cluster)

Phase 3: 대규모 확장 (에이전트 ~50,000대+)
├── API Server x 5+ (Auto Scaling)
├── PostgreSQL x 1 (Primary) + Read Replica x 2
├── Redis x 3 (Cluster)
├── NATS x 3+ (Cluster)
└── Result Processor Worker x 3+
```

**핵심 확장 포인트:**
- API 서버: **Stateless** 설계, 로드밸런서 뒤에서 수평 확장
- DB 읽기 부하: Read Replica로 분산 (대시보드 쿼리 → Replica)
- 결과 처리: NATS Consumer 워커 수평 확장
- Agent Heartbeat: Redis에서 처리하여 DB 부하 감소

---

## 5. 기술 스택 선택과 근거

### 5.1 클라이언트 기술 스택

| 구분 | 선택 | 근거 |
|------|------|------|
| **언어** | Rust (stable) | 메모리 안전성, C++ 수준 성능, 단일 바이너리, Windows 네이티브 지원 |
| **비동기 런타임** | `tokio` | 사실상 표준, Windows 완벽 지원, 풍부한 생태계 |
| **Windows 서비스** | `windows-service` | 검증된 Windows 서비스 프레임워크 |
| **Windows API** | `windows-rs` | Microsoft 공식 Rust 크레이트, Win32 전체 API 접근 |
| **파일 감시** | `notify` (v8.x) | ReadDirectoryChangesW 기반, 크로스플랫폼, 62M+ 다운로드 |
| **HTTP/gRPC** | `tonic` | Rust용 gRPC, Tokio 기반, 양방향 스트리밍 |
| **직렬화** | `prost` (Protobuf) | tonic과 통합, 서버와 동일 .proto 스키마 공유 |
| **NER 추론** | `ort` (ONNX Runtime) | Microsoft ONNX Runtime 래퍼, CPU/GPU 지원 |
| **정규식** | `regex` + `aho-corasick` | 빠른 다중 패턴 매칭 |
| **로컬 DB** | `rusqlite` | SQLite 바인딩, 안정적 |
| **해시** | `xxhash-rust` | 파일 변경 감지용 고속 해시 |
| **로깅** | `tracing` | 구조화 로깅, 비동기 친화적 |
| **에러 처리** | `thiserror` + `anyhow` | 라이브러리/어플리케이션 레벨 에러 처리 |
| **스레드 풀** | `rayon` | CPU 집약 작업용 데이터 병렬 처리 |
| **메모리 할당** | `mimalloc` | 조각화 최소화, 멀티스레드 성능 우수 |
| **설치 패키지** | WiX Toolset | Windows MSI 패키지 생성, 엔터프라이즈 표준 |

### 5.2 서버 기술 스택

| 구분 | 선택 | 근거 |
|------|------|------|
| **언어** | Go 1.22+ | 높은 동시성, 빠른 개발, 단일 바이너리 |
| **REST 프레임워크** | Fiber v3 | 고성능, Express 스타일 API |
| **gRPC** | `google.golang.org/grpc` | Go 공식 gRPC, 서버 스트리밍 지원 |
| **ORM** | sqlc 또는 GORM | sqlc: 타입 안전 SQL 쿼리, GORM: 빠른 개발 |
| **DB** | PostgreSQL 16 + TimescaleDB | 안정성, 시계열 확장 |
| **캐시** | Redis 7 | 세션, 캐시, rate limiting |
| **메시지 큐** | NATS + JetStream | 경량, 고성능, 영속적 메시지 |
| **인증** | JWT (access + refresh token) | Stateless, 확장 용이 |
| **API 문서** | Swagger/OpenAPI 3.0 | 자동 문서 생성 |
| **대시보드** | React 18 + TypeScript + Vite | 넓은 생태계, 타입 안전성 |
| **차트** | Recharts 또는 Apache ECharts | 대시보드 시각화 |
| **컨테이너** | Docker + Docker Compose | 서버 배포, 개발 환경 통일 |
| **오케스트레이션** | Kubernetes (대규모) | 수평 확장, 자동 복구 |
| **모니터링** | Prometheus + Grafana | 서버 메트릭, 알림 |
| **로깅** | Loki + Grafana | 중앙화 로그 수집 |

### 5.3 클라이언트 업데이트 메커니즘

```
Agent                           Server
  │                                │
  ├─── Heartbeat (버전 정보 포함) ──→│
  │                                ├── 최신 버전과 비교
  │←── UpdateAvailable 응답 ────────┤
  │                                │
  ├─── 업데이트 패키지 다운로드 ─────→│
  │    (청크 다운로드, 체크포인트)     │
  │←── 패키지 바이너리 ─────────────┤
  │                                │
  ├── SHA-256 무결성 검증            │
  ├── 코드 서명(code signing) 검증   │
  ├── 이전 바이너리 백업              │
  ├── 새 바이너리 교체                │
  ├── Windows 서비스 재시작           │
  │                                │
  ├── 업데이트 결과 보고 ───────────→│
```

**롤백 메커니즘:**
- 업데이트 전 이전 바이너리를 `.bak`으로 백업
- 새 버전 시작 후 30초 내 Heartbeat 실패 시 자동 롤백
- 관리자가 서버에서 강제 롤백 명령 전송 가능

### 5.4 서버/클라이언트 헬스 체크

**클라이언트 → 서버:**
- 30초 간격 Heartbeat (gRPC unary)
- 포함 정보: Agent ID, 버전, OS 정보, CPU/메모리 사용률, 스캔 상태, 마지막 스캔 시각

**서버 측 헬스 체크:**
- 2분간 Heartbeat 미수신 → Agent "의심" 상태
- 5분간 미수신 → Agent "오프라인" 상태
- 대시보드에 실시간 반영 (WebSocket 또는 SSE)

**서버 자체 모니터링:**
- `/health` 엔드포인트: DB 연결, Redis 연결, NATS 연결 상태 확인
- Prometheus 메트릭: API 응답 시간, 에러율, 큐 길이, DB 연결 풀 상태
- Grafana 알림: 임계치 초과 시 Slack/이메일 알림

---

## 6. 텍스트 추출 전략

### 6.1 지원 파일 형식 및 파싱 라이브러리

| 파일 형식 | 확장자 | 추출 방법 | Rust 라이브러리/전략 |
|----------|--------|----------|-------------------|
| **Plain Text** | .txt, .csv, .log, .json, .xml | 직접 읽기 | `std::fs` + 인코딩 감지 |
| **Microsoft Word** | .docx | ZIP 해제 → XML 파싱 | `zip` + `quick-xml` |
| **Microsoft Word (구)** | .doc | COM/OLE 구조 파싱 | `ole` 크레이트 또는 외부 도구 |
| **Microsoft Excel** | .xlsx | ZIP 해제 → XML 파싱 | `calamine` |
| **Microsoft Excel (구)** | .xls | BIFF 포맷 파싱 | `calamine` |
| **Microsoft PowerPoint** | .pptx | ZIP 해제 → XML 파싱 | `zip` + `quick-xml` |
| **PDF** | .pdf | 텍스트 레이어 추출 | `pdf-extract` 또는 `lopdf` |
| **HWP (한글)** | .hwp | OLE 구조 → 본문 스트림 파싱 | `hwp-rs` (Rust 네이티브) |
| **HWPX (한글)** | .hwpx | ZIP 해제 → XML 파싱 | `zip` + `quick-xml` |
| **이메일** | .eml | MIME 파싱 | `mailparse` |
| **이메일 (Outlook)** | .msg | OLE/MAPI 구조 파싱 | `ole` + 커스텀 MAPI 파서 |
| **RTF** | .rtf | RTF 토큰 파싱 | 커스텀 파서 (단순 형식) |
| **HTML** | .html, .htm | 태그 제거 | `scraper` 또는 `select` |

### 6.2 파일 형식별 상세 전략

#### Office 문서 (OOXML: docx, xlsx, pptx)
- OOXML은 ZIP 아카이브 내 XML 파일로 구성
- `zip` 크레이트로 압축 해제 → `quick-xml` 이벤트 기반 파서로 텍스트 노드 추출
- 스트리밍 처리 가능: ZIP 내 파일을 순차적으로 읽으며 메모리 최소화
- 임베디드 이미지 내 텍스트는 1차 버전에서 미지원 (향후 OCR 연동 고려)

#### PDF
- 텍스트 레이어가 있는 PDF: `lopdf` 또는 `pdf-extract`로 텍스트 추출
- 이미지 PDF (스캔본): 1차 버전에서 미지원 (향후 Tesseract OCR 연동 고려)
- 암호화된 PDF: 비밀번호 없으면 "스캔 불가" 처리

#### HWP (한글)
- HWP v5 파일은 OLE2 Compound Document 형식
- `hwp-rs` 크레이트를 활용하되, 유지보수 상태를 확인하고 필요 시 자체 구현
- 핵심 구조: OLE 스트림 → zlib 압축 해제 → 본문(BodyText) 섹션에서 텍스트 추출
- HWPX는 OOXML과 유사한 ZIP+XML 구조로 처리 용이

#### 이메일 (eml, msg)
- `.eml`: RFC 2822 표준, `mailparse` 크레이트로 MIME 구조 파싱
- `.msg`: Microsoft OLE 기반, `ole` 크레이트로 MAPI 속성 추출
- 첨부파일: 재귀적으로 텍스트 추출 파이프라인에 투입

### 6.3 DRM 파일 처리 전략

```
파일 읽기 시도 → DRM 감지 → DRM SDK 호출 → 복호화 → 텍스트 추출 → 안전 삭제
                   │
                   └── DRM 미감지 → 일반 텍스트 추출 진행
```

**DRM 감지 방법:**
1. 파일 헤더 시그니처 검사 (DRM 벤더별 고유 시그니처)
2. 파일 확장자 매핑 (`.drm`, `.fas` 등)
3. Windows Shell Extension 정보 확인

**DRM 벤더 연동 아키텍처:**
- 플러그인 구조로 DRM 벤더별 어댑터(adapter) 구현
- 각 어댑터는 `DrmDecryptor` 트레이트를 구현
- 새 DRM 벤더 추가 시 어댑터 추가만으로 확장 가능

```rust
trait DrmDecryptor: Send + Sync {
    fn can_handle(&self, file_path: &Path) -> bool;
    fn decrypt_to_stream(&self, file_path: &Path) -> Result<Box<dyn Read>>;
    fn vendor_name(&self) -> &str;
}
```

### 6.4 인코딩 감지

한국 기업 환경에서는 EUC-KR(CP949)과 UTF-8이 혼재하므로 정확한 인코딩 감지가 필수이다.

**감지 전략 (순서대로):**
1. **BOM(Byte Order Mark) 확인**: UTF-8 BOM, UTF-16 LE/BE BOM
2. **UTF-8 유효성 검사**: `std::str::from_utf8` - 유효하면 UTF-8로 확정
3. **통계적 감지**: `chardetng` 크레이트 (Firefox의 인코딩 감지 엔진의 Rust 포팅)
4. **폴백**: 감지 실패 시 EUC-KR(CP949) 가정 (한국 환경 기본값)

**디코딩:** `encoding_rs` 크레이트 사용 (Firefox에서 사용하는 인코딩 변환 라이브러리)

---

## 7. 클라이언트-서버 통신 프로토콜

### 7.1 프로토콜 선택: gRPC (Agent ↔ Server)

**선택 근거:**
- **대역폭 효율**: Protobuf 바이너리 직렬화 → JSON 대비 3~10배 작은 페이로드
- **양방향 스트리밍**: 서버에서 정책 변경을 실시간 푸시 가능
- **타입 안전성**: `.proto` 스키마에서 클라이언트(Rust)와 서버(Go) 코드 자동 생성
- **성능**: REST 대비 8~10배 빠른 응답 시간 (벤치마크 기준)
- **HTTP/2 기반**: 멀티플렉싱, 헤더 압축

### 7.2 통신 패턴

```protobuf
syntax = "proto3";
package agent.v1;

service AgentService {
    // 단방향: Agent → Server
    rpc RegisterAgent(RegisterRequest) returns (RegisterResponse);
    rpc Heartbeat(HeartbeatRequest) returns (HeartbeatResponse);
    rpc ReportResults(stream ScanResultBatch) returns (ReportResponse);

    // 서버 스트리밍: Server → Agent (정책 푸시)
    rpc SubscribePolicy(PolicySubscribeRequest) returns (stream PolicyUpdate);

    // 단방향: Agent → Server
    rpc CheckUpdate(UpdateCheckRequest) returns (UpdateCheckResponse);
}
```

### 7.3 오프라인 내성 (Offline Resilience)

```
정상 연결 시:
Agent ──[결과 전송]──→ Server ──[ACK]──→ Agent (로컬 DB에서 삭제)

연결 실패 시:
Agent ──[결과 전송]──X (실패)
Agent: 로컬 SQLite에 결과 저장, 재시도 큐에 추가
재시도: 1분 → 2분 → 4분 → ... → 최대 30분 간격 (지수 백오프)

연결 복구 시:
Agent: 미전송 결과를 시간순으로 배치 전송
Server: 중복 결과는 idempotency key로 필터
```

### 7.4 보안

- **TLS 1.3**: 모든 gRPC 통신은 TLS 암호화 필수
- **상호 인증(mTLS)**: Agent 설치 시 클라이언트 인증서 발급, 서버가 Agent 신원 확인
- **API 키**: 조직별 API 키로 Agent 등록 시 조직 식별
- **Heartbeat 토큰**: 등록 시 발급받은 Agent 토큰을 매 요청에 포함
- 상세 보안 설계는 보안 설계 문서 참조

---

## 부록 A: 예상 시스템 요구사항

### 클라이언트 (Agent)
| 항목 | 최소 사양 | 권장 사양 |
|------|----------|----------|
| OS | Windows 10 1809+ | Windows 10 21H2+ / Windows 11 |
| CPU | x86_64, 2코어 | x86_64, 4코어 |
| RAM | 4 GB (Agent: ~200 MB) | 8 GB (Agent: ~300 MB) |
| 디스크 | 500 MB (Agent + DB) | 1 GB |
| 네트워크 | 서버와 HTTPS 통신 가능 | - |

### 서버 (50,000 에이전트 기준)
| 구성요소 | 사양 |
|---------|------|
| API Server x 3~5 | 4 vCPU, 8 GB RAM each |
| PostgreSQL Primary | 8 vCPU, 32 GB RAM, SSD 500 GB |
| PostgreSQL Read Replica x 2 | 4 vCPU, 16 GB RAM, SSD 500 GB |
| Redis | 4 vCPU, 16 GB RAM |
| NATS Cluster x 3 | 2 vCPU, 4 GB RAM each |
| Result Processor x 3 | 2 vCPU, 4 GB RAM each |

## 부록 B: 향후 확장 고려사항

1. **macOS / Linux 지원**: Rust의 크로스플랫폼 특성 활용, 파일 감시만 플랫폼별 구현
2. **OCR 연동**: Tesseract 등으로 이미지 내 텍스트 추출 (스캔본 PDF, 이미지 파일)
3. **클라우드 스토리지 스캔**: OneDrive, Google Drive 동기화 폴더 감시
4. **USB/외장 스토리지 감시**: 디바이스 연결 이벤트 감지 후 자동 스캔
5. **중앙 집중 NER 서버**: GPU 서버에서 NER 추론 제공 (클라이언트 부하 경감)
6. **멀티테넌시 강화**: SaaS 모델로 전환 시 완전한 테넌트 격리

---

*문서 버전: 1.0*
*작성일: 2026-02-09*
*작성자: Systems Architect (Claude)*
