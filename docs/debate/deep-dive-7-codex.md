# Deep Dive 7 (Codex): 규칙 정의 형식(코드 vs JSON/YAML) 도입 시점

**대상 미합의:** `docs/debate/unresolved.md`의 *미합의 7*  
**목표:** “표현식 금지, 열거형만” 수준의 **최소 JSON 스키마**가 MVP에서 실제로 굴러가는지 PoC로 확인

---

## 결론 (PoC 기준)

- “열거형 기반 JSON 스키마(표현식/미니언어 금지)”는 **구현 난이도가 낮고**, “서명된 룰 번들 업데이트”와 잘 결합된다.  
- 따라서 MVP에서도 **규칙을 코드 하드코딩만으로 관리**하는 것보다, 최소 스키마로 시작하는 쪽이 운영(핫픽스/튜닝) 측면에서 유리하다.
- 핵심 가드레일:
  - 스키마는 **enum-only**로 제한(validator id, kind 등)
  - regex compile/validator mapping 실패 시 번들 전체를 fail-closed(적용 거부)
  - 번들 적용은 **서명 검증** 필수

---

## PoC 코드

- 코드: `poc/unresolved7_rule_bundle_poc.py`
- 실행: `python3 poc/unresolved7_rule_bundle_poc.py`

### PoC가 한 것

1. 최소 JSON 번들(규칙 2개)을 정의하고, `Ed25519`로 서명/검증
2. 번들 v1/v2에서 전화번호 regex를 변경하여:
   - v1: `010/011/016/017/018/019`만 탐지
   - v2: `070`(VoIP)까지 탐지
   를 “코드 변경 없이(=번들만 변경)”로 재현
3. 번들 내용을 1바이트 수정(=regex 변경)했을 때 **기존 서명으로 검증 실패**하는지 확인

---

## 실행 결과 (요약)

```text
bundle_v1_findings:
  ... RRN ... verdict='CONFIRMED' ...
  ... PHONE ... value='010-1234-5678' ...

bundle_v2_findings:
  ... PHONE ... value='010-1234-5678' ...
  ... PHONE ... value='070-1234-5678' ...

tamper_verify=FAIL_OK
```

해석:
- v1에서는 `070-...`이 탐지되지 않다가, v2 번들만 바꿔서 탐지되었다. (규칙 업데이트)
- 서명 검증으로 변조된 번들이 적용되지 않는다.

---

## 설계 반영 권고

1. MVP부터 “enum-only JSON 스키마”로 규칙을 관리하고, 번들은 서명해서 배포  
2. JSON canonicalization/서명 범위는 PoC처럼 “재직렬화”에 의존하지 말고, 실제 배포에서는:
   - `bundle.zip`(또는 tar) 같은 **바이너리 아티팩트 전체를 서명**
   - 내부에 `rules.json`, `metadata.json`, `sha256` 목록 포함
3. 확장 방향:
   - 표현식/조건문/스크립트는 금지(미니 언어로 폭발)
   - 대신 “validator enum + context 키워드 리스트 + window” 같은 **제한된 조합**만 늘린다.

