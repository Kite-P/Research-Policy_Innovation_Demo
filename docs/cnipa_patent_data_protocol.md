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

4.4A-R3E 后，Full 授权只接受 `cnipa_strict_pilot_gate_v2`，并同时校验固定样本、目标和来源证据，以及 `pilot_change_candidate_rows.csv`、`pilot_change_event_roster.csv`、`pilot_change_row_review.csv` 的 SHA-256 指纹。R3E 已在固定 Pilot 92 家/461 firm-year 上完成独立事件与行级审核：14 个候选行、6 个 verified distinct events、12 个 event-linked firm-year rows，strict Pilot Gate 为 `STRICT_PILOT_GATE_PASS`。历史 5 cases / 3-of-5 和 legacy 6 review rows 均不作为新 Gate 分母。v1、legacy summary 及 `--pilot-pass` 单独不能授权 Full；本轮未执行 Full 或 targeted refresh。整体范围仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`，详见 `docs/cnipa_entity_name_audit.md`。

R2 先完成 92 家/461 firm-year 的固定 Pilot，再从既有 CNINFO 年报索引恢复并审计 2020—2024 全目标证据；身份键纠正后主窗口为 23,448 firm-year，其中 22,753 行提取到法人名称，353 行的名称时间关系仍未决，695 行没有提取到名称。当前状态仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`；不得将查询预检批次视为已完整确认的历史申请人集合。

每批最多 20 个名称、最多 1,500 字符仍是项目暂定参数，不是已确认的 CNIPA 官方网页限制；须在合法访问后实际核验。名称批次预检不等于 CNIPA 查询或专利数据采集。

## Local parser output

`read_cnipa_export` 支持 XLSX 和 XML，并标准化为：

`application_number`、`application_date`、`publication_number`、`publication_date`、`applicant_raw`、`patent_title`、`patent_type_raw`、`ipc_raw`。

专利类型优先使用 CNIPA 导出字段定义。无法从明确字段判断时输出 `unknown`，不根据公开号末尾的 A、B、U 字符自动猜测发明或实用新型。

## Audit requirements

未来人工导出后必须记录来源页面、导出时间、字段字典、查询批次、下载文件校验值和覆盖情况；不得记录账号、密码、token、cookie 或本机绝对路径。
