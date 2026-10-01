# 4.4A-R4B CNIPA 定向诊断 Pilot

## 4.4A-R4C1-G3 Strict-14 离线失败分解（2026-10-01）

本轮 G3 仅读取 G2 冻结产物及本地 H1/H2 正文，网络请求=0、专利系统访问=0；不改生产 parser/revision、H1/H2 源文件、GT、Full/status/cache 或 Gate。4 个 H2 targets 中 2 个已解决，另 2 个分别为公告正文版式导致的 extractor gap、以及 discovery 无公告但既有 H1 年报已明确事件的情形。4 份已取回公告正文均含预期名称对，其中 2 份支持已完成事件、2 份仅为待审批/待登记阶段；1 份完成公告虽明确 issuer、名称对与 2025 年末登记日，当前 extractor 仍未识别。3 个 discovery audit 均未保存完整分页总数；未发现超过 3 份已返回候选的证据，但不能据此证明检索集合穷尽。

固定 6-event denominator：正确 3，未解决 3，分别归为 H2 extractor gap、H1 年报事件未进入 event roster、以及 H2 年度精度事件缺少规范化有效年份。故 2 个 unresolved H2 target 并不直接造成 3 个 unresolved events。固定 14-row denominator：fused 正确 4/14、失配 10/14；失配分为 H2 dependency 2、H1 residual 3、event propagation 3、event mapping 2。失败依赖图合计 5 个机制。唯一 year-end mismatch 属于 H1 temporal/year-end parser residual。300365 negative control 通过。Frozen45 仍为 45/45/45，prior-correct25 regressions=0。

当前 Gate 仍为 `STRICT_PILOT_GATE_REPLAY_INCOMPLETE`；`h1_parser_repair_status=H1_PARSER_REPAIR_NEEDS_FIX`，reason=`current_v3_residual_h1_error+pending_canonical_replay_evidence`。`FULL_WIDE_REPARSE_BLOCKED` 有效；GT、Full/status/cache 前后 hash 一致。Parser revision 仍为 `issuer_scope_v3`。逐项取证与哈希清单仅位于 ignored `results/cnipa_preflight/strict14_g3_forensics_20261001/`。

## 执行结论

## 4.4A-R4C1-G2 canonical-equivalent replay baseline（已由 G3 细分，2026-10-01）

R4C1-G2 复用 14/14 精确 H1 PDF/TXT、URL 与双文件 SHA-256 provenance，H1 GET=0；冻结 row/evidence key fingerprint 仍为 `9a5dcbf6099c43b41711518d5dd5772d2d9eb20346e98fe632d5be178161bee1`。三份 frozen GT raw SHA-256 均保持冻结值。R4C1-G 的 2/14 evidence-state 与 13/14 year-end 明确归类为 `H1_ONLY_NON_EQUIVALENT_REPLAY_RESULT`，不作为 canonical parser Gate accuracy。

候选构造调用 canonical `_build_pilot_change_candidate_rows()`：G1 旧候选数 2，G2 H1-only canonical 候选数 7，H2 融合后仍为 7；其中相邻年度名称差异候选标记 5 行。离线 H2 manifest 共 4 个 firm-year，全部由 H1 相邻轨迹或旧非 GT H1 候选来源独立推出；无 `H2_QUERY_PAIR_UNDERIVED`。有效本地 H2 carry=1；bounded discovery=3；公告 PDF GET=4；累计 H2 guarded HTTP attempts=10/24；作用域护栏曾拦截 1 次未发送的错误参数请求；SourceBlocked=0。H2 独立确认 2 条（本轮公告 1 条、既有 carry 1 条）。600936/2025 的 3 份官方 PDF 均 HTTP 200，但 production extractor 未确认预期 pair；603003/2023 的限定 discovery 未找到候选公告。

固定 14 行结果：H1-only evidence-state 2/14、year-end 13/14；canonical fused evidence-state 4/14、year-end 13/14。四条事件预测对固定 6-event 分母评分：old/new/date/date-precision 各 3/6，unresolved=3。由于两个所需 H2 evidence replay 未完成，current Gate=`STRICT_PILOT_GATE_REPLAY_INCOMPLETE`，不是 parser failure；`h1_parser_repair_status=H1_PARSER_REPAIR_NEEDS_FIX`，原因=`pending_canonical_replay_evidence`。未改 parser，revision 保持 `issuer_scope_v3`。

