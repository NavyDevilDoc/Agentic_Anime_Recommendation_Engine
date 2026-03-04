"""
MODULE: analysis/cost_predictor.py
FUNCTION: MLOps telemetry tool to calculate daily burn rate and forecast 30-day API sustainment costs via GCP.
"""
import os
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load the local environment variables so the CLI can find the GCP URI
load_dotenv('env_variables.env')

# --- PRICING HEURISTICS (Gemini 2.5 Flash) ---
# Rates per 1,000,000 tokens
COST_PER_1M_INPUT = 0.30
COST_PER_1M_OUTPUT = 2.50

def get_db_uri():
    """
    Smart routing to grab the URI whether running locally via CLI or inside Streamlit.
    Pulls the URI securely from the environment.
    """
    return os.environ.get("GCP_POSTGRES_URI")

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
    uri = get_db_uri()
    
    if not uri:
        print("❌ Telemetry Warning: GCP_POSTGRES_URI not found. Log aborted.")
        return

    print("🔗 Connecting to Google Cloud PostgreSQL...")
    try:
        engine = create_engine(uri)
        # Replaced 'engine_logs' with 'telemetry_logs' to match the new cloud architecture
        query = "SELECT timestamp, user_prompt, generated_sql, recommended_titles, success FROM telemetry_logs"
        df = pd.read_sql_query(query, engine)
    except Exception as e:
        print(f"❌ Failed to retrieve telemetry from cloud: {e}")
        return

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
    print(" 📊 MLOPS TELEMETRY & COST FORECAST (GCP CLOUD)")
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