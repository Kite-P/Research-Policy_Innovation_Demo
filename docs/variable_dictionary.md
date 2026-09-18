# 第一阶段研究变量字典

本字典对应 `data/processed/research_panel_variables.parquet`。变量在统一公司年度面板上构造，不做 winsorization；缺失值按分母、原始字段和专利记录 provenance 传播。

| variable | 中文名称 | formula | source | missing rule | interpretation | planned role |
|---|---|---|---|---|---|---|
| `size_ln` | 企业规模 | `ln(total_assets)` | `total_assets` | `total_assets <= 0` 或缺失 | 资产规模的对数 | 控制变量 |
| `leverage` | 资产负债率 | `total_liabilities / total_assets` | `total_liabilities`, `total_assets` | 资产分母不为正或任一缺失 | 负债融资程度 | 控制变量 |
| `roa` | 总资产收益率 | `net_profit / total_assets` | `net_profit`, `total_assets` | 资产分母不为正或任一缺失 | 资产获利能力 | 控制变量 |
| `rd_intensity` | 研发强度 | `rd_expense / revenue` | `rd_expense`, `revenue` | 收入分母不为正或任一缺失 | 研发投入相对营业收入的强度 | 主要解释变量候选 |
| `cash_ratio` | 现金资产比 | `cash / total_assets` | `cash`, `total_assets` | 资产分母不为正或任一缺失 | 现金资产缓冲程度 | 控制变量 |
| `employee_ln` | 员工规模 | `ln(employees)` | `employees` | 员工数不为正或缺失 | 人员规模的对数 | 控制变量 |
| `firm_age` | 企业上市年龄 | `year - listing_year + 1` | `year`, `listing_date` | 上市日期缺失或计算结果不合理 | 上市后的存续年数 | 描述/控制变量 |
| `patent_total` | 专利总量 | `invention_patents + utility_patents` | 专利字段、`patent_record_present` | 未观测记录或任一加总项缺失 | 发明与实用新型专利数量之和 | 结果变量构成 |
| `patent_total_ln` | 专利总量对数 | `ln(1 + patent_total)` | `patent_total` | `patent_total` 缺失或小于 0 | 专利产出的对数变换 | 结果变量 |
| `invention_ln` | 发明专利对数 | `ln(1 + invention_patents)` | `invention_patents`、`patent_record_present` | 未观测记录或字段缺失 | 发明专利产出的对数变换 | 结果变量 |
| `citation_ln` | 专利引用对数 | `ln(1 + patent_citations)` | `patent_citations`、`patent_record_present` | 未观测记录或字段缺失 | 专利引用表现的对数变换 | 结果变量 |
| `invention_share` | 发明专利占比 | `invention_patents / patent_total` | `invention_patents`, `patent_total` | 总专利不为正或任一缺失 | 专利结构中发明专利的占比 | 结果/描述变量 |
| `citations_per_invention` | 单件发明引用 | `patent_citations / invention_patents` | `patent_citations`, `invention_patents` | 发明专利不为正或任一缺失 | 每件发明专利的平均引用 | 结果/描述变量 |

## 已有字段的使用说明

`roe` 保留为原始清洗字段，暂不替换 `roa`。`province`、`industry`、`ownership` 和 `listing_date` 主要用于描述与后续匹配；它们基本是企业层面的时间不变特征，在 firm fixed effects 模型中通常会被企业固定效应吸收，不应强行解释为独立的时间变化系数。

`patent_record_present = 0` 表示当前专利表没有该 firm-year 记录，不等于专利数为零。因此该状态下所有专利衍生变量均保持 missing。
