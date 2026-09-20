# 导师科研项目

## 项目目的

用于财务会计、公司金融和企业创新方向的科研训练。

当前训练重点包括：

- Python 数据清洗
- 上市公司面板数据构建
- 财务数据库匹配
- 政策文本处理
- 专利数据处理
- Stata 实证分析
- 可复现科研工作流

## Python 环境

项目 Python：

Python 3.13.15

虚拟环境：

.venv

环境由 uv 管理。

## 项目结构

- data/raw：原始数据
- data/processed：处理后的数据
- data/external：外部辅助数据
- notebooks：探索性分析与训练 Notebook
- src：可复用 Python 代码
- tests：测试代码
- docs：研究文档
- results：分析结果、图表和回归结果

## 原则

原始数据、处理数据和研究结果默认不提交到 Git 仓库。

## 当前进展

### 2026-09-20 阶段提交

本阶段已完成真实上市公司总体构建与财务数据获取管线，并完成上市/退市年份、企业标识和免费数据源口径的系统验证。

阶段总结：

[阶段总结.md](阶段总结.md)

### 第四章 4.1：真实数据研究设计冻结

已冻结真实企业研究的总体、样本年份、财务与专利变量口径、政策匹配规则、专利 0/missing 语义边界和 2025 年专利覆盖审计规则：