300365/2020 与 /2021 的 H1 flags 均为 `UNKNOWN`，两条年末 issuer name 均正确；“成都分公司”没有进入 issuer。frozen45 issuer/year-end/evidence-state 均 45/45，prior-correct25 regressions=0。GT 三文件、Full status/run state/cache 均与冻结 hash 一致（cache 28,548 files / 40,412,037 bytes）；`FULL_WIDE_REPARSE_BLOCKED` 仍有效。未访问专利系统。其它状态保持：`TARGETED_DIAGNOSTIC_PILOT_COMPLETE`、`FULL_NAME_FOLLOWUP_REQUIRED`、`CNIPA_ENTITY_NAME_NEEDS_FIX`，zero/missing semantics 均 pending。逐行材料仅在 ignored `results/cnipa_preflight/strict14_g2_replay_20261001/`。

## 4.4A-R4C1-G H1-only Strict-14 replay（历史非等价诊断，2026-10-01）

冻结 row key 为 14/14 且与 evidence-state GT key set 完全一致，key fingerprint=`9a5dcbf6099c43b41711518d5dd5772d2d9eb20346e98fe632d5be178161bee1`。本地没有精确可复用 PDF/TXT；仅从已有 source metadata 对 14 个精确 CNINFO H1 年报 URL 各 GET 一次，HTTP 200 为 14/14，PDF/TXT 校验均通过，source block=0；H2 request=0。三份 GT 原始 SHA-256 与冻结值一致且未修改。

该轮 `issuer_scope_v3` H1-only row denominator 固定为 14：evidence-state 2/14、year-end name 13/14；parser candidate rows=2。因未复现 H2 row fusion 和 canonical adjacent-name candidate semantics，这些数值为非等价诊断，不能作为 canonical Gate 结论。六事件旧报表得分各 3/6。随后由 G2 canonical-equivalent fused replay 取代当前 Gate 判断。

冻结 45-row corpus 以当前 parser 重放为 issuer/year-end/evidence-state 各 45/45，prior-correct 25 行 regressions=0。诊断执行仍为 `TARGETED_DIAGNOSTIC_PILOT_COMPLETE`，follow-up=`FULL_NAME_FOLLOWUP_REQUIRED`，全范围=`CNIPA_ENTITY_NAME_NEEDS_FIX`，zero/missing semantics 均 pending。无 Full、专利系统、OCR 或其它研究流程访问；逐行材料只在 ignored `results/cnipa_preflight/strict14_v3_replay_20261001/`。

## 4.4A-R4C0 状态闭合与 H1 误差分类（2026-10-01）

R4C0 将执行完整性与名称修复准备度分开判定。冻结的 94 行 / 86 家 Pilot 已有 94/94 个合法终态；53 条请求审计序号连续，64 条来源 provenance 全部映射，保护对象前后 SHA-256 一致。因此 `targeted_diagnostic_execution_status=TARGETED_DIAGNOSTIC_PILOT_COMPLETE`。其中 2 行 `SOURCE_UNRESOLVED`、44 行 `TARGETED_H2_REQUIRED`、10 行 `OCR_OR_MANUAL_REQUIRED` 均是已记录的终态，不再被误判为执行未完成。

当前 `full_name_followup_status=FULL_NAME_FOLLOWUP_REQUIRED`：仍有 H1 parser discrepancy、H2、OCR/人工及来源/索引待办。它不改变 `cnipa_entity_name_scope_status=CNIPA_ENTITY_NAME_NEEDS_FIX`；Pilot v3 Gate 仍为 `STRICT_PILOT_GATE_PASS`，`zero_semantics` 与 `missing_semantics` 仍为 pending。旧单轴 `TARGETED_DIAGNOSTIC_PILOT_NEEDS_FIX` 仅作为旧状态定义下的历史记录，不再表达当前执行完整性。

