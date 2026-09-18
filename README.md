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
