#!/bin/bash
# ============================================
#  Cub Scouts Pack Manager - Start Script
# ============================================

echo ""
echo "  ⚜️  Starting Cub Scouts Pack Manager..."
echo ""

# Navigate to the script's directory
cd "$(dirname "$0")"

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "  ❌  Python 3 is required but not installed."
    echo "      Download from: https://www.python.org/downloads/"
    exit 1
fi

# Install required Python packages if missing
echo "  📦  Checking dependencies..."
python3 -c "import flask" 2>/dev/null    || pip3 install flask --quiet
python3 -c "import bcrypt" 2>/dev/null   || pip3 install bcrypt --quiet
python3 -c "import reportlab" 2>/dev/null || pip3 install reportlab --quiet
python3 -c "import psycopg2" 2>/dev/null || pip3 install psycopg2-binary --quiet
echo "  ✅  Dependencies ready."
echo ""

# Set DB path to a writable location
# Change DB_PATH below to move the database to a different location
export DB_PATH="${DB_PATH:-$(pwd)/scouts.db}"
echo "  💾  Database: $DB_PATH"
echo ""

# Start the server
python3 server.py
