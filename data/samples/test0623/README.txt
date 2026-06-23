English Test Data Set (test0623)
================================

Purpose:
  Provide richer English content for end-to-end pipeline testing.

Step 1 - Scenario Anchoring:
  1. Create a new pipeline with scenario "SME Credit Approval" and domain "Credit Risk".
  2. Copy the content of step1_scenario_name.txt into the scenario name field (if blank).
  3. Copy the content of step1_scenario_content.txt into the scenario content textarea.
  4. Use the sub-scenarios in step1_sub_scenarios.csv to fill the sub-scenario list.
     (Pre-screening, Financial Analysis, Collateral Evaluation, Risk Grading & Pricing, Approval Decision)
  5. Select output format "Markdown" or "Excel", then click "Generate Scenario Skeleton".

Step 2 - Knowledge Extraction:
  1. Upload step2_credit_policy.md as the primary knowledge source file.
  2. Optionally also upload step2_case_library.md for case-based extraction.
  3. Select model "DeepSeek-V4-Flash" (or your configured model).
  4. Click "Run Knowledge Extraction" / "Generate SKILL.md".

Expected Result:
  - Step 1 produces an English scenario skeleton with the given sub-scenarios.
  - Step 2 extracts structured knowledge rules (conditions, logic, SQL, anti-patterns, source references).
  - Step 3/4/5 can then proceed as normal.
