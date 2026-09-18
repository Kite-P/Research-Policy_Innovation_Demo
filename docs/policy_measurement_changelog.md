# 2.7 政策来源与连续性测量加固变更记录

## 1. 原 measurement

第二章原主指标为 `policy_continuity_tfidf`：2019—2025 年省级政府工作报告产业文本，字符 2—4 gram，统一 `min_df=2` vocabulary，TF 为 `1+ln(count)`，平滑 IDF 为 `ln((1+N)/(1+df))+1`，L2 标准化后计算相邻年度 cosine similarity。

## 2. 加固原因

原 manifest 没有显式 source tier，历史下载异常混在当前 notes 中，连续年度 pair 没有来源质量字段，也没有 pair-level text-volume controls。原指标的 IDF 使用全样本语料，因此新增 expanding-window 指标作为 no-look-ahead robustness，不改变原主指标。

## 3. Source tier

逐条人工规则核验后，49 条来源分为：Tier 1 `direct_provincial_official` 30 条，Tier 2 `other_government_official` 11 条，Tier 3 `official_or_state_media_reprint` 4 条，Tier 4 `other_complete_reprint` 4 条。每条记录均有 `source_tier_reason` 和 `source_tier_verified=1`。

当前未完成可审计的 canonical source 替换。湖北 2022 的省政府 PDF 搜索结果仍可被检索到，但当前请求返回 404，因此没有把不可下载链接替换进 manifest；保留原中国网完整转载，标记为 Tier 4，并保留其历史来源说明。

历史 `fetch_error=PermissionError` 等信息已迁移到 `retrieval_history_note`，当前 49/49 的 `retrieval_status` 均为 `success`，两类状态不再混用。

## 4. Pair quality fields

新增 `source_tier_current`、`source_tier_previous`、`source_tier_max`、`source_tier_changed` 和 `both_direct_official`。2019 年因无 lag，所有 pair 字段保持 missing；2020—2025 年均有有效 pair。

## 5. Expanding-window metric

新增 `policy_continuity_tfidf_expanding`。每个年份的 TF-IDF vocabulary 和 IDF 只使用不晚于该年的报告，之后仍比较同一省份的 t 年与 t-1 年产业文本。2020—2025 共 42 个有效值，均值 0.3360，范围 0.0702—0.5454；与原主指标 Pearson 相关 0.8936，排序相关 0.8922。

通过未来文本变异测试：只改变 2025 年文本时，2020—2024 年 expanding 指标完全不变。

## 6. Pair-level text-volume controls

新增：

- `pair_mean_log_industry_chars`
- `abs_log_industry_length_change`
- `pair_mean_log_full_chars`
- `abs_log_full_length_change`

这些字段只用于后续稳健性控制，不进入 primary metric 定义。

## 7. Measurement revision audit

`results/policy_continuity/measurement_revision.csv` 显示旧版与新版 `policy_continuity_tfidf` 的 42 个有效 pair 中，变化数量为 0，最大绝对差和中位绝对差均为 0。原因是本次没有替换可下载 canonical raw source，且清洗规则和 primary TF-IDF 定义保持不变。

## 8. 对第二章结论的影响

第二章原 primary metric 没有被重新定义或替换；2.7 只增加来源透明度、no-look-ahead robustness 和 pair controls。第二章关于政策表述连续性 proxy 的限制仍然有效，不能将该指标解释为政策执行强度或真实政策稳定性。
