# Excel Output Template

## Workbook Structure

Create Excel workbook with following sheets and columns.

## Sheet 1: Summary

Dashboard overview with key metrics.

| Column | Description | Format |
|--------|-------------|--------|
| Metric | Metric name | Text |
| Value | Current value | Number/% |
| Benchmark | Industry/target benchmark | Number/% |
| Status | Good/Warning/Bad | Conditional formatting |

Key metrics to include:
- Total Spend
- Total Conversions
- Average CPA
- Average CTR
- Average QS (weighted)
- Search Impression Share
- Ad Strength distribution

## Sheet 2: Structure

Account structure issues.

| Column | Description |
|--------|-------------|
| Campaign | Campaign name |
| Issue_Type | Naming/Structure/Organization |
| Issue_Description | Specific issue found |
| Severity | High/Medium/Low |
| Recommendation | Suggested fix |

## Sheet 3: Quality_Score

QS analysis by campaign and ad group.

| Column | Description |
|--------|-------------|
| Campaign | Campaign name |
| Ad_Group | Ad group name (if applicable) |
| Weighted_QS | Calculated weighted QS |
| Keyword_Count | Number of keywords |
| QS_Below_5_Count | Keywords with QS < 5 |
| Total_Cost | Total spend |
| Exp_CTR_Issues | Count of Below Average |
| Ad_Rel_Issues | Count of Below Average |
| LP_Exp_Issues | Count of Below Average |
| Est_Savings | Estimated savings if QS improved |

## Sheet 3b: QS_Distribution

Quality Score distribution analysis.

| Column | Description |
|--------|-------------|
| Quality_Score | QS level (1-10, --) |
| Cost | Total cost |
| Cost_Pct | % of total cost |
| Clicks | Total clicks |
| Clicks_Pct | % of total clicks |
| Conversions | Total conversions |
| Conv_Pct | % of total conversions |
| CPA | Cost per acquisition |
| Efficiency | Conv_Pct / Cost_Pct |

Summary row: Low QS (1-6) vs High QS (7-10)

## Sheet 4: Keywords

Keyword-level recommendations.

| Column | Description |
|--------|-------------|
| Campaign | Campaign name |
| Ad_Group | Ad group name |
| Keyword | Keyword text |
| Match_Type | Exact/Phrase/Broad |
| Status | Current status |
| QS | Quality Score |
| Cost | Total cost |
| Clicks | Total clicks |
| Conversions | Total conversions |
| CPA | Cost per acquisition |
| Impr_Share | Impression share |
| Action | Pause/Scale/Monitor/Review |
| Priority | High/Medium/Low |
| Reason | Why this action recommended |

## Sheet 5: Search_Terms

Search term analysis.

| Column | Description |
|--------|-------------|
| Campaign | Campaign name |
| Ad_Group | Ad group name |
| Search_Term | Search query |
| Match_Type | How the term matched |
| Cost | Total cost |
| Clicks | Total clicks |
| Conversions | Total conversions |
| CPA | Cost per acquisition |
| CTR | Click-through rate |
| Relevance_Score | 0-1 relevance to keywords |
| Status | Added/Excluded/None |
| Action | Add_Keyword/Add_Negative/Monitor |
| Priority | High/Medium/Low |

## Sheet 5b: Match_Type_Analysis

Match type performance breakdown.

| Column | Description |
|--------|-------------|
| Match_Type | Exact/Phrase/Broad + variants |
| Cost | Total cost |
| Cost_Pct | % of total cost |
| Conversions | Total conversions |
| Conv_Pct | % of total conversions |
| CPA | Cost per acquisition |
| CTR | Click-through rate |
| Efficiency | Conv_Pct / Cost_Pct ratio |
| Action | Scale/Maintain/Reduce |

## Sheet 5c: Cross_Campaign_Overlap

Search terms appearing in multiple campaigns.

| Column | Description |
|--------|-------------|
| Search_Term | Overlapping search term |
| Campaigns | List of campaigns (pipe-separated) |
| Campaign_Count | Number of campaigns |
| Total_Cost | Combined cost across campaigns |
| Total_Conversions | Combined conversions |
| Winner_Campaign | Campaign with best CPA |
| Action | Add negatives to losing campaigns |
| Priority | Based on cost |

## Sheet 5d: Brand_Leak

Brand terms appearing in non-brand campaigns.

| Column | Description |
|--------|-------------|
| Campaign | Non-brand campaign name |
| Ad_Group | Ad group name |
| Search_Term | Brand search term |
| Cost | Wasted cost |
| Conversions | Conversions (should be in brand) |
| Action | Add as negative |

## Sheet 6: Ads

Ad evaluation.

