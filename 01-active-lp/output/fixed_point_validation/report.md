# Final-policy fixed-point validation

Certified conservative integer quote intervals plus empirical cross-model fidelity and guarded settlement accounting. No compiled AVM behavior, opcode budget, or production safety claim.

```json
{
  "holdout": {
    "histories": 96,
    "path_funding_runs": 288,
    "requested_actions": 21369,
    "trade_requests": 20682,
    "lp_entries": 687,
    "terminal_branches_per_model": 1830,
    "terminal_model_runs": 5490,
    "acceptance_disagreements": 0,
    "rejections_by_model": {
      "A": 0,
      "B": 0,
      "C": 0
    },
    "other_rejections": 0,
    "C_one_sided_quote_checks": 20682,
    "C_one_sided_quote_failures": 0,
    "all_terminal_claims_paid": true,
    "min_C_refund_margin": "86.119094",
    "min_C_outcome_margin": "54.464606",
    "max_trade_quote_abs_A_B": "4.9E-77",
    "max_trade_quote_abs_A_B_path": {
      "path_id": "holdout_41058",
      "funding": "floor"
    },
    "max_trade_quote_abs_A_C": "0.00002460198753058547672198630102942488014636071663170556239685926010786141572",
    "max_trade_quote_abs_A_C_path": {
      "path_id": "holdout_41072",
      "funding": "floor"
    },
    "max_price_abs_A_B": "1.9E-79",
    "max_price_abs_A_B_path": {
      "path_id": "holdout_41015",
      "funding": "floor"
    },
    "max_price_abs_A_C": "0.00000632730271509916894821165006678121443272813211727148219285659234106225817942",
    "max_price_abs_A_C_path": {
      "path_id": "holdout_41003",
      "funding": "floor"
    },
    "max_C_entry_price_jump": "0",
    "max_C_entry_price_jump_path": {
      "path_id": "holdout_41000",
      "funding": "floor"
    },
    "max_terminal_nav_abs_A_B": "1.3E-76",
    "max_terminal_nav_abs_A_B_path": {
      "path_id": "holdout_41093",
      "funding": "floor"
    },
    "max_terminal_nav_abs_A_C": "0.00114465555087974938923452992455035079640566001499771108242734112779368536323",
    "max_terminal_nav_abs_A_C_path": {
      "path_id": "holdout_41030",
      "funding": "proportional_20pct"
    },
    "max_terminal_nav_per_deposit_abs_A_C": "0.0000220568722820490389511068372989852493352686811894889863491527681265874476453",
    "max_terminal_nav_per_deposit_abs_A_C_path": {
      "path_id": "holdout_41011",
      "funding": "proportional_20pct"
    },
    "max_C_settlement_dust": "0.000004",
    "max_C_settlement_dust_path": {
      "path_id": "holdout_41016",
      "funding": "proportional_20pct"
    }
  },
  "stress": {
    "histories": 7,
    "path_funding_runs": 21,
    "requested_actions": 627,
    "trade_requests": 504,
    "lp_entries": 123,
    "terminal_branches_per_model": 297,
    "terminal_model_runs": 891,
    "acceptance_disagreements": 0,
    "rejections_by_model": {
      "A": 3,
      "B": 3,
      "C": 3
    },
    "other_rejections": 0,
    "C_one_sided_quote_checks": 504,
    "C_one_sided_quote_failures": 0,
    "all_terminal_claims_paid": true,
    "min_C_refund_margin": "55.988604",
    "min_C_outcome_margin": "0.249239",
    "max_trade_quote_abs_A_B": "5E-77",
    "max_trade_quote_abs_A_B_path": {
      "path_id": "stress_concentrated_n8",
      "funding": "floor"
    },
    "max_trade_quote_abs_A_C": "0.00006224594453330139414851823200588775376874764203826184599312057142980075830",
    "max_trade_quote_abs_A_C_path": {
      "path_id": "stress_cancel_profit_sells",
      "funding": "floor"
    },
    "max_price_abs_A_B": "3.0E-79",
    "max_price_abs_A_B_path": {
      "path_id": "stress_concentrated_n8",
      "funding": "floor"
    },
    "max_price_abs_A_C": "0.00005703128615709568822064803739933995460026969855201566468430487286516810041854",
    "max_price_abs_A_C_path": {
      "path_id": "stress_low_tail_n64",
      "funding": "floor"
    },
    "max_C_entry_price_jump": "0",
    "max_C_entry_price_jump_path": {
      "path_id": "stress_zero_flow_n3",
      "funding": "floor"
    },
    "max_terminal_nav_abs_A_B": "6.11E-75",
    "max_terminal_nav_abs_A_B_path": {
      "path_id": "stress_concentrated_n8",
      "funding": "floor"
    },
    "max_terminal_nav_abs_A_C": "0.03747155012377099430295077278113326558097475022974142090701753463693889124741",
    "max_terminal_nav_abs_A_C_path": {
      "path_id": "stress_concentrated_n8",
      "funding": "proportional_20pct"
    },
    "max_terminal_nav_per_deposit_abs_A_C": "0.0034107068763946145977670028370426941059112059392522841935987510119974043591429",
    "max_terminal_nav_per_deposit_abs_A_C_path": {
      "path_id": "stress_many_cohorts",
      "funding": "proportional_20pct"
    },
    "max_C_settlement_dust": "0.000024",
    "max_C_settlement_dust_path": {
      "path_id": "stress_many_cohorts",
      "funding": "fixed_20"
    }
  }
}
```
