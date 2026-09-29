# CNIPA 免费专利数据协议

## Source decision

正式撤销 Google Patents BigQuery 作为本研究 2020—2024 年专利来源。公开 metadata 未能可靠支持目标年份，因此不再要求 Google Cloud authentication。首选来源改为国家知识产权局知识产权数据资源公共服务系统及其专利检索与分析系统。

本阶段只完成接口准备，不注册、不登录、不下载专利、不绕过验证码，也不运行专利相关回归。

## Time and entity scope

- primary application year: 2020—2024;
- 2025: coverage audit only;
- entity scope: `listed_entity_only`;
- included names: listed legal entity name and verified historical legal name;
- excluded by default: short name, stock abbreviation, subsidiary, fuzzy name and unverified alias.

## Query protocol

查询由公司法定全称组成，名称首尾空白被删除，重复项删除，使用 UTF-8 字节序确定性升序。多个名称以 ` OR ` 连接，不使用通配符。默认 pilot 参数为每批最多 20 个名称、最多 1500 个字符；实际网页长度限制须在合法访问后重新记录。

## Export fields

至少保存以下字段：

`申请号`、`申请日`、`公开（公告）号`、`公开（公告）日`、`申请人（专利权人）`、`发明名称`、`专利类型/文献类型`、`IPC`。

系统提供时一并保存申请人邮编。无需下载 PDF 全文。

## Entity-name preflight

CNIPA 查询名称只来自已核验的当前法人全称和有正式来源支持的历史法人全称。EastMoney F10 `ORG_NAME` 作为当前法人名称来源；`FORMERNAME` 只作为候选，按观察到的 `→` 分隔解析后仍须逐名核验。股票简称、曾用股票简称、子公司、模糊别名及未决候选均不得进入查询。缺少历史名称证据不删除目标企业。

当前名称预检报告见 `docs/cnipa_entity_name_audit.md`。企业级名称证据、碰撞表和查询批次保留在本地 ignored 输出。即使查询名存在多 firm-key 映射，也只记录碰撞，不自动合并或分配专利结果。未确认历史名称有效期时保留 `temporal_match_uncertain`，不能静默跨期匹配。

R3E-R 复核确认，R3E 曾报告的行级 1.0 是由 parser 预测复制到 `manual_*` / `review_*` 后自我比较所得，不是独立 ground truth，现已作废。Full 只接受 `cnipa_strict_pilot_gate_v2`，并校验固定样本、目标、来源证据、候选集、事件 roster、行级预测，以及独立事件 ground truth 和行级 ground truth 的指纹。R3F 修正后，候选预测为 12 行，但评估分母仍是冻结的 14 行；6 个事件的旧名、新名、日期和日期精度准确率均为 1.0，year-end legal-name accuracy 为 14/14，change-flag accuracy 为 12/14。两份 300365 年报没有发行人层面的明确未更名陈述，故两项仍为 `UNKNOWN`，Gate 保持 `PILOT_GATE_NOT_PASSED`，不得授权 Full。历史 5 cases / 3-of-5 和 legacy 6 review rows 不作为新 Gate 分母。v1、legacy summary 及 `--pilot-pass` 单独不能授权 Full；本轮未执行 Full 或 targeted refresh。整体范围仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`，详见 `docs/cnipa_entity_name_audit.md`。

R2 先完成 92 家/461 firm-year 的固定 Pilot，再从既有 CNINFO 年报索引恢复并审计 2020—2024 全目标证据；身份键纠正后主窗口为 23,448 firm-year，其中 22,753 行提取到法人名称，353 行的名称时间关系仍未决，695 行没有提取到名称。当前状态仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`；不得将查询预检批次视为已完整确认的历史申请人集合。

每批最多 20 个名称、最多 1,500 字符仍是项目暂定参数，不是已确认的 CNIPA 官方网页限制；须在合法访问后实际核验。名称批次预检不等于 CNIPA 查询或专利数据采集。

## 4.4A-R3G 更名事实与证据状态

上一段 R3F 的 v2 change-flag Gate 和 `PILOT_GATE_NOT_PASSED` 是历史状态，已由本节 R3G v3 测量定义取代；旧 v2 summary 不再具有 Full 授权效力。