冻结的 45 个独立复核有效 H1 行（40 家）重算为 issuer 27/45、year-end 26/45、evidence-state 28/45；这是困难诊断样本，不是总体准确率。互斥 overlap 为：三项全对 25、仅 evidence 错 1、issuer 与 year-end 错 3、year-end 与 evidence 错 1、三项全错 15，其余类别为 0。发生至少一项偏差的 20 行中，通用根因分布为 `LABEL_LAYOUT_UNMATCHED` 14、`ISSUER_SCOPE_ERROR` 3、`TEMPORAL_EVIDENCE_OVERCLAIM` 2、`FIELD_BOUNDARY_ERROR` 1。MEDIUM 的边界问题确认是完整回答标记边界处理误删合法名称首字“无”；不包含企业特判。HIGH 中仍错的两行根因不同，分别为标签版式未覆盖和发行人范围误取。此前 12 个完整年报正文布局缺口在本轮均归为 `LABEL_LAYOUT_UNMATCHED`。17 个 evidence-state 错配按原始状态转移为：`LEGAL_NAME_EXTRACTION_FAILED` → `CONFIRMED_YEAR_END_NAME_ONLY` 14（明确名称证据漏提取）、`CONFIRMED_NO_CHANGE` → `CONFIRMED_YEAR_END_NAME_ONLY` 2（把未证实的无变更编码成 NO）、`CONFIRMED_YEAR_END_NAME_ONLY` → `CONFIRMED_NAME_CHANGE` 1（变更事件证据未提取）。由于“仅确认年末名称”不是“确认无变更”，此处保留原始类别，不将不同语义压成单一 YES/NO/UNKNOWN 轴。另有 25 行虽需 H2，但三项 H1 parser 输出均正确；H2 需求不计作 parser 错误。

固定回归语料的指纹如下，R4C1 parser 变更须绑定此组输入：reviewed keys `6d4b0b4d7f7d9bcebb3ffd34917b96f6329146a40fbe4458ff786471349bfdbd`；PDF/TXT evidence hashes `ae73d34758d8cfdb0a6e4a051ec8c1bd79c5e59d1082338b87bcdff5e64e777b`；parser predictions `5f0bf6ea30e99684106736c43be1c7f7f94cfb5715bf53d10499a13077ab581b`；independent review values `c2106221ceed4aa15c0d5b8d77204a36ceb07b3a1d4543b83cc02dedc04c43c4`；45-row corpus frame `a91d65868abc56c5fc537ce76b3d25fb82f6c434cecf17a780293b8bb8da0f80`；independent review source artifact SHA-256 `10aef21a9f2d441ed307a979c6e945197404f225301c91bdd332c43ecd9c4a81`。R4C1 plan 仅提出通用候选，尚未实施 parser 修改。

复现语料、逐行 TXT/审查依据、指纹、分类表及 R4C1 通用修复候选仅保存在 ignored `results/cnipa_full_gap_diagnosis/r4c0_20261001/`。本轮网络、H2、OCR、Full refresh 均为 0；生产 parser、Full 状态/cache、coverage 和 frozen GT 未改。

> 以下 R4C1 初始记录形成于 strict-14 源文件恢复之前；其中“无法重算”的状态已由本页 R4C1-G2 canonical-equivalent replay 结果取代。

## 4.4A-R4C1 H1 parser 通用修复结果（2026-10-01）

R4C1 对冻结的 45 行 / 40 家 VALID_FULL_H1 corpus 重放前确认 R4C0 reviewed-key、evidence-hash、baseline-prediction、independent-review 与 frame fingerprints 均与冻结摘要一致；v2 baseline 为 issuer 27/45、year-end 26/45、evidence-state 28/45，原本三项全对 25 行。通用 parser 升至 `issuer_scope_v3` 后，重放结果为三项各 45/45，25 行负向回归控制 25/25 无回退。没有 firm key、股票代码或审阅名称特判。分类维持 R4C0 的 FIELD_BOUNDARY_ERROR 1、LABEL_LAYOUT_UNMATCHED 14、ISSUER_SCOPE_ERROR 3、TEMPORAL_EVIDENCE_OVERCLAIM 2；版式子聚类为报告标题/封面名称块 12、释义先行/重复标签 1、其他标签或章节变体 1。逐行结果与聚类仅存 ignored R4C1 结果目录。

