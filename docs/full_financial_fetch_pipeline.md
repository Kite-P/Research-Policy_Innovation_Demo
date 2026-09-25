# 4.3F-Full-Pipeline 真实财务抓取

## 当前状态

- 全量抓取状态：`SSE_SZSE_FULL_FETCH_COMPLETE`
- 来源总体：5,690 家企业、30,328 个 firm-year
- Phase A：5,272 家 SSE/SZSE 非金融企业、28,548 个 firm-year
- 分块：53/53 完成
- 状态计数：5,008 `COMPLETE`、4 `PARTIAL`、260 `QUERY_FAILED`、0 `NOT_FETCHED`、0 `SOURCE_BLOCKED`
- 面板键：重复 `firm_key + year` 为 0；上市/退市日期边界之外的 firm-year 为 0
- 当前企业核心字段完整率：SSE 99.1688%，SZSE 99.4936%，均通过 90% Gate
- 当前企业 R&D 覆盖率：SSE 92.3531%，SZSE 95.4295%
- 正式 Stata sentinel：`FINANCIAL_SSE_SZSE_FULL_VALIDATION_PASS`
- BSE：`BSE_MAPPING_REQUIRED`；金融业企业：132 家，排除在 Phase A 之外

Phase A 仅覆盖 SSE/SZSE 非金融企业，不代表来源总体 5,690 家全部完成财务抓取。失败的退市企业保留在目标面板及状态汇总中，不因失败而从研究总体删除。

## 目标与数据边界

正式目标根据 enriched universe 和冻结的行业规则确定。SSE/SZSE 中行业已知的非金融企业进入 Phase A；286 家 BSE 企业保留为待官方新旧代码映射对象；132 家金融业企业标记为 `excluded_financial`。不使用证券代码前三位推算 BSE 映射。

每家企业的缓存以 `firm_key` 为键，缓存和运行状态均为本地数据，不纳入 Git。抓取使用至少 1 秒间隔、单进程执行、断点续跑；源站阻断时停止，不绕过访问控制。

## 最终验证

- Finalizer 核对 manifest、run state、53 个 chunk、firm 状态及合法 firm-year 集合后，生成正式 parquet 和 Stata `.dta`。
- Stata/MP 18 实际验证通过 `isid firm_key year`、2020—2025 年份、交易所范围、变量数值类型及派生变量有限值检查。
- 总面板核心字段缺失数（含退市企业）：资产 1,092；负债 1,092；现金 1,092；营业收入 1,095；净利润 1,092；员工人数 1,093。退市样本缺失按观测保留，不补零。
- Stata 面板规模：5,272 家、28,548 个 firm-year；SSE 12,413 行、SZSE 16,135 行。

## 早期 Canary

早期 200 家 canary 用于抓取链路验证：1,114 个 firm-year，二次执行 200/200 缓存命中；Stata sentinel 为 `FINANCIAL_FULL_CANARY_VALIDATION_PASS`。该 canary 已由上述正式 Phase A 结果取代，不作为当前全量完成状态的依据。

## 后续边界

BSE 正式抓取须等待用户提供合法取得的官方新旧代码映射。CNIPA 专利收集、政策匹配及回归均未在本阶段执行。
