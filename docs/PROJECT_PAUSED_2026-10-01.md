# Research-Policy_Innovation_Demo 项目暂停交接

**状态：长期暂停。** 当前优先开展导师要求的第二个项目；未来计划返回本项目继续。以下交接以旧项目基准提交 `37cdb4e1c385fdbb8949fa6900b5584fbd56a699` 为准。

## 最后研究状态

- Parser revision：`issuer_scope_v3`
- Frozen45：issuer 45/45、year-end 45/45、evidence-state 45/45；prior-correct25 regressions = 0
- Strict Gate：`STRICT_PILOT_GATE_REPLAY_INCOMPLETE`
- `h1_parser_repair_status`：`H1_PARSER_REPAIR_NEEDS_FIX`
- 原因：`current_v3_residual_h1_error + pending_canonical_replay_evidence`
- Entity-name status：`CNIPA_ENTITY_NAME_NEEDS_FIX`
- Zero/missing semantics：pending
- `FULL_WIDE_REPARSE_BLOCKED`：仍生效

G3 共分解出五类独立失败依赖：H2 extractor、H1 residual parser、row/event propagation、event mapping，以及 year-precision date normalization。Frozen strict row denominator 为 14，fused correct 4、mismatch 10；300365 negative control 通过。G3 本轮网络请求数为 0。

## 恢复顺序

1. 核对 HEAD、ignored evidence 与相关指纹。
2. 修复 H2 extractor gap。
3. 修复 H1 residual year-end / flag issue。
4. 修复 row/event fusion 与 mapping。
5. 修复 year-precision normalization。
6. 重新执行 strict14 canonical replay。
7. 仅在 Gate 通过后进入 R4C2 Full impact preflight。

不得直接启动 Full reparse；不得重跑 23,448、22,751 或 1,048 项批次。Full/status/cache 在 G3 期间未变。

## 本地恢复证据

以下 ignored 路径随项目本地保留，不属于 Git 提交内容：

- `results/cnipa_preflight/`
- `results/cnipa_full_gap_diagnosis/`
- `results/cnipa_legal_name_recovery/`

仓库 local Git identity 为 Kite-P。不得在交接文档或其他 tracked 文件中记录凭据或本机绝对路径。
