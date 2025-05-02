
from flask import Flask, request, jsonify, session, send_from_directory, redirect
import sqlite3
import pandas as pd
import os
from werkzeug.utils import secure_filename
from flask_cors import CORS

app = Flask(__name__, static_folder='static')
app.secret_key = 'secret_key_here'
CORS(app, supports_credentials=True)

DB_PATH = 'inventory.db'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(app.static_folder, exist_ok=True)

# Initialize database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    category TEXT,
    sku TEXT UNIQUE,
    quantity INTEGER DEFAULT 0,
    image_path TEXT
)
''')
conn.commit()
conn.close()

@app.route('/')
def home():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/dashboard.html')
def dashboard():
    if 'user_id' not in session:
        return redirect('/')
    return send_from_directory(app.static_folder, 'dashboard.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password required'})

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'message': 'Username already exists'})
    conn.close()
    return jsonify({'success': True, 'message': 'User registered'})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    if user:
        session['user_id'] = user[0]
        return jsonify({'success': True, 'message': 'Login successful'})
    return jsonify({'success': False, 'message': 'Invalid credentials'})

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'success': True, 'message': 'Logged out'})

@app.route('/inventory', methods=['GET'])
def inventory():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT product_name, category, sku, quantity, image_path FROM inventory")
    rows = cursor.fetchall()
    conn.close()
    return [{
        'product_name': row[0],
        'category': row[1],
        'sku': row[2],
        'quantity': row[3],
        'image_path': row[4]
    } for row in rows]

@app.route('/add', methods=['POST'])
def add():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    data = request.json
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO inventory (product_name, category, sku, quantity, image_path)
            VALUES (?, ?, ?, ?, ?)
        ''', (data['product_name'], data['category'], data['sku'], data['quantity'], data['image_path']))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Product added'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/delete', methods=['DELETE'])
def delete():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    sku = request.args.get('sku')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM inventory WHERE sku = ?', (sku,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Deleted SKU {sku}'})

@app.route('/upload', methods=['POST'])
def upload():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    file = request.files.get('csvFile')
    if not file:
        return jsonify({'success': False, 'message': 'No file uploaded'})
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to read CSV: {str(e)}'})
    required_columns = {'product_name', 'category', 'sku', 'quantity', 'image_path'}
    if not required_columns.issubset(df.columns):
        return jsonify({
            'success': False,
            'message': 'CSV is missing required columns: ' + ', '.join(required_columns - set(df.columns))
        })
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for _, row in df.iterrows():
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO inventory (product_name, category, sku, quantity, image_path)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                row['product_name'],
                row['category'],
                row['sku'],
                int(row['quantity']),
                row['image_path']
            ))
        except Exception as e:
            conn.close()
            return jsonify({'success': False, 'message': f'Error inserting row: {str(e)}'})
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    sku = request.args.get('sku')
    if not sku:
        return jsonify({'success': False, 'message': 'SKU not provided'})
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT quantity FROM inventory WHERE sku = ?', (sku,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': f'SKU {sku} not found'})
    quantity = row[0]
    if quantity < 1:
        conn.close()
        return jsonify({'success': False, 'message': f'SKU {sku} is out of stock'})
    cursor.execute('UPDATE inventory SET quantity = quantity - 1 WHERE sku = ?', (sku,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Successfully checked out SKU {sku}. Remaining stock: {quantity - 1}'})

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    app.run(debug=True)
