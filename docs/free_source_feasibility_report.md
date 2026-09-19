# 4.1F 免费数据源可行性验证完成汇报

## 1. Git

- Commit: 本节唯一提交（最终 hash 以 Git 记录为准）
- HEAD: 本节 push 后核对
- origin/main: 本节 push 后核对
- status: 本节 push 后核对

本节只允许一个 commit 和一次 push。pilot 结果、缓存、网络响应和日志均保留在 Git ignored 的 `results/free_source_pilot/`。

## 2. Environment

- Python: 3.13.15
- AKShare: 1.18.96
- pytest: 新增测试通过；最终以全项目测试结果为准
- Ruff: 最终以全项目检查结果为准
- BigQuery CLI: `bq` 未安装
- Google Cloud CLI: `gcloud` 未安装

## 3. Pilot Universe

| Exchange | Firms |
|---|---:|
| SSE | 8 |
| SZSE | 8 |
| BSE | 4 |

固定样本如下：

| Exchange | Stock code | Stock name |
|---|---|---|
| SSE | 603339 | 四方科技 |
| SSE | 688677 | 海泰新光 |
| SSE | 600843 | 上工申贝 |
| SSE | 603040 | 新坐标 |
| SSE | 600855 | 航天长峰 |
| SSE | 600110 | 诺德股份 |
| SSE | 600575 | 淮河能源 |
| SSE | 603666 | 亿嘉和 |
| SZSE | 002014 | 永新股份 |
| SZSE | 300268 | 佳沃食品 |
| SZSE | 300161 | 华中数控 |
| SZSE | 001914 | 招商积余 |
| SZSE | 300556 | 丝路视觉 |
| SZSE | 300455 | 航天智装 |
| SZSE | 002873 | 新天药业 |
| SZSE | 300246 | 宝莱特 |
| BSE | 920436 | 大地电气 |
| BSE | 920185 | 贝特瑞 |
| BSE | 920266 | 生物谷 |
| BSE | 920489 | 佳先股份 |

样本由交易所公开列表按固定 SHA-256 排序规则选择，均满足上市日期不晚于 2022-01-01。

## 4. Profile Feasibility

### SSE

- success: 8/8
- company_name: 8/8
- industry: 8/8
- address: 8/8
- province: 8/8

### SZSE

- success: 8/8
- company_name: 8/8
- industry: 8/8
- address: 8/8
- province: 8/8

### BSE

- success: 4/4
- company_name: 4/4
- industry: 4/4
- address: 4/4
- province: 4/4

北交所选定样本通过了 `stock_profile_cninfo` Profile 请求，取得了法定公司全称、行业、上市日期和注册地址。

## 5. Profile Limitations

- 地址为当前接口提供的 static registered address，不是历史 firm-year 地址。
- 曾用简称只作为审计字段，不能自动视为历史法人全称。
- 本 pilot 中 BSE 取得了法定公司全称，但这只证明样本级接口可用，不替代全市场覆盖审计。
- ST 状态未获得可靠的 firm-year 历史字段。

## 6. Financial Interfaces

- balance-sheet interface: `ak.stock_balance_sheet_by_report_em(symbol=em_symbol)`
- profit-sheet interface: `ak.stock_profit_sheet_by_report_em(symbol=em_symbol)`
- BSE support: 可返回资产负债表数据，但收入和净利润候选字段仍需人工确认，因此只能判为 partial。
- 年度筛选：仅保留 `REPORT_DATE` 为 2022-12-31、2023-12-31、2024-12-31 的行。

## 7. Financial Field Mapping

| Target | Actual source column | Coverage | Status |
|---|---|---:|---|
| `total_assets` | `TOTAL_ASSETS` | 100% | PASS |
| `total_liabilities` | `TOTAL_LIABILITIES` | 100% | PASS |
| `cash` | `MONETARYFUNDS`/`MONETARY_FUNDS` 候选 | 100% | PASS |
| `revenue` | `TOTAL_OPERATE_INCOME` 与 `OPERATE_INCOME` 同时存在 | 0% | AMBIGUOUS |
| `net_profit` | `NETPROFIT` 与 `PARENT_NETPROFIT` 同时存在 | 0% | AMBIGUOUS |
| `rd_expense` | `RESEARCH_EXPENSE` | SSE 100%、SZSE 87.5%、BSE 100% | PASS/PARTIAL |
| `employees` | 未识别可靠历史字段 | 0% | UNAVAILABLE_FREE_SOURCE |

