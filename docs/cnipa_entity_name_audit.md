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

R3E 曾记录的行级准确率与 legal-name precision 1.0 不构成独立审计结果：当时 `manual_*` / `review_*` 字段由 parser 预测直接复制，再与同源预测比较，属于自我比较。该结论已由 R3E-R 独立复核取代，不得作为 Full 授权依据。

## 4.4A-R3E-R 历史 Pilot Ground-Truth 复核（已由 R3F 更新）

固定 Pilot 仍为 seed `20260927`、92 家、461 个 firm-year；不改变 14 条候选行及 6 个事件的冻结总体。预测产物与独立 ground-truth CSV 已分离，逐项审核了全部 6 个事件和 14 条行级记录，并将候选、事件 roster、行级预测及两份 ground truth 的指纹绑定到 strict v2 摘要。两条 300365 记录明确判为 `NOT_A_LEGAL_NAME_CHANGE_EVENT`：2020 年报主体名称正常；2021 解析文本来自成都分公司释义，不是上市主体名称。

独立复核结果：事件旧名、新名、精确日期准确率分别为 1.0、1.0、1.0（精确日期分母 5；事件日期精度准确率 1.0）；14 条行级候选的 legal-name precision 为 13/14（0.9286），change-flag accuracy 为 12/14（0.8571），year-end legal-name accuracy 为 13/14（0.9286）。证券简称误判 0，未审事件/行 0，未决候选/事件 0。误差来自 300365 的两条解析结果：2020 change flag 为 UNKNOWN；2021 change flag 为 UNKNOWN 且年末解析名错误地取到分公司释义。没有排除错误行来抬高指标。最终 `PILOT_GATE_NOT_PASSED`，Full 不获授权。

v1、legacy summary 与 `--pilot-pass` 单独不能授权 Full。当前 Full 授权校验必须同时匹配固定样本/目标/来源、候选集、事件 roster、行级预测以及事件和行级 ground-truth 共五类相关指纹。Full evidence cache 未改动；本轮没有启动 Full、targeted refresh 或任何专利流程。

