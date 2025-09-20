#!/usr/bin/env python3
"""
Quick Setup Script for LlamaIndex RSS Integration
================================================

Автоматическая установка и настройка LlamaIndex интеграции.
"""

import os
import sys
import subprocess
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LlamaIndexSetup:
    """Quick setup for LlamaIndex integration"""

    def __init__(self):
        self.project_root = Path(__file__).parent
        self.required_files = [
            'llamaindex_production.py',
            'llamaindex_components.py',
            'llamaindex_cli.py',
            'llamaindex_schema.sql',
            'requirements_llamaindex.txt'
        ]

    def check_prerequisites(self) -> bool:
        """Check if all required files exist"""

        print("🔍 Checking prerequisites...")

        missing_files = []
        for file in self.required_files:
            if not (self.project_root / file).exists():
                missing_files.append(file)

        if missing_files:
            print(f"❌ Missing files: {', '.join(missing_files)}")
            return False

        print("✅ All required files present")
        return True

    def check_python_version(self) -> bool:
        """Check Python version compatibility"""

        print("🐍 Checking Python version...")

        if sys.version_info < (3, 8):
            print("❌ Python 3.8+ required")
            return False

        print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")
        return True

    def install_dependencies(self) -> bool:
        """Install LlamaIndex dependencies"""

        print("📦 Installing LlamaIndex dependencies...")

        try:
            # Check if pip is available
            subprocess.run([sys.executable, '-m', 'pip', '--version'],
                         check=True, capture_output=True)

            # Install requirements
            requirements_file = self.project_root / 'requirements_llamaindex.txt'

            print("  Installing core LlamaIndex...")
            subprocess.run([
                sys.executable, '-m', 'pip', 'install',
                'llama-index>=0.13.0'
            ], check=True)

            print("  Installing vector stores...")
            subprocess.run([
                sys.executable, '-m', 'pip', 'install',
                'llama-index-vector-stores-postgres',
                'llama-index-vector-stores-pinecone'
            ], check=True)

            print("  Installing LLMs and embeddings...")
            subprocess.run([
                sys.executable, '-m', 'pip', 'install',
                'llama-index-llms-openai',
                'llama-index-llms-gemini',
                'llama-index-embeddings-gemini'
            ], check=True)

            print("  Installing additional dependencies...")
            subprocess.run([
                sys.executable, '-m', 'pip', 'install',
                'pgvector>=0.3.5',
                'pinecone-client>=5.0.0',
                'sentence-transformers>=3.0.0'
            ], check=True)

            print("✅ Dependencies installed successfully")
            return True

        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install dependencies: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error during installation: {e}")
            return False

    def check_environment_variables(self) -> bool:
        """Check required environment variables"""

        print("🌍 Checking environment variables...")

        required_vars = {
            'PG_DSN': 'PostgreSQL connection string',
            'OPENAI_API_KEY': 'OpenAI API key',
            'GEMINI_API_KEY': 'Google Gemini API key',
            'PINECONE_API_KEY': 'Pinecone API key',
            'PINECONE_INDEX': 'Pinecone index name'
        }

        missing_vars = []

        for var, description in required_vars.items():
            if not os.getenv(var):
                missing_vars.append(f"{var} ({description})")

        if missing_vars:
            print("⚠️ Missing environment variables:")
            for var in missing_vars:
                print(f"  - {var}")
            print("\nAdd them to your .env file or set manually:")
            print("export GEMINI_API_KEY=your-gemini-key")
            print("export PINECONE_API_KEY=your-pinecone-key")
            print("export PINECONE_INDEX=rssnews-embeddings")
            return False

        print("✅ All environment variables set")
        return True

    def test_imports(self) -> bool:
        """Test if LlamaIndex imports work"""

        print("🧪 Testing imports...")

        test_imports = [
            ('llama_index.core', 'LlamaIndex core'),
            ('llama_index.vector_stores.postgres', 'PostgreSQL vector store'),
            ('llama_index.vector_stores.pinecone', 'Pinecone vector store'),
            ('llama_index.llms.openai', 'OpenAI LLM'),
            ('llama_index.llms.gemini', 'Gemini LLM'),
            ('llama_index.embeddings.gemini', 'Gemini embeddings'),
        ]

        failed_imports = []

        for module, description in test_imports:
            try:
                __import__(module)
                print(f"  ✅ {description}")
            except ImportError as e:
                print(f"  ❌ {description}: {e}")
                failed_imports.append(module)

        if failed_imports:
            print(f"\n❌ Failed imports: {len(failed_imports)}")
            return False

        print("✅ All imports successful")
        return True

    def test_basic_functionality(self) -> bool:
        """Test basic LlamaIndex functionality"""

        print("🚀 Testing basic functionality...")

        try:
            # Test CLI integration
            from llamaindex_cli import LlamaIndexCLI
            cli = LlamaIndexCLI()
            print("  ✅ CLI integration")

            # Test main components
            from llamaindex_production import RSSLlamaIndexOrchestrator
            print("  ✅ Core orchestrator")

            from llamaindex_components import (
                HybridRetriever, CostTracker, QueryCache
            )
            print("  ✅ Supporting components")

            print("✅ Basic functionality test passed")
            return True

        except Exception as e:
            print(f"❌ Functionality test failed: {e}")
            return False

    def setup_database_schema(self) -> bool:
        """Apply database schema if possible"""

        print("🗄️ Setting up database schema...")

        pg_dsn = os.getenv('PG_DSN')
        if not pg_dsn:
            print("⚠️ PG_DSN not set, skipping database setup")
            print("Run manually: psql $PG_DSN -f llamaindex_schema.sql")
            return True

        try:
            import psycopg2
            schema_file = self.project_root / 'llamaindex_schema.sql'

            with psycopg2.connect(pg_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(schema_file.read_text())
                    conn.commit()

            print("✅ Database schema applied")
            return True

        except ImportError:
            print("⚠️ psycopg2 not available, skipping database setup")
            print("Run manually: psql $PG_DSN -f llamaindex_schema.sql")
            return True
        except Exception as e:
            print(f"⚠️ Database setup failed: {e}")
            print("Run manually: psql $PG_DSN -f llamaindex_schema.sql")
            return True

    def run_setup(self) -> bool:
        """Run complete setup process"""

        print("🚀 Starting LlamaIndex RSS Integration Setup")
        print("=" * 50)

        steps = [
            ("Prerequisites", self.check_prerequisites),
            ("Python Version", self.check_python_version),
            ("Dependencies", self.install_dependencies),
            ("Environment Variables", self.check_environment_variables),
            ("Import Test", self.test_imports),
            ("Functionality Test", self.test_basic_functionality),
            ("Database Schema", self.setup_database_schema),
        ]

        for step_name, step_func in steps:
            print(f"\n🔄 {step_name}...")
            if not step_func():
                print(f"\n❌ Setup failed at: {step_name}")
                return False

        print("\n" + "=" * 50)
        print("🎉 LlamaIndex RSS Integration Setup Complete!")
        print("\n📚 Next steps:")
        print("1. Test installation: python main.py llamaindex-monitor")
        print("2. Process sample data: python main.py llamaindex-ingest --limit 10")
        print("3. Try a query: python main.py llamaindex-query 'latest tech news' --preset qa")
        print("4. Read full documentation: LLAMAINDEX_SETUP.md")

        return True


def main():
    """Main setup function"""

    setup = LlamaIndexSetup()

    if len(sys.argv) > 1 and sys.argv[1] == '--quick':
        # Quick mode: minimal checks
        print("⚡ Quick setup mode")
        success = (
            setup.check_prerequisites() and
            setup.install_dependencies() and
            setup.test_imports()
        )
    else:
        # Full setup
        success = setup.run_setup()

    if success:
        print("\n🚀 Setup completed successfully!")
        return 0
    else:
        print("\n❌ Setup failed. Check errors above.")
        return 1


if __name__ == "__main__":
    exit(main())