按照计划，收入和净利润没有在多个候选列中擅自选择；当前不生成正式财务变量。

## 8. Annual Observation Coverage

| Exchange | Expected firm-years | Core financial complete |
|---|---:|---:|
| SSE | 24 | 0/24 |
| SZSE | 24 | 0/24 |
| BSE | 12 | 0/12 |

资产、负债和现金覆盖均达到 100%，但收入和净利润因列名歧义未纳入完整核心财务观测，因此 SSE/SZSE 未达到 90% gate。

## 9. Historical Employee Count

`UNAVAILABLE_FREE_SOURCE`

当前财务接口没有识别出可靠的 2022—2024 历史员工人数，未用当前员工数复制替代。

## 10. Historical ST Status

`UNAVAILABLE_FREE_SOURCE`

Profile 接口未提供可靠的 firm-year ST/*ST 历史状态字段。

## 11. Google BigQuery Environment

- bq installed: No
- gcloud installed: No
- authenticated: No
- billing enabled by task: No
- actual query executed: No
- maximum-bytes protection: 查询构造器设定 10 GB 上限；由于未安装 CLI，未执行 dry-run 或实际查询

## 12. Google Patents Schema

本机没有可用 BigQuery 身份验证环境，因此以下字段未被实际查询确认：

- publication_number: 未确认
- application_number: 未确认
- country_code: 未确认
- kind_code: 未确认
- filing_date: 未确认
- assignee: 未确认
- assignee_harmonized: 未确认

已实现 schema query、freshness query 和 exact-name query builder，但未把数据集名称直接当作可用来源。

## 13. Google Patents Freshness

`GOOGLE_AUTH_REQUIRED`

未执行 freshness query，因此没有伪造 2020—2025 计数或最新申请日期。

## 14. Patent Entity Match Pilot

未执行。根据计划，只有 freshness gate PASS 后才进行 20 家企业名称匹配。

## 15. BSE Decision Evidence

- Profile support: 4/4 PASS
- Financial support: partial；资产、负债、现金可得，收入和净利润列名歧义
- Patent matching support: 未测试，Google BigQuery 身份验证缺失

本节不修改正式研究总体，不静默删除 BSE。后续记录为 `PENDING_SCOPE_REVISION_BSE`。

## 16. R&D Availability

- source field: `RESEARCH_EXPENSE`
- coverage: SSE 24/24、SZSE 21/24、BSE 12/12
- definition certainty: 字段可识别，但最终研发支出定义仍需结合来源 metadata 确认

## 17. Employee-Control Issue

员工人数不可得，输出：

`PENDING_DESIGN_REVISION_EMPLOYEE`

不直接修改第三章 `employee_ln` 或 baseline controls。

## 18. Pilot Result

`FREE_STACK_NOT_READY`

原因：Profile 可用，但免费财务链的收入、净利润存在未解决的列名歧义，员工历史值不可得，Google Patents 尚未完成认证、schema 和 freshness 验证。

## 19. Recommended 4.2F Scope

- exchanges: 暂建议先以 SSE + SZSE 作为候选，不冻结正式总体；BSE 等待 `PENDING_SCOPE_REVISION_BSE` 审核
- years: Profile/财务 pilot 2022—2024；正式窗口仍按 4.1 既定设计
- Profile source: AKShare/CNINFO，注册地址标记为 static
- Financial source: AKShare/EastMoney 公开财务报表接口，但需先确认收入和净利润口径
- Patent source: Google Patents BigQuery 仍待免费身份验证和 freshness gate
- unresolved variables: `revenue`、`net_profit`、`employees`、历史 ST、历史注册地址、专利来源和实体匹配

## 20. Repository Boundary

- no raw data tracked: 是
- no pilot result tracked: 是
- no cache tracked: 是
- no credentials: 是
- no absolute paths: 是

## 21. Deviations

计划中指定的接口均已按低频 pilot 实际调用。由于 `revenue` 和 `net_profit` 出现多个候选列，未自动选择；由于缺少 BigQuery 身份验证，未执行专利查询。无其他偏离。

## 22. Stop

`4.2F NOT EXECUTED`