CNIPA 全范围状态仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`：主窗口的 353 个时间关系未决和 695 行缺少年报法人名称尚待后续处理；`zero_semantics` / `missing_semantics` 仍为 pending。verified historical names 仍为 3，unique query names 仍为 5,269。未访问 CNIPA 专利系统，未检索或下载专利。

R3E-R 目标测试：48 passed。全库验证及推送卫生结果以 R3E-R 本轮最终检查记录为准。

## 4.4A-R3F 发行人范围解析修正与固定 Pilot 复核

仅按授权重新取得 300365 的 2020、2021 两份 CNINFO 年报正文。两份请求均 HTTP 200，分别为 4,135,847 bytes（SHA-256 `c8549861dbecf2db79d8884af8e179cfd8d71510adac74a5a2a322c09dda8091`）和 2,385,682 bytes（SHA-256 `315cac49f367b748ba6b14875cbd4ceac22f9eceda9adad54d311e64ee3e5e11`）；均由 `pdftotext -layout` 提取。PDF 未持久化；正文及诊断材料只保存在本地 ignored results。

两年正式发行人名称均位于“第二节 公司简介和主要财务指标—一、公司信息”的“公司的中文名称”字段，内容为“北京恒华伟业科技股份有限公司”。旧解析器对全文做无边界的 `公司名称` 子串匹配，2021 年先命中释义中的“股份改制前公司名称”，并把后续“成都分公司 指 北京恒华伟业科技股份有限公司成都分公司”误认成发行人名称。修复改为字段边界匹配并优先限定正式公司信息栏目；不包含证券代码、分公司或企业全称特判。旧成功缓存没有 parser revision，曾使旧解析结果继续留在 Pilot 产物中；当前缓存加入解析版本校验，旧成功解析不会再被静默复用。

两份报告均未发现发行人层面的“公司名称是否变更”字段或明确的未更名陈述。2021 年的“公司注册地址历史变更情况”只涉及注册地址；释义中的分公司名称也不是发行人更名证据。因此 change flag 仍为 `UNKNOWN`，不因未检出更名事件而推断为 `NO`。

重新生成的候选集为 12 行；评估仍按冻结的 14 个 row-ground-truth 键逐行计分，未因候选退出而缩小分母。6 个事件 roster 未变，旧名、新名、日期和日期精度准确率均为 1.0；14 行 year-end legal-name accuracy 为 14/14，change-flag accuracy 为 12/14（0.8571）。剩余两项旗标差异对应仍为 `UNKNOWN` 的 300365 年度记录。行级审核完整，事件准确率无回退，但严格 Gate 仍为 `PILOT_GATE_NOT_PASSED`，不授权 Full。两份冻结 ground truth 未修改，指纹保持不变；未执行 Full、额外年度抓取或专利流程。

R3F 验证：全库 pytest 323 passed；Ruff `All checks passed!`；116 个依赖兼容；push hygiene 通过。tracked 变更仅涉及本段审计文档、协议/进度文档、metadata、通用解析器、Pilot Gate 脚本和测试。

## 4.4A-R3G 更名发生事实与 parser 证据状态 Gate

R3F 的 `PILOT_GATE_NOT_PASSED` 是旧测量口径下的历史状态，现由 R3G v3 Gate supersede。R3F 的 parser 预测、固定 14-row evaluation keys、6 个事件和两份冻结 ground truth 均保持不变。本轮没有把 `300365` 的历史发生事实从 `NO` 改成 `UNKNOWN`，也没有修改 parser 来迎合旧标签。

明确拆分两个测量目标：`historical_change_occurrence` 记录目标年度现实中是否发生法人名称变更；`company_name_change_flag` 是 parser 的 evidence-supported issuer-name-change state。历史准确率只作诊断，严格 Gate 使用独立审核的 `review_expected_parser_flag`。仅未检出事件不能得出 `NO`；无足够 H1/H2 时间证据时应为 `UNKNOWN`。已明确的年末法人名称不因 flag 为 `UNKNOWN` 自动缺失，分支名称不作为发行人事件。

新增本地 ignored `pilot_change_evidence_state_ground_truth.csv`，独立覆盖冻结的 14 行；历史发生分布为 YES=4、NO=10、UNRESOLVED=0；证据状态分布为 YES=4、NO=8、UNKNOWN=2。300365-2020 和 300365-2021 的历史事实均为 NO，证据状态均为 UNKNOWN。此审核表不是旧 GT 的替代版本，也未提交 Git。

v3 strict summary 绑定 evidence-state GT fingerprint `351231a42842ae08e0d612b3b06f1b9811018ec37eec8b9219e09c2a99324d26`。新表中的历史发生标签与冻结 row GT 逐行 14/14 一致，YES 行 event ID 亦通过一致性核验。冻结旧 GT 文件 SHA-256 仍分别为 event `E1900A01FFF61610E1325623EC59870D9063A14C6925E4075639855745D5E174`、row `81EB18D82611CE7BDDF7D9895ED57237026B9B5D97B0DD258DDA7D0BA266D342`。固定分母仍为 14；历史 occurrence accuracy=12/14（诊断），parser evidence-state accuracy=14/14；year-end legal-name=14/14；event old-name、new-name、date、date-precision accuracy 均为 1.0；独立审核未决数为 0。Gate 为 `STRICT_PILOT_GATE_PASS`。

Full 授权 schema 升为 `cnipa_strict_pilot_gate_v3`，必须重算并匹配 evidence-state fingerprint、14-row 分母和 1.0 evidence-state accuracy。v1、legacy、旧 v2 summary 与 `--pilot-pass` 单独均不可绕过。R3G 未执行 Full 23,448、targeted Full、CNIPA 专利系统访问、353/695 修复、BSE、财务/省份/政策流程或回归。范围状态仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`；`zero_semantics` 和 `missing_semantics` 仍为 pending。

R3G 最终验证：pytest 326 passed；Ruff `All checks passed!`；`uv pip check` 检查 116 packages 且兼容；push hygiene PASS。独立审核完整，旧 GT fingerprints 精确不变。仅涉及 Gate runner、测试、CNIPA protocol/audit/progress 文档及 metadata；不含 parser 行为或数据范围修改。

## 4.4A-R3G-K Canonical Runner 与 Full 定向刷新安全

唯一实现固定为 `scripts/run_cninfo_legal_name_recovery_20260929.py`；`20260927.py` 已收敛为只委托 canonical `main()` 的兼容入口。测试导入迁移到 canonical，保留一项旧入口委托测试；解析器及 canonical runner 的企业代码特判扫描覆盖 300237、600936、603003、603196、300365。

evidence-state validator 现在逐行按审核事实重推 `review_expected_parser_flag`，并拒绝目标年内/外事件事实矛盾或事实与标签不一致。冻结 event/row/evidence-state GT 只读；R3G v3 PASS 与固定 14 行分母不变。

