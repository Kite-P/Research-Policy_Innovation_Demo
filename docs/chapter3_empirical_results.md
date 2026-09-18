# 第二章 2.7 更新与第三章实证总结

## 一、交付边界

本报告承接第二章 2.7 测量加固，并汇总第三章 3.1—3.5 的正式识别、基准估计和稳健性结果。企业面板仍是训练研究数据，因此本文档只报告管线、规格和兼容计算结果，不把结果解释为真实中国企业的政策因果效应。

本阶段未执行异质性分析、机制分析、工具变量、DID 或事件研究；主规格仍是连续政策连续性 proxy 的 Firm FE + Year FE 面板模型。

## 二、第二章 2.7 更新

### 2.7.1 来源质量与测量版本

49 条政策来源均已补充 `source_tier`、分级理由、验证状态和历史抓取记录，当前 49/49 条为 `retrieval_status=success`。来源分布为：Tier 1 direct provincial official 30 条、Tier 2 other government official 11 条、Tier 3 official/state-media reprint 4 条、Tier 4 other complete reprint 4 条。来源 manifest、下载校验和逐条审计见 `metadata/policy_source_manifest.csv` 与 `docs/policy_measurement_changelog.md`；例如湖北省人民政府公报 PDF 可作为官方公报来源核验样例。[湖北省人民政府公报来源](https://www.hubei.gov.cn/xxgk/gb/202302/W020230213531558645088.pdf)

未找到能够稳定下载且足以改变正文的更高等级 canonical replacement，因此没有为了提高等级而替换原始文本。历史抓取错误已移入历史字段，不再混入当前 retrieval status。

### 2.7.2 连续性指标与修订审计

- 原主指标 `policy_continuity_tfidf` 保留；新增 `policy_continuity_tfidf_expanding`，并通过未来年份文本变异测试。
- 2020—2025 年 42 个有效 province-year pair 的 pre/post primary revision 变化数为 0，最大绝对差为 0。
- 新增 `source_tier_*`、`both_direct_official` 以及 pair-level industry/full text volume controls。
- 企业面板仍为 240 行、40 家企业、7 个省份、2020—2025 六年；政策匹配为 240/240，未改变第二章数据库主键和行数。

因此第二章可以更新为“政策文本连续性测量已加固并封存”，但仍只能把该指标称为文本 proxy，不能等同于真实政策稳定性。

## 三、第三章冻结的识别设计

主规格为：

```text
Y_it = beta * policy_continuity_tfidf_pt + controls_it
       + firm FE + year FE + error_it
```

- Primary outcome：`patent_total_ln`
- Secondary outcomes：`invention_ln`、`citation_ln`
- Primary policy metric：`policy_continuity_tfidf`
- Controls：`size_ln`、`leverage`、`roa`、`cash_ratio`、`employee_ln`
- 固定效应：Firm FE + Year FE
- Primary cluster：province，共 7 个 cluster
- Primary inference：Webb wild cluster bootstrap，10,000 次，seed `20260918`
- 时序：contemporaneous；lagged 规格只作为预先固定的稳健性检验

详细冻结记录见 `docs/chapter3_identification_design.md` 和 `metadata/chapter3_model_specifications.csv`。

## 四、基准结果

以下为冻结规格下的 Python 兼容计算结果，Stata 结果栏对应的 `.do` 入口已保留，但本机未发现 Stata/MP 可执行文件，因此没有将这些数字表述为实际 Stata 执行结果。常规 p 值和部分 HC2/firm-cluster 对照采用兼容实现的正态近似；Webb 结果为固定 10,000 次、seed `20260918` 的兼容 wild-bootstrap 输出。

| 规格 | 因变量 | N | beta | province-cluster SE | 常规 p | Webb p | Webb 95% CI |
|---|---|---:|---:|---:|---:|---:|---|
| Model 0 | `patent_total_ln` | 213 | -0.4633 | 0.2807 | 0.0989 | 0.0512 | [-0.4610, 0.4696] |
| Primary baseline | `patent_total_ln` | 213 | -0.4373 | 0.2791 | 0.1172 | 0.0608 | [-0.4440, 0.4542] |
| Secondary | `invention_ln` | 214 | -0.1550 | 0.3770 | 0.6808 | 0.6243 | [-0.5563, 0.5540] |
| Secondary | `citation_ln` | 213 | -0.6810 | 0.4529 | 0.1327 | 0.1477 | [-0.9169, 0.9091] |

基准结果没有提供稳定的统计显著性证据；特别是 primary 的 Webb p=0.0608，不能按 5% 阈值宣称显著。该结论只描述当前训练数据和兼容计算，不构成因果结论。

## 五、第三章稳健性结果

### 5.1 时序与替代指标

| 规格 | 因变量 | N | beta | Webb p | Webb 95% CI |
|---|---|---:|---:|---:|---|
| Lagged primary | `patent_total_ln` | 206 | -0.2192 | 0.5294 | [-0.5982, 0.6054] |
| Lagged primary | `invention_ln` | 207 | 0.3483 | 0.4116 | [-0.7975, 0.7872] |
| Lagged primary | `citation_ln` | 206 | 0.0263 | 0.9510 | [-0.8123, 0.8209] |
| Expanding metric | `patent_total_ln` | 213 | -0.4048 | 0.0399 | [-0.3909, 0.3949] |
| Full-report TF-IDF | `patent_total_ln` | 213 | 0.1178 | 0.3347 | [-0.2182, 0.2252] |
| Theme continuity | `patent_total_ln` | 213 | 0.7763 | 0.2546 | [-1.0872, 1.0975] |

替代指标的方向和量级并不稳定，且 expanding 指标的区间仍跨过 0；因此不根据单一替代规格的 p 值改写 primary 规格。

### 5.2 测量、来源与样本稳健性

| 检验 | beta | N | cluster 数 | Webb p |
|---|---:|---:|---:|---:|
| Industry text volume control | -0.4423 | 213 | 7 | 0.2717 |
| Full text volume control | -0.8469 | 213 | 7 | 0.0287 |
| Source-quality control | -0.4459 | 213 | 7 | 0.0478 |
| Direct-source restricted | -0.3386 | 156 | 7 | 0.2044 |

Direct-source restricted 样本只有 156 个观测，仍然保留 7 个省级 cluster，推断脆弱性已在结果中标注。体量控制和 source-quality 控制会改变系数或推断结果，说明文本长度与来源质量不能被忽略；这属于测量敏感性证据，不足以支持因果稳定性。

7 个 leave-one-province-out 结果的 beta 范围为 -0.6060 至 -0.1659，Webb p 范围为 0.0271 至 0.4245；省份删除会改变推断结果，表明小 cluster 数和省份构成是重要限制。

Webb 与 Rademacher 权重敏感性如下：Webb p=0.0608，Rademacher p=0.1002；两者均使用 10,000 次重复和相同 seed。20 个 firm-year 的专利 outcome 缺失保持为 missing，没有将未观测专利填充为 0；缺失主要分布在 2020—2025 年的若干企业-年份组合中。

## 六、复现入口与验收状态

- Python 模块：`src/chapter3_analysis.py`、`src/chapter3_robustness.py`、`src/chapter3_measurement.py`
- Stata 入口：`stata/08_policy_baseline.do`、`stata/09_policy_timing_robustness.do`、`stata/10_policy_measurement_robustness.do`
- Notebook：`notebooks/16_empirical_design_audit.ipynb` 至 `notebooks/19_policy_measurement_robustness.ipynb`
- 结果目录：`results/chapter3/`，按项目规则保持 Git ignored
- 测试：最终验收执行全项目 pytest 与 Ruff
- Git：2.7、3.1、3.2、3.3、3.4、3.5 分节提交并推送；最终要求本地 `HEAD == origin/main` 且工作树 clean

## 七、最终判断与后续边界

第二章已经完成 2.7 测量加固并更新封存；第三章的识别设计、基准模型、时序稳健性、替代指标、测量稳健性和样本稳健性管线均已完成。就当前训练数据而言，结果不支持把政策文本连续性 proxy 宣称为稳定、显著的企业创新因果效应。

第三章下一步只应在真实企业数据替换训练面板、确认真实专利缺失机制并具备可执行的 Stata/MP 或等价正式推断环境后，重跑同一套冻结规格；不得直接沿用本报告的训练数据系数作为正式论文结论。
