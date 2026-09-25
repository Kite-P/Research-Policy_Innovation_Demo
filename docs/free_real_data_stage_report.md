# 4.1P—4.3F 免费真实数据阶段报告

## Git

- 4.1P: `017ac3316becfc5aa9fe976bb99adb3a5c29382c`
- 4.2F: `bf8cf6eedaf13a32df079756f50d872d858e353b`
- 4.2F-R: `3da731e9105a72d1dff23fa7e228fba9a16bc4a3`
- 4.3F-R: `bed595b81b6b07818715748b1293733cc3014659`

## Patent Source Decision

- Google Patents BigQuery：正式撤销；不再要求认证。
- CNIPA：已选定为免费官方来源，尚未注册、登录或下载。
- patent entity scope：`listed_entity_only`。
- primary years：2020—2024 application year；2025 仅 coverage audit。

## CNIPA Preparation

- query generator：确定性去重、精确法定名称、无通配符；默认每批 20 家、1500 字符。
- parser：支持 XLSX/XML，输出统一字段。
- patent type：优先使用导出字段，无法确认时为 `unknown`。
- tests：已通过。

## Real Company Universe

- total firms: 5,690
- total firm-years: 30,328
- current firms: 5,449
- delisted firms: 241
- SSE: 2,390 firms
- SZSE: 3,014 firms
- BSE: 286 firms
- years: 2020—2025
- BSE 2020 firm-years: 0

已补入上海、深圳历史退市列表。`firm_key` 由交易所、规范证券代码和市场上市日期组成，不包含公司名称；北交所前身挂牌日期保留为 `predecessor_listing_date`，市场口径统一从 2021-11-15 起算。当前总体仍需完成法定名称、行业和省份的正式 Profile gate。

## BSE Mapping

- official mapping source: 北京证券交易所新旧代码对照表。
- mapping rows loaded: 0；官方网页程序化请求返回 403，未绕过访问控制。
- unmatched BSE firms: 286。
- known mapping tests: `835185 → 920185`、`833266 → 920266` 已通过 fixture 测试。
- code-switch handling: 已实现读取官方合法下载文件后 old/new fallback；禁止前三位替换推算。

## Financial Panel

已完成面板引擎、缓存、断点、代码 fallback、请求阻断停止和变量构造。引擎现在只接受与当前有效总体完全一致的 `firm_key + year` 缓存键，并保留缺失年度。50 家混合样本的全有效年度 pilot 已完成：201 个 firm-year、50 家企业、0 个重复键、0 个上市前年度、0 个退市后年度；财务核心字段成功 130/201。

| Year | SSE coverage | SZSE coverage | BSE coverage |
|---|---:|---:|---:|
| 50-firm pilot | 176 rows / 45 firms | 0 | 25 rows / 5 firms |

核心字段固定为资产、负债、现金、营业总收入、归属于母公司所有者的净利润和员工人数；研发费用缺失保持 missing。

## Automated Verification

- targeted tests：4.3F-R 面板测试通过；
- full pytest/Ruff：本轮提交前重新执行；
- Stata 11：脚本已创建；当前环境未发现可调用的 Stata 可执行文件，未虚报执行结果；
- Stata 12：脚本已创建，需在生成正式财务面板后执行；
- 不运行真实政策回归。

## Repository Boundary

原始数据、缓存、生成结果、日志和凭据均保持本地 ignored，不提交 GitHub。

## 4.2F-E Profile 收口与财务覆盖 Gate

- Profile 来源已由 CNINFO 切换为 EastMoney F10 `RPT_F10_BASIC_ORGINFO`；CNINFO 路线记录为 `AKSHARE_CNINFO_PROFILE_INCOMPATIBLE`。
- 5,690 个 firm-level Profile 记录全部返回 `PASS`；合法名称、省份、CSRC 行业和 ORG_CODE 覆盖率均为 100%，省份冲突为 0。
- 丰富后的企业总体仍为 30,328 个 firm-year，30328 个 `firm_key + year` 通过 Stata `isid`，年份为 2020—2025。
- Profile 试点通过后执行了全量 enrichment；原始数据、缓存和生成结果仍保持 ignored，不提交 GitHub。
- 财务缓存改用 `firm_key`，并记录来源组件可用性、字段级缺失和失败原因。
- 旧 50 家 pilot 的成功率为 130/201；新的分层试点实际为 70 家，BSE 后 2021 新上市层在总体中为 0 家。SSE 当前层与近期 IPO SSE 未达到 90% 核心字段覆盖，财务 Gate 未通过。

当前阶段状态：`PROFILE_GATE_PASS_FINANCIAL_GATE_NEEDS_FIX`。本轮未执行政策回归、专利下载或第五章真实识别。

