"""
MODULE: analysis/cost_predictor.py
FUNCTION: MLOps telemetry tool to calculate daily burn rate and forecast 30-day API sustainment costs.
"""
import sqlite3
import pandas as pd
import os

# --- PATH ANCHORING ---
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.basename(SCRIPT_DIR) in ['tools', 'analysis', 'src']:
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
else:
    ROOT_DIR = SCRIPT_DIR

TELEMETRY_DB = os.path.join(ROOT_DIR, "data", "anime_telemetry.db")

# --- PRICING HEURISTICS (Gemini 2.5 Flash) ---
# Rates per 1,000,000 tokens
COST_PER_1M_INPUT = 0.30
COST_PER_1M_OUTPUT = 2.50

def estimate_tokens(row):
    """
    Applies the 1 token ≈ 4 characters heuristic.
    Models the two-strike API call architecture (SQL Generation + Reranking).
    """
    if not row['success']:
        # Failed runs only hit the SQL generator (mostly input tokens)
        in_chars = len(str(row['user_prompt'])) + 3000 # Base prompt overhead
        out_chars = len(str(row['generated_sql'])) if row['generated_sql'] else 0
        return pd.Series({'input_tokens': in_chars / 4, 'output_tokens': out_chars / 4})
    
    # Successful runs hit both the SQL generator and the Reranker
    # Reranker reads ~15 candidate profiles (approx 7500 chars)
    in_chars = len(str(row['user_prompt'])) + 3000 + 7500 
    out_chars = len(str(row['generated_sql'])) + len(str(row['recommended_titles'])) + 1000 # JSON overhead
    
    return pd.Series({'input_tokens': in_chars / 4, 'output_tokens': out_chars / 4})

def run_cost_analysis():
    if not os.path.exists(TELEMETRY_DB):
        print("❌ Telemetry database not found. Run the app to generate logs first.")
        return

    with sqlite3.connect(TELEMETRY_DB) as conn:
        df = pd.read_sql_query("SELECT timestamp, user_prompt, generated_sql, recommended_titles, success FROM engine_logs", conn)

    if df.empty:
        print("⚠️ No telemetry data available yet to calculate burn rate.")
        return

    # Extract the date for daily grouping
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date

    # Apply Token Heuristics
    df[['input_tokens', 'output_tokens']] = df.apply(estimate_tokens, axis=1)

    # Calculate Exact Costs
    df['input_cost'] = (df['input_tokens'] / 1_000_000) * COST_PER_1M_INPUT
    df['output_cost'] = (df['output_tokens'] / 1_000_000) * COST_PER_1M_OUTPUT
    df['total_cost'] = df['input_cost'] + df['output_cost']

    # Group by Day
    daily_summary = df.groupby('date').agg(
        total_queries=('timestamp', 'count'),
        total_cost=('total_cost', 'sum')
    ).reset_index()

    # Calculate projections
    avg_daily_cost = daily_summary['total_cost'].mean()
    avg_daily_queries = daily_summary['total_queries'].mean()
    projected_30_day_cost = avg_daily_cost * 30

    print("\n==================================================")
    print(" 📊 MLOPS TELEMETRY & COST FORECAST")
    print("==================================================")
    print(f"Total Queries Logged:  {len(df)}")
    print(f"Total API Spend (Est): ${df['total_cost'].sum():.4f}\n")
    
    print("--- 30-DAY SUSTAINMENT PROJECTION ---")
    print(f"Average Daily Queries: {avg_daily_queries:.1f}")
    print(f"Average Daily Cost:    ${avg_daily_cost:.4f}")
    print(f"30-Day Projected Cost: ${projected_30_day_cost:.4f}")
    print("==================================================\n")

if __name__ == "__main__":
    run_cost_analysis()