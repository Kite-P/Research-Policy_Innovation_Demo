# 第一章执行汇报：基础数据工程、研究面板与第一阶段实证管线

> 汇报范围：1.1 财务数据、1.2 公司基本信息、1.3 专利数据、1.4 统一研究面板、1.5 研究变量、1.6 描述统计与第一版基准诊断、1.7 成果封存。
>
> 数据性质：模拟训练数据。本文中的固定效应回归仅用于验证变量和实证管线，不构成政策连续性或企业创新的正式因果结论。

## 一、结论先行

第一章已经完成并封存。

- 数据层：财务、Profile、Patent 已完成审计和清洗；
- 面板层：已构建 240 行、40 家企业、2020–2025 年的统一 firm-year 面板；
- 变量层：已构造财务、企业特征和专利创新变量；
- 分析层：已完成样本流、描述统计、相关性和三组 Firm FE + Year FE 诊断模型；
- 工程层：Python、Stata/MP、pytest、Ruff 和 Git 可复现流程均已验证；
- 交付层：五个新增 commit 均已 push，`HEAD == origin/main`，工作区 clean；
- 边界：尚未进入政策文本、政策连续性指标、DID、事件研究、稳健性、异质性或机制分析。

## 二、完成矩阵与 Git 交付

| 章节 | 已交付内容 | Commit | Push |
|---|---|---|---|
| 1.3 | 专利审计、清洗与验证 | `1ce1cb5` | 已完成 |
| 1.4 | 统一公司年度研究面板 | `06e7511` | 已完成 |
| 1.5 | 第一阶段研究变量 | `4438360` | 已完成 |
| 1.6 | 描述统计与基准诊断 | `8068e2d` | 已完成 |
| 1.7 | 第一章成果总结与封存 | `bc65710` | 已完成 |

最终状态：

```text
Branch: main
HEAD:  bc657103b78bd6822026bd34676a54d3b1bde4ea
origin/main: bc657103b78bd6822026bd34676a54d3b1bde4ea
git status --short: 无输出
```

## 三、数据体系与样本流

| 数据阶段 | 行数/规模 | 说明 |
|---|---:|---|
| Raw Financial | 260 行 | 40 家企业、2020–2025 |
| Clean Financial | 240 个 firm-year | `stock_code + year` 唯一 |
| Profile | 42 家企业 | 40 家匹配财务样本，2 家样本外 |
| Raw Patent | 225 行 | 40 家企业、5 个字段 |
| Clean Patent | 220 个 firm-year | `stock_code + year` 唯一 |
| Patent-observed research firm-year | 220 | `patent_record_present=1` |
| Final research panel | 240 个 firm-year | 40 家企业、2020–2025，每年 40 行 |

样本流的机器可读结果保存在：

```text
results/first_stage/sample_flow.csv
```

## 四、数据审计与清洗结论

### 4.1 Financial

完成了股票代码和年份标准化、数字字符串解析、真实缺失识别、完全重复与冲突重复区分、ROE 一致性核验及已确认污染处理。最终保留 240 个唯一 `stock_code + year`。

### 4.2 Profile

完成了股票代码、公司名称、省份和上市日期格式统一；保留所有制 3 条真实缺失和上市日期 10 条真实缺失。最终保留 42 个唯一 `stock_code`。其中 `900001`、`900002` 不属于财务研究样本，因此没有进入最终研究面板。

### 4.3 Patent

- 股票代码有 3 条非标准格式记录，采用 `strip → 纯数字验证 → zfill(6)` 标准化；
- 标准化 firm-year 后有 5 个重复组、10 条重复组成员；
- 4 组是完全重复，分别只保留一条；
- 1 组是 `patent_citations` 冲突，结合字段缺失和主体分布保留证据更充分的版本；
- 三个专利字段各有 1 条原始缺失；
- `patent_citations=99,999` 和冲突版本 `1,234` 明显脱离主体分布，且无法可靠恢复，因此设为 missing；
- 没有将未观测 firm-year 填为 0，也没有使用均值、中位数或 winsorization 替代缺失。

最终专利清洗结果：220 行、40 家企业、2020–2025，主键唯一。清洗后缺失数为：`invention_patents=1`、`utility_patents=1`、`patent_citations=2`。

专利清洗的核心文件：

