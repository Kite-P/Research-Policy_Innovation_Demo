# 第一阶段科研训练成果：基础数据工程与企业创新面板

## 一、研究方向

总体研究方向是“产业政策连续性 / 预期管理”与“企业创新策略”的交叉研究。第一阶段的定位是建立可复现的公司年度研究数据库、构建企业创新指标，并验证 Python + Stata 实证分析管线。

当前尚未进入政策文本核心变量阶段，因此本报告中的固定效应结果是 baseline diagnostic，不是政策连续性的正式因果识别结果。

## 二、数据体系

| 数据 | 实际范围 |
|---|---|
| Financial | 40 firms，2020–2025，240 个 clean firm-year；raw 260 行 |
| Profile | 42 家公司；40 家财务公司完整覆盖，2 家额外公司被排除出研究样本 |
| Patent | raw 225 行、40 家公司、220 个唯一 firm-year；最终 clean 220 行 |

## 三、数据质量与清洗

### Financial

财务数据完成了股票代码和年份标准化、数字字符串解析、真实缺失识别、完全重复与冲突重复区分、ROE 一致性核验及已确认污染处理。最终 240 个 `stock_code + year` 唯一。

### Profile

Profile 完成股票代码、公司名称、省份和上市日期格式统一；保留所有制 3 条真实缺失和上市日期 10 条真实缺失。最终 42 个唯一 `stock_code`，其中 900001、900002 不在财务研究样本内。

### Patent

原始专利表的股票代码有 3 条非标准格式记录（短码或首尾空格），标准化采用 strip、纯数字检查和 zfill(6)，未产生代码碰撞。标准化 firm-year 后识别 5 个重复组、10 条重复组成员：4 组完全重复、1 组引用数冲突。完全重复只保留一份；冲突组结合字段缺失和引用数分布保留证据更充分的版本。

三个专利字段各有 1 条原始缺失。`patent_citations=99,999` 和冲突版本 `1,234` 均明显脱离主体分布，且无法从可靠信息恢复，因此对应单元格设为 missing；没有填 0、均值或中位数，也没有删除整个 firm-year。最终引用字段缺失 2 条，其他两个专利字段各缺失 1 条。

## 四、统一研究面板

最终 `research_panel_base` 为 240 行、40 家公司、2020–2025 六个年份，每年 40 条，`stock_code + year` 唯一。

- Financial × Profile：以财务面板为左表，按 `stock_code` many-to-one 合并，240/240 条成功匹配；Profile 的 2 家额外公司不进入研究面板。
- Panel × Patent：按 `stock_code + year` one-to-one 左连接，面板行数保持 240。
- `patent_record_present` 由 merge provenance 构造：220 条为 1，20 条为 0。
- 对 Patent 中不存在的 firm-year，`invention_patents`、`utility_patents`、`patent_citations` 保持 missing。未观测专利记录不等于专利数为 0。

## 五、研究变量

| 变量 | 含义 | 公式 |
|---|---|---|
| `size_ln` | 企业规模 | `ln(total_assets)` |
| `leverage` | 资产负债率 | `total_liabilities / total_assets` |
| `roa` | 总资产收益率 | `net_profit / total_assets` |
| `rd_intensity` | 研发强度 | `rd_expense / revenue` |
| `cash_ratio` | 现金资产比 | `cash / total_assets` |
| `employee_ln` | 员工规模 | `ln(employees)` |
| `firm_age` | 上市年龄 | `year - listing_year + 1` |
| `patent_total` | 专利总量 | `invention_patents + utility_patents` |
| `patent_total_ln` | 专利总量对数 | `ln(1 + patent_total)` |
| `invention_ln` | 发明专利对数 | `ln(1 + invention_patents)` |
| `citation_ln` | 专利引用对数 | `ln(1 + patent_citations)` |
| `invention_share` | 发明占比 | `invention_patents / patent_total` |
| `citations_per_invention` | 单件发明引用 | `patent_citations / invention_patents` |

完整定义见 [`docs/variable_dictionary.md`](variable_dictionary.md)。变量面板保持 240 行、key 不变；全部数值变量无 `inf/-inf`。`patent_record_present=0` 的全部专利衍生变量保持 missing。本阶段未做 winsorization。

## 六、描述统计

| Variable | N | Missing | Mean | SD | Median | Min | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| `size_ln` | 239 | 1 | 23.911332 | 0.802557 | 24.140172 | 20.531485 | 24.811137 |
| `leverage` | 238 | 2 | 0.465786 | 0.183971 | 0.465852 | 0.156780 | 0.798617 |
| `roa` | 237 | 3 | 0.139127 | 0.693181 | 0.028604 | -1.136998 | 8.951074 |
| `rd_intensity` | 239 | 1 | 0.060018 | 0.031706 | 0.059510 | 0.005026 | 0.118347 |
| `patent_total_ln` | 218 | 22 | 3.064146 | 0.234241 | 3.044522 | 2.302585 | 3.555348 |
| `invention_ln` | 219 | 21 | 2.105369 | 0.339647 | 2.079442 | 1.098612 | 2.833213 |
| `citation_ln` | 218 | 22 | 3.089637 | 0.422849 | 3.135494 | 1.791759 | 4.174387 |

完整结果由 `results/first_stage/descriptive_statistics.csv` 生成，未手工改写结果文件。

## 七、相关性

使用 Pearson correlation 和 pairwise available observations，并输出每一对变量的实际 N。较高的相关关系包括：`invention_ln` 与 `citation_ln` 为 0.886898（N=217），`invention_ln` 与 `invention_share` 为 0.751348（N=218），`patent_total_ln` 与 `invention_ln` 为 0.598213（N=218）。这些是相关性，不是因果结论。

## 八、第一版基准诊断

模型均为 Firm FE + Year FE + firm-clustered SE，Stata 命令族为 `xtreg ..., fe vce(cluster firm_id)` 并加入 `i.year`。

| Model | Outcome | RD coefficient | SE | p-value | N | Firms | Within R2 |
|---|---|---:|---:|---:|---:|---:|---:|
| A | `patent_total_ln` | -0.250261 | 0.488121 | 0.611051 | 213 | 40 | 0.028313 |
| B | `invention_ln` | 0.622818 | 0.808302 | 0.445631 | 214 | 40 | 0.047614 |
| C | `citation_ln` | 1.069395 | 1.054496 | 0.316772 | 213 | 40 | 0.050839 |

当前模型没有政策变量，数据为模拟训练数据，以上结果仅验证变量和面板回归管线，不构成“研发投入显著促进创新”或政策假设成立的因果结论。

## 九、第一阶段已经完成的能力

原始数据审计、Python 数据清洗、面板主键管理、跨表匹配、专利创新指标、变量构造、Parquet / Stata 双格式、Python / Stata 双端验证、固定效应模型、聚类标准误、pytest、Ruff 和 Git 可复现工作流均已完成。

## 十、当前限制

- 当前使用模拟训练数据；
- 公司样本规模较小；
- 专利存在部分 firm-year 未观测；
- 尚未接入真实 CSMAR/WIND/专利数据库；
- 尚未建立正式政策文本语料库；
- 尚未构建政策连续性指标；
- 当前 FE 模型只是 baseline diagnostic；
- 不能据此进行真实政策因果结论。

## 十一、下一章入口

下一阶段应从政策文本数据开始，依次进行文本清洗、政策连续性 / 预期管理指标构建、地区或行业政策与 firm-year 匹配、正式识别设计、主回归、稳健性、异质性和机制分析。本次第一章封存后不提前实施第二章。