已加入 Full 安全前置检查：完整 23,448 行基线、精确 manifest 子集、非空原因、无重复/越界键、manifest fingerprint，以及成功缓存旧 parser revision 时普通宽范围 resume 硬阻断。对现有本地 Full 状态作只读预检，确认 23,448/23,448 键完整，普通宽范围 resume 被拦截，检测到 22,751 条旧 revision 成功缓存。定向写回只替换 manifest 键，记录目标行前后指纹并验证非目标行指纹完全不变。此轮只实现和测试安全逻辑，不执行 Full、定向抓取或网络请求；实体范围仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`，zero/missing semantics 仍 pending。

## 4.4A-R4A Full 缺口与旧解析成功缓存离线分层

对正式 2020—2024 主窗口重新逐行计算八类 coverage，23,448 行与当前 primary target 键集合完全一致且唯一。分类总数为 22,256 个年末名称、126 个已确认变更、18 个无变更、353 个时间关系未决、444 个报告未找到、238 个名称提取失败、13 个文本提取失败、0 个来源封锁。353 与 695 个 no-name 键互斥，gap 并集精确为 1,048。entity-year coverage 另含 5,089 条 2025 audit 行，不属于 Full 主窗口，未并入分母。

1,048 gap 分成 9 个非空子类。时间未决主要是 349 行有当前/年末名称但无事件对或日期；报告缺失类为 253 行有历史来源记录但无 URL、191 行位于挂牌/退市边界年；名称提取失败类为 180 行有文本但无匹配标签、58 行报告标题/年份正常但发行人栏目版式未匹配；13 条 `REPORT_FETCH_FAILED` 的原始失败原因为 `pdftotext` 空文本/过短，属于被误归类的文本提取失败。无 URL 不解释为官方报告不存在，缺失 HTTP/PDF 元数据也不推断为下载失败。

旧 parser revision 的成功缓存实际为 22,751 行，全部分层：HIGH 34 行/18 家，MEDIUM 2,155 行/612 家，LOW 20,562 行/4,830 家，`INSUFFICIENT_LOCAL_EVIDENCE` 为 0。HIGH 的 34 行是释义/分支/子公司等 R3F-like 聚合风险。LOW 仅指现有元数据暂未发现同类风险，不代表已证明正确；风险规则与结果详见 `docs/cnipa_full_gap_diagnosis.md`。

确定性诊断 Pilot seed `20260930` 生成 94 个 firm-year、86 家企业，覆盖 9/9 gap 子类及所有实际非空 stale 风险层；包含 LOW negative controls。状态为 `FULL_NAME_DIAGNOSIS_READY_FOR_TARGETED_PILOT`，不改变 `STRICT_PILOT_GATE_PASS`、`CNIPA_ENTITY_NAME_NEEDS_FIX`、`zero_semantics=pending` 或 `missing_semantics=pending`。Pilot 未执行。本轮网络请求为 0，Full/status/state、cache、coverage 与全部 frozen Pilot/GT artifacts 的前后哈希一致；企业级明细仅在 ignored results。

## 4.4A-R4B 定向诊断 Pilot（部分执行）

沿用冻结的 94-row / 86-firm R4A manifest，指纹与 R4A 一致。预算守门达到 120 后即停止；30 份 PDF 收到 HTTP 200 并完成 TXT，5 个 index 样本未找到可选报告，其余样本未完成。已取回文件离线解析得到 24 行 `CONFIRMED_YEAR_END_NAME_ONLY`、2 行 `CONFIRMED_NO_CHANGE`、4 行 `LEGAL_NAME_EXTRACTION_FAILED`；其中至少 2 份 PDF 是年报摘要，不作为完整 H1 年报。

独立 source review 与 parser prediction 分离。当前 PASS denominator=0；84 行为 `SOURCE_UNRESOLVED`，10 个未联网控制为 `LOCAL_CONTROL_ONLY`，source-grounded accuracy 不可计算。HIGH/MEDIUM/LOW 各抽样 10 行，但未据此推断全体错误率或授权批量刷新。状态为 `TARGETED_DIAGNOSTIC_PILOT_NEEDS_FIX`。Full/status/state/cache、coverage、frozen GT 和 R4A 输入前后哈希一致。请求上限已用尽，本轮未继续请求。固定 Gate 仍为 `STRICT_PILOT_GATE_PASS`；整体仍为 `CNIPA_ENTITY_NAME_NEEDS_FIX`；zero/missing semantics 仍 pending。汇总见 `docs/cnipa_targeted_diagnostic_pilot.md`。
