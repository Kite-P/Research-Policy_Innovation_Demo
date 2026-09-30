# 4.4A-R4B CNIPA 定向诊断 Pilot

## 执行结论

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
