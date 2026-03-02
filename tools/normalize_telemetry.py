"""
MODULE: analysis/normalize_telemetry.py
FUNCTION: Retroactively squishes blown-out sentiment scores back into a [-1.0, 1.0] domain.
"""
import sqlite3
import os

# --- BULLETPROOF PATH ANCHORING ---
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.basename(SCRIPT_DIR) in ['tools', 'analysis', 'src']:
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
else:
    ROOT_DIR = SCRIPT_DIR

DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")

def normalize_sentiment_domain():
    if not os.path.exists(DB_PATH):
        print(f"❌ CRITICAL: Vault not found at {DB_PATH}")
        return

    print("\n" + "📐"*15)
    print(" INITIATING TELEMETRY NORMALIZATION")
    print("📐"*15 + "\n")

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            # 1. Find the absolute boundaries
            cursor.execute("SELECT MAX(avg_sentiment) FROM anime_info WHERE avg_sentiment > 0")
            max_pos = cursor.fetchone()[0] or 1.0

            cursor.execute("SELECT MIN(avg_sentiment) FROM anime_info WHERE avg_sentiment < 0")
            max_neg = cursor.fetchone()[0] or -1.0
            
            # Prevent dividing by numbers less than 1 if the bounds are already safe
            scale_pos = max(max_pos, 1.0)
            scale_neg = abs(min(max_neg, -1.0))

            print(f"Detected Upper Bound: {max_pos:.4f} (Scaling factor: {scale_pos:.4f})")
            print(f"Detected Lower Bound: {max_neg:.4f} (Scaling factor: {scale_neg:.4f})")

            auth = input("\nType 'NORMALIZE' to permanently re-scale the vault's telemetry: ").strip()
            
            if auth == "NORMALIZE":
                # Scale positives
                cursor.execute("""
                    UPDATE anime_info 
                    SET avg_sentiment = avg_sentiment / ? 
                    WHERE avg_sentiment > 0
                """, (scale_pos,))
                
                # Scale negatives (divide by absolute value to maintain negative sign)
                cursor.execute("""
                    UPDATE anime_info 
                    SET avg_sentiment = avg_sentiment / ? 
                    WHERE avg_sentiment < 0
                """, (scale_neg,))
                
                conn.commit()
                print("\n✅ TELEMETRY NORMALIZED. All scores are safely bounded between -1.0 and 1.0.")
            else:
                print("\n🛑 Authorization aborted.")

    except Exception as e:
        print(f"❌ Operation Failed: {e}")

if __name__ == "__main__":
    normalize_sentiment_domain()