## 4.2F-E-R 财务 Gate 定义纠错与复核

- BSE 日期逻辑已修正：286 家中 transferred 67 家，native/post-2021 219 家；BSE 2020 firm-year 为 0。
- 新总体和 enriched universe 已重新生成；旧 Profile cache 仅按相同 `firm_key` 复用，native BSE 新键重新查询，Profile 5690/5690 PASS。
- `INDUSTRYCSRC1` 的实际值是层级化中文 CSRC 行业名称，不是数值代码；金融业规则为值等于 `金融业` 或以 `金融业-` 开头。金融企业 132 家，非金融企业 5558 家，缺失 0 家。
- 财务 pilot 使用 seed `20260923` 的 SHA-256 分层抽样，8 个 strata 均达到目标，共 80 家；金融企业和缺失行业企业均未进入 pilot。
- SSE current nonfinancial：25/25，`SSE_FINANCE_GATE_PASS`；SZSE current nonfinancial：25/25，`SZSE_FINANCE_GATE_PASS`；合并主 Gate 通过。
- SSE 失败分解显示失败集中在 5 家退市企业的 2020 观测，不属于 current nonfinancial 主 Gate；字段缺失和 `QUERY_FAILED` 已按 exchange、stratum、current/delisted、year 输出。
- BSE transferred 与 native 均单独保留；由于官方新旧代码映射仍未取得，标记为 `BSE_GATE_PENDING_MAPPING`，不阻塞 SSE/SZSE 主 Gate。
- EastMoney `province` 仍是 static Profile，不作为已解决的 historical firm-year province；正式政策匹配前仍需另行冻结省份口径。

当前阶段状态：`READY_FOR_FULL_FINANCIAL_FETCH`。本轮未启动全市场抓取、政策匹配、CNIPA 下载或真实回归。

## Blocking Issues

1. CNIPA 仍需用户合法注册后才能进行人工专利导出。
2. BSE 官方新旧代码表需通过合法下载作为本地输入。
3. 正式全市场财务抓取前仍需保持逐 firm_key 缓存、来源组件可用性和失败原因审计。
4. BSE 官方新旧代码表仍需通过合法下载作为本地输入；本轮未用前缀推算替代官方映射。

## Next User Action

## 4.3F-Pilot-R 财务 Gate 最终确认

- pilot 样本：100 家企业、531 个 firm-year，限定 2020—2025。
- SSE current nonfinancial：35 家、201 个 firm-year，核心完整率 100%，PASS。
- SZSE current nonfinancial：35 家、200 个 firm-year，核心完整率 100%，PASS。
- 退市 SSE/SZSE：分别单独报告，失败不影响主 Gate。
- BSE transferred/native：分别单独报告，状态保持 `BSE_MAPPING_REQUIRED`；未使用前三位转换，也未伪造 mapping。
- 缓存第二次运行 100/100 命中；未重新请求 API。
- Stata pilot 校验通过；全市场 5690 家正式财务抓取尚未执行。

当前阶段状态：`READY_FOR_FULL_FINANCIAL_FETCH`。

下一轮仅在用户明确指令后执行 `4.3F Full`，不得自动开始。

## 4.3F-Full-Pipeline 真实财务全量抓取流水线

- Phase A 正式完成：5,272 家 SSE/SZSE 非金融企业、28,548 个 firm-year，53/53 个 chunk 完成。来源总体为 5,690 家、30,328 个 firm-year；BSE 和金融业企业不属于 Phase A。
- 状态计数：5,008 `COMPLETE`、4 `PARTIAL`、260 `QUERY_FAILED`；`NOT_FETCHED=0`、`SOURCE_BLOCKED=0`。目标企业均保留，未按抓取结果删样本。
- Finalizer 核验正式面板 5,272 家、28,548 行，重复键 0、非法上市/退市边界 firm-year 0，交易所仅 SSE/SZSE。Stata/MP 18 实际验证通过 firm-year 唯一性、年份、交易所、变量类型及派生变量有限值检查，sentinel 为 `FINANCIAL_SSE_SZSE_FULL_VALIDATION_PASS`。
- 当前企业核心字段完整率：SSE 99.1688%，SZSE 99.4936%；当前企业 R&D 覆盖率分别为 92.3531% 和 95.4295%。核心质量 Gate 通过。完整面板核心字段缺失数见 `docs/full_financial_fetch_pipeline.md`。
- BSE 状态仍为 `BSE_MAPPING_REQUIRED`，等待合法取得的官方新旧代码映射；132 家金融业企业保持排除。CNIPA、政策匹配和回归未执行。

当前状态：`SSE_SZSE_FULL_FETCH_COMPLETE`。早期 200 家 canary 仅作为链路验证历史，不替代正式 Phase A 结果。
