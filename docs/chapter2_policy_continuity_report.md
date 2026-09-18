# 第二章：省级政策文本、政策连续性指标与企业面板匹配报告

## 1. 研究设计

本章以第一章最终样本覆盖的北京市、上海市、广东省、江苏省、浙江省、四川省和湖北省为地区范围，收集 2019—2025 年年度政府工作报告。政策连续性以相邻年度报告的文本相似性 proxy 构造，因此 2019 年只作为 2020 年连续性计算的前置报告，企业匹配阶段只使用 2020—2025 年指标。

## 2. 地区与文本覆盖

最终来源清单覆盖 7 个地区、7 个年份和 49 个 province-year 单元，49/49 个原始文件下载成功并通过 SHA-256、字节数和唯一键审计。来源优先使用省级政府门户、政府公报、人大/政府官方转载；部分年份因页面不可下载采用官方媒体、政府部门或完整转载来源，来源层级和备注均保留在 [`metadata/policy_source_manifest.csv`](../metadata/policy_source_manifest.csv)，不能把所有记录无条件表述为省政府门户一级来源。

代表性可核验来源包括：[上海市政府工作报告归档](https://www.shanghai.gov.cn/nw12336/index.html)、[江苏省政府 2023 年报告](https://www.js.gov.cn/art/2023/1/28/art_84319_10733782.html)、[湖北省 2023 年报告 PDF](https://www.hubei.gov.cn/xxgk/gb/202302/W020230213531558645088.pdf)。

## 3. 文本清洗与产业文本提取

原始 HTML/PDF 保存在 Git ignored 的 `data/raw/policy_reports/`，清洗输出为 `data/processed/policy_reports_clean.parquet`。管线严格尝试来源声明编码、HTML meta、UTF-8 和 GB18030，不以 `errors="ignore"` 静默丢弃内容；同时进行 Unicode NFKC、脚本/样式/导航/页脚模板清理、正文容器识别和段落恢复。

产业文本只保留包含核心产业关键词的段落，语境关键词只用于命中量诊断。结果覆盖 49/49 条正文和 49/49 条产业文本，4 条产业文本占比异常仅作为 `abnormal_industry_share` 标记保留。

## 4. Primary continuity

对产业文本和完整报告分别做 Unicode 规范化、去空白和非中文/字母/数字过滤，再在 49 份报告上建立统一的字符 2—4 gram vocabulary，`min_df=2`。对 n-gram 计数 (c_{dj})，TF 为 (1+ln(c_{dj}))，IDF 为

\[
\mathrm{IDF}_j=\ln\left(\frac{1+N}{1+df_j}\right)+1,
\]

随后进行 L2 标准化，并对相邻年度向量计算 cosine similarity，得到 `policy_continuity_tfidf`。2019 年按构造为 missing，2020—2025 年 42/42 个主指标有效，范围为 0.0662—0.4315。

## 5. Robustness metrics

使用相同算法对 `full_text_clean` 计算 `policy_continuity_full_tfidf`；同时将关键词按 technology innovation、manufacturing upgrade、digital economy、green transition、emerging industry、enterprise support、talent 七类统计，归一化为类别份额向量并计算 `policy_continuity_theme`。

主指标均值为 0.2769，全文指标均值为 0.3345，主题指标均值为 0.9704。2—3 gram 和 3—5 gram 替代指标与主指标的排序相关性分别为 0.9972 和 0.9955；主指标与全文指标、主题指标的排序相关性分别为 0.8196 和 0.2647。

## 6. 指标有效性

独立验证见 [`docs/policy_continuity_validation.md`](policy_continuity_validation.md)，没有使用企业专利、企业创新变量或回归显著性筛选指标。固定种子 `20260918` 的人工审计包含最高 3 对、最低 3 对和 4 对随机中间案例，共 10 对相邻报告。

主指标与产业文本字符数的相关系数为 0.6193，与完整文本字符数、产业文本占比和关键词命中量的相关系数分别为 0.2850、0.1761 和 0.3618；与年度全文和产业文本长度变化的相关系数分别为 0.0225 和 0.0483。体量风险被保留为限制和后续控制参考，没有因此删除主指标。

## 7. 企业匹配

将 `province_year_policy_metrics` 按 `province + year` 与第一章 `research_panel_variables` 做 many-to-one 左连接。政策字段包括三个连续性指标、全文/产业文本长度、产业文本占比和关键词命中量；`policy_metric_present` 由 merge provenance 直接构造。

最终结果 `data/processed/research_panel_policy.parquet/.dta` 为 240 个 firm-year、40 家企业、2020—2025 六个年份，`stock_code + year` 唯一，240/240 个 firm-year 的 `policy_metric_present=1`，没有行数膨胀。2019 年没有被直接复制到企业 2020 行；它只用于构造 2020 连续性。

## 8. 限制

- 政府工作报告不是所有具体产业政策文件的全集；
- 文本相似性是政策表述连续性的 proxy，不是政策执行强度或政策稳定性的真实值；
- 写作模板、篇幅和网页结构可能影响相似性；
- 产业段落抽取依赖关键词词典，存在覆盖和语义边界限制；
- 部分来源为官方转载或公报，来源层级差异需要在后续研究中继续控制和披露；
- 当前企业面板为第一章训练数据，第二章只完成数据库准备，不据此报告政策对创新的因果效果。

## 9. 第三章入口

下一阶段再讨论正式基准识别、标准误聚类层级、滞后结构、主回归、稳健性、异质性和机制检验。本章没有运行 `policy_continuity_tfidf → patent` 的企业结果回归。

## 10. 2.7 测量加固更新

2.7 对第二章进行了透明度加固，但没有改变 primary metric。新增 source tier、source pair quality、expanding-window TF-IDF 和 pair-level text-volume controls；旧版与新版 `policy_continuity_tfidf` 的 42 个有效值最大绝对差为 0。新增 expanding 指标只在每个年份可用信息内计算，作为 no-look-ahead robustness，不取代原主指标。
