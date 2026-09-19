# 4.1F-R 免费数据源修正完成汇报

## 1. Git

- Previous 4.1F commit: `cbb5357ea2d229b8c1d2a693fb4e9c913b1c8bcf`
- 本轮修订提交：见 Git 记录
- 本轮仅包含一次提交和一次 push；pilot 结果、缓存、网络响应和日志均保留在 Git ignored 的 `results/free_source_pilot/`

## 2. Environment

- Python: 3.13.15
- AKShare: 1.18.96
- BigQuery CLI: `bq` 未安装
- Google Cloud CLI: `gcloud` 未安装
- 全项目 pytest、Ruff 和依赖检查在提交前执行

## 3. Pilot Universe

固定样本为 20 家：SSE 8 家、SZSE 8 家、BSE 4 家，覆盖 2022—2024 年，共 60 个 firm-year。样本与上一版 4.1F 保持一致，不因结果调整。

## 4. Profile Feasibility

SSE、SZSE、BSE 的 Profile 请求均为 100% 成功。公司全称、行业、注册地址和省份分别为 20/20；注册地址是当前静态注册地址，不等同于历史 firm-year 注册省份。ST firm-year 历史状态仍未获得可靠免费字段。

## 5. Financial Field Mapping

| Target | Selected source field | Definition | Coverage | Status |
|---|---|---|---:|---|
| `total_assets` | `TOTAL_ASSETS` | 合并期末总资产 | 60/60 | PASS |
| `total_liabilities` | `TOTAL_LIABILITIES` | 合并期末总负债 | 60/60 | PASS |
| `cash` | `MONETARYFUNDS` / `MONETARY_FUNDS` | 货币资金 | 60/60 | PASS |
| `revenue` | `TOTAL_OPERATE_INCOME` | 营业总收入 | 60/60 | PASS |
| `net_profit` | `PARENT_NETPROFIT` | 归属于母公司所有者的净利润 | 60/60 | PASS |
| `rd_expense` | `RESEARCH_EXPENSE` | 研发费用 | 57/60 | PARTIAL |
| `employees` | `STAFF_NUM`（F10 指标） | 报告期末员工人数 | 60/60 | PASS |

本轮同时保留 `OPERATE_INCOME` 和 `NETPROFIT` 作为审计字段，生成 `financial_definition_audit.csv`。收入两列在 pilot 中数值一致；净利润的母公司口径与合并净利润在 44/60 个 firm-year 不一致，因此 baseline 固定使用 `PARENT_NETPROFIT`，不混用口径。

## 6. Annual Observation Coverage

| Exchange | Expected firm-years | Core financial complete | Employee complete |
|---|---:|---:|---:|
| SSE | 24 | 24/24 | 24/24 |
| SZSE | 24 | 24/24 | 24/24 |
| BSE | 12 | 12/12 | 12/12 |

核心财务字段包括资产、负债、现金、收入和净利润。20 家企业的员工人数均有 2022、2023、2024 三个年度值，20/20 家企业的三年值均发生变化，未发现静态复制问题。

## 7. R&D and ST

`RESEARCH_EXPENSE` 可作为研发费用字段，覆盖 SSE 24/24、SZSE 21/24、BSE 12/12；其缺失记录保留为 missing，不补零。ST/*ST firm-year 历史状态仍不可得，因此不进入 baseline 样本删除规则。该部分不修改第三章冻结变量。

## 8. Google Patents

- `bq` 和 `gcloud` 均未安装；未登录、未执行 BigQuery schema、freshness 或实体匹配查询。
- 专利 SQL 已修正为对 `assignee` 与 `assignee_harmonized` 分别 `UNNEST`，并使用 `NORMALIZE` 后的名称匹配；相关查询构造测试通过。
- 当前专利状态仍为 `GOOGLE_AUTH_REQUIRED`，不伪造 2020—2025 覆盖率、最新申请日期或企业匹配结果。

## 9. Result and Scope Decision

`FREE_FINANCIAL_READY_PATENT_AUTH_REQUIRED`

免费 Profile、财务核心字段和员工人数 pilot 已通过；研发费用属于可用但部分缺失的描述性字段；历史注册地址、历史 ST 和专利认证仍是限制。BSE 不从正式总体中静默删除，正式数据下载前仍需进行全市场覆盖审计。4.2F 未执行。

## 10. Repository Boundary

- raw data、pilot result、cache、credentials 和绝对路径均未进入 Git tracked files；
- 本地结果位于 `results/free_source_pilot/`，继续保持 ignored；
- 本轮未提交 4.1F-R 计划文本；
- 提交前执行 staged diff、关键词和边界检查。

## 11. Stop

`4.2F NOT EXECUTED`
