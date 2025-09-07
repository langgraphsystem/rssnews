# Migration from Google Sheets to PostgreSQL

## Completed Migration

This project has been successfully migrated from using Google Sheets API to PostgreSQL database.

### Key Changes Made

1. **New Database Client**: Created `pg_client.py` to replace `sheets_client.py`
2. **Schema Migration**: Implemented PostgreSQL schema with all required tables:
   - `feeds` - RSS feed sources
   - `raw` - Article processing queue  
   - `articles_index` - Deduplication index
   - `diagnostics` - Error logging
   - `config` - Key-value configuration

3. **Updated All Core Files**:
   - `main.py` - Uses `PgClient` instead of `SheetClient`
   - `discovery.py` - Updated to work with PostgreSQL
   - `poller.py` - Rewritten for database operations
   - `worker.py` - Completely rewritten for PostgreSQL

### Installation Requirements

Install the PostgreSQL adapter:
```bash
pip install psycopg2-binary
```

### Configuration

Set the PostgreSQL connection string in your environment:
```bash
export PG_DSN="postgresql://postgres:password@host:port/dbname?sslmode=require"
```

For Railway PostgreSQL, the DSN format is typically:
```
postgresql://postgres:password@hostname.railway.app:5432/railway?sslmode=require
```

### Database Schema

The migration creates the following tables automatically on first run:

- **feeds**: Stores RSS feed information with status tracking
- **raw**: Main article processing queue with all metadata
- **articles_index**: Deduplication tracking by URL and text hash  
- **diagnostics**: Error and event logging
- **config**: Key-value configuration storage

### Usage

The command-line interface remains the same:

```bash
# Initialize database schema
python main.py ensure

# Add RSS feeds
python main.py discovery --feed https://example.com/rss

# Poll feeds for new articles
python main.py poll

# Process articles
python main.py work
```

### Migration Benefits

1. **Performance**: Direct SQL queries instead of API calls
2. **Reliability**: No API rate limits or network dependencies
3. **Scalability**: PostgreSQL can handle much larger datasets
4. **Flexibility**: Advanced queries and analytics capabilities
5. **Cost**: No Google Sheets API quotas or limits

### Notes

- All original functionality has been preserved
- The interface remains compatible with existing scripts
- Database tables are created automatically on first run
- Comprehensive error logging to `diagnostics` table