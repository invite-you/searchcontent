# Deep Dive 1 (Codex): Aho-Corasick 프리필터의 적용 범위

**대상 미합의:** `docs/debate/unresolved.md`의 *미합의 1*  
**목표:** “키워드가 없으면 Regex 단계도 스킵”이 **정확도 관점에서 안전한가**를 PoC로 검증

---

## 결론 (PoC 기준)

- “키워드 0개 => Regex/Checksum까지 스킵”은 **구조화 PII를 미탐지**할 수 있다. (숫자만 있는 표/스프레드시트/CSV 등)
- 안전측 기본값은 **Regex/Checksum은 항상 실행**하고, 키워드 프리필터는 **NER 호출 여부(비싼 단계) 게이팅**에만 쓰는 것이다.
- 단, 이 PoC는 “실제 코퍼스에서 빈도”는 말해주지 않는다. Phase 0에서 *키워드-리스 파일*의 구조화 PII 포함 비율을 측정해야, 공격적 스킵(Gemini안) 채택 여부를 결정할 수 있다.

---

## PoC 코드

- 코드: `poc/unresolved1_keyword_prefilter_poc.py`
- 실행: `python3 poc/unresolved1_keyword_prefilter_poc.py`

### 검증 내용

1. “키워드 프리필터”는 (Aho-Corasick 대신) 단순 substring 검색으로 대체해도 **정확도 논점**은 동일하므로, PoC에서는 substring 기반으로 구현했다.
2. 키워드가 전혀 없는 숫자열에 **체크섬 유효한 주민등록번호(RRN)**, 전화번호, 이메일이 포함된 케이스를 만들고:
   - 전략 A: `키워드 없으면 Regex 스킵`
   - 전략 B: `Regex/Checksum은 항상 실행`
   의 결과를 비교했다.

---

## 실행 결과 (요약)

실제 실행 출력 중 핵심 부분:

```text
[example 1] keyword_hit=False
text: '1043321819601  1043321819601  1043321819601'
skip_regex_if_no_keyword findings: []
always_regex findings: [Finding(kind='RRN', value='104332-1819601', checksum_ok=True), ...]

[example 2] keyword_hit=False
text: '01012345678 1043321819601 user@example.com'
skip_regex_if_no_keyword findings: []
always_regex findings: [Finding(kind='RRN', ...), Finding(kind='EMAIL', ...), Finding(kind='PHONE', ...)]

ASSERTION:
- keyword-less numeric-only input can contain checksum-valid RRNs: True
```

해석:
- 키워드가 0개인 텍스트에도 구조화 PII가 들어갈 수 있으므로, “키워드 없으면 Regex까지 스킵”은 구조적으로 **미탐을 만든다.**

---

## 설계 반영 권고

1. **Regex/Checksum은 항상 실행(스트리밍 + 조기 종료로 비용 최소화)**  
2. 키워드 프리필터는 **NER 게이팅에만 사용**  
3. 만약 “키워드 없으면 Regex 스킵”을 성능 최적화로 검토하려면, Phase 0에서 최소 다음 메트릭을 실제 코퍼스에서 측정:
   - `P(structured_pii | keyword_hit=false)`  
   - 파일 타입/확장자별 분포(특히 `csv/xlsx`류)

