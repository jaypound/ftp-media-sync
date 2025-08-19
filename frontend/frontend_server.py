from flask import Flask, send_from_directory, send_file, request
import os
import requests

app = Flask(__name__)

# Get the directory where this script is located
frontend_dir = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
def index():
    return send_file(os.path.join(frontend_dir, 'index.html'))

@app.route('/<path:filename>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def static_files(filename):
    # If it's an API request, proxy it to the backend
    if filename.startswith('api/'):
        backend_url = f'http://127.0.0.1:5000/{filename}'
        
        # Forward the request to the backend
        if request.method == 'GET':
            resp = requests.get(backend_url, params=request.args)
        elif request.method == 'POST':
            resp = requests.post(backend_url, json=request.get_json(), headers={'Content-Type': 'application/json'})
        elif request.method == 'PUT':
            resp = requests.put(backend_url, json=request.get_json(), headers={'Content-Type': 'application/json'})
        elif request.method == 'DELETE':
            resp = requests.delete(backend_url)
        else:
            return "Method not allowed", 405
            
        # Return the backend response
        return resp.json() if resp.headers.get('content-type', '').startswith('application/json') else resp.text, resp.status_code
    
    # Otherwise, serve static files
    return send_from_directory(frontend_dir, filename)

if __name__ == '__main__':
    print("Starting Frontend Server (IPv4 only)...")
    print("Frontend will be available at: http://127.0.0.1:8000")
    app.run(debug=True, host='127.0.0.1', port=8000)