R4C1 未能重新计算冻结 strict-14 Pilot 与 6-event metrics：对应 14 行不与 45 行语料重叠，本地没有 strict-14 年报 TXT；已有 Gate summary 是旧解析器结果，不能当作 v3 重算。故本轮 `h1_parser_repair_status=H1_PARSER_REPAIR_NEEDS_FIX`，不宣称 Gate 仍经本轮验证通过。既有 Pilot v3 历史 Gate 记录不被改写。其他状态保持 `targeted_diagnostic_execution_status=TARGETED_DIAGNOSTIC_PILOT_COMPLETE`、`full_name_followup_status=FULL_NAME_FOLLOWUP_REQUIRED`、`cnipa_entity_name_scope_status=CNIPA_ENTITY_NAME_NEEDS_FIX`、`zero_semantics=pending`、`missing_semantics=pending`。无网络/H2/OCR/Full refresh；Full/cache、frozen GT 未修改。

## 4.4A-R4B2 最终状态（2026-10-01）

R4B2 在同一冻结 94 行 / 86 家 manifest 上续跑，三个冻结指纹均一致。R4B 历史 120 次 guarded attempts 保持不变；R4B2 新 epoch 共 53 次尝试、53 个响应、0 个传输异常、0 个预派发错误、0 个来源封锁，累计 173 次，未触及本 epoch 的 120 次预算。请求审计 53 行；已完成证据重下载 0；H2 请求 0。

旧 R4B 30 条 acquisition 均依据 prediction key/path/hash 映射到 frozen key，mapping unresolved=0；来源分类为 27 `VALID_FULL_H1`、2 `ANNUAL_REPORT_SUMMARY`、1 `WRONG_ISSUER`。累计来源分类为 45 份有效完整年报、8 份摘要、1 份错误发行人、10 份正文提取未解决。两份摘要和错误发行人的具体 frozen key 仅记于 ignored 来源台账。旧 27 条有效 H1 加新增 18 条有效 H1 均完成独立复核，合计 45/45。

94 行均有终态：44 `TARGETED_H2_REQUIRED`、1 `SOURCE_REVIEW_PASS`、9 `SOURCE_IDENTITY_PROBLEM`、10 `OCR_OR_MANUAL_REQUIRED`、18 `INDEX_COMPLETE_RESULT_SET_NO_VALID_REPORT`、2 `SOURCE_UNRESOLVED`、10 `LOCAL_CONTROL_ONLY`。18 个索引行完整扫描未发现合格候选，另 2 行证券目录映射缺失，不能声称没有年报。HIGH 10 行中 7 行当前 parser 已纠正、2 行仍错误或空值、1 行来源错误；MEDIUM 10 行中 9 行正确、1 行仍错。MEDIUM 根因为通用 `FIELD_BOUNDARY_ERROR`：值规范化将以合法汉字“无”开头的名称误判为回答标记并剥除；本轮未改生产 parser。temporal 10 行为 9 行需定向 H2、1 行 H1 已足够。extraction 20 行分为 12 个完整年报正文的 parser layout gap 和 8 个官方年度报告摘要（非完整 H1）；另一个重叠 fetch/text 10 行的 PDF 有效但 TXT 为空/过短，均未运行 OCR。

45 行 source-grounded review 的 parser accuracy：issuer name 27/45、year-end name 26/45、evidence-state 28/45；这是该独立复核样本的当前 parser 表现，不是 population accuracy。此前仅 27 行的 pre-network 子样本仍分别为 23/27、22/27、23/27，两个口径不应混用。

> 本段中的 `TARGETED_DIAGNOSTIC_PILOT_NEEDS_FIX` 是 R4C0 状态拆分前的旧单轴历史状态；当前执行状态和后续准备度以本节 R4C0 结论为准。

R4B2 最终全库验证：pytest 385 passed；Ruff `All checks passed!`；`uv pip check` 检查 116 packages 且全部兼容；push hygiene PASS。

以下原有结果描述为 R4B 首轮历史快照，不代表 R4B2 累计状态。

状态：`TARGETED_DIAGNOSTIC_PILOT_NEEDS_FIX`。本轮严格使用 R4A 冻结的 94 个 firm-year、86 家企业清单，没有重新抽样。manifest SHA-256 为 `30C47523292A96F19EDF889ACDD0851B26887B08D60B91F06E14EF2D9420F78C`；frame fingerprint 为 `8e26547eda6d24ff78af39e8bf652128809d57b67414655495fba50b130bc2fb`；key fingerprint 为 `96D4FF6735B18707129CE2C4F485F0D22C3547F28A0A9DAF1C164330F4757861`，与 R4A 冻结指纹一致。

