"""
Production Database Setup Script
Applies schema extensions and initializes production features
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.production_db_client import ProductionDBClient

logger = logging.getLogger(__name__)


def setup_production_database():
    """Apply production schema extensions and initialize data"""

    print("🔧 Setting up production database features...")

    try:
        # Initialize database client
        db = ProductionDBClient()

        # Read schema extensions
        schema_path = Path(__file__).parent / "database" / "schema_extensions.sql"

        if not schema_path.exists():
            print(f"❌ Schema file not found: {schema_path}")
            return False

        print("📖 Reading schema extensions...")
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        # Execute schema
        print("⚙️  Applying schema extensions...")
        with db._cursor() as cur:
            # Split by major sections and execute
            statements = schema_sql.split(';')

            executed = 0
            for statement in statements:
                statement = statement.strip()
                if statement and not statement.startswith('--'):
                    try:
                        cur.execute(statement)
                        executed += 1
                    except Exception as e:
                        # Log warning but continue for optional statements
                        if "already exists" not in str(e).lower():
                            logger.warning(f"Statement failed (continuing): {e}")

            print(f"✅ Executed {executed} SQL statements")

        # Verify key tables exist
        print("🔍 Verifying production tables...")
        verification_queries = [
            "SELECT COUNT(*) FROM search_logs WHERE 1=0",
            "SELECT COUNT(*) FROM domain_profiles WHERE 1=0",
            "SELECT COUNT(*) FROM alerts_subscriptions WHERE 1=0",
            "SELECT COUNT(*) FROM clusters_topics WHERE 1=0",
            "SELECT COUNT(*) FROM quality_metrics WHERE 1=0",
            "SELECT COUNT(*) FROM user_interactions WHERE 1=0",
            "SELECT COUNT(*) FROM system_config WHERE 1=0"
        ]

        verified_tables = 0
        with db._cursor() as cur:
            for query in verification_queries:
                try:
                    cur.execute(query)
                    verified_tables += 1
                except Exception as e:
                    print(f"❌ Table verification failed: {e}")

        print(f"✅ Verified {verified_tables}/{len(verification_queries)} production tables")

        # Check existing configuration
        print("📋 Checking system configuration...")
        weights = db.get_scoring_weights()
        if weights:
            print("✅ Scoring weights loaded:")
            for key, value in weights.items():
                print(f"   {key}: {value}")
        else:
            print("⚠️  No scoring weights found in configuration")

        # Check domain profiles
        print("🌐 Checking domain profiles...")
        top_domains = db.get_top_domains_by_score(limit=5)
        if top_domains:
            print(f"✅ Found {len(top_domains)} domain profiles:")
            for domain in top_domains[:3]:
                print(f"   {domain['domain']}: {domain['source_score']:.2f}")
        else:
            print("⚠️  No domain profiles found")

        # Test search logging
        print("📝 Testing search logging...")
        from database.production_db_client import SearchLogEntry
        test_log = SearchLogEntry(
            user_id="test_setup",
            query="test query",
            query_normalized="test query",
            search_method="test",
            results_count=0
        )

        if db.log_search(test_log):
            print("✅ Search logging works")

            # Clean up test log
            with db._cursor() as cur:
                cur.execute("DELETE FROM search_logs WHERE user_id = 'test_setup'")
        else:
            print("❌ Search logging failed")

        print("\n🎉 Production database setup completed successfully!")
        print("\n📊 Next steps:")
        print("1. Run: python ranking_api.py health")
        print("2. Test search: python ranking_api.py search --query 'test'")
        print("3. Check bot integration")

        return True

    except Exception as e:
        print(f"❌ Setup failed: {e}")
        logger.error(f"Database setup failed: {e}")
        return False


def check_dependencies():
    """Check if required dependencies are installed"""
    print("🔍 Checking dependencies...")

    required_packages = [
        'datasketch',
        'numpy',
        'sklearn'
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"❌ Missing packages: {', '.join(missing)}")
        print("Run: pip install -r requirements.txt")
        return False

    print("✅ All dependencies available")
    return True


def main():
    """Main setup function"""
    print("🚀 RSS News Production Setup")
    print("=" * 40)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Check dependencies
    if not check_dependencies():
        print("\n❌ Setup aborted due to missing dependencies")
        return False

    # Setup database
    if not setup_production_database():
        print("\n❌ Setup failed")
        return False

    print("\n✅ Production setup completed successfully!")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)