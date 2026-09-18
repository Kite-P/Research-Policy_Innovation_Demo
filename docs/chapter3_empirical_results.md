# 第二章 2.7 更新与第三章 3.6 技术纠错后实证报告

## 一、结论先行

第二章 2.7 的政策来源与文本连续性测量保持不变；第三章 3.6 修复了 Python lag、Model 0 controls、Stata Year FE、Python WCB/HC2/within R² 权威性等实现问题，并实际运行 Stata/MP 18。

当前正式结果全部以 results/chapter3/stata_*.csv 为准。Python 只保留 point estimate 和样本量 cross-check。企业面板仍是训练研究数据，不能把结果解释为真实中国企业的政策因果效应。

## 二、2.7 测量加固状态

49 条政策来源均有 source tier、理由、验证状态和历史抓取记录；Tier 1=30、Tier 2=11、Tier 3=4、Tier 4=4，当前 retrieval status 为 49/49 success。原始 primary policy_continuity_tfidf 未被替换；42 个有效 pair 的 pre/post primary revision 变化数为 0，最大绝对差为 0。expanding-window 指标、source pair 字段和文本体量控制仍保留。

企业政策面板为 240 行、40 家企业、7 个省份、2020—2025 六年，stock_code + year 唯一，政策匹配 240/240。2.7 仍只把连续性指标解释为文本 proxy。

## 三、冻结识别设计

- Primary outcome：patent_total_ln
- Secondary outcomes：invention_ln、citation_ln
- Primary X：policy_continuity_tfidf
- Controls：size_ln、leverage、roa、cash_ratio、employee_ln
- 固定效应：Firm FE + Year FE
- Cluster：province
- Primary inference：Stata wildbootstrap，Webb、10,000 reps、seed 20260918、equal-tailed
- Lagged、expanding、full-report、theme、文本体量、来源质量、restricted、leave-one-province-out、权重敏感性均按预先固定家族执行

## 四、基准结果：Stata/MP 18 authoritative

| Model | Outcome | Beta | Province SE | Province p | HC2 p | WCB p | WCB 95% CI | N | Within R² |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|
| Model 0 | patent_total_ln | -0.5534 | 0.2652 | 0.0820 | — | 0.1238 | [-1.5251, 0.1775] | 218 | 0.0193 |
| Primary | patent_total_ln | -0.4373 | 0.2506 | 0.1316 | 0.1796 | 0.2024 | [-1.3136, 0.3331] | 213 | 0.0567 |
| Secondary invention | invention_ln | -0.1550 | 0.3386 | 0.6632 | — | 0.6774 | [-1.1637, 1.3488] | 214 | 0.0482 |
| Secondary citation | citation_ln | -0.6810 | 0.4066 | 0.1450 | — | 0.1644 | [-1.9758, 0.6690] | 213 | 0.0514 |

四个模型的 WCB CI 均包含 0。Primary HC2 使用 Stata vce(hc2 province_id, dfadjust)，within R² 直接读取 e(r2_w)。

## 五、lagged policy 修正结果

唯一 province-year 表先计算 lag，再 many-to-one 合并回 firm-year：

- 总面板：240 行
- 2020 lag 缺失：40
- 2021—2025 lag 非缺失：200
- lagged patent_total_ln：N=177
- lagged invention_ln：N=178
- lagged citation_ln：N=177

| Specification | Outcome | Beta | WCB p | WCB CI | N |
|---|---|---:|---:|---|---:|
| Lagged | patent_total_ln | 0.5361 | 0.1666 | [-0.4891, 1.8022] | 177 |
| Lagged | invention_ln | 0.9903 | 0.1772 | [-1.0822, 3.1325] | 178 |
| Lagged | citation_ln | 0.7309 | 0.5538 | [-2.5972, 3.5424] | 177 |
| Expanding | patent_total_ln | -0.4048 | 0.1418 | [-1.0866, 0.3032] | 213 |
| Expanding | invention_ln | -0.2263 | 0.4654 | [-0.8325, 0.8406] | 214 |
| Expanding | citation_ln | -0.6604 | 0.1528 | [-1.5771, 0.5154] | 213 |
| Full report | patent_total_ln | 0.1178 | 0.3350 | [-0.1599, 0.8152] | 213 |
| Theme | patent_total_ln | 0.7763 | 0.3814 | [-0.6367, 3.0955] | 213 |

旧 Python lagged N=206/207 已全部移除。

## 六、测量与来源稳健性