| Column | Description |
|--------|-------------|
| Campaign | Campaign name |
| Ad_Group | Ad group name |
| Ad_Type | RSA/ETA/Other |
| Status | Enabled/Paused/Removed |
| Ad_Strength | Poor/Average/Good/Excellent |
| Headlines_Count | Number of headlines |
| Descriptions_Count | Number of descriptions |
| Has_Pins | Yes/No |
| Final_URL | Landing page URL |
| CTR | Click-through rate |
| Conv_Rate | Conversion rate |
| Keyword_Relevance | LLM assessment score |
| Issues | List of issues |
| Recommendations | Specific improvements |

## Sheet 6b: Ad_Strength_Distribution

Ad Strength spend distribution.

| Column | Description |
|--------|-------------|
| Ad_Strength | Excellent/Good/Average/Poor/Pending |
| RSA_Count | Number of RSAs |
| Cost | Total cost |
| Cost_Pct | % of total cost |
| Conversions | Total conversions |
| Conv_Pct | % of total conversions |
| CPA | Cost per acquisition |
| Target_Pct | Target spend % |
| Gap | Current vs Target gap |

## Sheet 6c: RSA_Count_Analysis

RSA count per ad group.

| Column | Description |
|--------|-------------|
| Campaign | Campaign name |
| Ad_Group | Ad group name |
| RSA_Count | Number of RSAs |
| Cost | Total cost |
| Conversions | Total conversions |
| Issue | Too many RSAs / No RSA / OK |
| Action | Consolidate / Add RSA / None |

## Sheet 7: Extensions

Extension coverage matrix.

| Column | Description |
|--------|-------------|
| Campaign | Campaign name |
| Sitelinks | ✓/✗ |
| Callouts | ✓/✗ |
| Structured_Snippets | ✓/✗ |
| Call | ✓/✗/N/A |
| Location | ✓/✗/N/A |
| Image | ✓/✗ |
| Price | ✓/✗ |
| Promotion | ✓/✗ |
| Missing_Count | Number missing |
| Priority | High/Medium/Low |

## Sheet 8: Placements (Display only)

| Column | Description |
|--------|-------------|
| Campaign | Campaign name |
| Placement | Placement URL/app |
| Type | Website/App/YouTube |
| Cost | Total cost |
| Conversions | Total conversions |
| CPA | Cost per acquisition |
| CTR | Click-through rate |
| Pct_of_Spend | % of campaign spend |
| Action | Exclude/Monitor/Keep |
| Reason | Why this action |

## Sheet 9: Rejected

Disapproved items.

| Column | Description |
|--------|-------------|
| Type | Ad/Keyword/Extension |
| Campaign | Campaign name |
| Ad_Group | Ad group name |
| Item | Specific item |
| Rejection_Reason | Google's reason |
| Fix_Recommendation | How to resolve |
| Priority | Based on potential impact |

## Sheet 10: Roadmap

Prioritized action items.

| Column | Description |
|--------|-------------|
| Priority_Rank | 1, 2, 3... |
| Category | Structure/QS/Keywords/Ads/etc |
| Action | Specific action to take |
| Affected_Items | Campaigns/ad groups/keywords |
| Impact | High/Medium/Low |
| Effort | Low/Medium/High |
| Priority_Score | Impact × Effort score |
| Timeline | Immediate/This Week/This Month |
| Est_Impact | Estimated improvement |
| Notes | Additional context |

## Conditional Formatting

Apply to all sheets:

```python
# Traffic light formatting for Status/Action columns
def apply_formatting(ws):
    # Red for Bad/Pause/High priority issues
    red_fill = PatternFill(start_color='FFCCCC', end_color='FFCCCC', fill_type='solid')
    
    # Yellow for Warning/Review/Medium
    yellow_fill = PatternFill(start_color='FFFFCC', end_color='FFFFCC', fill_type='solid')
    
    # Green for Good/Scale/Low priority
    green_fill = PatternFill(start_color='CCFFCC', end_color='CCFFCC', fill_type='solid')
```

## Python Generation Example

```python
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows

def create_audit_workbook(data_dict, output_path):
    """
    Create formatted audit workbook.
    
    Args:
        data_dict: Dict with sheet names as keys, DataFrames as values
        output_path: Output file path
    """
    wb = Workbook()
    
    for sheet_name, df in data_dict.items():
        if sheet_name == list(data_dict.keys())[0]:
            ws = wb.active
            ws.title = sheet_name
        else:
            ws = wb.create_sheet(sheet_name)
        
        # Write data
        for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
            for c_idx, value in enumerate(row, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=value)
                
                # Header formatting
                if r_idx == 1:
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
                    cell.font = Font(bold=True, color='FFFFFF')
        
        # Auto-width columns
        for column in ws.columns:
            max_length = max(len(str(cell.value or '')) for cell in column)
            ws.column_dimensions[column[0].column_letter].width = min(max_length + 2, 50)
    
    wb.save(output_path)
```