`company_name_change_flag` 表示 **evidence-supported issuer-name-change state**：它回答当前允许的 H1/H2 发行人级证据是否足以支持目标年度的 `YES` 或 `NO`。它不是“现实中最终查不到更名就必然为 NO”的完整历史事实变量。未检出更名不能单独推出 `NO`；证据不足时必须为 `UNKNOWN`。`UNKNOWN` 不等同于 `NO`，也不等同于专利结果缺失。

历史发生事实另由 `historical_change_occurrence` 表示，取值 `YES` / `NO` / `UNRESOLVED`。固定 Pilot 的旧 `pilot_change_row_ground_truth.csv` 继续保存这项历史/事件事实，不被证据状态标签替代或改写。新增 ignored 本地审核表 `pilot_change_evidence_state_ground_truth.csv` 是独立测量目标，覆盖原冻结的全部 14 个 firm-year 键；其指纹由 v3 summary 绑定。对已核验且日期在目标年度以外的事件，仅当事件日期与正式法人名称轨迹共同形成足够时间证据时才可判证据状态 `NO`；只有年末法人名或单纯未提及事件时仍为 `UNKNOWN`。分公司、子公司和证券简称变化不构成发行人证据。

`company_name_change_flag = UNKNOWN` 不会自动使已由官方报告确认的 `legal_name_at_year_end` 变为缺失。只要年末法人名称本身明确，该名称仍可确认；名称的时间归属确实无法确定时才使用 `TEMPORAL_UNRESOLVED`。

R3G 仍用 R3F 原 parser 输出重算固定 14 行，不删除候选退出行。历史发生准确率为诊断指标；正式 Gate 使用 `parser_evidence_state_accuracy`，要求 14/14；年末名称、事件旧名、新名、日期和日期精度准确率也均须为 1.0，且所有独立审核完成。summary schema 升为 `cnipa_strict_pilot_gate_v3`，绑定新的 evidence-state ground-truth fingerprint 以及原 event/row GT fingerprints。v1、legacy、旧 v2 summary 和 `--pilot-pass` 单独均不能授权 Full。R3G 的固定 Pilot Gate 为 `STRICT_PILOT_GATE_PASS`；这只覆盖固定 Pilot，不代表 Full 23,448 行或 CNIPA 专利采集已执行。整体范围仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`，详见 `docs/cnipa_entity_name_audit.md`。

## 4.4A-R3G-K Runner 与定向 Full 安全边界

唯一 CNINFO 名称恢复实现为 `scripts/run_cninfo_legal_name_recovery_20260929.py`；`scripts/run_cninfo_legal_name_recovery_20260927.py` 仅保留兼容命令行委托，不包含独立授权、缓存或 Full 流程。内部测试与实现导入统一指向 canonical 文件。

证据状态 GT validator 会从三项审核事实重新推导预期标签：目标年内已验证发行人更名为 YES；否则明确未更名披露或具备充分时间顺序依据的目标年外更名为 NO；其余为 UNKNOWN。目标年内/外事实同时为 YES，或推导值与人工标签不一致时，Gate 无效。`verified_change_event_outside_target_year=YES` 本身即声明事件与法人名称轨迹足以确定目标年状态。

当完整 Full 状态和 23,448 键集合已完成，但成功缓存仍是旧 parser revision 时，普通 `--resume` 会硬性阻止宽范围重解析。对现有缓存的只读预检检测到 22,751 条旧 revision 成功记录，因此当前普通宽范围 resume 会被阻断。定向操作必须提供 `--targeted-refresh-manifest`（`firm_key,year,reason`），并通过精确目标子集、唯一键、非空原因和原 23,448 行基线校验。定向写回只替换 manifest 键，输出目标行前后哈希，并要求非目标行指纹完全相同；该机制仅为后续授权运行准备，本轮不运行任何 refresh。

## Local parser output

`read_cnipa_export` 支持 XLSX 和 XML，并标准化为：

`application_number`、`application_date`、`publication_number`、`publication_date`、`applicant_raw`、`patent_title`、`patent_type_raw`、`ipc_raw`。

专利类型优先使用 CNIPA 导出字段定义。无法从明确字段判断时输出 `unknown`，不根据公开号末尾的 A、B、U 字符自动猜测发明或实用新型。

## Audit requirements

未来人工导出后必须记录来源页面、导出时间、字段字典、查询批次、下载文件校验值和覆盖情况；不得记录账号、密码、token、cookie 或本机绝对路径。
