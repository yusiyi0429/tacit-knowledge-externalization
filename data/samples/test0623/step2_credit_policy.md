# SME Credit Approval Policy (Effective 2026-01-01)

## 1. Eligibility and Pre-screening Rules

### Rule 1.1 - Minimum Operating History
- **Business Description**: Only SMEs with continuous operations for at least 24 months are eligible for any credit facility.
- **Applicable Conditions**: All new applications.
- **Decision Logic**: Reject if months_in_operation < 24; otherwise proceed.
- **Anti-pattern / Pitfall Tip**: Do not accept "pre-revenue" startups or newly shell companies even if they provide large collateral.
- **Source Document**: SME Credit Policy Manual, Chapter 2.1

### Rule 1.2 - Industry Restrictions
- **Business Description**: Certain high-risk industries are restricted or prohibited.
- **Applicable Conditions**: All applicants.
- **Decision Logic**: 
  - If industry in (coal_mining, real_estate_development, online_gambling, cryptocurrency_trading) → Reject.
  - If industry in (luxury_retail, entertainment, export_trading) → Escalate to credit committee.
  - Otherwise → Proceed.
- **Anti-pattern / Pitfall Tip**: Do not rely solely on the stated business scope in the business license; verify actual revenue sources via bank statements.
- **Source Document**: Restricted Industries List v2026

### Rule 1.3 - AML and Fraud Red Flags
- **Business Description**: Applications showing suspicious ownership structures or unexplained large transactions must be escalated.
- **Applicable Conditions**: All applicants.
- **Decision Logic**: Escalate if any of the following is true:
  - Beneficial owner is a PEP (politically exposed person).
  - More than 50% of recent deposits are from unrelated third parties.
  - Cash deposits exceed 30% of stated revenue without reasonable explanation.
- **Anti-pattern / Pitfall Tip**: Never approve an application with unresolved AML alerts solely to meet sales targets.
- **Source Document**: AML Procedures, Section 4.3

## 2. Financial Analysis Rules

### Rule 2.1 - Debt-to-Income (DTI) Cap
- **Business Description**: The applicant's total monthly debt obligations, including the proposed loan installment, must not exceed 60% of verified monthly income.
- **Applicable Conditions**: All term loans and working capital loans.
- **Decision Logic**: Reject if (existing_monthly_debt + proposed_installment) / monthly_income > 0.60.
- **SQL Reference**:
  ```sql
  SELECT application_id
  FROM applications a
  JOIN financials f ON a.id = f.application_id
  WHERE (f.existing_monthly_debt + a.proposed_installment) / f.monthly_income > 0.60;
  ```
- **Anti-pattern / Pitfall Tip**: Do not use projected future income to inflate the denominator; use trailing 12-month average only.
- **Source Document**: SME Credit Policy Manual, Chapter 3.2

### Rule 2.2 - Cash Flow Stability
- **Business Description**: The applicant must demonstrate stable operating cash inflow for at least 12 consecutive months.
- **Applicable Conditions**: All applicants without AAA-rated guarantor.
- **Decision Logic**: Reject if fewer than 10 of the last 12 months show positive operating cash flow, or if there is a consecutive 3-month negative cash-flow period.
- **SQL Reference**:
  ```sql
  SELECT customer_id,
         COUNT(CASE WHEN net_operating_cash_flow > 0 THEN 1 END) AS positive_months,
         MAX(consecutive_negative_months) AS max_consecutive_negative
  FROM cash_flow_12m
  GROUP BY customer_id
  HAVING positive_months < 10 OR max_consecutive_negative >= 3;
  ```
- **Anti-pattern / Pitfall Tip**: One-off large inflows from asset sales should not be counted as operating cash flow.
- **Source Document**: Financial Analysis Guidelines, Chapter 5

### Rule 2.3 - Profitability Requirement
- **Business Description**: The applicant should have been profitable in at least one of the last two fiscal years.
- **Applicable Conditions**: Term loans with tenor > 12 months.
- **Decision Logic**: Reject if net_profit_year_1 < 0 AND net_profit_year_2 < 0.
- **Anti-pattern / Pitfall Tip**: Do not ignore "below-the-line" losses disguised as extraordinary items.
- **Source Document**: SME Credit Policy Manual, Chapter 3.4

## 3. Collateral Evaluation Rules

### Rule 3.1 - Collateral Required for Large Loans
- **Business Description**: Loans above RMB 1,000,000 must be fully collateralized unless the applicant holds an internal AAA credit grade.
- **Applicable Conditions**: Facility amount > RMB 1,000,000.
- **Decision Logic**: 
  - If loan_amount > 1,000,000 AND credit_grade != 'AAA' AND collateral_value < loan_amount → Reject or reduce facility.
  - Otherwise → Proceed.
