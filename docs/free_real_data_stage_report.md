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

`REAL_UNIVERSE_NEEDS_FIX`
