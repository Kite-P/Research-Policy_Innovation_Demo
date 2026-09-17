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

下一阶段进入公司基本信息与专利数据的清洗和匹配。

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
