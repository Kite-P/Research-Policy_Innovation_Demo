# CNIPA 申请人名称预检

## 范围与结论

目标来自完成身份键纠正后的沪深非金融企业 Phase A：5,269 家、28,537 个 2020—2025 firm-year。主窗口 2020—2024 为 23,448 行；2025 年 5,089 行仅作覆盖审计。目标键与本地正式 manifest、财务面板和历史省份面板逐行一致。来源总体为 5,687 家、30,317 行；BSE 286 家仍待官方映射，金融业企业 132 家继续排除。

身份审计确认 600555、600190、600614 的早期挂牌日期分别属于同一发行人的 B 股，而旧 firm_key 错用了 A 股代码。正式目标现保留 A 股挂牌键、排除 3 个经官方年报及同一 ORG_CODE/年报公告序列确认的 B 股日期别名。旧正式财务缓存及历史省份观测均已复用，不重新抓取。此纠正使总体和下游面板目标计数相应减少；三个身份别名不再形成名称碰撞或重复赋权。

当前状态仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`。当前法人名称覆盖 5,269/5,269；但主窗口仍有 353 个名称时间关系未决，695 行没有可用法人名称提取结果，部分报告未找到或解析失败。因此，本报告不认定历史法人名称 universe 已达到正式专利采集 Gate。

## 名称来源与字段语义

当前法人名称来自 EastMoney F10 `ORG_NAME`，并经过 Profile、来源字段和组织代码一致性核验。EastMoney `FORMERNAME` 已冻结为 `FORMER_SECURITY_NAME_ONLY`，不得作为历史法人名称来源。现有 2,306 家企业对应 6,417 条 `FORMERNAME` 候选全部标记为 `rejected_stock_abbreviation / REJECTED`，`query_eligible=0`。

年报抽取器使用 CNINFO 正式年度报告正文，并区分法人全称与证券简称。固定 seed 的既有 Pilot 为 92 家、461 个 firm-year；425 份报告成功取得，423 个名称完成上下文人工复核，名称精确率 100%，证券简称误判 0%，缺失率 8.24%。5 个名称变更相关 Pilot 案例中，变更标记及旧/新名称解析各有 3/5 完全匹配（60%）；Pilot 结果不被当作 Full 的质量通过证明。

## 2020—2024 年报证据恢复

Full 目标与 status 键集合精确一致，共 23,448 行。处理复用了 Historical Province 的 CNINFO 报告索引、已保存的年报证据和本地状态缓存；本轮身份纠正只筛除错误 firm_key 并重新汇总，没有重新下载报告。

| 指标 | 结果 |
| --- | ---: |
| 报告成功获取 | 22,991 |
| 抽取到法人名称 | 22,753 |
| `CONFIRMED_YEAR_END_NAME_ONLY` | 22,256 |
| `CONFIRMED_NAME_CHANGE` | 126 |
| `CONFIRMED_NO_CHANGE` | 18 |
| `TEMPORAL_UNRESOLVED` | 353 |
| `REPORT_NOT_FOUND` | 444 |
| `LEGAL_NAME_EXTRACTION_FAILED` | 238 |
| `REPORT_FETCH_FAILED` | 13 |
| `SOURCE_BLOCKED` | 0 |

以上 coverage 状态互斥且合计 23,448。即使底层抽取状态为 `COMPLETE_NO_CHANGE`，若时间证据同时为 `TEMPORAL_UNRESOLVED`，coverage 仍按时间未决计，不作已确认解释。年报证据的 URL、公告编号、PDF 哈希、名称上下文及失败原因仅留在 ignored 本地结果。

## 2025 覆盖审计

2025 年 5,089 个目标 firm-year 中，报告成功获取 5,013 个，抽取到法人名称 4,967 个。状态为：4,826 `CONFIRMED_YEAR_END_NAME_ONLY`、37 `CONFIRMED_NAME_CHANGE`、7 `CONFIRMED_NO_CHANGE`、97 `TEMPORAL_UNRESOLVED`、68 `REPORT_NOT_FOUND`、46 `LEGAL_NAME_EXTRACTION_FAILED`、8 `REPORT_FETCH_FAILED`；来源封锁为 0。该年度不进入主专利 outcome window。

## 历史名称、碰撞与查询批次

正式披露支持的历史法人全称共 3 个，涉及 2 家企业；未验证的前名不进入查询。纠正身份键后，预检保留 3 组规范化名称碰撞，均为不同证券代码间共享查询名并保留完整映射；未解决碰撞组为 0。名称碰撞只解决到名称查询与实体映射层，不代表专利结果已取得或完成按申请日期归属。

当前查询预检包含 5,269 个唯一可查询名称、5,272 条名称—firm_key 映射及 264 个确定性批次；每个名称恰好进入一个批次，最大查询字符串长度为 374。`max_names=20`、`max_chars=1500` 仍为未在 CNIPA 页面实测的项目参数，状态为 `CNIPA_QUERY_LIMIT_UNCONFIRMED`。

## Gate 与边界

- 当前法人名称覆盖完整，`FORMERNAME` 语义保持冻结，全部证券简称候选排除。
- 三个 B/A 双重挂牌实体的伪重复键已纠正，财务与历史省份面板均已按新目标重建；历史省份 Gate 通过。
- 仍有 353 个主窗口时间关系未决及 695 个主窗口 firm-year 未抽取到年报法人名称，故维持 `CNIPA_ENTITY_NAME_NEEDS_FIX`。
- `zero_semantics`、`missing_semantics` 仍为 `pending`；没有 CNIPA 登录、专利检索/下载、企业—专利归属或回归。
- 企业级名称、逐年证据、碰撞详情、PDF 哈希和 query 明细均为本地 ignored 数据，不纳入版本控制。
- R2 身份纠正轮当时 pytest：292 passed；Ruff：`All checks passed!`；116 个依赖兼容；推送卫生和 Markdown 检查通过。该数字是上一轮历史结果。

## 4.4A-R2K 实体键纠正后的只读复核

CNINFO 身份键更正后，现有名称与 year coverage 文件仅按新 firm-year key 做了只读对齐；本轮未登录 CNIPA、未发起 CNIPA 请求，也未下载专利。当前 primary 目标为 23,448 个 firm-year，2025 审计为 5,089 个 firm-year；名称键与当前目标相符。

严格按冻结的 Pilot Gate 复核，pilot Gate 不通过，Full 状态保持 `FULL_EVIDENCE_CACHE_PRE_GATE`，整体仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`。本地 ignored 的 `pilot_summary.json` / `pilot_run_state.json` 却报告 6 个案例、全项 1.0 和 `pilot_gate_pass=true`，与计划记录的 5 个变更案例及 Gate 未通过结论冲突。为避免覆盖原始证据，本轮未修改这些文件；该冲突不作为通过依据。353 个时间关系未决、695 个主窗口 firm-year 未抽取到法人名称；`zero_semantics`、`missing_semantics` 仍为 pending。R2K 最终全库 pytest：294 passed；Ruff：`All checks passed!`；uv 依赖检查：116 packages compatible；push hygiene：PASS。

