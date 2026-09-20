# 4.1P—4.3F 免费真实数据阶段报告

## Git

- 4.1P: `017ac3316becfc5aa9fe976bb99adb3a5c29382c`
- 4.2F: `bf8cf6eedaf13a32df079756f50d872d858e353b`
- 4.2F-R: `3da731e9105a72d1dff23fa7e228fba9a16bc4a3`
- 4.3F-R: 本轮提交后记录

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

## Blocking Issues

1. CNIPA 仍需用户合法注册后才能进行人工专利导出。
2. BSE 官方新旧代码表需通过合法下载作为本地输入。
3. Profile pilot 仍受 CNINFO 返回结构缺少 `count` 的接口问题影响，法定名称、行业和省份 gate 未通过。
4. 全市场财务抓取是可恢复的长时间任务，当前仅完成 50 家混合样本 pilot，未启动全市场抓取。

## Next User Action

`REAL_UNIVERSE_NEEDS_FIX`
