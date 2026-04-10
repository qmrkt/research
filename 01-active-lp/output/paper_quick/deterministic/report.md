# Active LP Result Snapshot

- Results: 9
- Run families: deterministic
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 3.709404702152548257295422586E-29
- Mean fairness gap (late minus early NAV/deposit): 0.02414595379810647501598486518
- Invariant failures: 0

## Run Families

- `deterministic`: results=9, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.342380814452447987823048748E-29, invariant_failures=0

## Fairness Extremes

- `positive` #1: `skewed_late_lp` (deterministic) fairness_gap=0.1139392829117664504807242379
- `positive` #2: `same_final_claims_different_timing` (deterministic) fairness_gap=0.0400594700638785947641349721
- `positive` #3: `long_tail_late_lp` (deterministic) fairness_gap=0.0211738279275841992730247060
- `positive` #4: `early_vs_late_same_delta_b` (deterministic) fairness_gap=0.0208632596755901026139658264
- `positive` #5: `same_block_trade_reordering` (deterministic) fairness_gap=0.0189009676447594154980598792
- `negative` #1: `cancellation_refund_path` (deterministic) fairness_gap=-0.0191069784755991348061986554
- `absolute` #1: `skewed_late_lp` (deterministic) fairness_gap=0.1139392829117664504807242379
- `absolute` #2: `same_final_claims_different_timing` (deterministic) fairness_gap=0.0400594700638785947641349721
- `absolute` #3: `long_tail_late_lp` (deterministic) fairness_gap=0.0211738279275841992730247060
- `absolute` #4: `early_vs_late_same_delta_b` (deterministic) fairness_gap=0.0208632596755901026139658264
