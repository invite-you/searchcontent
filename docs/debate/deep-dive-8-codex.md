# Deep Dive 8 (Codex): MVP 실시간 감지에서 “즉시 스캔” vs “큐잉 + 리소스 거버너”

**대상 미합의:** `docs/debate/unresolved.md`의 *미합의 8*  
**목표:** 이벤트 폭주 상황에서 “즉시 스캔”과 “큐잉 + CPU 예산”의 트레이드오프를 PoC로 수치화

---

## 결론 (PoC 기준)

- “즉시 스캔”은 이벤트가 burst로 들어오는 순간 **CPU 점유율이 상승**하고 backlog가 생긴다(=사용자 업무 방해 리스크).
- “큐잉 + CPU 예산(예: 10%)”은 CPU를 지킬 수 있지만, backlog가 큰 경우 **처리 지연(P95)이 수십 초~분 단위**로 늘어날 수 있다.
- 현실적인 정책은 “즉시 스캔 vs 큐잉”의 이분법이 아니라:
  - 워처 이벤트는 **항상 큐잉**
  - 스캔 실행은 **동적 예산(active vs idle)** 으로 조정
  - backlog/사용자 활동에 따라 f를 올려서 야간/유휴에 빠르게 따라잡는 방식

---

## PoC 코드

- 코드: `poc/unresolved8_realtime_queueing_poc.py`
- 실행: `python3 poc/unresolved8_realtime_queueing_poc.py`

### PoC 모델(단순화)

- 파일 이벤트가 시간에 따라 도착(버스트):
  - 200 events/s * 2s (400개)
  - 10 events/s * 8s (80개)
  - 총 480개
- “가벼운 스캔(Regex/Validator만)”을 파일당 `scan_cost_ms=15ms CPU`로 모델링
- 정책:
  - immediate: 이벤트 도착 즉시 스캔(단일 워커)
  - queued_with_budget(f): CPU duty cycle을 f로 제한(단일 워커)
  - active_then_idle: active 구간은 f=0.10, 마지막 이벤트 이후는 f=0.50로 backlog를 빠르게 드레인

---

## 실행 결과 (요약)

```text
events=480 scan_cost_ms=15.0

immediate (scan right away)
  cpu_fraction=0.726
  p95_latency_s=3.795

queued_with_budget(f=0.10)
  cpu_fraction=0.100
  p95_latency_s=60.900

active_then_idle(active=0.10 idle=0.50 ...)
  cpu_fraction=0.323
  p95_latency_s=17.500
```

해석:
- 즉시 스캔은 지연이 비교적 작지만, 그만큼 CPU를 공격적으로 사용한다.
- “조용한 에이전트”를 목표로 CPU 예산을 낮추면, 지연이 크게 늘 수 있다.
- 따라서 실시간 워처는 “즉시 스캔”이 아니라 “큐잉”만 담당하고, 실제 스캔은 **동적 거버닝**이 필요하다.

---

## 설계 반영 권고

1. 워처(`ReadDirectoryChangesW`)는 **큐 적재까지만** 하고, 스캔 트리거는 스케줄러/거버너가 결정  
2. 거버너는 최소 다음 신호를 사용(Phase 0에서 실측 필요):
   - 사용자 활동(입력/포그라운드 앱)
   - CPU/IO 사용률
   - 큐 backlog 크기
3. Phase 0에서 반드시 측정할 것:
   - 핵심 3폴더 이벤트율(평균/버스트)
   - 포맷별 “가벼운 스캔” 비용(Regex/Checksum) vs “무거운 스캔”(추출/NER) 비용
   - f(active/idle) 기본값 후보와 그때의 P95 지연