- `notebooks/05_patent_audit.ipynb`
- `notebooks/06_patent_cleaning.ipynb`
- `src/patent_cleaning.py`
- `stata/03_validate_clean_patents.do`

## 五、统一研究面板

### 5.1 合并规则

1. 以 Clean Financial 作为 240 行面板骨架；
2. Financial × Profile：按 `stock_code` 做 many-to-one 左连接；
3. Panel × Patent：按 `stock_code + year` 做 one-to-one 左连接；
4. 从 Patent merge provenance 构造 `patent_record_present`；
5. 不根据专利字段是否 missing 反向推断记录是否存在。

### 5.2 最终结果

| 检查项 | 结果 |
|---|---:|
| 最终行数 | 240 |
| 企业数 | 40 |
| 年份数 | 6 |
| 年份范围 | 2020–2025 |
| 每年观测数 | 40 |
| Profile 匹配 | 240/240 |
| `patent_record_present=1` | 220 |
| `patent_record_present=0` | 20 |
| `stock_code + year` 重复数 | 0 |

对 20 个未观测专利 firm-year，`invention_patents`、`utility_patents` 和 `patent_citations` 均保持 missing。这表示“当前专利数据中没有记录”，不表示“专利数量为零”。

核心文件：

- `src/build_research_panel.py`
- `tests/test_research_panel.py`
- `notebooks/07_panel_build.ipynb`
- `stata/04_validate_research_panel.do`

## 六、第一阶段研究变量

| 变量 | 含义 | 公式 | 主要用途 |
|---|---|---|---|
| `size_ln` | 企业规模 | `ln(total_assets)` | 控制变量 |
| `leverage` | 资产负债率 | `total_liabilities / total_assets` | 控制变量 |
| `roa` | 总资产收益率 | `net_profit / total_assets` | 控制变量 |
| `rd_intensity` | 研发强度 | `rd_expense / revenue` | 主要解释变量候选 |
| `cash_ratio` | 现金资产比 | `cash / total_assets` | 控制变量 |
| `employee_ln` | 员工规模 | `ln(employees)` | 控制变量 |
| `firm_age` | 上市年龄 | `year - listing_year + 1` | 描述/控制变量 |
| `patent_total` | 专利总量 | `invention_patents + utility_patents` | 创新指标构成 |
| `patent_total_ln` | 专利总量对数 | `ln(1 + patent_total)` | 结果变量 |
| `invention_ln` | 发明专利对数 | `ln(1 + invention_patents)` | 结果变量 |
| `citation_ln` | 专利引用对数 | `ln(1 + patent_citations)` | 结果变量 |
| `invention_share` | 发明占比 | `invention_patents / patent_total` | 结构/结果变量 |
| `citations_per_invention` | 单件发明引用 | `patent_citations / invention_patents` | 结构/结果变量 |

统一规则：

- 比率变量仅在分母严格为正时计算；
- log 变量不接受非法输入；
- 上市日期缺失时不推测上市年份；
- `patent_record_present=0` 时所有专利衍生变量保持 missing；
- 变量面板保持 240 行和原始 firm-year key；
- 全部数值变量无 `inf/-inf`；
- 本阶段不做 winsorization。

完整字典：`docs/variable_dictionary.md`。

## 七、描述统计

以下为主要变量的真实输出摘要，完整结果见：

```text
results/first_stage/descriptive_statistics.csv
```

| Variable | N | Missing | Mean | SD | Median | Min | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| `size_ln` | 239 | 1 | 23.911332 | 0.802557 | 24.140172 | 20.531485 | 24.811137 |
| `leverage` | 238 | 2 | 0.465786 | 0.183971 | 0.465852 | 0.156780 | 0.798617 |
| `roa` | 237 | 3 | 0.139127 | 0.693181 | 0.028604 | -1.136998 | 8.951074 |
| `rd_intensity` | 239 | 1 | 0.060018 | 0.031706 | 0.059510 | 0.005026 | 0.118347 |
| `patent_total_ln` | 218 | 22 | 3.064146 | 0.234241 | 3.044522 | 2.302585 | 3.555348 |
| `invention_ln` | 219 | 21 | 2.105369 | 0.339647 | 2.079442 | 1.098612 | 2.833213 |
| `citation_ln` | 218 | 22 | 3.089637 | 0.422849 | 3.135494 | 1.791759 | 4.174387 |

