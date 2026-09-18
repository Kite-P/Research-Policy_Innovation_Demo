version 18.0
clear all
set more off

use "data/processed/research_panel_policy.dta", clear
count
assert r(N) == 240
isid stock_code year
egen firm_id = group(stock_code)
quietly summarize firm_id
assert r(max) == 40
quietly summarize year
assert r(min) == 2020
assert r(max) == 2025
assert policy_metric_present == 1
summarize policy_continuity_tfidf policy_continuity_full_tfidf policy_continuity_theme
assert policy_continuity_tfidf >= 0 & policy_continuity_tfidf <= 1
assert policy_continuity_full_tfidf >= 0 & policy_continuity_full_tfidf <= 1
assert policy_continuity_theme >= 0 & policy_continuity_theme <= 1
assert policy_cont_tfidf_exp >= 0 & policy_cont_tfidf_exp <= 1
assert source_tier_max >= 1 & source_tier_max <= 4
assert both_direct_official == 0 | both_direct_official == 1
assert policy_metric_present == 1
summarize pair_mean_log_industry_chars abs_log_industry_length_change pair_mean_log_full_chars abs_log_full_length_change
xtset firm_id year
