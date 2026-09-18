# 第三章：政策连续性与企业创新的面板识别训练——识别设计冻结

## 研究定位

第一章企业财务、Profile 和 Patent 数据属于模拟训练数据；政策报告和政策文本是真实公开文本。因此本章建立的是 formal empirical pipeline rehearsal，不构成真实中国企业因果研究发现。

## 冻结变量

- Primary outcome：`patent_total_ln = ln(1 + invention_patents + utility_patents)`；
- Secondary outcomes：`invention_ln`、`citation_ln`，只作 supporting outcomes；
- Primary explanatory variable：`policy_continuity_tfidf`，保留 0—1 原始尺度；
- Baseline controls：`size_ln`、`leverage`、`roa`、`cash_ratio`、`employee_ln`；
- `rd_intensity` 保留给机制或后续扩展，不放入 baseline，以免阻断潜在政策→研发→创新路径；
- `firm_age` 在 Firm FE + Year FE 下与时间结构高度共线，不进入 baseline；
- province、industry、ownership、listing_date 不作为普通 time-varying controls。

## 基准识别

基准使用当年政策连续性 (X_t) 匹配当年企业结果 (Y_t)，并预先指定 (X_{t-1}) 为 timing robustness：

\[
Y_{it}=\beta PolicyContinuity_{pt}+\gamma Controls_{it}+\alpha_i+\lambda_t+\varepsilon_{it}.
\]

其中 (p) 是企业所在省份，固定效应为 Firm FE 和 Year FE。识别来自企业随时间变化及省份之间的年度相对变化，不是随机实验。

当前模型是连续变量的 two-way fixed-effects panel regression，不是传统 DID：没有统一 treatment event，也没有 treated/control group。

## 推断层级

核心政策变量在 province-year 层面变化，因此 primary cluster level 冻结为 province，而不是 firm。样本实际有 7 个省级 clusters，普通 cluster-robust p-value 存在 small-G 风险。

Primary inference 冻结为省级 Webb wild cluster bootstrap：two-sided、10,000 repetitions、seed `20260918`、equal-tailed 95% CI。辅助报告 conventional province-clustered CRVE、Stata 18 `HC2 + dfadjust` 省级 cluster；firm-clustered CRVE 仅作 comparator。

## 缺失和稳健性预注册

`patent_record_present=0` 的专利结果保持 missing，不填 0。所有企业回归前预先执行 lagged policy、expanding-window policy、full-report metric、theme metric、pair-level text-volume controls、source-quality control、direct-source restricted sample、leave-one-province-out 和 bootstrap weight sensitivity。不得因显著性、方向或置信区间调整 primary outcome、primary metric、样本或 bootstrap 权重。

完整冻结规格见 [`metadata/chapter3_model_specifications.csv`](../metadata/chapter3_model_specifications.csv)。本节不读取正式政策系数结果。

## 3.6 execution correction note

3.6 仅修复实现，不改变上述冻结 specification。已修正 Python 的 province-year lag 构造、Model 0 controls 元数据和旧兼容推断的权威等级；三份 Stata 脚本均补充 `i.year`、数据结构前置验证、Stata HC2 `dfadjust` 和 Stata 18 `wildbootstrap` 结果提取。当前正式结果以实际 Stata/MP 18 输出为准，Python 仅用于 beta/N cross-check。