- **Anti-pattern / Pitfall Tip**: Do not accept collateral from related parties without independent valuation.
- **Source Document**: Collateral Management Policy, Chapter 2

### Rule 3.2 - Acceptable Collateral Types and Haircuts
- **Business Description**: Different collateral types carry different valuation haircuts.
- **Applicable Conditions**: All secured facilities.
- **Decision Logic**: 
  - Residential real estate: max LTV 70%, haircut 30%.
  - Commercial real estate: max LTV 60%, haircut 40%.
  - Machinery and equipment: max LTV 40%, haircut 60%.
  - Accounts receivable: max LTV 50%, haircut 50%, eligible only from top-3 debtors.
- **Anti-pattern / Pitfall Tip**: Inventory collateral should not include perishable goods or customized items without resale market.
- **Source Document**: Collateral Management Policy, Chapter 3

### Rule 3.3 - Third-Party Appraisal
- **Business Description**: Real estate collateral must be appraised by an appraiser on the bank's approved panel within the last 6 months.
- **Applicable Conditions**: Real estate collateral.
- **Decision Logic**: Reject if appraisal_date < today - 6 months OR appraiser_id NOT IN approved_appraisers.
- **Anti-pattern / Pitfall Tip**: Do not accept valuations where the appraiser is also a related party of the borrower.
- **Source Document**: Collateral Management Policy, Chapter 4

## 4. Risk Grading and Pricing Rules

### Rule 4.1 - Internal Risk Grade Assignment
- **Business Description**: Each approved application is assigned an internal risk grade (AAA, AA, A, BBB, BB, B, CCC) based on a composite score.
- **Applicable Conditions**: All applications reaching the grading stage.
- **Decision Logic**:
  - Score >= 90 → AAA
  - 80 <= Score < 90 → AA
  - 70 <= Score < 80 → A
  - 60 <= Score < 70 → BBB
  - 50 <= Score < 60 → BB
  - 40 <= Score < 50 → B
  - Score < 40 → CCC (reject unless fully collateralized)
- **Anti-pattern / Pitfall Tip**: Do not override the automated risk grade without documented committee approval.
- **Source Document**: Risk Grading Framework v2026

### Rule 4.2 - Risk-Based Pricing
- **Business Description**: The approved interest rate is the base rate plus a risk spread based on the internal grade.
- **Applicable Conditions**: All approved facilities.
- **Decision Logic**:
  - AAA: base_rate + 1.0%
  - AA: base_rate + 1.5%
  - A: base_rate + 2.0%
  - BBB: base_rate + 3.0%
  - BB: base_rate + 4.5%
  - B: base_rate + 6.0%
- **Anti-pattern / Pitfall Tip**: Do not waive the risk spread for relationship reasons; pricing concessions require committee approval.
- **Source Document**: Pricing Policy, Chapter 2

## 5. Approval Authority and Conditions

### Rule 5.1 - Approval Authority Matrix
- **Business Description**: Different decision-makers have different approval limits.
- **Applicable Conditions**: All facilities.
- **Decision Logic**:
  - RM + automated scorecard: <= RMB 200,000
  - Branch credit manager: <= RMB 1,000,000
  - Regional credit committee: <= RMB 3,000,000
  - Head office credit committee: > RMB 3,000,000
- **Anti-pattern / Pitfall Tip**: Never split a single facility into multiple smaller applications to bypass authority limits.
- **Source Document**: Delegation of Authority Matrix

### Rule 5.2 - Standard Conditions Precedent
- **Business Description**: Approved loans are subject to standard conditions before disbursement.
- **Applicable Conditions**: All approved facilities.
- **Decision Logic**: Disbursement is blocked until:
  - Legal contracts are signed and stamped.
  - Collateral is registered (where applicable).
  - Insurance policy naming the bank as beneficiary is in place.
  - Any outstanding AML/fraud alerts are cleared.
- **Anti-pattern / Pitfall Tip**: Do not disburse before confirming collateral registration is complete.
- **Source Document**: Loan Operations Manual, Chapter 6

### Rule 5.3 - Technology Startups with IP Assets
- **Business Description**: Technology startups without revenue but with valuable IP may be considered for specialist venture-debt facilities.
- **Applicable Conditions**: Industry = technology, revenue = 0 or negative, IP assets exist.
- **Decision Logic**: Escalate to the technology finance committee with an independent IP valuation report.
- **Anti-pattern / Pitfall Tip**: Do not apply standard SME cash-flow criteria to pre-revenue tech startups; use the dedicated venture-debt scorecard.
- **Source Document**: Technology Finance Policy, Chapter 1