- 研究总体为中国大陆上海、深圳、北京三地 A 股上市公司，分析单位为 `firm-year`；
- 财务与 Profile 准备窗口为 2020—2025 年；专利 primary analysis 默认截止 2024 年，2025 年仅用于覆盖审计；
- baseline 排除金融业，不因 ST/*ST 自动删除，采用合并财务报表口径；
- 专利主时间口径为申请年，baseline 包括发明和实用新型申请，外观设计保留为审计字段；
- 真实数据来源尚未在当前环境确认，状态为 `SOURCE_ACCESS_BLOCKED`，已形成后续人工导出规范；
- 未下载大规模真实数据，未进入 4.2。

### 第四章 4.1F：免费真实数据源可行性验证

已用同一组 20 家上市公司 pilot 实际复核 AKShare 免费 Profile、财务和 F10 指标接口：

- SSE、SZSE、BSE 的 Profile 样本级成功率均为 100%；
- `TOTAL_OPERATE_INCOME`、`PARENT_NETPROFIT` 以及资产、负债、现金均为 60/60 firm-year；
- F10 `STAFF_NUM` 为 60/60，20 家企业均有三年变化；研发费用 `RESEARCH_EXPENSE` 为 57/60；
- Google Patents BigQuery 因本机缺少身份验证环境，未执行 freshness 和企业名称匹配；
- 当前状态为 `FREE_FINANCIAL_READY_PATENT_AUTH_REQUIRED`，不进入 4.2F。

可行性报告：

[`docs/free_source_feasibility_report.md`](docs/free_source_feasibility_report.md)

研究设计：

[`docs/chapter4_real_data_design.md`](docs/chapter4_real_data_design.md)

导出规范与字段字典：

[`docs/real_data_export_specification.md`](docs/real_data_export_specification.md)

[`metadata/real_data_scope.csv`](metadata/real_data_scope.csv)

[`metadata/real_data_schema.csv`](metadata/real_data_schema.csv)

### 2026-09-18：公司基本信息清洗

已完成模拟公司基本信息数据的审计和正式清洗：

- 标准化 42 家公司的股票代码、公司名称和省级地区；
- 统一多种上市日期格式，包括 Excel 日期序列号；
- 保留所有制和上市日期中的真实缺失；
- 验证公司级 `stock_code` 主键唯一；
- 财务面板全部 40 家公司均能成功匹配公司基本信息；
- Profile 中额外 2 家公司被识别为财务样本外记录；
- 输出并验证 Parquet 与 Stata 数据版本；
- 完成 Stata/MP 实际加载和主键验证。

审计过程：

[`notebooks/03_profile_audit.ipynb`](notebooks/03_profile_audit.ipynb)

正式清洗：

[`notebooks/04_profile_cleaning.ipynb`](notebooks/04_profile_cleaning.ipynb)

阶段进展报告：

[`docs/progress_2026-09-18.md`](docs/progress_2026-09-18.md)

Stata 验证：

[`stata/02_validate_clean_profile.do`](stata/02_validate_clean_profile.do)

下一阶段进入专利数据审计和清洗。

### 2026-09-18：专利数据清洗

已完成模拟专利数据的独立审计、正式清洗和 processed 数据验证：

- 审计原始 225 行、40 家公司和 220 个唯一 firm-year；
- 识别 5 个重复 firm-year 组，其中 4 组完全重复、1 组为引用数冲突；
- 标准化股票代码为 6 位字符串，保留三个专利字段的真实缺失；
- 对有证据支持的极端引用值设为 missing，并未删除整个 firm-year 或填零；
- 输出并验证 Parquet 与 Stata 数据版本，最终保留 220 行唯一 firm-year；
- 相对于 240 个财务 firm-year，20 个 firm-year 在专利表中未观测到记录，未将其解释为零专利；
- 完成 Stata/MP 实际加载和主键、年份、非负性验证。

审计过程：

[`notebooks/05_patent_audit.ipynb`](notebooks/05_patent_audit.ipynb)

正式清洗：

[`notebooks/06_patent_cleaning.ipynb`](notebooks/06_patent_cleaning.ipynb)

可复用清洗逻辑与测试：

[`src/patent_cleaning.py`](src/patent_cleaning.py)

Stata 验证：

[`stata/03_validate_clean_patents.do`](stata/03_validate_clean_patents.do)

### 2026-09-17：财务面板正式清洗

已完成模拟财务面板第一轮正式清洗：

- 将 260 条原始记录清洗为 240 个唯一 firm-year；
- 完成股票代码、年份和主要财务数值字段标准化；
- 区分并处理完全重复与冲突重复记录；
- 完成 ROE 口径核验和已确认异常处理；
- 保留无法无依据填补的缺失值；
- 输出经过验证的 Parquet 与 Stata 数据版本；
- 完成 Python 回读和 Stata/MP 实际加载验证。

技术过程：

[`notebooks/02_data_cleaning.ipynb`](notebooks/02_data_cleaning.ipynb)

阶段进展报告：

[`docs/progress_2026-09-17.md`](docs/progress_2026-09-17.md)

Stata 数据验证：

[`stata/01_validate_clean_financials.do`](stata/01_validate_clean_financials.do)

下一阶段进入统一研究面板构建。

### 2026-09-18：统一公司年度研究面板

已将财务、公司基本信息和专利 processed 数据合并为统一研究面板：

- 以 240 个财务 firm-year 作为左表骨架，保留 40 家公司和 2020–2025 年；
- Profile 按 `stock_code` 做 many-to-one 合并，240/240 条财务记录成功匹配；
- Patent 按 `stock_code + year` 做 one-to-one 左连接，最终面板仍为 240 行；
- 从 merge provenance 构造 `patent_record_present`，其中 220 条为 1、20 条为 0；
- 未观测专利记录的三个专利字段保持 missing，没有填充为 0；
- 已验证 Parquet、Stata 和 Stata/MP 实际面板设定所需的 key、年份、年度观测数和覆盖关系。

面板构建：

[`src/build_research_panel.py`](src/build_research_panel.py)

Notebook：

[`notebooks/07_panel_build.ipynb`](notebooks/07_panel_build.ipynb)

测试与 Stata 验证：

[`tests/test_research_panel.py`](tests/test_research_panel.py)

[`stata/04_validate_research_panel.do`](stata/04_validate_research_panel.do)

下一阶段进入第一阶段研究变量构造。

### 2026-09-18：第一阶段研究变量

已在统一研究面板上构造第一批后续实证变量：

- 财务变量：`size_ln`、`leverage`、`roa`、`rd_intensity`、`cash_ratio`、`employee_ln`；
- 公司特征变量：`firm_age`；
- 创新变量：`patent_total`、`patent_total_ln`、`invention_ln`、`citation_ln`、`invention_share`、`citations_per_invention`；
- 比率变量仅在正分母下计算，log 变量不接受非法输入，上市日期缺失不推测；
- `patent_record_present=0` 的所有专利衍生变量均保持 missing；
- 保持 240 行和原始 firm-year key，不做 winsorization；
- 完成 Parquet、Stata、Notebook 和 Stata/MP 实际验证。

变量构造：

[`src/build_research_variables.py`](src/build_research_variables.py)

变量字典：

[`docs/variable_dictionary.md`](docs/variable_dictionary.md)

Notebook、测试与 Stata 验证：

[`notebooks/08_variable_construction.ipynb`](notebooks/08_variable_construction.ipynb)

[`tests/test_research_variables.py`](tests/test_research_variables.py)

[`stata/05_validate_research_variables.do`](stata/05_validate_research_variables.do)

下一阶段进入描述统计、相关性和第一版固定效应 baseline diagnostic。

### 第二章 2.2：省级政府工作报告语料库

已建立第一版省级年度政府工作报告来源清单，覆盖第一章最终研究面板中的 7 个省级地区、2019—2025 年共 49 个 province-year 单元。清单记录来源 URL、发布时间、来源域名、原始文件相对路径、HTTP 状态、SHA-256、字节数、下载状态和复核备注。

已验证：

- 49/49 个 province-year 单元存在且唯一；
- 49/49 个原始文件下载成功，原始正文保存于 Git ignored 的 `data/raw/policy_reports/`；
- SHA-256 与字节数逐文件一致；
- 下载器不会把 HTTP 错误、反爬验证页或重定向异常标记为成功；
- 原始文件不进入 Git，仓库只跟踪来源清单、下载器、审计逻辑和测试。

来源清单与下载器：

[`metadata/policy_source_manifest.csv`](metadata/policy_source_manifest.csv)

[`src/policy_source_manifest.py`](src/policy_source_manifest.py)

[`src/fetch_policy_reports.py`](src/fetch_policy_reports.py)

审计 Notebook 与测试：

[`notebooks/10_policy_source_audit.ipynb`](notebooks/10_policy_source_audit.ipynb)

[`tests/test_policy_source_manifest.py`](tests/test_policy_source_manifest.py)

[`tests/test_policy_fetch.py`](tests/test_policy_fetch.py)

本节不把来源等级不一致的转载默认为省政府一级来源；相关行保留了来源等级待人工复核备注，后续文本清洗和指标构造应继续沿用该 provenance。

### 第二章 2.3：政策文本清洗与产业文本提取

已完成省级政府工作报告的可复现文本清洗管线：严格处理 HTML/PDF 解码、Unicode 规范化、脚本与导航噪声删除、正文容器识别、段落恢复和底部模板文本；产业文本只保留包含核心产业关键词的段落，语境关键词仅用于诊断统计。

最终输出 `data/processed/policy_reports_clean.parquet`，覆盖 49 个 province-year 单元、18 个字段。独立验收结果为 49/49 条正文非空、49/49 条产业文本非空；4 条产业文本占比异常记录被保留为 `abnormal_industry_share` 质量标记，不删除正文、不伪造内容。原始下载文件保持只读，未进入 Git。

清洗脚本、Notebook 与测试：

[`src/policy_text_cleaning.py`](src/policy_text_cleaning.py)

[`notebooks/11_policy_text_cleaning.ipynb`](notebooks/11_policy_text_cleaning.ipynb)

[`tests/test_policy_text_cleaning.py`](tests/test_policy_text_cleaning.py)

### 第二章 2.4：省级政策连续性指标

已基于 2.3 清洗语料构造三类 province-year 指标：产业文本主指标 `policy_continuity_tfidf`、全文稳健性指标 `policy_continuity_full_tfidf` 和关键词类别份额向量的 `policy_continuity_theme`。TF-IDF 使用字符 2—4 gram、全体 49 份报告统一 vocabulary、`min_df=2`、`1+ln(count)` TF、平滑 IDF 和 L2 标准化；2019 年连续性按构造保持缺失，不以 0 或均值替代。

输出：

[`src/policy_continuity.py`](src/policy_continuity.py)

[`notebooks/12_policy_continuity.ipynb`](notebooks/12_policy_continuity.ipynb)

[`tests/test_policy_continuity.py`](tests/test_policy_continuity.py)

`province_year_policy_metrics.parquet/.dta` 为 Git ignored 处理结果。最终核验为 49 行、12 列、`province + year` 唯一，2020—2025 三类连续性各 42 个有效值，三类指标均处于 [0,1]。

### 第二章 2.5：政策连续性指标有效性验证

已完成独立 measurement validation，验证只使用政策文本与政策指标，不使用企业专利或企业回归结果。结果写入 Git ignored 的 `results/policy_continuity/`，完整说明见 [`docs/policy_continuity_validation.md`](docs/policy_continuity_validation.md)。覆盖、分布、地区轨迹、年度变化、固定种子案例、2—3/3—5 n-gram 稳健性、排序一致性和文本体量相关性均已输出。

### 第二章 2.6：政策指标与企业面板匹配及第二章封存

已将 2.4 的 province-year 指标按 `province + year` 与第一章 `research_panel_variables.parquet` 做 many-to-one 左连接。最终数据库保持 240 个 firm-year、40 家企业、2020—2025 六个年份和唯一 `stock_code + year`；240/240 个 firm-year 匹配成功，`policy_metric_present` 由 merge provenance 构造。未运行第三章政策连续性与企业创新回归。

[`src/merge_policy_panel.py`](src/merge_policy_panel.py)

[`notebooks/14_policy_panel_merge.ipynb`](notebooks/14_policy_panel_merge.ipynb)

[`stata/07_validate_policy_panel.do`](stata/07_validate_policy_panel.do)
[`docs/chapter2_policy_continuity_report.md`](docs/chapter2_policy_continuity_report.md)

第二章完成后，下一阶段入口为正式政策连续性实证识别；本仓库当前仍不把文本连续性 proxy 表述为政策稳定性的真实值。

### 2.7：政策来源与连续性测量加固

已补充 49 条来源的逐条 source tier、理由、验证状态和历史抓取问题字段；保留原 primary `policy_continuity_tfidf`，新增 expanding-window 指标、来源 pair 质量字段和成对文本体量控制。pre/post measurement revision 显示 primary 有效值没有变化。

详情见 [`docs/policy_measurement_changelog.md`](docs/policy_measurement_changelog.md) 和 [`notebooks/15_policy_measurement_hardening.ipynb`](notebooks/15_policy_measurement_hardening.ipynb)。

### 第三章 3.1：正式识别设计冻结

已冻结 primary outcome、secondary outcomes、primary policy metric、baseline controls、Firm FE + Year FE、contemporaneous timing、province clustering 和 Webb wild cluster bootstrap primary inference。当前设计是连续变量双向固定效应面板，不是传统 DID。

### 第三章 3.2：基准模型

已生成 Model 0、primary baseline、`invention_ln` 和 `citation_ln` 基准结果；3.6 后正式结果位于 Git ignored 的 `results/chapter3/stata_baseline_inference.csv`，由实际 Stata/MP 18 运行产生。Python 只用于 point-estimate/N cross-check。

### 第三章 3.3：时序与替代指标稳健性

已固定执行 lagged primary、expanding-window primary、full-report TF-IDF 和 theme continuity 四类稳健性规格；3.6 后正式结果位于 `results/chapter3/stata_timing_robustness.csv`。不因显著性选择模型，primary 规格不变。

### 第三章 3.4：测量、来源与样本稳健性

已完成 text-volume controls、source-quality control、direct-source restricted sample、leave-one-province-out、missing-patent diagnostic 和 Webb/Rademacher sensitivity。当前 20 个专利未观测 firm-year 保持 missing，不填 0；不执行异质性或机制分析。

### 第三章 3.5：第三章总结与封存

已完成第三章实证结果汇总，见 [`docs/chapter3_empirical_results.md`](docs/chapter3_empirical_results.md)。当前报告明确区分 Python 兼容计算与未执行的 Stata/MP 正式推断，不把训练面板结果写成真实企业因果结论；后续仅在真实企业数据和正式推断环境就绪后按冻结规格重跑。

### 第三章 3.6：技术纠错与 Stata 权威复核

已修正 province-year lag、Model 0 controls、Year FE、Python 旧 WCB/HC2/within R² 权威边界，并通过 `scripts/run_stata_chapter3.ps1 -Target all` 实际执行 Stata/MP 18。正式结果改读 `results/chapter3/stata_*.csv`；技术纠错记录见 [`docs/chapter3_technical_correction.md`](docs/chapter3_technical_correction.md)。

### 2026-09-18：描述统计与第一版基准诊断

已完成第一阶段分析管线：

- 输出样本流、22 个变量的描述统计和 10 个主要连续变量的 Pearson pairwise correlation；
- 同步输出每对相关系数实际使用的观测数 `correlation_n.csv`；
- Stata/MP 18 使用 `xtreg ..., fe vce(cluster firm_id)` 加 `i.year` 完成三组诊断模型；
- Model A `patent_total_ln`：研发强度系数 -0.250261，SE 0.488121，p=0.611051，N=213，within R2=0.028313；
- Model B `invention_ln`：研发强度系数 0.622818，SE 0.808302，p=0.445631，N=214，within R2=0.047614；
- Model C `citation_ln`：研发强度系数 1.069395，SE 1.054496，p=0.316772，N=213，within R2=0.050839。

分析 Notebook：

[`notebooks/09_descriptive_analysis.ipynb`](notebooks/09_descriptive_analysis.ipynb)

Stata 管线：

[`stata/06_first_stage_analysis.do`](stata/06_first_stage_analysis.do)

所有结果保存在 Git ignored 的 `results/first_stage/`。这些模型只有研发强度和财务控制变量，没有政策连续性变量，因此仅用于验证变量与面板回归管线，不构成政策因果结论。

### 第一章阶段报告

第一阶段全部成果已整理为：

[`docs/chapter1_first_stage_report.md`](docs/chapter1_first_stage_report.md)

该报告汇总数据审计、统一研究面板、变量定义、描述统计、相关性、三组固定效应诊断、限制和下一章入口。第一章到此封存，不提前进入政策文本分析。

### 2026-09-16：原始财务数据审计

已完成第一阶段科研数据工程训练：

- 建立独立、可复现的 Python 科研环境
- 编写模拟公司财务、公司基本信息和专利数据生成器
- 建立 pytest 自动测试与 Ruff 代码质量检查
- 完成 `firm_financials.xlsx` 原始财务面板数据质量审计
- 初步识别缺失值、伪缺失值、格式异常、完全重复和 firm-year 主键冲突

当前阶段坚持 **raw 数据不修改、先审计后清洗**。

技术过程：

[`notebooks/01_data_audit.ipynb`](notebooks/01_data_audit.ipynb)

阶段进展报告：

[`docs/progress_2026-09-16.md`](docs/progress_2026-09-16.md)

下一阶段将建立正式的数据清洗规则，并输出标准化的 processed 数据。
