"""
QualityMixin — data quality analysis methods.
"""

import tkinter as tk

import pandas as pd


class QualityMixin:
    """Mixin providing data quality analysis methods."""

    # ------------------------------------------------------------------
    # Data quality analysis (v2 — live version)
    # ------------------------------------------------------------------

    def analyze_data_quality(self):
        """Automatically analyze and display basic data quality metrics"""
        if self.df is None or len(self.df) == 0:
            self.quality_text.delete("1.0", tk.END)
            self.quality_text.insert("1.0", "No data loaded.")
            return

        try:
            # Score columns
            score_cols = [
                "up__r",
                "up__c",
                "up__f",
                "up__v",
                "up__a",
                "in__r",
                "in__c",
                "in__f",
                "in__v",
                "in__a",
                "do__r",
                "do__c",
                "do__f",
                "do__v",
                "do__a",
            ]

            available_score_cols = [col for col in score_cols if col in self.df.columns]

            # Calculate metrics
            total_records = len(self.df)
            total_companies = (
                self.df["company_name"].nunique()
                if "company_name" in self.df.columns
                else 0
            )

            # Missing values
            if available_score_cols:
                missing_count = self.df[available_score_cols].isna().sum().sum()
                total_cells = len(self.df) * len(available_score_cols)
                missing_pct = (
                    (missing_count / total_cells) * 100 if total_cells > 0 else 0
                )
            else:
                missing_count = 0
                missing_pct = 0

            # Email completeness
            has_email = 0
            if "email_address" in self.df.columns:
                has_email = self.df["email_address"].notna().sum()
            email_pct = (has_email / total_records) * 100 if total_records > 0 else 0

            # Out of range values (for score columns)
            out_of_range = 0
            if available_score_cols:
                for col in available_score_cols:
                    numeric_col = pd.to_numeric(self.df[col], errors="coerce")
                    out_of_range += ((numeric_col < 0) | (numeric_col > 5)).sum()

            # Build quality summary
            quality_summary = f"""DATA QUALITY ANALYSIS
Total Records: {total_records} | Companies: {total_companies} | Emails: {has_email} ({email_pct:.1f}%)
Missing Values: {missing_count} ({missing_pct:.1f}%) | Out of Range: {out_of_range}
Quality Status: {"[OK] Good" if missing_pct < 5 and out_of_range == 0 else "[WARNING] Issues detected"}

"""

            self.quality_text.delete("1.0", tk.END)
            self.quality_text.insert("1.0", quality_summary)

        except Exception as e:
            self.quality_text.delete("1.0", tk.END)
            self.quality_text.insert("1.0", f"Error analyzing data: {str(e)}")