## 八、相关性

采用 Pearson correlation 和 pairwise available observations，并同时输出每一对变量的实际 N：

```text
results/first_stage/correlation_matrix.csv
results/first_stage/correlation_n.csv
```

值得注意的相关关系：

- `invention_ln` 与 `citation_ln`：0.886898，N=217；
- `invention_ln` 与 `invention_share`：0.751348，N=218；
- `patent_total_ln` 与 `invention_ln`：0.598213，N=218。

这些结果只描述相关性，不表示因果关系。

## 九、第一版基准诊断

模型设定：

```text
Firm FE + Year FE + firm-clustered standard errors
xtreg outcome rd_intensity size_ln leverage roa cash_ratio i.year, fe vce(cluster firm_id)
```

真实输出：

| Model | Outcome | RD coefficient | SE | p-value | N | Firms | Within R2 |
|---|---|---:|---:|---:|---:|---:|---:|
| A | `patent_total_ln` | -0.250261 | 0.488121 | 0.611051 | 213 | 40 | 0.028313 |
| B | `invention_ln` | 0.622818 | 0.808302 | 0.445631 | 214 | 40 | 0.047614 |
| C | `citation_ln` | 1.069395 | 1.054496 | 0.316772 | 213 | 40 | 0.050839 |

结果文件：

```text
results/first_stage/regression_results.csv
```

解释边界：当前模型没有政策连续性变量，数据为模拟训练数据。因此不能写成“研发投入显著促进企业创新”或“政策假设成立”，只能表述为当前模拟样本中的管线诊断结果。

## 十、最终验证与复核证据

### Python

- `pytest`：13 passed；
- Ruff：`All checks passed!`；
- 变量面板：240 行、key 唯一、无 `inf/-inf`；
- Parquet 与 Stata 数据均完成回读验证。

### Stata

以下脚本均由 Stata/MP 18 实际运行完成：

```text
stata/01_validate_clean_financials.do
stata/02_validate_clean_profile.do
stata/03_validate_clean_patents.do
stata/04_validate_research_panel.do
stata/05_validate_research_variables.do
stata/06_first_stage_analysis.do
```

### Git 与隐私

- 五个新增章节 commit 均已 push；
- `HEAD == origin/main`；
- `git status --short` 无输出；
- staged 内容未包含 `data/`、`results/`、`.parquet`、`.dta` 或 `.log`；
- 本地绝对路径扫描无匹配；
- Stata 授权信息等敏感内容扫描无匹配。

## 十一、最终文件索引

### 公开追踪文件

- 审计与清洗：`notebooks/05_patent_audit.ipynb`、`notebooks/06_patent_cleaning.ipynb`、`src/patent_cleaning.py`；
- 面板构建：`notebooks/07_panel_build.ipynb`、`src/build_research_panel.py`；
- 变量构造：`notebooks/08_variable_construction.ipynb`、`src/build_research_variables.py`、`docs/variable_dictionary.md`；
- 第一阶段分析：`notebooks/09_descriptive_analysis.ipynb`、`stata/06_first_stage_analysis.do`；
- Stata 验证：`stata/03_validate_clean_patents.do` 至 `stata/05_validate_research_variables.do`；
- 自动化测试：`tests/test_patent_cleaning.py`、`tests/test_research_panel.py`、`tests/test_research_variables.py`；
- 总结报告：`docs/chapter1_first_stage_report.md`。

### 本地 Git ignored 产物

```text
data/processed/
results/first_stage/
logs/
```

## 十二、限制与下一阶段入口

当前限制：

- 使用模拟训练数据；
- 企业样本规模较小；
- 部分 firm-year 未观测到专利记录；
- 尚未接入真实 CSMAR/WIND/专利数据库；
- 尚未建立正式政策文本语料库和政策连续性指标；
- 当前固定效应模型只是 baseline diagnostic。

下一阶段入口：

```text
政策文本数据
→ 文本清洗
→ 政策连续性 / 预期管理指标
→ 地区或行业政策 × firm-year 匹配
→ 正式识别设计
→ 主回归、稳健性、异质性与机制分析
```

第一章至此封存。本报告完成后不继续实施第二章。
