# 第四章 4.1 真实数据研究设计

## 研究总体与分析单位

正式研究总体为中国大陆 A 股上市公司，覆盖上海证券交易所、深圳证券交易所和北京证券交易所。分析单位为 `firm-year`。企业进入某年度样本的前提是该年度处于上市期间；退市企业保留其实际上市期间内的年度观测，不因退市本身删除。

财务与公司基本信息的准备窗口为 2020—2025 年。专利主结果的默认分析窗口冻结为 2020—2024 年，2025 年只采集并进行覆盖审计，不默认进入主回归。若专利数据库文档、更新政策和覆盖审计共同证明 2025 年申请年度数据足够完整，才可在第五章之前提出 2020—2025 年的额外稳健性版本；不得根据结果显著性决定是否纳入。

## 样本规则

- Baseline 排除金融业，优先依据中国证监会上市公司行业分类或数据源正式行业编码，不按公司名称猜测。
- 不因 ST 或 *ST 自动删除，保留 `st_flag`；排除 ST/*ST 只作为预注册稳健性分析。
- 北交所自 2021 年起纳入可覆盖的 A 股样本，2020 年不回填北交所上市状态。
- 政策匹配优先使用历史 firm-year 注册省份；若数据源只有当前注册地址，记录 `static_address` 并在报告中披露。
- `stock_code` 统一为 6 位字符串，同时保留 `exchange` 和数据源永久企业标识 `firm_id_source`（如可得）。不得只依赖公司名称。

## 财务口径与变量定义

Baseline 使用合并财务报表，禁止在企业之间混用母公司与合并口径。必需字段包括总资产、总负债、营业收入、净利润、现金、研发支出和员工人数。净利润优先采用归属于母公司股东的净利润；若所选数据库仅提供合并净利润，则全样本统一使用该字段，并将来源定义写入 schema。

核心变量冻结为：

| 变量 | 定义 |
|---|---|
| `size_ln` | `ln(total_assets)` |
| `leverage` | `total_liabilities / total_assets` |
| `roa` | `net_profit / total_assets` |
| `cash_ratio` | `cash / total_assets` |
| `employee_ln` | `ln(employees)` |
| `rd_intensity` | `rd_expense / revenue`，用于描述统计和未来机制，不进入第五章 baseline controls |

现金优先采用货币资金或数据源明确规定的 cash and cash equivalents；研发字段必须以数据源 metadata 的正式定义为准；员工人数采用期末人数或数据源明确规定的时点人数。

## 专利测量

主时间口径为专利申请年，不静默改用授权年。Primary 专利数量为发明专利申请数与实用新型专利申请数之和，单独保留 `invention_patents` 和 `invention_ln`；外观设计保留为 `design_patents` 审计字段，但不进入 baseline `patent_total`。

专利来源正式切换为国家知识产权局知识产权数据资源公共服务系统及其专利检索与分析系统。由于免费 CNIPA 数据没有现成的上市公司—控制子公司映射，第一版真实研究采用 `listed_entity_only`，只纳入上市公司法人本身及经过验证的历史法人全称，不自动加入简称、子公司或模糊名称。

专利无记录不能直接解释为零。只有在完整企业年度总体中确认该企业当年无专利记录时，才可定义为零；只列出有专利企业的数据库必须先建立完整企业总体；覆盖不完整或实体匹配失败时保持 missing。`zero_semantics` 和 `missing_semantics` 必须在 4.4 前依据来源文档和审计结果书面确定。

引用数据是可选的 secondary outcome，不是第五章 baseline 的硬性条件。只有在来源明确给出引用定义、观察截止日、前向引用窗口和自引规则时才使用；否则不构造真实 `citation_ln` 主结果，并将其记录为不可比的 measurement limitation。

## 2025 Patent Coverage Risk

2025 年申请存在公开滞后和右截尾风险。因此 2025 年只进入采集与审计，不进入 primary real analysis。未来 4.4 的覆盖审计必须报告来源最新更新时间，以及 2020、2021、2022、2023、2024、2025 各申请年度的计数，并记录数据库 documentation、update policy、entity coverage 和零专利 firm-year universe。未获得完整性证据前，`PRIMARY_REAL_ANALYSIS_END_YEAR = 2024`。

## 政策时间范围

真实 primary 企业分析为 2020—2024 年，因此需要 2019—2024 年政策来源以构造滞后前一年的连续性指标。已有 2025 年政策文本继续保留；政策来源扩展建议保持 2019—2025 年，以便未来进行有来源依据的 2025 稳健性分析。

## 数据来源优先级与许可边界

公司基本信息、财务报表、行业、注册地址和 ST 状态优先使用一个可同时覆盖这些模块的结构化学术金融数据库，以减少跨源定义差异。候选包括 CSMAR、Wind、CNRDS 及学校合法提供的其他数据库；具体模块、表名和字段定义必须在实际访问后记录，不凭记忆填写。

专利来源为国家知识产权局官方免费数据系统。当前尚未注册或下载数据；真实数据只能来自用户合法访问的数据、学校数据库订阅、官方公开数据或明确允许使用的接口；不绕过登录或付费墙，不记录账号、密码、token、cookie 或许可证信息。

## 第四章与第五章分工

第四章负责真实数据来源、样本构成、字段定义、实体匹配、覆盖审计和 measurement limitation。第五章仅在 4.1—4.4 完成并冻结数据版本后，按第三章已冻结的识别设计重跑真实企业面板与正式推断。当前不下载专利、不构造真实回归结果；4.2F 和 4.3F 仅处理公开上市公司总体与免费财务面板。

## 当前状态

4.1P 已完成免费专利来源切换，当前状态为 `CNIPA_REGISTRATION_REQUIRED`。

AKShare/CNINFO 在 20 家 pilot 上取得了 Profile、法定公司全称、行业、注册地址和省份；AKShare/EastMoney 公开财务接口取得了资产、负债、现金、收入和净利润，字段分别固定为 `TOTAL_ASSETS`、`TOTAL_LIABILITIES`、`MONETARYFUNDS`/`MONETARY_FUNDS`、`TOTAL_OPERATE_INCOME` 和 `PARENT_NETPROFIT`。EastMoney F10 指标接口取得了 2022—2024 年员工人数 60/60，20 家企业均有三年变化。研发费用 `RESEARCH_EXPENSE` 为 57/60；历史注册地址和 firm-year ST 状态仍未获得。

Google Patents BigQuery 已从正式来源撤销，不再要求认证。CNIPA 尚未注册或下载，当前只完成查询、解析和名称规范工具准备。

因此：

- 不修改第三章冻结变量；
- 不把 BSE 从正式总体中静默删除，正式下载前继续做全市场覆盖审计；
- 员工控制已有免费 pilot 字段，不再标记为不可得，但正式数据仍需统一口径审计；
- 不把 pilot 结果当作正式全市场真实数据；
- 不下载专利、不扩展政策、不合并真实政策面板、不运行真实回归。

完整结果见 [`free_source_feasibility_report.md`](free_source_feasibility_report.md)。

## 4.2F 当前执行状态

已使用 SSE、SZSE、BSE 当前列表及上海、深圳历史退市列表构建 2020—2025 firm-year universe，输出为本地 ignored 的 `data/processed/real_company_universe.parquet` 和 `.dta`。当前结果为 5,690 家企业、30,328 个合法 firm-year，其中当前企业 5,449 家、退市企业 241 家；BSE 2020 年观测已排除。

Profile pilot 已从 CNINFO 切换至 EastMoney F10 `RPT_F10_BASIC_ORGINFO`。正式 Profile 全量返回 5,690 个 firm-level 记录，`ORG_NAME`、`PROVINCE`/`REG_ADDRESS`、`INDUSTRYCSRC1`、`EM2016` 和 `ORG_CODE` 均通过字段审计；不使用证券简称回填法人全称。`real_company_universe_enriched` 保持 30,328 行，Stata 主键与年份复核通过。

## 4.2F-E Profile 收口与财务覆盖 Gate

本轮已完成：

- 旧 CNINFO Profile 路线冻结为 `AKSHARE_CNINFO_PROFILE_INCOMPATIBLE`，不再作为正式 Profile 来源；
- EastMoney Schema probe、60 家分层 Profile pilot 和 5,690 家全量 enrichment；
- Profile 缓存按 `firm_key` 保存，串行请求间隔不少于 0.8 秒，403/429/验证码响应立即停止；
- 当前企业法定名称、省份和 CSRC 行业覆盖率均为 100%，ORG_CODE 非空率为 100%，省份冲突数为 0；
- `real_company_universe_enriched.parquet` 与 `.dta` 已生成，30328 个 `firm_key + year` 无重复，年份为 2020—2025，交易所分布与原总体一致；
- 财务缓存键改为 `firm_key`，并增加资产负债表、利润表、员工指标可用性和结构化 `failure_reason` 字段；
- 旧 50 家财务 pilot 已输出字段缺失分解；新的分层财务 pilot 实际为 70 家，因当前总体不存在 BSE 后 2021 新上市层；
- 财务 Gate 结果：BSE 转板层、SZSE 当前层通过 90% 核心字段门槛；SSE 当前层和近期 IPO SSE 未通过，退市层也未通过。

因此当前真实数据状态为 `READY_FOR_FULL_FINANCIAL_FETCH`，仅表示 SSE/SZSE 当前非金融企业财务 Gate 已通过，不表示已经完成全市场财务抓取。BSE 仍需官方新旧代码映射，历史 firm-year 省份仍未解决。本轮不进入政策匹配、专利下载或第五章真实回归。