## 4.4A-R3 严格 Pilot Gate 收口

R3 对同一 seed、92 家和 461 个 firm-year 的既有 Pilot 做了本地只读取证，没有重新抽样或请求 H2。现存 `pilot_context_audit.csv` 有 6 行被标记为当前已审核的更名相关 firm-year；旧 `_finalize_pilot_audit()` 将这些行数直接当作独立案例数，并用该文件自身的标注覆盖 legacy summary，因此 `6 / 1.0 / PASS` 不能证明冻结 Gate 通过。跟踪文档保留的冻结结论仍是 5 个案例、各项准确率 3/5。冻结版逐案 roster/版本没有留存，故无法证据化指出当前 6 行中的哪一行是冻结口径之外的第六项，也不能把行数推断成唯一事件数；canonical denominator 当前未能确定。

本地 ignored 输出新增 `pilot_gate_reconciliation.csv` 与 `pilot_strict_gate_summary.json`。严格摘要记录 92/461、样本/目标/来源证据 SHA-256 指纹、6 条 legacy review 行、未确定的案例分母和 `PILOT_GATE_NOT_PASSED`。它不改写原 `pilot_summary.json`，也不授权 Full。未来必须有独立冻结的 `pilot_gate_case_review.csv`，逐例提供人工结论及证据链接，并通过样本、目标和来源证据指纹校验后，才可判定 Gate。

Runner 已阻断旧 summary 与 `--pilot-pass` 单独授权 Full；H2 公告现须明确形成所审核的旧名→新名关系，不能仅凭公告中分别出现两个名称和通用“完成变更”语句通过。增加 H1/H2 时间解析和严格 Gate 回归测试。现有缓存证据记载 `300237` 2024 年更名于目标年内完成，`600936` 2025 年更名于 2025-12-31 完成；本轮没有新的 H2 网络请求，也未重下年报。Full cache 保持 `FULL_EVIDENCE_CACHE_PRE_GATE`，没有 targeted refresh。总状态仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`；353 个时间关系未决、695 行缺少名称，`zero_semantics` / `missing_semantics` 保持 pending；未访问 CNIPA 专利系统。