计划动作分布为 exact H1 50、单企业年度索引查询 20、人工来源复核 14、无网络 negative control 10。执行守门计数达到 120 后停止，未再发出请求。审计中可确认 30 份 PDF 返回 HTTP 200 并完成文本提取；另有 5 个索引样本记录为未找到可选报告，其余计划动作未能完成。首轮执行器的传输错误使预算计数包含未实际发出的请求；网络请求审计日志不完整，因此除可确认的 30 个 PDF 响应和 5 个索引查询结果外，不将守门计数误称为精确 wire-request 总数。无 403、429、验证码或访问挑战。

30 份已取回 PDF 均有本地 TXT。离线重新解析后：24 行为 `CONFIRMED_YEAR_END_NAME_ONLY`、2 行为 `CONFIRMED_NO_CHANGE`、4 行为 `LEGAL_NAME_EXTRACTION_FAILED`。其中 27 行通过官方来源、发行人、年度及完整年报身份核验；2 份 exact URL 返回年度报告摘要，另 1 份发行人身份不符，均不计作有效 H1 全文。当前 30 行具备新正文；另外 54 行没有完成来源获取，10 行是仅使用本地元数据的控制组。

独立来源复核表与 parser predictions 分开保存，没有将预测值复制到 review 字段。对取得正文且发行人/年度/全文身份可核对的 HIGH/MEDIUM stale-success 样本，独立复核 PASS 为 17 行；67 行仍为 `SOURCE_UNRESOLVED`，10 个控制行为 `LOCAL_CONTROL_ONLY`。review denominator=17：issuer-name accuracy=16/17，year-end-name accuracy=16/17，evidence-state accuracy=17/17。该分母只适用于已审核子样本，不外推全体。

HIGH 抽样 10 行中 7 行完成来源复核：old wrong=7、current parser corrected=7、current parser still wrong=0；另 3 行 unresolved，已审核的 7 行中未观察到 HIGH 风险误报。MEDIUM 抽样 10 行均完成复核：old wrong=1、current corrected=0、current still wrong=1。HIGH 样本呈现的共同错误与范围误选相符；MEDIUM 至少有不同表现，需继续分层。LOW 的 10 行全部为 `LOCAL_CONTROL_ONLY`，不纳入准确率分母。

349 temporal 子类抽样 10 行，虽有 3 份报告正文，但没有完成独立 temporal adjudication；`TARGETED_H2_REQUIRED` 明确结论数为 0，其余均保持 unresolved。两类 legal-name extraction failure 合计抽样 20 行，3 份取得正文、尚无独立 PASS。report-not-found 抽样 20 行，其中 5 个单企业年度查询未找到可选报告，15 行受预算/执行中断影响而未完成；13 fetch/text-failure 子类抽样 10 行，均未成功获取新的正文。具体分组见 ignored 的 `subfamily_scalability_matrix.csv`。

## 边界与受保护对象

- 没有 CNIPA 专利系统访问，没有 OCR、H2 搜索或市场级公告扫描。
- 没有写回 Full status/state/cache、entity-year coverage 或任何 frozen GT。
- `full_status.csv`、`full_run_state.json`、Full cache tree、GT 与 R4A 输入的前后 SHA-256 一致。
- Pilot v3 Gate 继续为 `STRICT_PILOT_GATE_PASS`；整体 `cnipa_entity_name_scope_status` 仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`；`zero_semantics`、`missing_semantics` 仍为 `pending`。

## 诊断与后续计划

本轮材料只支持局部观察，不足以对 9 个 gap 子类作规模化修复判断。R4C 仅生成候选计划，不执行：HIGH 34 行不得直接全量刷新；MEDIUM 2,155 行先细分并复核当前 parser 仍错的样本；349 temporal 大类先核对本地名称轨迹，再另行授权有边界的 H2；238 extraction failures、444 report-not-found 和 13 fetch/text failures 需分别分流。具体 ignored 结果位于 `results/cnipa_full_gap_diagnosis/r4b_20260930/`，其中包含逐行材料，未纳入版本控制。

本轮结论不改变研究范围状态，也不授权 Full、targeted Full refresh 或专利采集。
