# 第三章 3.6 技术纠错记录

## 1. 为什么进行 3.6

第三章 3.2—3.5 已经冻结研究设计，但代码审查发现部分 Python 兼容推断和 Stata 复现脚本不能作为权威结果。本轮只修正实现，不改变研究问题、变量、固定效应、聚类层级和稳健性家族。

## 2. 已确认的问题

### 2.1 Python WCB

旧 _wcb() 以 bootstrap beta 分布分位数代替 Stata wildbootstrap 的 bootstrap-t 与 hypothesis-inversion CI，不能作为正式 WCB p 值或区间。

### 2.2 Webb weights

旧 Python support 重复了 -sqrt(1/2) 和 +sqrt(1/2)，遗漏 -1 和 +1。正确六点 support 为：

-sqrt(3/2), -1, -sqrt(1/2), +sqrt(1/2), +1, +sqrt(3/2)

现在该函数仅保留为 legacy compatibility-only 诊断，Python 正式输出不再包含 wcb_p、WCB CI、HC2 或 within_r2。

### 2.3 Lagged policy

旧代码在 firm-year 行上按 province 分组 shift；同一省同一年有多家公司时，后一个企业行可能把同年另一企业的政策值误当作上一年政策。修正为唯一 province-year 政策表计算 lag，再以 province + year many-to-one 回填。

### 2.4 Year FE

旧 stata/08_policy_baseline.do、09_policy_timing_robustness.do 和 10_policy_measurement_robustness.do 的正式命令遗漏 i.year。现在每条 xtreg 和 wildbootstrap xtreg 都显式包含 i.year。

### 2.5 Model 0

旧 Python 先构造完整 controls design，再靠列索引切片，导致 Model 0 不能可靠保证无 controls。现在根据 specification 先明确构造 regressors；Model 0 只有 policy，Primary 恰好使用冻结的五个 controls。

### 2.6 HC2 与 within R²

旧 Python HC2 是近似 cluster sandwich，不等价于 Stata vce(hc2 province_id, dfadjust)；旧 1-SSE/总平方和也不是 Stata e(r2_w)。当前正式报告分别读取 Stata 的 HC2 和 e(r2_w)。

### 2.7 Stata execution

本轮通过 scripts/run_stata_chapter3.ps1 实际调用 Stata/MP 18，08、09、10 均产生日志和 sentinel。WCB 结果从每次命令后的 r(table) 按 row names pvalue/ll/ul 提取，没有从 console 文本猜测。

## 3. 冻结设计是否改变

没有改变。Primary outcome、secondary outcomes、primary policy metric、五个 controls、Firm FE + Year FE、province cluster、Webb 10,000 reps、seed 20260918、equal-tailed inference 和预注册 robustness 家族均保持不变。

## 4. Stata 权威结果

- Point estimate：Stata xtreg, fe + i.year
- Conventional province cluster：Stata vce(cluster province_id)
- HC2：Stata vce(hc2 province_id, dfadjust)
- Primary small-cluster inference：Stata wildbootstrap，Webb、10,000 reps、seed 20260918、equal-tailed
- Python：只做 point-estimate/N cross-check

Primary baseline 的 Stata beta 为 -0.4372774，province-cluster SE 为 0.2505925，HC2 p=0.1796，Webb p=0.2024，95% WCB CI 为 [-1.3136, 0.3331]。四个基准模型的 WCB 区间均包含 0。

## 5. Python / Stata coefficient consistency

四个基准模型均满足 beta 与 N 一致：

| Model | Abs beta diff | N match |
|---|---:|---|
| Model 0 | 9.99e-16 | Yes |
| Primary | 2.78e-15 | Yes |
| Secondary invention | 2.39e-15 | Yes |
| Secondary citation | 7.77e-16 | Yes |

tolerance 为 1e-7。

## 6. Before / after 关键变化

| Result | Old compatibility result | Corrected authoritative result | Reason |
|---|---:|---:|---|
| Model 0 beta | -0.4633, N=213 | -0.5534, N=218 | controls construction and Stata Year FE authority |
| Primary beta | -0.4373 | -0.4373 | point estimate cross-check一致 |
| Primary WCB p | 0.0608 | 0.2024 | actual Stata WCB |
| Primary WCB CI | [-0.4440, 0.4542] | [-1.3136, 0.3331] | Stata inverted CI |
| Lagged primary beta | -0.2192, N=206 | +0.5361, N=177 | province-year lag correction |
| Lagged invention N | 207 | 178 | province-year lag correction |

旧 p 值和区间不再用于研究解释。

## 7. 研究结论变化

在模拟企业训练数据上，修正后的 Primary beta 仍为负，但 authoritative Webb inference 不显著，且 95% CI 跨过 0。lagged 规格改变方向，expanding、full-report、theme 以及测量稳健性方向和推断也不完全一致。leave-one-province-out 的 beta 为 -0.6060 至 -0.1659，所有排除省份后的 WCB CI 均跨过 0。

因此当前结果不支持稳定的政策连续性 proxy 企业创新因果效应。该判断受 7 个省级 clusters、短面板、40 家企业、模拟 outcome、文本 proxy 测量和专利缺失机制限制。

## 8. 当前剩余限制

- 省级 cluster 只有 7 个；leave-one-out 后只有 6 个，WCB 推断脆弱。
- 面板为 40 家企业、2020—2025 六年。
- 企业 outcome 是训练研究数据，不是正式真实企业样本。
- 文本连续性只是政策文本 proxy。
- 20 个 firm-year 的专利未观测仍保持 missing，没有填 0。
- 49 条来源包含 Tier 1—4，不应表述为全部省级门户一级来源。

## 9. 可复现入口

- Runner：scripts/run_stata_chapter3.ps1 -Target all
- Stata：stata/08_policy_baseline.do、stata/09_policy_timing_robustness.do、stata/10_policy_measurement_robustness.do
- Cross-check：src/chapter3_stata_crosscheck.py
- Before snapshot：results/chapter3/pre_3_6/，Git ignored
- 权威结果：results/chapter3/stata_*.csv，Git ignored
