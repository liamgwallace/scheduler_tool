from flask import Flask, send_from_directory, jsonify, request
import os
import requests
import socket

app = Flask(__name__)

API_SERVER = 'http://localhost:8000'  # API server running on port 8000


@app.route('/')
def index():
    # Serve index.html from the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(current_dir, 'index.html')


@app.route('/api/automation/list_all/')
def fetch_automations():
    response = requests.get(f'{API_SERVER}/automation/list_all/')
    return jsonify(response.json())


@app.route('/api/repo/list_all/')
def fetch_repos():
    response = requests.get(f'{API_SERVER}/repo/list_all/')
    return jsonify(response.json())


@app.route('/api/automation/create_or_update/', methods=['POST'])
def create_update_automation():
    response = requests.post(f'{API_SERVER}/automation/create_or_update/', json=request.json)
    return jsonify(response.json())


@app.route('/api/repo/clone_and_run/', methods=['POST'])
def clone_and_run_repo():
    response = requests.post(f'{API_SERVER}/repo/clone_and_run/', json=request.json)
    return jsonify(response.json())


@app.route('/api/automation/<task_id>/get_code/', methods=['GET'])
def get_automation_code(task_id):
    response = requests.get(f'{API_SERVER}/automation/{task_id}/get_code/')
    return jsonify(response.json())


@app.route('/api/automation/<task_id>/delete/', methods=['DELETE'])
def delete_automation(task_id):
    response = requests.delete(f'{API_SERVER}/automation/{task_id}/delete/')
    return jsonify(response.json())


@app.route('/api/repo/<repo_name>/delete/', methods=['DELETE'])
def delete_repo(repo_name):
    response = requests.delete(f'{API_SERVER}/repo/{repo_name}/delete/')
    return jsonify(response.json())


@app.route('/api/repo/<repo_name>/re-pull/', methods=['POST'])
def re_pull_repo(repo_name):
    # Forward POST request to the API server for re-pulling the repository
    response = requests.post(f'{API_SERVER}/repo/{repo_name}/re-pull/')
    return jsonify(response.json())


if __name__ == "__main__":
    # Get the machine's local IP address
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    port = 5000

    # Run the Flask server
    app.run(host="0.0.0.0", port=port, debug=False)