| Specification | Beta | WCB p | WCB CI | N | Clusters |
|---|---:|---:|---|---:|---:|
| Industry volume | -0.4423 | 0.5254 | [-1.7600, 1.4178] | 213 | 7 |
| Full volume | -0.8469 | 0.1798 | [-1.9474, 0.6701] | 213 | 7 |
| Source quality | -0.4459 | 0.1684 | [-1.2491, 0.2692] | 213 | 7 |
| Direct source restricted | -0.3386 | 0.3794 | [-1.3794, 0.7868] | 156 | 7 |

Direct-source restricted 样本为 156 个观测、38 家企业，仍保留 7 个 province clusters。

## 七、Leave-one-province-out

| Excluded | Beta | Province SE | WCB p | WCB CI | N | Clusters |
|---|---:|---:|---:|---|---:|---:|
| 上海市 | -0.4465 | 0.2637 | 0.2358 | [-1.6097, 0.4449] | 180 | 6 |
| 北京市 | -0.1659 | 0.2194 | 0.4860 | [-1.7087, 0.4447] | 168 | 6 |
| 四川省 | -0.6060 | 0.2833 | 0.1876 | [-1.5326, 0.7922] | 197 | 6 |
| 广东省 | -0.3285 | 0.2656 | 0.4366 | [-1.3004, 0.7801] | 173 | 6 |
| 江苏省 | -0.5602 | 0.3690 | 0.2180 | [-1.4820, 0.4401] | 181 | 6 |
| 浙江省 | -0.5267 | 0.2585 | 0.1204 | [-1.6873, 0.1463] | 184 | 6 |
| 湖北省 | -0.4529 | 0.2355 | 0.1996 | [-1.3485, 0.2799] | 195 | 6 |

存在省份构成敏感性：beta 范围为 -0.6060 至 -0.1659，但所有 authoritative WCB CI 均包含 0；删除省份后仅剩 6 个 clusters，推断应谨慎。

## 八、Bootstrap 权重敏感性

| Weight | WCB p | WCB CI | Reps | Seed |
|---|---:|---|---:|---:|
| Webb | 0.2024 | [-1.3136, 0.3331] | 10000 | 20260918 |
| Rademacher | 0.1710 | [-1.3534, 0.3355] | 10000 | 20260918 |

两种权重下 p 均大于 0.05，CI 均包含 0。

## 九、3.6 技术纠错与 before/after

旧结果不再作为正式推断：

| Result | Old compatibility | Corrected Stata |
|---|---:|---:|
| Model 0 beta/N | -0.4633 / 213 | -0.5534 / 218 |
| Primary beta | -0.4373 | -0.4373 |
| Primary WCB p | 0.0608 | 0.2024 |
| Primary WCB CI | [-0.4440, 0.4542] | [-1.3136, 0.3331] |
| Lagged primary beta/N | -0.2192 / 206 | 0.5361 / 177 |
| Lagged invention N | 207 | 178 |

根因包括：旧 Python WCB 不是 bootstrap-t inversion、Webb support 定义错误、firm-row lag 错位、Stata 漏掉 i.year、Model 0 slicing 错误、Python HC2 和 within R² 不等价。详细记录见 docs/chapter3_technical_correction.md。

## 十、Python / Stata point-estimate cross-check

四个基准模型均通过 tolerance=1e-7：

| Model | Python beta | Stata beta | Abs diff | Python N | Stata N | Pass |
|---|---:|---:|---:|---:|---:|---|
| Model 0 | -0.5533951 | -0.5533951 | 9.99e-16 | 218 | 218 | Yes |
| Primary | -0.4372774 | -0.4372774 | 2.78e-15 | 213 | 213 | Yes |
| Secondary invention | -0.1550427 | -0.1550427 | 2.39e-15 | 214 | 214 | Yes |
| Secondary citation | -0.6809689 | -0.6809689 | 7.77e-16 | 213 | 213 | Yes |

## 十一、复现与限制

- Stata/MP 18 已实际执行，08、09、10 日志均包含对应 sentinel。
- Stata runner：scripts/run_stata_chapter3.ps1 -Target all
- 权威结果：results/chapter3/stata_*.csv，Git ignored
- before snapshot：results/chapter3/pre_3_6/，Git ignored
- 20 个专利未观测 firm-year 仍保持 missing，没有填 0。
- 7 个省级 clusters、短面板、40 家企业、模拟 outcome、文本 proxy 和来源等级是主要限制。
- 不执行异质性、机制、IV、DID 或事件研究。

## 十二、最终判断

第三章实现错误已修正；第三章已经使用 actual Stata/MP 18 authoritative inference；第三章可以封存为“技术复核完成”的训练数据版本。下一步只能在真实企业数据、真实专利缺失机制和正式推断环境就绪后，按同一冻结规格重跑，不得直接沿用当前训练数据系数。
