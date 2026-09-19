# 4.1P—4.3F 免费真实数据阶段报告

## Git

- 4.1P: `017ac3316becfc5aa9fe976bb99adb3a5c29382c`
- 4.2F: `bf8cf6eedaf13a32df079756f50d872d858e353b`
- 4.3F: 本轮提交后记录

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

- total firms: 5,565
- total firm-years: 29,362
- SSE: 2,320 firms
- SZSE: 2,901 firms
- BSE: 344 firms
- years: 2020—2025
- BSE 2020 firm-years: 0

列表总体和 firm-year 展开已完成。当前公开列表对 SSE/SZSE 的注册地址、省份和正式行业字段覆盖不足，分别保留缺失并进入审计；不能把当前版本直接称为最终政策匹配面板。

## BSE Mapping

- official mapping source: 北京证券交易所新旧代码对照表。
- mapping rows loaded: 0；官方网页程序化请求返回 403，未绕过访问控制。
- unmatched BSE firms: 344。
- known mapping tests: `835185 → 920185`、`833266 → 920266` 已通过 fixture 测试。
- code-switch handling: 已实现读取官方合法下载文件后 old/new fallback；禁止前三位替换推算。

## Financial Panel

已完成面板引擎、缓存、断点、代码 fallback、请求阻断停止和变量构造。单公司真实烟测已通过；全市场长时间抓取尚未启动，因此下表暂不填报全市场 coverage：

| Year | SSE coverage | SZSE coverage | BSE coverage |
|---|---:|---:|---:|
| 2020—2025 | pending full fetch | pending full fetch | pending official mapping and full fetch |

核心字段固定为资产、负债、现金、营业总收入、归属于母公司所有者的净利润和员工人数；研发费用缺失保持 missing。

## Automated Verification

- targeted tests：4.3F 面板测试通过；
- full pytest/Ruff：在 4.3F 提交前重新执行；
- Stata 11：脚本已创建，需在生成正式总体后执行；
- Stata 12：脚本已创建，需在生成正式财务面板后执行；
- 不运行真实政策回归。

## Repository Boundary

原始数据、缓存、生成结果、日志和凭据均保持本地 ignored，不提交 GitHub。

## Blocking Issues

1. CNIPA 仍需用户合法注册后才能进行人工专利导出。
2. BSE 官方新旧代码表需通过合法下载作为本地输入。
3. 全市场财务抓取是可恢复的长时间任务，当前只完成引擎和真实单公司烟测，未宣称全市场已完成。

## Next User Action

`CNIPA_REGISTRATION_REQUIRED`
