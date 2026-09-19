# 真实数据导出规范

本规范用于 4.2 之后的人工导出。所有导出均须来自合法授权的数据源；导出文件放入本地被忽略的数据目录，不提交 GitHub。导出前先记录数据源名称、模块/表、字段定义、数据更新时间和许可范围，不记录账号、密码、token、cookie 或许可证信息。

## Profile export

Source: 待用户确认的 CSMAR、Wind、CNRDS 或学校数据库

Module/Table: 待实际界面或官方文档确认

Years: 2020—2025；如数据源提供历史 firm-year 地址和上市状态，完整导出

Universe: 上海、深圳、北京 A 股上市公司；保留研究年份中曾上市的企业

Required fields: `stock_code`, `company_name`, `year`, `exchange`, `listing_date`, `province`, `industry_code`, `industry_name`, `st_flag`

Recommended fields: `city`, `ownership`, `firm_id_source`, `delisting_date`

File format: UTF-8 CSV 或 XLSX；日期使用明确的 ISO 日期或数据字典可解释格式

Expected key: `stock_code + year`；若企业基本信息只按企业静态记录提供，需另行提供历史上市状态和地区口径说明

## Financial export

Source: 与 Profile 尽量相同的结构化学术金融数据库

Module/Table: 待实际界面或官方文档确认

Years: 2020—2025

Universe: 同 Profile；保留合并报表口径

Statement type: Consolidated financial statements

Required fields: `stock_code`, `year`, `total_assets`, `total_liabilities`, `revenue`, `net_profit`, `cash`, `rd_expense`, `employees`

Field definitions: 期末合并总资产、期末合并总负债、营业收入、统一定义的净利润、货币资金或统一定义的现金及现金等价物、当期研发支出/投入、期末员工人数

File format: UTF-8 CSV 或 XLSX；保留原始单位和数据字典

Expected key: `stock_code + year`；导出后检查重复、单位、负值和缺失，不在导出阶段填补缺失

## Patent export

Source: 已完成上市公司/子公司实体匹配的专业专利数据库

Module/Table: 待实际访问确认

Years: 至少 2020—2025；主分析暂定 2020—2024

Universe: 与 Profile 对齐的上市公司及其控制并表子公司，或统一的 `listed_entity_only`

Required fields: `stock_code`, `year`, `invention_patents`, `utility_patents`, `patent_total`, `patent_entity_scope`, `patent_source`

Audit fields: `design_patents`, `application_year`, `grant_year`, `forward_citations`, `citation_window`, `entity_id_source`, `source_update_date`

File format: UTF-8 CSV 或 XLSX；保留申请/授权区分、企业实体映射说明和计数单位

Expected key: `stock_code + year`；若原始数据为专利明细，必须先按冻结 entity scope 和 application year 聚合，并保留聚合审计表

## Required source audit

在采用专利来源前，必须回答：

1. 是否有可靠的申请年；
2. 是否区分发明、实用新型和外观设计；
3. 是否覆盖控制并表子公司；
4. 是否提供引用定义、观察截止日、前向窗口和自引规则；
5. 是否区分申请和授权；
6. 数据库最新更新时间是什么；
7. 是否存在完整上市公司年度总体，从而区分零专利和未观测；
8. 2020—2025 各申请年度的覆盖计数是否足以支持 2025 审计。

## Delivery checklist

人工导出后不得直接进入回归。先提交 Profile、Financial、Patent 三份文件及其数据字典/来源说明，随后执行字段、主键、年份、单位、实体范围、缺失语义和隐私检查。任何字段定义不确定、申请年不可得或子公司范围不一致时，暂停进入后续章节并记录阻塞原因。
