# CNIPA 申请人名称预检

## 范围与结论

目标来自完成身份键纠正后的沪深非金融企业 Phase A：5,269 家、28,537 个 2020—2025 firm-year。主窗口 2020—2024 为 23,448 行；2025 年 5,089 行仅作覆盖审计。目标键与本地正式 manifest、财务面板和历史省份面板逐行一致。来源总体为 5,687 家、30,317 行；BSE 286 家仍待官方映射，金融业企业 132 家继续排除。

身份审计确认 600555、600190、600614 的早期挂牌日期分别属于同一发行人的 B 股，而旧 firm_key 错用了 A 股代码。正式目标现保留 A 股挂牌键、排除 3 个经官方年报及同一 ORG_CODE/年报公告序列确认的 B 股日期别名。旧正式财务缓存及历史省份观测均已复用，不重新抓取。此纠正使总体和下游面板目标计数相应减少；三个身份别名不再形成名称碰撞或重复赋权。

当前状态仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`。当前法人名称覆盖 5,269/5,269；但主窗口仍有 353 个名称时间关系未决，695 行没有可用法人名称提取结果，部分报告未找到或解析失败。因此，本报告不认定历史法人名称 universe 已达到正式专利采集 Gate。

## 名称来源与字段语义

当前法人名称来自 EastMoney F10 `ORG_NAME`，并经过 Profile、来源字段和组织代码一致性核验。EastMoney `FORMERNAME` 已冻结为 `FORMER_SECURITY_NAME_ONLY`，不得作为历史法人名称来源。现有 2,306 家企业对应 6,417 条 `FORMERNAME` 候选全部标记为 `rejected_stock_abbreviation / REJECTED`，`query_eligible=0`。

年报抽取器使用 CNINFO 正式年度报告正文，并区分法人全称与证券简称。固定 seed 的既有 Pilot 为 92 家、461 个 firm-year；425 份报告成功取得，423 个名称完成上下文人工复核，名称精确率 100%，证券简称误判 0%，缺失率 8.24%。 tracked 历史 audit 曾记录 5 个名称变更相关 cases、变更标记及旧/新名称解析各 3/5；这是历史结果，不是 R3E 当前 canonical 分母。Pilot 结果不被当作 Full 的全范围质量通过证明。

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

R3 的判断属于当时状态：同一 seed、92 家和 461 个 firm-year 的既有 Pilot 中，legacy review CSV 有 6 行；旧冻结 roster 已遗失，故 R3 未尝试复原，也未将行数当作事件数。R3 当时 strict Gate 未通过。该阶段结论由后续 R3E 前瞻冻结的事件级 roster 与行级审核取代；历史 5 cases / 3-of-5 仅作为旧 tracked 结果保留。

R3 的本地 v1 摘要不构成 R3E 的 Gate 输入，也不授权 Full。

## 4.4A-R3E 规范化更名事件 Pilot Gate

固定样本未变：seed `20260927`、92 家、461 个 firm-year。新的确定性候选集包含 14 个 change-related candidate firm-year rows；其中 12 行映射到 6 个有来源支持的独立法人名称变更事件，另 2 行经行级审核判为非更名事件并记录排除理由和官方年报来源。事件数与行数分别计量。

六个事件为：600936 的 2025 年变更、300237 的 2024 与 2025 两次变更、603003 的 2023 年变更、002059 的 2010 年历史变更、603196 的 2026 年变更（该事件仅用于解释 2025 年报的后续名称，不将 2025 年 firm-year 标为发生变更）。300237/2025 的公告未载明具体工商登记日，按 year precision 保存，不推定日级日期。

300237/2024 的官方公告确认“山东美晨生态环境股份有限公司→山东美晨科技股份有限公司”，工商登记日为 2024-08-13；600936/2025 的官方公告确认“广西广播电视信息网络股份有限公司→广西北投科技股份有限公司”，登记日为 2025-12-31。300237 两份公告及 600936 公告共进行 3 次定点 H2 官方来源复核。历史 5 cases / 3-of-5、legacy CSV 的 6 条 review rows、新 canonical 6 distinct events / 12 event-linked rows / 14 candidate rows 分属不同口径，不能互作同一分母。

新 ignored 文件为 `pilot_change_candidate_rows.csv`、`pilot_change_event_roster.csv`、`pilot_change_row_review.csv`；v2 摘要 schema 为 `cnipa_strict_pilot_gate_v2`。事件旧名、新名、可核实精确日期准确率均为 1.0；事件相关 firm-year change flag 与 year-end legal name 准确率均为 1.0；legal-name precision 为 1.0，证券简称误判 0，人工未审 0，未决候选/事件均为 0。v1、legacy summary 和 `--pilot-pass` 单独均不能授权 Full；Full 仍需 v2 与三份指纹匹配审核文件。本轮没有启动 Full 或 targeted refresh，Full evidence cache 保持不变。

CNIPA 全范围状态仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`：主窗口的 353 个时间关系未决和 695 行缺少年报法人名称尚待后续处理；`zero_semantics` / `missing_semantics` 仍为 pending。verified historical names 仍为 3，unique query names 仍为 5,269。未访问 CNIPA 专利系统，未检索或下载专利。

R3E 全库 pytest：311 passed；Ruff：`All checks passed!`；uv 依赖检查：116 packages compatible；push hygiene：PASS。
