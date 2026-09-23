# 4.3F-Pilot 完成汇报

## 1. Sample

- firms: 100
- firm-years: 531
- exchange distribution: SSE 40, SZSE 40, BSE 20
- strata distribution:
  - seasoned_current_sse: 30
  - seasoned_current_szse: 30
  - bse_transferred: 10
  - bse_post_2021: 10
  - recent_ipo_sse: 5
  - recent_ipo_szse: 5
  - delisted_sse: 5
  - delisted_szse: 5
- 抽样使用 seed `20260923` 和 firm_key SHA-256 稳定排序；各层不足时不跨层补充。

## 2. Data Retrieval

- successful firms: 90
- failed firms: 10
- blocked requests: 0
- first-run cache hit: 0/100
- second-run cache hit: 100/100
- cache files: 100，均按 firm_key 写入
- 请求范围：仅 100 家企业、2020–2025 年；未启动全市场抓取。

## 3. Field Coverage

覆盖率以 531 个实际 firm-year 为分母：

| field | coverage |
| --- | ---: |
| total_assets | 91.71% |
| total_liabilities | 91.71% |
| cash | 91.71% |
| revenue | 91.71% |
| net_profit | 91.71% |
| employees | 91.71% |
| rd_expense | 85.69% |

派生变量未发现 `inf` 或 `-inf`；资产、员工数和收入的非正输入均保持为缺失，没有生成负数对数或零分母结果。

## 4. Failure Decomposition

失败原因已输出到 `failure_decomposition.csv`，按 exchange、pilot_stratum、year、field 和 failure_reason 分解。

- 10 家失败企业集中在退市 SSE/SZSE 层，原因主要是历史接口查询失败，未观察到 API 阻断。
- 当前 SSE/SZSE 企业的主要缺失来自部分年份的 `rd_expense`，不影响核心字段成功率判断。
- BSE 企业未出现全字段查询失败，但其代码映射仍未完成，因此不能据此宣称 BSE 全量财务链已经收口。

## 5. BSE Result

```yaml
BSE transferred queried: 10
BSE native queried: 10
old code used: 0
new code used: 0
fallback used: false
status: BSE_MAPPING_REQUIRED
```

本轮没有使用前三位代码转换，也没有伪造旧代码/新代码映射。由于当前没有官方 mapping 文件，BSE 使用当前代码进行了查询，但正式全量抓取前仍需补齐并验证官方旧新代码表及 fallback 链。

## 6. Stata

已使用本机 Stata 18 MP 实际执行 `financial_pilot.dta` 校验：

- `isid firm_key year`: PASS
- year range 2020–2025: PASS
- variable types and required fields: PASS
- invalid extreme derived values: 0
- execution sentinel: `FINANCIAL_PILOT_VALIDATION_PASS`

## 7. Decision

```text
PILOT_NEEDS_FIX
```

API 未阻断、缓存复用和 Stata 导出链通过；但退市历史查询失败以及 BSE 官方 mapping 尚未完成，当前不满足直接进入 5690 家全市场财务抓取的条件。下一轮应先处理上述两项，再重新确认 full-fetch readiness。
