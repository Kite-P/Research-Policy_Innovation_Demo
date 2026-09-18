# 第二章政策连续性研究设计与文本口径

## 1. 研究目标与边界

本章构建一个可复现、可解释、能够与企业 `firm-year` 面板匹配的省级年度政策连续性指标。研究方向为：

```text
产业政策连续性 / 政策预期稳定性
×
企业创新策略
```

本章只完成政策研究设计、政策文本语料库、文本清洗、连续性指标、指标有效性验证和企业面板匹配。第二章不运行正式政策效应主回归，不使用企业创新结果、专利回归显著性或政策系数 p-value 来选择指标、词典或参数。

## 2. 研究地区与年份

研究地区从第一章最终变量面板 `data/processed/research_panel_variables.parquet` 的唯一 `province` 读取，而不是根据计划预先硬编码。当前实际地区为 7 个：

```text
北京市、上海市、广东省、江苏省、浙江省、四川省、湖北省
```

政策原始报告年份固定为 `2019–2025`。2019 年只用于构造 2020 年的相邻年份连续性；企业分析年份仍固定为 `2020–2025`。

政策层级固定为：

```text
province-year
```

因此预期为 49 个原始报告单元和最多 42 个连续性单元，实际覆盖以语料库审计结果为准。

地区元数据：

```text
metadata/policy_region_scope.csv
```

## 3. 主语料定义

### 3.1 Primary corpus

主语料固定为：

```text
Annual provincial-level Government Work Report
```

每个 `province-year` 必须对应恰好一份 canonical report。北京市、上海市等直辖市与其他省份按同一省级行政单元处理。

本章第一版不把通知、意见、规划、办法、实施细则、专项行动、产业规划或单项科技/财政政策混入主语料。这样可以避免文件数量、文种构成、发布频率和网站收录差异污染连续性指标。

### 3.2 Canonical source

来源优先级为：

1. 省级人民政府官方网站；
2. 省级人大、政府公报等官方平台；
3. 其他官方政府网站的完整转载。

媒体转载不能作为 primary source。每个报告同时记录 `source_url`、`alternate_url`、`source_title`、`publish_date`、`report_year`、`source_type`、下载状态和 SHA256。报告年份以报告内容对应年份为准，不单纯使用网页发布时间年份。

## 4. 产业文本定义

产业/创新段落的纳入规则冻结为：

> 一段文本只要出现至少一个 `core` keyword，即纳入产业/创新文本。

`context` keyword 不能单独触发纳入，只用于主题解释和辅助分类，避免“企业”“人才”等泛化词吸收大量非产业段落。

关键词元数据：

```text
metadata/policy_industry_keywords.csv
```

字段为：`term`、`category`、`tier`、`description`。

## 5. Primary continuity 指标

主指标冻结为：

```text
policy_continuity_tfidf
```

含义：同一省份相邻两年政府工作报告中产业/创新相关文本的 TF-IDF 字符 n-gram cosine similarity。

### 5.1 文本预处理

向量化前执行：

- Unicode normalize；
- ASCII lowercase；
- 删除空白；
- 删除非中文、英文和数字字符；
- 保留中文字符、A–Z/a–z 和 0–9。

### 5.2 TF-IDF

Primary 参数固定为：

```text
analyzer: character n-gram
ngram_range: 2–4
min_document_frequency: 2
```

对每个 n-gram：

```text
tf = 1 + ln(c)
idf = ln((1 + N) / (1 + df)) + 1
tfidf = tf × idf
```

每份文档向量进行 L2 normalization。连续性定义为：

```text
continuity(p,t) = cosine(TFIDF(p,t), TFIDF(p,t-1))
```

因为向量非负，正常有效值应位于 `[0, 1]`。2019 年没有前一年政策文本，因此其 continuity 为 missing，不填 0。

## 6. Robustness 指标

### 6.1 Whole-report TF-IDF

```text
policy_continuity_full_tfidf
```

使用整份政府工作报告清洗文本计算相邻年份字符 n-gram TF-IDF cosine similarity，用于判断产业文本连续性是否只是整体政府报告文本连续性的映射。

### 6.2 Theme continuity

```text
policy_continuity_theme
```

根据预先冻结的主题词典，计算每个 `province-year` 的主题命中数：

```text
category_share_i = hits_i / total_keyword_hits
```

主题 share 向量之间计算相邻年份 cosine similarity。如果 `total_keyword_hits=0`，该指标为 missing，不填 0。

## 7. 辅助指标与缺失规则

每个 `province-year` 记录：

```text
full_text_chars
industry_text_chars
industry_text_share
keyword_hits_total
```

其中：

```text
industry_text_share = industry_text_chars / full_text_chars
```

缺失规则：

- 缺少 canonical report：该 `province-year` 保留 manifest 记录，但文本和指标为 missing；
- 2019 年 continuity：missing；
- 缺少前一年文本：当年 continuity 为 missing；
- 产业文本为空：产业文本指标为 missing，不填 0；
- 主题总命中数为 0：theme continuity 为 missing；
- 不使用均值、中位数、前值或后值填补政策指标。

## 8. 研究完整性规则

指标、词典和参数必须在正式企业结果回归之前冻结。禁止先计算多套指标、分别进行企业创新回归，再挑选显著指标作为主指标。若后续发现算法问题，必须保留原版本、记录修改理由并重新验证，不能依据企业结果显著性修改定义。

## 9. 本章不做的工作

- 不把所有产业政策文件混入第一版主语料；
- 不依赖商业 embedding 或付费 NLP 服务构造主指标；
- 不把完整政策原文写入 Git；
- 不运行正式政策效应主回归；
- 不根据企业创新结果优化指标。
