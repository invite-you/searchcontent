# Rust 기술 조사 보고서

본 문서는 PII Scanner 프로젝트의 기술적 타당성 검토 및 구현 방향 설정을 위해 Rust 관련 주요 기술 주제를 조사한 결과입니다.

## 1. Windows 파일 시스템 모니터링

### 1.1 USN Journal (Update Sequence Number Journal)
NTFS 파일 시스템의 변경 사항을 추적하는 고성능 저널링 기능입니다. 파일 생성, 삭제, 변경 이력을 빠르게 조회할 수 있습니다.

*   **관련 크레이트:**
    *   **`usn-journal-rs`**: USN 저널 레코드 읽기, 모니터링, MFT(Master File Table) 엔트리 열거, 파일 ID 경로 변환 등을 제공하는 안전한 추상화 라이브러리입니다. 가장 적합한 선택지로 보입니다.
    *   **`usnrs`**: `$UsnJrnl:$J` 파일 파싱 및 `USN_RECORD_V2` 처리에 특화되어 있습니다.
*   **구현 포인트:**
    *   관리자 권한 필요.
    *   실시간 감시보다는 **초기 전체 스캔** 또는 **증분 스캔** 시 변경된 파일 목록을 빠르게 확보하는 용도로 적합합니다.

### 1.2 Minifilter 드라이버 통신
실시간 파일 I/O 차단 및 감시를 위해서는 커널 모드 미니필터 드라이버가 필수적입니다. Rust로 드라이버 자체를 작성하거나, C/C++ 드라이버와 통신하는 유저 모드 에이전트를 개발해야 합니다.

*   **아키텍처:**
    *   **Kernel Mode:** `FltCreateCommunicationPort`를 통해 통신 포트 생성. (C++ 또는 `windows-drivers-rs` 사용 가능하나, 안정성을 위해 C++ 권장될 수 있음)
    *   **User Mode (Rust):** `FilterConnectCommunicationPort`로 드라이버 포트에 연결.
*   **Rust 구현:**
    *   **`windows` 크레이트**: `Windows.Win32.Storage.FileSystem` 등의 네임스페이스를 통해 필요한 Win32 API를 직접 호출합니다.
    *   **통신 프로토콜**: 드라이버와 유저 모드 간 공유할 데이터 구조체는 `#[repr(C)]`로 정의하여 메모리 레이아웃을 일치시켜야 합니다.

## 2. Rust 보안 도구 생태계

Rust는 메모리 안전성과 성능 덕분에 보안 도구 개발에 널리 쓰이고 있습니다.

*   **대표적인 오픈소스 도구:**
    *   **`RustScan`**: 초고속 포트 스캐너. 비동기 처리를 통한 성능 극대화 사례.
    *   **`sniffglue`**: 멀티스레드 패킷 스니퍼. 안전한 패킷 처리 참고 가능.
    *   **`Hayabusa`**: Windows 이벤트 로그 분석 및 타임라인 생성 도구. 대용량 로그 처리 성능 참고.
    *   **`Feroxbuster`**: 웹 디렉터리 브루트포싱 도구.
*   **주요 라이브러리:**
    *   **`rustls`**: OpenSSL을 대체하는 메모리 안전한 최신 TLS 라이브러리.
    *   **`orion` / `ring`**: 고성능 암호화 라이브러리.
    *   **`nom` / `serde`**: 바이너리 및 텍스트 데이터의 안전하고 빠른 파싱.

## 3. Rust 바이너리 보호 및 난독화

상용 솔루션으로서 리버스 엔지니어링을 방어하기 위한 기법들입니다.

### 3.1 컴파일 타임 난독화
*   **문자열 암호화:**
    *   **`obfstr`**: 컴파일 타임에 문자열 리터럴을 XOR 암호화하고 런타임에 복호화합니다. `obfstr!("secret string")` 형태로 사용.
    *   **`litcrypt`**: 유사한 기능을 제공하는 매크로 라이브러리.
*   **제어 흐름 난독화:**
    *   **`rustfuscator`**: 소스 코드를 변환하여 제어 흐름을 복잡하게 만들고 암호화를 적용하는 도구/라이브러리.
    *   **`goldberg`**: 제어 흐름 및 리터럴 난독화를 위한 절차적 매크로.

### 3.2 릴리즈 빌드 설정
*   **심볼 제거 (Strip):** `Cargo.toml`에 `strip = true` 설정으로 디버그 심볼 제거.
*   **LTO (Link Time Optimization):** `lto = true` 설정으로 바이너리 최적화 및 분석 난이도 상향.

### 3.3 안티 디버깅 (Anti-Debugging)
Windows API를 `windows` 또는 `windows-sys` 크레이트로 호출하여 구현합니다.
*   **API 체크:** `IsDebuggerPresent()`, `CheckRemoteDebuggerPresent()`.
*   **PEB (Process Environment Block) 검사:** `BeingDebugged` 플래그, `NtGlobalFlag` 등을 직접 메모리에서 확인.
*   **타이밍 체크:** `RDTSC` 등을 이용해 코드 실행 시간을 측정하여 디버거 간섭 탐지.

### 3.4 상용 패커 호환성
*   **VMProtect / Themida:** Rust 바이너리는 네이티브 코드이므로 상용 패커와 호환됩니다. 중요 함수 가상화 등을 통해 강력한 보호가 가능합니다.

## 4. Rust Windows 서비스 개발

Windows 서비스 형태로 백그라운드에서 상시 동작하는 에이전트를 개발하는 방법입니다.

*   **표준 크레이트: `windows-service`**
    *   Windows 서비스 API를 래핑한 사실상의 표준 라이브러리입니다.
    *   서비스 제어 처리기(`ServiceControlHandler`) 등록, 상태 보고, 서비스 메인 루프 구현을 돕습니다.
*   **주요 구조:**
    *   `define_windows_service!`: 서비스 엔트리 포인트 정의 매크로.
    *   `service_main`: 실제 서비스 로직이 실행되는 함수.
    *   `ServiceControlHandler`: 시작, 중지, 일시정지 등의 시스템 신호를 처리.
*   **설치 및 관리:**
    *   서비스 등록/삭제 기능도 해당 크레이트의 `ServiceManager`를 통해 구현 가능합니다 (예: `myapp.exe install`).

## 결론 및 제언

*   **파일 감시:** 실시간 차단이 필요하다면 **Minifilter(C++) + Rust Agent** 구조가 필수적이며, 단순 로깅/스캔 목적이라면 **USN Journal(`usn-journal-rs`)** 활용이 효율적입니다. 본 프로젝트는 실시간 탐지가 목표이므로 하이브리드 접근이 필요할 수 있습니다.
*   **보안:** `obfstr` 등을 통한 기본적 난독화와 `strip`/`lto` 최적화를 적용하고, 필요 시 상용 패커 도입을 고려해야 합니다.
*   **서비스:** `windows-service` 크레이트를 사용하여 안정적인 서비스 구조를 구축할 수 있습니다.
