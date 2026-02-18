# Deep Dive 4 (Codex): 모델/아티팩트 보호 수준 (암호화 vs 서명)

**대상 미합의:** `docs/debate/unresolved.md`의 *미합의 4*  
**목표:** (1) “서명”과 “AES-GCM 암호화”의 **기계적 차이/실패 모드**를 확인하고 (2) 14MB급 아티팩트에서 오버헤드를 계측

---

## 결론 (PoC 기준)

- **무결성(Integrity)** 관점에서 MVP 필수는 **서명 검증**이다. (업데이트 체인 포함)
- **암호화(at-rest)** 는 “IP 보호”로 주장되지만, 키가 클라이언트에 존재하는 이상(그리고 메모리에 로드되는 이상) 한계가 뚜렷하다.  
  즉, 암호화는 “평문 파일 노출 최소화”에는 도움이 되지만 **유출 방지의 결정타는 아니다.**
- 성능 오버헤드 자체는 14MB 기준으로 **해시 38ms, AES-GCM 35ms 수준(이 환경 기준)** 이라 “가능은 하다”. 문제는 성능이 아니라 **키 관리/복구/장애 시 폴백**이다.

---

## PoC 코드

- 코드: `poc/unresolved4_artifact_protection_poc.py`
- 실행: `python3 poc/unresolved4_artifact_protection_poc.py`

### PoC가 한 것

- 14MB 랜덤 바이트를 “`model.onnx`”로 가정
- `sha256(model)` 측정
- `Ed25519(sign(sha256))` 및 verify 측정
- `AES-256-GCM(model)` encrypt/decrypt 측정
- 1바이트 변조 시:
  - 서명 검증이 실패하는지
  - AESGCM 복호화가 실패하는지

---

## 실행 결과 (요약)

```text
artifact_size_bytes=14680064 (~14MB)
sha256_ms=37.91
ed25519_sign_ms=0.1415
ed25519_verify_ms=0.1564
aesgcm_encrypt_ms=35.43
aesgcm_decrypt_ms=33.89
tamper_signature_verify=FAIL_OK
tamper_aesgcm_decrypt=FAIL_OK
```

해석:
- “서명”의 비용은 사실상 **해시 계산 비용**이 지배한다.
- AES-GCM도 14MB에서 수십 ms로 가능하지만, 이는 “속도”의 문제가 아니라 “키 관리/장애 대응” 문제로 바뀐다.

---

## 설계 반영 권고

1. **MVP 필수:** 서명 검증(무결성) + 안전한 배포 체인(서명된 번들, 롤백)  
2. **암호화는 옵션:** 자체 파인튜닝 모델/IP 보호가 비즈니스적으로 정말 중요할 때만 기본값으로 올리고, 그렇지 않으면 옵션으로 둔다.  
3. 암호화 채택 시 필수 조건:
   - 키 저장: Windows에서는 최소 DPAPI/TPM 같은 OS/하드웨어 키 보호가 필요(단, 이 자체가 운영 리스크)
   - 복호화 실패 시: **NER 비활성화 + Regex-only 폴백** (장애 원인 제거)
   - 서명 검증은 암호화와 별개로 유지(키 탈취/변조 대비)

