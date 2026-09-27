# CNIPA 申请人名称预检

## 范围与结论

本阶段仅为正式专利数据访问前的实体名称和查询批次预检。目标集合严格来自沪深非金融企业正式 Phase A 面板：5,272 家企业、28,548 个合法 firm-year。目标 `firm_key` 与正式 Phase A manifest 完全一致，并与 enriched Profile 的 firm 集合逐一核对；没有因名称缺失删除企业。

当前状态为 `CNIPA_ENTITY_NAME_NEEDS_FIX`。当前法人全称可覆盖全部目标，但历史名称候选尚未完成充分核验，且名称碰撞的专利结果归属仍未解决。因此，查询准备文件只含已核实的当前法人全称及少量有证据的历史法人全称；本状态不代表可开始正式专利采集。

## 名称来源及试点审查

当前法人名称取自 EastMoney F10 `ORG_NAME`，并要求 Profile 状态、来源字段及组织代码通过检查。目标企业中 5,272/5,272 有当前法人全称。当前名称以 `PROFILE_CURRENT` 单独记录来源，不将其误标为历史名称 H1—H3。

本轮对 `RPT_F10_BASIC_ORGINFO` 做字段级复核：在同一记录结构中，`ORG_NAME` 提供当前法人全称，`FORMERNAME` 提供曾用证券简称链；按固定 seed `20260927` 从现有 pilot 抽取 12 家，通过公开接口复现字段值，其中包含 `G`、`ST`、`*ST` 等简称变体。再与交易所/年度报告中的“股票简称/证券简称”和法人名称字段交叉核对。字段语义冻结为 `FORMER_SECURITY_NAME_ONLY`；6,438 条 `FORMERNAME` 企业—候选记录整体标为 `rejected_stock_abbreviation / REJECTED`，全部 `query_eligible=0`。这不是逐条名称搜索，也不把这些简称用作历史法人全称。接口字段可从[EastMoney F10 数据接口](https://datacenter.eastmoney.com/securities/api/data/v1/get?reportName=RPT_F10_BASIC_ORGINFO)复核。

按 seed `20260927` 分层抽样后，pilot 合并去重为 61 家，覆盖 SSE/SZSE 当前企业、SSE/SZSE 退市企业、`FORMERNAME` 非空、含多个简称及经正式材料识别的法人更名案例。另有 2 个历史法人全称在正式披露来源中核实，涉及 1 家企业，日期仅记录到年份并标记时间匹配不确定。没有把简称扩写或当作法人名称。

在 5,272 家目标中，`FORMERNAME` 非空的有 2,309 家，共拆分出 6,438 条企业—候选名称记录；本轮已按字段语义整体拒绝 6,438 条，均不可查询。名称规范化仅执行 Unicode NFKC、空白规整及确定性去重，不删减或补加法人组织形式。

## firm-year 法人名称覆盖

目标财务面板含 28,548 个 2020–2025 firm-year；主窗口 2020–2024 为 23,458 个 firm-year。既有 Historical Province 缓存保存了报告年份、CNINFO 来源链接和注册地址抽取结果，但没有保留年度报告正文/PDF，也没有可复用的法人名称抽取文本。因此本轮没有将当前 Profile 名称回填为历史年度名称；本地 ignored 文件 `results/cnipa_preflight/entity_year_name_coverage.csv` 将 23,458 个主窗口 firm-year 标记为 `REPORT_UNAVAILABLE`，其中有报告元数据/链接也不视作名称证据。主窗口可验证年报法人名称覆盖为 0/23,458；`temporal_unresolved=23,458`。已有 2 个正式来源核实的历史法人全称仍保留在名称库，但不足以证明总体年度覆盖。

## 名称碰撞

发现 6 组规范化名称对应多个 `firm_key`。逐组核对 `ORG_CODE`、证券代码与上市/退市区间后，3 组属于同一组织代码对应不同证券代码，状态记为 `RESOLVED_SHARED_QUERY_TEMPORAL_ALLOCATION`：查询名称共享一次、保留全部 firm_key 映射，后续按上市实例/申请日期处理。另 3 组为同一证券键对应多个 firm_key，日期属性存在冲突，无法从现有元数据证明权威 listing key，保持 `UNRESOLVED`。没有合并 firm_key；未决组禁止自动归属专利结果。

## 查询批次 Gate

查询名单仅使用 `query_eligible=1` 的名称：5,272 个当前法人名称及 2 个经验证的历史法人名称，合并后为 5,268 个唯一名称；企业映射 5,274 条。分为 264 个批次。自动 Gate 确认每个 eligible 名称恰好进入一个批次，批内不重复、每批不超过 20 个名称，渲染查询字符串不超过 1,500 字符；本轮观察到的最大长度为 374 字符。6,438 条 `FORMERNAME` 候选均排除；碰撞名称保留完整映射，3 组仍标记未决。

`max_names=20`、`max_chars=1500` 仅是项目预设，尚未在合法 CNIPA 访问中验证，因此状态仍为 `CNIPA_QUERY_LIMIT_UNCONFIRMED`。查询批次和企业名称明细只保存在 ignored 本地文件中。

## 限制与边界

- 2020–2024 主窗口 23,458 个 firm-year 均缺少本地年报正文/名称证据；历史法人名称覆盖不可评估为完整，故 Gate 不通过。
- 因本地未留存年度报告正文，本轮未构建或声称验证通用年报法人名称/报告期内更名抽取器；不得用合成 fixture 代替实际来源验证。补齐正式正文后再实现并测试名称、变更前后名称及生效时间抽取。
- 6 组碰撞中 3 组已确认为同一组织代码的不同证券实例并保留共享查询映射；另 3 组同证券键/多 firm_key 疑点未决，尚不能判定权威 listing key。
- `zero_semantics` 和 `missing_semantics` 仍为 `pending`；CNIPA 无搜索结果不能据此编码为零。
- 本轮未登录 CNIPA、未导出或下载专利，未做企业—专利匹配、正式研究面板、BSE 处理、政策匹配或回归。
- 企业级名称、证据、碰撞明细、pilot 和查询批次均为本地 ignored 数据，不纳入版本控制。
- 本轮完整 pytest：265 passed，0 failed（2026-09-27）。
- Ruff：`All checks passed!`；依赖检查：116 packages compatible；push hygiene：通过。
- 2025 coverage audit：5,090 个目标 firm-year，5,090 个均因本地无年报正文而标为 `REPORT_UNAVAILABLE`；不将报告链接误作名称证据。
