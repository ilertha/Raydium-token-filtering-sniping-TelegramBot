import sqlite3
from datetime import datetime, timedelta

# Connect to SQLite database (it will create the database file if it doesn't exist)
conn = sqlite3.connect('tokens.db', check_same_thread=False)
cursor = conn.cursor()


# Create table to store token mint addresses
cursor.execute('''
    CREATE TABLE IF NOT EXISTS tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mint_address TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )
''')
conn.commit()


# Function to insert new token entry into the database
def insert_token(mint_address):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('INSERT INTO tokens (mint_address, timestamp) VALUES (?, ?)', (mint_address, timestamp))
    conn.commit()


# Fetch tokens that are older than 1 minute
def get_tokens_older_than_1_min():
    one_min_ago = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        SELECT id, mint_address FROM tokens 
        WHERE timestamp <= ?
    ''', (one_min_ago,))
    return cursor.fetchall()


# Delete token from the database
def delete_token(token_id):
    cursor.execute('DELETE FROM tokens WHERE id = ?', (token_id,))
    conn.commit()


# Close the database connection when done
def close_db():
    conn.close()