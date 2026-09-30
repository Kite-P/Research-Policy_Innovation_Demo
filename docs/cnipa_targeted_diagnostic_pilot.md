# 4.4A-R4B CNIPA 定向诊断 Pilot

## 执行结论

状态：`TARGETED_DIAGNOSTIC_PILOT_NEEDS_FIX`。本轮严格使用 R4A 冻结的 94 个 firm-year、86 家企业清单，没有重新抽样。manifest SHA-256 为 `30C47523292A96F19EDF889ACDD0851B26887B08D60B91F06E14EF2D9420F78C`；frame fingerprint 为 `8e26547eda6d24ff78af39e8bf652128809d57b67414655495fba50b130bc2fb`；key fingerprint 为 `96D4FF6735B18707129CE2C4F485F0D22C3547F28A0A9DAF1C164330F4757861`，与 R4A 冻结指纹一致。

计划动作分布为 exact H1 50、单企业年度索引查询 20、人工来源复核 14、无网络 negative control 10。执行守门计数达到 120 后停止，未再发出请求。审计中可确认 30 份 PDF 返回 HTTP 200 并完成文本提取；另有 5 个索引样本记录为未找到可选报告，其余计划动作未能完成。首轮执行器的传输错误使预算计数包含未实际发出的请求；网络请求审计日志不完整，因此除可确认的 30 个 PDF 响应和 5 个索引查询结果外，不将守门计数误称为精确 wire-request 总数。无 403、429、验证码或访问挑战。

30 份已取回 PDF 均有本地 TXT。离线重新解析后：24 行为 `CONFIRMED_YEAR_END_NAME_ONLY`、2 行为 `CONFIRMED_NO_CHANGE`、4 行为 `LEGAL_NAME_EXTRACTION_FAILED`。至少 2 份 exact URL 返回年度报告摘要而非完整年报，故不能计为有效 H1 全文。当前只有 30 行具备新正文；另外 54 行没有完成来源获取，10 行是仅使用本地元数据的控制组。

独立来源复核表与 parser predictions 分开保存，没有将预测值复制到 review 字段。94 行中 84 行仍为 `SOURCE_UNRESOLVED`，10 个控制行为 `LOCAL_CONTROL_ONLY`；独立 PASS 分母为 0。因此三项 source-grounded accuracy 均报告为不可计算，而不是 0% 或 100%。`HIGH`、`MEDIUM`、`LOW` 各抽样 10 行，但旧值错误数、新 parser 更正数及误报风险数均未作推断。

## 边界与受保护对象

- 没有 CNIPA 专利系统访问，没有 OCR、H2 搜索或市场级公告扫描。
- 没有写回 Full status/state/cache、entity-year coverage 或任何 frozen GT。
- `full_status.csv`、`full_run_state.json`、Full cache tree、GT 与 R4A 输入的前后 SHA-256 一致。
- Pilot v3 Gate 继续为 `STRICT_PILOT_GATE_PASS`；整体 `cnipa_entity_name_scope_status` 仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`；`zero_semantics`、`missing_semantics` 仍为 `pending`。

## 诊断与后续计划

本轮材料只支持局部观察，不足以对 9 个 gap 子类作规模化修复判断。已有正文显示当前 issuer-scoped parser 在部分文本中能提取年末名称；但缺少独立逐行事件审核，且有报告全文/摘要识别和采集恢复方面的问题。R4C 仅生成候选计划，不执行：HIGH 34 行不得直接全量刷新；MEDIUM 2,155 行先细分再做第二轮 Pilot；349 temporal 大类先核对本地名称轨迹，再另行授权有边界的 H2；238 extraction failures、444 report-not-found 和 13 fetch/text failures 需分别分流。具体 ignored 结果位于 `results/cnipa_full_gap_diagnosis/r4b_20260930/`，其中包含逐行材料，未纳入版本控制。

本轮结论不改变研究范围状态，也不授权 Full、targeted Full refresh 或专利采集。
