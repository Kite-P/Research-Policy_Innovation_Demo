# 第三章 3.6 技术纠错与 Stata 复核实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 在不改变冻结研究设计的前提下，修复第三章 Python 与 Stata 实现错误，实际运行 Stata/MP 18，完成 authoritative inference、before/after 审计、报告重写并以单一 corrective commit 推送。

**Architecture:** Python 仅负责 point-estimate 和结构验证；Stata 08–10 负责正式固定效应、cluster、HC2 和 wildbootstrap 推断。统一的 Stata runner 通过 `STATA_EXE` 或本机发现执行脚本，机器可读结果写入 ignored 的 `results/chapter3/`，Python cross-check 读取新结果并验证 beta/N 一致性。

**Tech Stack:** Python 3.14、pandas、numpy、pytest、Ruff、PowerShell、Stata/MP 18。

**Spec:** 用户提供的 `3.6 第三章技术纠错与 Stata 权威复核执行计划`。

## Global Constraints

- 不修改第一章、第二章政策文本、2.7 source tier、primary outcome、primary policy metric、baseline controls、Firm FE + Year FE、province cluster、Webb WCB 和预注册 robustness 家族。
- Model 0 只使用 policy；Primary 使用冻结的 5 个 controls。
- Python 不再作为正式 WCB、HC2 或 within R² 来源。
- Lagged policy 必须先在唯一 province-year 表计算，再 many-to-one 回填 firm-year。
- Stata 正式命令必须显式包含 `i.year`。
- WCB 固定为 Webb、10,000 reps、seed 20260918、ptype equal。
- 只允许 1 个 corrective commit 和 1 次 push；禁止 `git add .`、force push、绝对安装路径、license 或 secret 泄露。

---

### Task 1: 保存 before 快照与建立测试基线

**Files:**
- Create: `results/chapter3/pre_3_6/`（ignored before snapshot）
- Create: `docs/superpowers/plans/2026-09-19-chapter3-technical-correction.md`

- [ ] Step 1: 复制现有 chapter3 ignored outputs 到 `pre_3_6`
- [ ] Step 2: 记录当前测试基线和 Stata 可执行文件发现结果
- [ ] Step 3: 写入并自审本计划

---

### Task 2: 先写 Python 与 Stata 纠错 failing tests

**Files:**
- Create: `tests/test_chapter3_corrections.py`
- Modify: `tests/test_chapter3_analysis.py`
- Modify: `tests/test_chapter3_robustness.py`
- Modify: `tests/test_chapter3_measurement.py`

- [ ] Step 1: 写 lag 多 firm 同省、首年缺失、完整面板 lag count 测试
- [ ] Step 2: 写 Model 0/Primary regressor metadata 测试
- [ ] Step 3: 写 Stata 每条 xtreg/wildbootstrap 命令必须含 i.year 的解析测试
- [ ] Step 4: 写正确 Webb support、authoritative output 字段和 cross-check generic comparator 测试
- [ ] Step 5: 运行新增测试并确认旧代码按预期失败

---

### Task 3: 修正 Python specification 与 lag

**Files:**
- Modify: `src/chapter3_analysis.py`
- Modify: `src/chapter3_robustness.py`

- [ ] Step 1: 让 `_fit` 先按 controls/extra_controls 明确构造 regressor_names
- [ ] Step 2: 移除 Model 0 的 off-by-one，返回 regressor_names
- [ ] Step 3: 将旧 `_wcb` 降级为明确标注的 legacy compatibility-only，正式输出不再读取其 wcb/hc2/within_r2
- [ ] Step 4: 用唯一 province-year 表计算 lag 并验证 240 行、2020 缺失 40、后续有效 200
- [ ] Step 5: 运行对应测试至通过

---

### Task 4: 创建 Stata runner 与重写 08–10

**Files:**
- Create: `scripts/run_stata_chapter3.ps1`
- Modify: `stata/08_policy_baseline.do`
- Modify: `stata/09_policy_timing_robustness.do`
- Modify: `stata/10_policy_measurement_robustness.do`

- [ ] Step 1: runner 只读取 STATA_EXE/User/Machine 或本地发现，不写绝对路径
- [ ] Step 2: 三份 do 文件统一加入数据、ID、panel、firm-province nesting、7 cluster 前置验证
- [ ] Step 3: 08 写出 conventional province cluster、HC2 dfadjust、firm comparator、Stata r2_w 和 WCB stored results
- [ ] Step 4: 09 修正 lagged 与所有 i.year，并写出 timing CSV
- [ ] Step 5: 10 修正测量、restricted、leave-one-out、Webb/Rademacher 并写出对应 CSV
- [ ] Step 6: 三份脚本追加 sentinel，runner 检查日志 sentinel

---

### Task 5: 运行 Stata 全量并建立 cross-check

**Files:**
- Create: `src/chapter3_stata_crosscheck.py`
- Create: `tests/test_chapter3_stata_crosscheck.py`
- Create: `notebooks/20_chapter3_technical_validation.ipynb`

- [ ] Step 1: 实际执行 runner Target all，并检查 08/09/10 sentinel
- [ ] Step 2: 从 Stata CSV 读取 authoritative baseline/timing/measurement outputs
- [ ] Step 3: 实现 beta/N comparator，tolerance <= 1e-7
- [ ] Step 4: 验证 WCB p/CI coherence、lag N、before/after 文件存在
- [ ] Step 5: 运行 cross-check tests

---

### Task 6: 重写技术文档与最终报告

**Files:**
- Create: `docs/chapter3_technical_correction.md`
- Modify: `docs/chapter3_empirical_results.md`
- Modify: `docs/chapter3_identification_design.md`
- Modify: `README.md`
- Modify: `docs/progress_2026-09-18.md`

- [ ] Step 1: 逐项记录 8 类根因、修正方法和设计未改变声明
- [ ] Step 2: 用 actual Stata 输出重写 baseline/timing/measurement/leave-one-out/weight sensitivity
- [ ] Step 3: 记录 Python cross-check、WCB provenance、p/CI coherence 和 before/after
- [ ] Step 4: 记录任何无法满足项，不把兼容计算冒充 Stata

---

### Task 7: 全量验证、单一提交与推送

- [ ] Step 1: 运行 01–10 Stata validation；如缺少 Stata，明确阻塞，不伪造完成
- [ ] Step 2: 运行 pytest、Ruff、Notebook JSON、结果字段和硬性数值验收
- [ ] Step 3: 执行 staged diff、绝对路径、license、secret 扫描
- [ ] Step 4: 仅一次 commit `fix: 修正第三章计量实现并完成Stata复核`
- [ ] Step 5: 仅一次 `git push origin main`，核验 clean 且 HEAD==origin/main
