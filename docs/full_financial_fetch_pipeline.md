# 4.3F-Full-Pipeline 真实财务全量抓取流水线

## 1. 流水线状态

- Pipeline status: `FULL_FETCH_PIPELINE_READY`
- Full fetch status: `NOT_EXECUTED`
- Source universe: 5,690 firms and 30,328 firm-years
- Full target manifest: 5,272 firms and 28,548 firm-years
- Formal fetch phase: SSE/SZSE nonfinancial firms only
- BSE phase: retained in the manifest as `BSE_MAPPING_REQUIRED`
- Financial-industry firms: retained as `excluded_financial`

The 5,690-firm fetch has not been started. This round only executed the formal 200-firm canary.

## 2. Target and chunk design

The target is built from the enriched company universe and fingerprinted by the sorted `firm_key` and `year` pairs. Phase A contains SSE/SZSE firms with known nonfinancial industry status, including current and delisted firms. Phase B contains BSE nonfinancial firms but is not formally executable until the official old/new code mapping is supplied. Financial firms remain visible in the manifest and are excluded from fetching.

Phase A contains 5,272 firms and is divided into 53 deterministic chunks of 100 firms or fewer. Cache files are isolated under the full-pipeline result directory and are never copied from the pilot cache. Cache validity requires the complete schema and exact firm-year key set.

Run state is written atomically after each firm. A stale or structurally invalid cache is refetched; a source-blocking response stops the run and records the blocking state. The universe fingerprint is checked before resuming.

## 3. 200-firm canary

- Firms: 200
- Firm-years: 1,114
- SSE: 92 firms
- SZSE: 108 firms
- Current: 191 firms
- Delisted: 9 firms
- First pass: 191 complete firms; 9 delisted firms had 37 failed firm-years with `QUERY_FAILED`
- Source-blocked requests: 0
- Duplicate firm-year keys: 0
- Core field coverage: 96.6786% for each of `total_assets`, `total_liabilities`, `cash`, `revenue`, `net_profit`, and `employees`
- R&D coverage: 88.4201%
- Current SSE core completeness: 100%
- Current SZSE core completeness: 100%

The second pass read all 200 firm caches without issuing new financial requests: `200/200 CACHE_HIT`. The final canary report is therefore `FULL_FETCH_PIPELINE_READY`.

## 4. Stata validation

The exported `canary_200.dta` was checked in Stata for firm-year uniqueness, year range, exchange scope, derived-variable finiteness, and invalid numeric values. The actual log contains the sentinel `FINANCIAL_FULL_CANARY_VALIDATION_PASS`.

## 5. BSE boundary

BSE firms remain in the manifest but are not included in the canary. The official old/new BSE code mapping is still required; no prefix-based code conversion is used.

## 6. Decision

The full financial fetch pipeline is ready for a later user-authorized full run. The 5,690-firm fetch, policy matching, patent collection, and regression analysis were not started in this round.
