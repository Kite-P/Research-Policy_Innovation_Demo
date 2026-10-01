# CNIPA Full 名称缺口与旧解析缓存离线分层

## 本轮范围与状态

R4C0 对 R4B2 的状态重新核验后，当前 `targeted_diagnostic_execution_status=TARGETED_DIAGNOSTIC_PILOT_COMPLETE`，`full_name_followup_status=FULL_NAME_FOLLOWUP_REQUIRED`。94/94 行均为合法终态；来源未决、H2、OCR/人工待办是后续工作，不表示执行不完整。45 行 H1 parser discrepancy taxonomy 及 40 家样本的 aggregate 指纹/统计见 `docs/cnipa_targeted_diagnostic_pilot.md`；逐行信息留在 ignored results。

R4A 的 `FULL_NAME_DIAGNOSIS_READY_FOR_TARGETED_PILOT` 与 R4B/R4B2 旧单轴 `TARGETED_DIAGNOSTIC_PILOT_NEEDS_FIX` 均为历史状态。固定 Pilot v3 Gate 仍为 `STRICT_PILOT_GATE_PASS`；全范围状态仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`；`zero_semantics` 与 `missing_semantics` 仍为 pending。R4B/R4B2/R4C0 详情见 `docs/cnipa_targeted_diagnostic_pilot.md`。

R4C1 将唯一 parser revision 集中到 `src/cnipa_annual_report_names.py` 的 `PARSER_REVISION=issuer_scope_v3`。冻结 R4C0 45 行重放为 issuer/year-end/evidence-state 各 45/45，原 25 个正确对照无回退；但固定 14 行与其 6 个事件缺少本地原始 TXT，不能用旧 Gate summary 替代 v3 重算。因此当前 H1 修复状态是 `H1_PARSER_REPAIR_NEEDS_FIX`，strict-14 与 event no-regression 尚未验证；原 Pilot v3 Gate PASS 仅作为历史独立结果保留。未运行网络、H2、OCR 或 Full refresh，未改 Full/cache/GT。

## Full baseline 与覆盖分区

主目标是 `formal_ready` 企业的 2020—2024 firm-year。entity-year coverage 文件另含 5,089 行 2025 审计记录；这些行不属于主目标，本轮按目标键交叉核对，不混入 Full 分母。主目标的 23,448 个键与 `full_status.csv` 完全一致且唯一；`full_run_state.json` 为 `stage=full`、`status=COMPLETE`、`status_key_set_exact=true`、`target_firm_years=23448`。

| Coverage family | Firm-years |
| --- | ---: |
| `CONFIRMED_YEAR_END_NAME_ONLY` | 22,256 |
| `CONFIRMED_NAME_CHANGE` | 126 |
| `CONFIRMED_NO_CHANGE` | 18 |
| `TEMPORAL_UNRESOLVED` | 353 |
| `REPORT_NOT_FOUND` | 444 |
| `LEGAL_NAME_EXTRACTION_FAILED` | 238 |
| `REPORT_FETCH_FAILED` | 13 |
| `SOURCE_BLOCKED` | 0 |
| 合计 | 23,448 |

353 条 temporal unresolved 与 695 条 no-name 互斥；695 = 444 + 238 + 13。两组并集精确为 1,048 个 firm-year。所有类别均从当前 baseline 逐行推导，而非按预设总数补齐。

## Gap 分层结果

| Gap family | Subfamily | Firm-years | 解释 / 建议动作 |
| --- | --- | ---: | --- |
| `TEMPORAL_UNRESOLVED` | `BOTH_NAMES_NO_EVENT_PAIR_NO_DATE` | 349 | 年报中有现名与年末名，但缺少可用旧/新名事件对及日期；人工来源复核 |
| `TEMPORAL_UNRESOLVED` | `PAIR_EXACT_DATE_POST_YEAR_END` | 1 | 精确日期落在目标年末之后；针对性核对 H2 变更公告 |
| `TEMPORAL_UNRESOLVED` | `PAIR_EXACT_DATE_PRE_TARGET_YEAR` | 1 | 精确日期早于目标年；针对性核对 H2 变更公告 |
| `TEMPORAL_UNRESOLVED` | `PAIR_YEAR_PRECISION_NO_DATE` | 2 | 有名称对但只有年度精度；人工复核时间证据 |
| `REPORT_NOT_FOUND` | `HISTORICAL_SOURCE_RECORD_WITHOUT_URL` | 253 | 历史来源记录没有可复用 URL；需要定向索引查找，不据此推断官方报告不存在 |
| `REPORT_NOT_FOUND` | `LISTING_OR_DELISTING_YEAR` | 191 | 与挂牌/退市边界年重合；来源索引仍需核对 |
| `LEGAL_NAME_EXTRACTION_FAILED` | `TEXT_PRESENT_NO_MATCHED_LABEL` | 180 | 文本长度正常但没有匹配到名称标签；可在已有内容可用时评估通用解析 |
| `LEGAL_NAME_EXTRACTION_FAILED` | `NORMAL_REPORT_TITLE_NO_ISSUER_LABEL_LAYOUT_UNMATCHED` | 58 | 标题含目标年份年度报告，但发行人名称栏目版式未匹配 |
| `REPORT_FETCH_FAILED` | `TEXT_EXTRACTION_FAILURE_MISCLASSIFIED_AS_FETCH_FAILURE` | 13 | 原始失败原因为 `pdftotext` 空文本/过短；缓存未保留 HTTP 与 PDF 字节数，不能进一步推断下载失败 |

Gap roster 对每一行保留目标要求的名称字段、变更标记、时间精度、标签与上下文、来源元数据、HTTP/PDF/文本元数据、parser revision、历史来源特征、内容持久化状态、诊断依据和建议动作。没有保存的 PDF/TXT 均标为 `CONTENT_NOT_PERSISTED`；未进行 OCR 或联网补取。13 条提取失败记录逐行保留在 ignored roster，tracked 文档只报告聚合类别。

## 旧 parser 成功缓存风险

以成功状态且 cache `parser_revision != issuer_scope_v2` 识别旧版成功行，实际共 22,751 条；四个互斥风险层覆盖全部记录。

| 风险层 | Firm-years | Firms | 解释 |
| --- | ---: | ---: | --- |
| `HIGH` | 34 | 18 | 释义/分支/子公司等明显范围信号；R3F 类风险优先复核 |
| `MEDIUM` | 2,155 | 612 | 宽标签、身份名称不一致或相邻年度/时间证据需要复核 |
| `LOW` | 20,562 | 4,830 | 高精度发行人标签、干净上下文且身份名称匹配；仅表示现有元数据未发现同类风险，不等于已证明正确 |
| `INSUFFICIENT_LOCAL_EVIDENCE` | 0 | 0 | 本批未出现无法评级的记录 |

HIGH + MEDIUM + LOW + INSUFFICIENT_LOCAL_EVIDENCE = 22,751。`LOW` 不是正确性认证。仅当上下文或匹配标签等关键证据缺失时才归为 `INSUFFICIENT_LOCAL_EVIDENCE`。风险判断使用 label、evidence context、候选名称、当前 profile / 已验证历史名称及相邻年度和 temporal 标记；单独出现地名不会触发 HIGH。HIGH 共 34 条，是本轮 R3F-like branch/glossary 聚合信号。

逐层年份、交易所、建议动作分布及企业级特征位于 ignored 的 `stale_success_risk_summary.csv` 与 `stale_success_risk.csv`；没有把企业级明细放入 tracked 文档。

## 诊断 Pilot manifest

使用 seed `20260930` 对每个非空 gap subfamily 和各非空 stale 风险层确定性抽样，并纳入少量 LOW negative controls。产物为 94 个 firm-year、86 家企业，未重复且全部属于 primary target；9/9 gap subfamilies 均覆盖。stale 风险实际非空层为 HIGH、MEDIUM、LOW，均有覆盖；`INSUFFICIENT_LOCAL_EVIDENCE` 本次为 0，因此不存在可抽取案例。四类建议动作计数：`REFETCH_EXACT_H1_URL` 50、`TARGETED_CNINFO_INDEX_LOOKUP` 20、`MANUAL_SOURCE_REVIEW` 14、`NO_NETWORK_NEGATIVE_CONTROL` 10。该 manifest 仅供后续审批和诊断规划，本轮没有执行其中任何网络动作。

## 只读与复核

- `full_status.csv` SHA-256 前后均为 `203c869a9a9022b8a7160647fde6fa8b04597a2bace56a7a8aee214d2c52c291`。
- `full_run_state.json` SHA-256 前后均为 `5c6b1e719f9bd8815542f1d73154afbb813ec13be4c48b875072eeee2734592d`。
- Full cache 28,548 个 JSON 的树哈希前后均为 `d141503a01165c91ffd580cdcbc3eea49258267197bed8f3a38e6bdffa4023d9`。
- entity-year coverage、所有现有 Pilot 产物及三份 frozen ground truth 前后 SHA-256 完全相同。event GT 指纹为 `E1900A01FFF61610E1325623EC59870D9063A14C6925E4075639855745D5E174`；row GT 为 `81EB18D82611CE7BDDF7D9895ED57237026B9B5D97B0DD258DDA7D0BA266D342`；evidence-state GT 文件 SHA-256 为 `523B1A31640F29FFE9BE9B003E8E44AFC514F08E0E028AEF2A126817B7A31CF3`。
- 本轮网络请求为 0；未改写 Full、cache、coverage 或 frozen Pilot/GT 数据。

本轮只建立问题结构和下一步 diagnostic Pilot 候选，不修改任何名称记录、不执行刷新，不改变 Pilot v3 Gate、`CNIPA_ENTITY_NAME_NEEDS_FIX` 或 pending 语义状态。

本轮验证：全库 pytest 342 passed；Ruff `All checks passed!`；`uv pip check` 检查 116 packages 且全部兼容。Push hygiene 在提交前执行。
