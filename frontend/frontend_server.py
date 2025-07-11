from flask import Flask, send_from_directory, send_file
import os

app = Flask(__name__)

# Get the directory where this script is located
frontend_dir = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
def index():
    return send_file(os.path.join(frontend_dir, 'index.html'))

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(frontend_dir, filename)

if __name__ == '__main__':
    print("Starting Frontend Server (IPv4 only)...")
    print("Frontend will be available at: http://127.0.0.1:8000")
    app.run(debug=True, host='127.0.0.1', port=8000)