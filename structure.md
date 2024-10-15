# Folder Structure

- scheduler_tool/
    - docker-compose.yaml
    - Dockerfile
    - requirements.txt
    - structure.md
    - app/
        - api.py
        - api_server.py
        - api_test.py
        - automation.log
        - automations.json
        - error.log
        - index.html
        - repos.json
        - web_server.py
        - repos/

### docker-compose.yaml
*Location:* `C:/Users/liamg/PycharmProjects/pythonProject/scheduler_tool`

```yaml
version: '3.8'

services:
  automation-api:
    build:
      context: .
      dockerfile: Dockerfile  # Reference the Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./automations.json:/app/automations.json  # Persist automation data
      - ./automation.log:/app/automation.log      # Log automation runs
      - ./error.log:/app/error.log                # Log errors
    restart: always

```

### Dockerfile
*Location:* `C:/Users/liamg/PycharmProjects/pythonProject/scheduler_tool`

```
FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git \
    && git clone https://github.com/yourusername/your-repo.git . \
    && apt-get remove -y git \
    && apt-get autoremove -y

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

```

### requirements.txt
*Location:* `C:/Users/liamg/PycharmProjects/pythonProject/scheduler_tool`

```python
Flask==2.1.3
Werkzeug==2.2.3
GitPython==3.1.31
APScheduler==3.10.4
requests
flask-cors
```

### api_server.py
*Location:* `C:/Users/liamg/PycharmProjects/pythonProject/scheduler_tool\app`

```python
from flask import Flask, request, jsonify
import subprocess
import logging
import os
import json
import git
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from functools import wraps
import shutil
import sys
import time
import errno
import stat
from apscheduler.jobstores.base import JobLookupError
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
scheduler = BackgroundScheduler()
scheduler.start()

# Set up logging
log_dir = os.path.abspath(".")
logging.basicConfig(
    filename=os.path.join(log_dir, 'automation.log'),
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
error_log = os.path.join(log_dir, 'error.log')

# Files to store automations and repositories
AUTOMATIONS_FILE = os.path.join(log_dir, "automations.json")
REPOS_FILE = os.path.join(log_dir, "repos.json")

# Ensure the necessary directories exist
repos_dir = os.path.join(log_dir, "repos")
os.makedirs(repos_dir, exist_ok=True)

# If automations.json or repos.json doesn't exist, create it
for file in [AUTOMATIONS_FILE, REPOS_FILE]:
    if not os.path.exists(file):
        with open(file, 'w') as f:
            json.dump({}, f, indent=4)

# Load automations from file
def load_automations():
    with open(AUTOMATIONS_FILE, 'r') as f:
        return json.load(f)

# Save automations to file
def save_automations(automations):
    with open(AUTOMATIONS_FILE, 'w') as f:
        json.dump(automations, f, indent=4)

# Load repositories from file
def load_repos():
    with open(REPOS_FILE, 'r') as f:
        return json.load(f)

# Save repositories to file
def save_repos(repos):
    with open(REPOS_FILE, 'w') as f:
        json.dump(repos, f, indent=4)

# Helper decorator for error handling
def handle_exceptions(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except HTTPException as e:
            response = jsonify({"detail": e.detail})
            response.status_code = e.status_code
            return response
        except Exception as e:
            logging.error(f"Unhandled exception: {str(e)}")
            with open(error_log, 'a') as err_file:
                err_file.write(f"Unhandled exception: {str(e)}\n")
            return jsonify({"detail": "Internal Server Error"}), 500
    return decorated_function

# Custom HTTPException for error handling
class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail

# Function to install packages immediately
def install_packages(packages):
    try:
        if packages:
            for package in packages:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", package],
                    check=True,
                    shell=False
                )
    except subprocess.CalledProcessError as e:
        package = package if 'package' in locals() else 'unknown'
        logging.error(f"Failed to install package: {package}. Error: {str(e)}")
        with open(error_log, 'a') as err_file:
            err_file.write(f"Failed to install package: {package}. Error: {str(e)}\n")
        raise HTTPException(400, f"Failed to install package: {package}. Error: {str(e)}")

# Function to run the code (packages already installed)
def run_task(code, task_id):
    try:
        exec(code, {})
        logging.info(f"Automation {task_id} successfully ran.")
    except Exception as e:
        logging.error(f"Error running automation {task_id}: {str(e)}")
        with open(error_log, 'a') as err_file:
            err_file.write(f"Error running automation {task_id}: {str(e)}\n")

# Function to run repo task
def run_repo_task(repo_script, repo_name):
    try:
        result = subprocess.run(
            [sys.executable, repo_script],
            check=True,
            shell=False
        )
        logging.info(f"Executed {repo_script} from repository {repo_name}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to execute {repo_script} from repository {repo_name}: {str(e)}")
        with open(error_log, 'a') as err_file:
            err_file.write(f"Failed to execute {repo_script} from repository {repo_name}: {str(e)}\n")

# Helper function to parse cron expressions
def parse_cron(cron_expr):
    try:
        cron_fields = cron_expr.strip().split()
        if len(cron_fields) != 5:
            raise ValueError("Cron expression must have exactly 5 fields")
        return {
            'minute': cron_fields[0],
            'hour': cron_fields[1],
            'day': cron_fields[2],
            'month': cron_fields[3],
            'day_of_week': cron_fields[4]
        }
    except Exception as e:
        raise HTTPException(400, f"Invalid cron expression: {str(e)}")

# Function to remove read-only files
def remove_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)

# Clone a GitHub repository and run main.py if it exists
def clone_and_run(repo_url, schedule=None, run_on_startup=False, run_once=False):
    repo_name = repo_url.rstrip('/').split('/')[-1].replace('.git', '')
    repo_dir = os.path.join(repos_dir, repo_name)

    # Clone the repository if it doesn't exist
    if not os.path.exists(repo_dir):
        try:
            repo = git.Repo.clone_from(repo_url, repo_dir)
            logging.info(f"Cloned repository {repo_url}")
            del repo  # Ensure the Repo object is deleted
        except Exception as e:
            logging.error(f"Failed to clone repository {repo_url}: {str(e)}")
            with open(error_log, 'a') as err_file:
                err_file.write(f"Failed to clone repository {repo_url}: {str(e)}\n")
            raise HTTPException(500, f"Failed to clone repository: {str(e)}")
    else:
        # Pull the latest changes
        try:
            repo = git.Repo(repo_dir)
            origin = repo.remotes.origin
            origin.pull()
            logging.info(f"Pulled latest changes for repository {repo_url}")
            del repo  # Ensure the Repo object is deleted
        except Exception as e:
            logging.error(f"Failed to pull repository {repo_url}: {str(e)}")
            with open(error_log, 'a') as err_file:
                err_file.write(f"Failed to pull repository {repo_url}: {str(e)}\n")
            raise HTTPException(500, f"Failed to pull repository: {str(e)}")

    # Install requirements.txt if it exists
    req_file = os.path.join(repo_dir, 'requirements.txt')
    if os.path.exists(req_file):
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_file],
                check=True,
                shell=False
            )
            logging.info(f"Installed requirements for {repo_name}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to install requirements for {repo_name}: {str(e)}")
            with open(error_log, 'a') as err_file:
                err_file.write(f"Failed to install requirements for {repo_name}: {str(e)}\n")
            raise HTTPException(500, f"Failed to install requirements: {str(e)}")

    # Run main.py if it exists
    main_py = os.path.join(repo_dir, 'main.py')
    if not os.path.exists(main_py):
        logging.error(f"No main.py found in {repo_name}")
        raise HTTPException(404, f"No main.py found in {repo_name}")

    # Schedule with cron if schedule is provided
    if schedule:
        cron_params = parse_cron(schedule)
        trigger = CronTrigger(**cron_params)
        scheduler.add_job(
            run_repo_task,
            trigger,
            id=repo_name,
            args=[main_py, repo_name],
            replace_existing=True
        )
        logging.info(f"Scheduled repository {repo_name} with cron schedule: {schedule}")

    # Run immediately if run_once is True
    if run_once:
        run_repo_task(main_py, repo_name)

    # Store repository metadata in repos.json
    repos = load_repos()
    repos[repo_name] = {
        "repo_url": repo_url,
        "schedule": schedule,
        "run_on_startup": run_on_startup,
        "run_once": run_once
    }
    save_repos(repos)

    return repo_name  # Return the repository name as the ID

# Routes for Automations

@app.route("/automation/create_or_update/", methods=["POST"])
@handle_exceptions
def create_or_update_automation():
    print(f"Endpoint '/automation/create_or_update/' triggered.")
    data = request.get_json()
    print(f"Payload: {data}")
    if not data:
        raise HTTPException(400, "Invalid JSON data")

    required_fields = ["task_id", "code", "packages", "schedule", "run_on_startup", "run_once"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(400, f"Missing field: {field}")

    task_id = data["task_id"]
    code = data["code"]
    packages = data.get("packages", [])
    schedule = data.get("schedule")
    run_on_startup = data.get("run_on_startup", False)
    run_once = data.get("run_once", False)

    # Step 1: Install packages
    install_packages(packages)

    automations = load_automations()

    # Step 2: If the task exists, update it
    if task_id in automations:
        try:
            scheduler.remove_job(task_id)
            logging.info(f"Removed existing automation job {task_id}")
        except JobLookupError:
            pass  # Job might not exist

    # Step 3: Schedule job with cron if schedule is provided
    if schedule:
        cron_params = parse_cron(schedule)
        trigger = CronTrigger(**cron_params)
        scheduler.add_job(run_task, trigger, id=task_id, args=[code, task_id])
        logging.info(f"Scheduled automation {task_id} with cron schedule: {schedule}")

    # Run immediately if run_once is True
    if run_once:
        run_task(code, task_id)

    # Step 4: Store automation details in JSON
    automations[task_id] = {
        "task_id": task_id,
        "code": code,
        "packages": packages,
        "schedule": schedule,
        "run_on_startup": run_on_startup,
        "run_once": run_once
    }
    save_automations(automations)

    return jsonify({
        "status": "success",
        "message": f"Automation {task_id} added or updated",
        "id": task_id
    }), 200

@app.route("/automation/list_all/", methods=["GET"])
@handle_exceptions
def list_automations():
    print(f"Endpoint '/automation/list_all/' triggered.")
    automations = load_automations()
    return jsonify(automations), 200

@app.route("/automation/<task_id>/get_code/", methods=["GET"])
@handle_exceptions
def get_automation_code(task_id):
    print(f"Endpoint '/automation/{task_id}/get_code/' triggered.")
    automations = load_automations()
    if task_id not in automations:
        raise HTTPException(404, "Automation not found")
    return jsonify({
        "task_id": task_id,
        "code": automations[task_id].get("code"),
        "packages": automations[task_id].get("packages"),
        "schedule": automations[task_id].get("schedule"),
        "run_on_startup": automations[task_id].get("run_on_startup"),
        "run_once": automations[task_id].get("run_once")
    }), 200

@app.route("/automation/<task_id>/delete/", methods=["DELETE"])
@handle_exceptions
def remove_automation(task_id):
    print(f"Endpoint '/automation/{task_id}/delete/' triggered.")
    automations = load_automations()
    if task_id not in automations:
        raise HTTPException(404, "Automation not found")

    try:
        scheduler.remove_job(task_id)
        logging.info(f"Removed automation job {task_id}")
    except JobLookupError as e:
        logging.warning(f"Could not remove job {task_id}: {str(e)}")

    del automations[task_id]
    save_automations(automations)

    return jsonify({
        "status": "success",
        "message": f"Automation {task_id} removed"
    }), 200

# Routes for Repositories

@app.route("/repo/clone_and_run/", methods=["POST"])
@handle_exceptions
def clone_and_run_repo():
    print(f"Endpoint '/repo/clone_and_run/' triggered.")
    data = request.get_json()
    print(f"Payload: {data}")
    if not data:
        raise HTTPException(400, "Invalid JSON data")

    required_fields = ["repo_url", "run_on_startup", "run_once"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(400, f"Missing field: {field}")

    repo_url = data["repo_url"]
    schedule = data.get("schedule")  # Optional
    run_on_startup = data["run_on_startup"]
    run_once = data["run_once"]

    repo_name = clone_and_run(repo_url, schedule, run_on_startup, run_once)
    return jsonify({
        "status": "success",
        "message": f"Cloned and ran repo {repo_url}",
        "id": repo_name
    }), 200

@app.route("/repo/list_all/", methods=["GET"])
@handle_exceptions
def list_repos_route():
    print(f"Endpoint '/repo/list_all/' triggered.")
    repos = load_repos()
    return jsonify(repos), 200

@app.route("/repo/<repo_name>/delete/", methods=["DELETE"])
@handle_exceptions
def remove_repo(repo_name):
    print(f"Endpoint '/repo/{repo_name}/delete/' triggered.")
    repos = load_repos()
    if repo_name not in repos:
        raise HTTPException(404, "Repository not found")

    # Remove scheduled job
    try:
        scheduler.remove_job(repo_name)
        logging.info(f"Removed scheduled job for repository {repo_name}")
    except JobLookupError:
        pass  # Job might not exist

    del repos[repo_name]
    save_repos(repos)

    # Remove the actual repo directory
    repo_dir = os.path.join(repos_dir, repo_name)
    if os.path.exists(repo_dir):
        try:
            shutil.rmtree(repo_dir, onerror=remove_readonly)
            logging.info(f"Removed repository directory {repo_dir}")
        except Exception as e:
            logging.error(f"Failed to remove repository directory {repo_dir}: {str(e)}")
            with open(error_log, 'a') as err_file:
                err_file.write(f"Failed to remove repository directory {repo_dir}: {str(e)}\n")
            raise HTTPException(500, f"Failed to remove repository directory: {str(e)}")

    return jsonify({
        "status": "success",
        "message": f"Repository {repo_name} removed"
    }), 200

@app.route("/repo/<repo_name>/re-pull/", methods=["POST"])
@handle_exceptions
def re_pull_repo(repo_name):
    print(f"Endpoint '/repo/{repo_name}/re-pull/' triggered.")
    repos = load_repos()
    if repo_name not in repos:
        raise HTTPException(404, "Repository not found")

    repo_data = repos[repo_name]
    repo_url = repo_data["repo_url"]
    schedule = repo_data.get("schedule")
    run_on_startup = repo_data.get("run_on_startup", False)
    run_once = repo_data.get("run_once", False)

    # Re-clone or pull the repository
    repo_dir = os.path.join(repos_dir, repo_name)
    if os.path.exists(repo_dir):
        try:
            repo = git.Repo(repo_dir)
            origin = repo.remotes.origin
            origin.pull()
            logging.info(f"Re-pulled repository {repo_url}")
            del repo  # Ensure the Repo object is deleted
        except Exception as e:
            logging.error(f"Failed to re-pull repository {repo_url}: {str(e)}")
            with open(error_log, 'a') as err_file:
                err_file.write(f"Failed to re-pull repository {repo_url}: {str(e)}\n")
            raise HTTPException(500, f"Failed to re-pull repository: {str(e)}")
    else:
        # If repo directory doesn't exist, clone it
        clone_and_run(repo_url, schedule, run_on_startup, run_once)
        return jsonify({
            "status": "success",
            "message": f"Cloned and ran repo {repo_url}",
            "id": repo_name
        }), 200

    # Schedule with cron if schedule is provided
    main_py = os.path.join(repo_dir, 'main.py')
    if not os.path.exists(main_py):
        logging.error(f"No main.py found in {repo_name} after re-pull")
        raise HTTPException(404, f"No main.py found in {repo_name} after re-pull")

    if schedule:
        # Reschedule the job
        try:
            scheduler.remove_job(repo_name)
        except JobLookupError:
            pass  # Job might not exist
        cron_params = parse_cron(schedule)
        trigger = CronTrigger(**cron_params)
        scheduler.add_job(
            run_repo_task,
            trigger,
            id=repo_name,
            args=[main_py, repo_name],
            replace_existing=True
        )
        logging.info(f"Rescheduled repository {repo_name} with cron schedule: {schedule}")

    # Run immediately if run_once is True
    if run_once:
        run_repo_task(main_py, repo_name)

    return jsonify({
        "status": "success",
        "message": f"Re-pulled and executed repo {repo_name}"
    }), 200

# Load and run repositories and automations on startup
def startup_event():
    # Load and run repositories
    repos = load_repos()
    for repo_name, repo_data in repos.items():
        repo_url = repo_data["repo_url"]
        schedule = repo_data.get("schedule")
        run_on_startup = repo_data.get("run_on_startup", False)
        run_once = False  # Avoid running twice on startup
        try:
            clone_and_run(
                repo_url,
                schedule,
                run_on_startup,
                run_once
            )
            # Run immediately if run_on_startup is True
            if run_on_startup:
                main_py = os.path.join(repos_dir, repo_name, 'main.py')
                if os.path.exists(main_py):
                    run_repo_task(main_py, repo_name)
        except Exception as e:
            logging.error(f"Failed to run repository {repo_name} on startup: {str(e)}")

    # Load and run automations
    automations = load_automations()
    for task_id, automation_data in automations.items():
        code = automation_data.get("code")
        packages = automation_data.get("packages", [])
        schedule = automation_data.get("schedule")
        run_on_startup = automation_data.get("run_on_startup", False)
        run_once = False  # Avoid running twice on startup

        # Install packages
        install_packages(packages)

        # Schedule job with cron if schedule is provided
        if schedule:
            cron_params = parse_cron(schedule)
            trigger = CronTrigger(**cron_params)
            scheduler.add_job(run_task, trigger, id=task_id, args=[code, task_id])
            logging.info(f"Scheduled automation {task_id} with cron schedule: {schedule}")

        # Run immediately if run_on_startup is True
        if run_on_startup:
            run_task(code, task_id)

# Register the startup event
@app.before_first_request
def before_first_request_func():
    startup_event()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

```

### api_test.py
*Location:* `C:/Users/liamg/PycharmProjects/pythonProject/scheduler_tool\app`

```python
import requests
import time

# Base URL of the API
BASE_URL = "http://localhost:8000"

def create_or_update_automation(task_id, code, packages, schedule, run_on_startup, run_once):
    response = requests.post(f"{BASE_URL}/automation/create_or_update/", json={
        "task_id": task_id,
        "code": code,
        "packages": packages,
        "schedule": schedule,
        "run_on_startup": run_on_startup,
        "run_once": run_once
    })
    print("Create or Update Automation Response:")
    print_response(response)

def list_automations():
    response = requests.get(f"{BASE_URL}/automation/list_all/")
    print("List Automations Response:")
    print_response(response)

def get_automation_code(task_id):
    response = requests.get(f"{BASE_URL}/automation/{task_id}/get_code/")
    print(f"Get Automation Code Response for task_id '{task_id}':")
    print_response(response)

def delete_automation(task_id):
    response = requests.delete(f"{BASE_URL}/automation/{task_id}/delete/")
    print(f"Delete Automation Response for task_id '{task_id}':")
    print_response(response)

def clone_and_run_repository(repo_url, schedule, run_on_startup, run_once):
    response = requests.post(f"{BASE_URL}/repo/clone_and_run/", json={
        "repo_url": repo_url,
        "schedule": schedule,
        "run_on_startup": run_on_startup,
        "run_once": run_once
    })
    print("Clone and Run Repository Response:")
    print_response(response)

def list_repositories():
    response = requests.get(f"{BASE_URL}/repo/list_all/")
    print("List Repositories Response:")
    print_response(response)

def delete_repository(repo_name):
    response = requests.delete(f"{BASE_URL}/repo/{repo_name}/delete/")
    print(f"Delete Repository Response for repo_name '{repo_name}':")
    print_response(response)

def repull_repository(repo_name):
    response = requests.post(f"{BASE_URL}/repo/{repo_name}/re-pull/")
    print(f"Re-pull Repository Response for repo_name '{repo_name}':")
    print_response(response)

def print_response(response):
    print("Status Code:", response.status_code)
    try:
        response_json = response.json()
        print("Response JSON:", response_json)
    except Exception as e:
        print("Response Text:", response.text)
        print("Failed to parse JSON:", str(e))
    print("-" * 50)

def main():
    # Testing Automations Endpoints
    print("=== Testing Automations Endpoints ===\n")
    task_id = "test_automation"
    code = "print('Hello from automation!')"
    packages = []  # No additional packages required
    schedule = "* * * * *"  # No schedule
    run_on_startup = True
    run_once = True  # Run immediately once

    create_or_update_automation(task_id, code, packages, schedule, run_on_startup, run_once)
    time.sleep(1)  # Pauses the program for 1 second
    list_automations()
    time.sleep(1)
    get_automation_code(task_id)
    time.sleep(1)
    # Uncomment the next line to delete the automation
    # delete_automation(task_id)
    time.sleep(1)
    list_automations()

    # Testing Repositories Endpoints
    print("\n=== Testing Repositories Endpoints ===\n")
    repo_url = "https://github.com/liamgwallace/test.git"  # Replace with an actual accessible repo URL
    schedule = "* * * * *"  # No schedule
    run_on_startup = True
    run_once = True  # Run immediately once

    clone_and_run_repository(repo_url, schedule, run_on_startup, run_once)
    list_repositories()

    repo_name = repo_url.rstrip('/').split('/')[-1].replace('.git', '')
    repull_repository(repo_name)
    time.sleep(1)
    # Uncomment the next line to delete the repository
    # delete_repository(repo_name)
    time.sleep(1)
    list_repositories()

if __name__ == "__main__":
    main()

```

### automations.json
*Location:* `C:/Users/liamg/PycharmProjects/pythonProject/scheduler_tool\app`

```json
{
    "test_automation": {
        "task_id": "test_automation",
        "code": "print('Hello from automation123!')",
        "packages": [],
        "schedule": "* * * * *",
        "run_on_startup": true,
        "run_once": true
    },
    "test123": {
        "task_id": "test123",
        "code": "print(\"liam is cool!\")",
        "packages": [],
        "schedule": "* * * * *",
        "run_on_startup": false,
        "run_once": true
    },
    "jen is the best": {
        "task_id": "jen is the best",
        "code": "print(\"we love Jen xxx\")",
        "packages": [],
        "schedule": "* * * * *",
        "run_on_startup": false,
        "run_once": true
    },
    "find liam a job": {
        "task_id": "find liam a job",
        "code": "print(\"job now\")",
        "packages": [],
        "schedule": null,
        "run_on_startup": false,
        "run_once": false
    }
}
```

### index.html
*Location:* `C:/Users/liamg/PycharmProjects/pythonProject/scheduler_tool\app`

```python
<!DOCTYPE html>
<html>
<head>
    <title>Automation and Repo Manager</title>
    <style>
        /* Simple styles for table */
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            border: 1px solid #ccc;
            padding: 8px;
            text-align: left;
        }
        button {
            margin: 2px;
        }
        .modal {
            display: none;
            position: fixed;
            z-index: 1;
            padding-top: 60px;
            left: 0; top: 0; width: 100%; height: 100%;
            overflow: auto; background-color: rgba(0,0,0,0.4);
        }
        .modal-content {
            background-color: #fefefe;
            margin: auto; padding: 20px;
            border: 1px solid #888; width: 80%;
        }
        .close {
            color: #aaa; float: right;
            font-size: 28px; font-weight: bold;
        }
        .close:hover, .close:focus {
            color: black; text-decoration: none; cursor: pointer;
        }
    </style>
</head>
<body>

<h1>Automation and Repo Manager</h1>

<h2>Automations</h2>
<button onclick="showCreateAutomationModal()">Create New Automation</button>
<table id="automations-table">
    <thead>
        <tr>
            <th>Task ID</th>
            <th>Schedule</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
        <!-- Automations will be populated here -->
    </tbody>
</table>

<h2>Repositories</h2>
<button onclick="showCreateRepoModal()">Add New Repository</button>
<table id="repos-table">
    <thead>
        <tr>
            <th>Repo Name</th>
            <th>Repo URL</th>
            <th>Schedule</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
        <!-- Repos will be populated here -->
    </tbody>
</table>

<!-- Modals -->
<div id="automation-modal" class="modal">
    <div class="modal-content">
        <span class="close" onclick="closeAutomationModal()">&times;</span>
        <h2 id="automation-modal-title">Edit Automation</h2>
        <form id="automation-form">
            <input type="hidden" id="automation-task-id">
            <label for="automation-task-id-input">Task ID:</label><br>
            <input type="text" id="automation-task-id-input" name="task_id"><br>
            <label for="automation-code">Code:</label><br>
            <textarea id="automation-code" name="code" rows="10" cols="50"></textarea><br>
            <label for="automation-packages">Packages (comma-separated):</label><br>
            <input type="text" id="automation-packages" name="packages"><br>
            <label for="automation-schedule">Schedule (cron expression):</label><br>
            <input type="text" id="automation-schedule" name="schedule"><br>
            <label for="automation-run-on-startup">Run on Startup:</label>
            <input type="checkbox" id="automation-run-on-startup" name="run_on_startup"><br>
            <label for="automation-run-once">Run Once:</label>
            <input type="checkbox" id="automation-run-once" name="run_once"><br><br>
            <button type="button" onclick="submitAutomationForm()">Submit</button>
        </form>
    </div>
</div>

<div id="repo-modal" class="modal">
    <div class="modal-content">
        <span class="close" onclick="closeRepoModal()">&times;</span>
        <h2 id="repo-modal-title">Edit Repository</h2>
        <form id="repo-form">
            <input type="hidden" id="repo-name">
            <label for="repo-url">Repo URL:</label><br>
            <input type="text" id="repo-url" name="repo_url"><br>
            <label for="repo-schedule">Schedule (cron expression):</label><br>
            <input type="text" id="repo-schedule" name="schedule"><br>
            <label for="repo-run-on-startup">Run on Startup:</label>
            <input type="checkbox" id="repo-run-on-startup" name="run_on_startup"><br>
            <label for="repo-run-once">Run Once:</label>
            <input type="checkbox" id="repo-run-once" name="run_once"><br><br>
            <button type="button" onclick="submitRepoForm()">Submit</button>
        </form>
    </div>
</div>

<script>
    const apiBaseUrl = 'http://localhost:8000';

    function fetchAutomations() {
        fetch(`${apiBaseUrl}/automation/list_all/`)
            .then(response => response.json())
            .then(data => {
                console.log('Automations data:', data); // Debug statement
                const tbody = document.getElementById('automations-table').getElementsByTagName('tbody')[0];
                tbody.innerHTML = '';
                for (const [task_id, automation] of Object.entries(data)) {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${task_id}</td>
                        <td>${automation.schedule || ''}</td>
                        <td>
                            <button onclick="editAutomation('${task_id}')">Edit</button>
                            <button onclick="runAutomationOnce('${task_id}')">Run Once</button>
                            <button onclick="deleteAutomation('${task_id}')">Delete</button>
                        </td>
                    `;
                    tbody.appendChild(tr);
                }
            })
            .catch(error => console.error('Error fetching automations:', error)); // Error handling
    }

    function fetchRepos() {
        fetch(`${apiBaseUrl}/repo/list_all/`)
            .then(response => response.json())
            .then(data => {
                console.log('Repositories data:', data); // Debug statement
                const tbody = document.getElementById('repos-table').getElementsByTagName('tbody')[0];
                tbody.innerHTML = '';
                for (const [repo_name, repo] of Object.entries(data)) {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${repo_name}</td>
                        <td>${repo.repo_url}</td>
                        <td>${repo.schedule || ''}</td>
                        <td>
                            <button onclick="editRepo('${repo_name}')">Edit</button>
                            <button onclick="runRepoOnce('${repo_name}')">Run Once</button>
                            <button onclick="deleteRepo('${repo_name}')">Delete</button>
                        </td>
                    `;
                    tbody.appendChild(tr);
                }
            })
            .catch(error => console.error('Error fetching repositories:', error)); // Error handling
    }

    function editAutomation(task_id) {
        document.getElementById('automation-modal-title').innerText = 'Edit Automation';
        fetch(`${apiBaseUrl}/automation/${task_id}/get_code/`)
            .then(response => response.json())
            .then(data => {
                document.getElementById('automation-task-id').value = task_id;
                document.getElementById('automation-task-id-input').value = task_id;
                document.getElementById('automation-task-id-input').disabled = true;
                document.getElementById('automation-code').value = data.code || '';
                document.getElementById('automation-packages').value = (data.packages || []).join(', ');
                document.getElementById('automation-schedule').value = data.schedule || '';
                document.getElementById('automation-run-on-startup').checked = data.run_on_startup || false;
                document.getElementById('automation-run-once').checked = data.run_once || false;
                showAutomationModal();
            })
            .catch(error => console.error('Error fetching automation details:', error)); // Error handling
    }

    function editRepo(repo_name) {
        document.getElementById('repo-modal-title').innerText = 'Edit Repository';
        fetch(`${apiBaseUrl}/repo/list_all/`)
            .then(response => response.json())
            .then(repos => {
                const repo = repos[repo_name];
                document.getElementById('repo-name').value = repo_name;
                document.getElementById('repo-url').value = repo.repo_url || '';
                document.getElementById('repo-schedule').value = repo.schedule || '';
                document.getElementById('repo-run-on-startup').checked = repo.run_on_startup || false;
                document.getElementById('repo-run-once').checked = repo.run_once || false;
                showRepoModal();
            })
            .catch(error => console.error('Error fetching repository details:', error)); // Error handling
    }

    function showCreateAutomationModal() {
        document.getElementById('automation-modal-title').innerText = 'Create New Automation';
        document.getElementById('automation-task-id').value = '';
        document.getElementById('automation-task-id-input').value = '';
        document.getElementById('automation-task-id-input').disabled = false;
        document.getElementById('automation-code').value = '';
        document.getElementById('automation-packages').value = '';
        document.getElementById('automation-schedule').value = '';
        document.getElementById('automation-run-on-startup').checked = false;
        document.getElementById('automation-run-once').checked = false;
        showAutomationModal();
    }

    function showCreateRepoModal() {
        document.getElementById('repo-modal-title').innerText = 'Add New Repository';
        document.getElementById('repo-name').value = '';
        document.getElementById('repo-url').value = '';
        document.getElementById('repo-schedule').value = '';
        document.getElementById('repo-run-on-startup').checked = false;
        document.getElementById('repo-run-once').checked = false;
        showRepoModal();
    }

    function showAutomationModal() {
        document.getElementById('automation-modal').style.display = 'block';
    }

    function closeAutomationModal() {
        document.getElementById('automation-modal').style.display = 'none';
    }

    function showRepoModal() {
        document.getElementById('repo-modal').style.display = 'block';
    }

    function closeRepoModal() {
        document.getElementById('repo-modal').style.display = 'none';
    }

    function submitAutomationForm() {
        const task_id = document.getElementById('automation-task-id-input').value;
        const code = document.getElementById('automation-code').value;
        const packages = document.getElementById('automation-packages').value.split(',').map(s => s.trim()).filter(s => s);
        const schedule = document.getElementById('automation-schedule').value || null;
        const run_on_startup = document.getElementById('automation-run-on-startup').checked;
        const run_once = document.getElementById('automation-run-once').checked;

        fetch(`${apiBaseUrl}/automation/create_or_update/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_id, code, packages, schedule, run_on_startup, run_once })
        }).then(response => response.json())
        .then(data => {
            alert(data.message);
            closeAutomationModal();
            fetchAutomations();
        })
        .catch(error => console.error('Error submitting automation form:', error)); // Error handling
    }

    function submitRepoForm() {
        const repo_url = document.getElementById('repo-url').value;
        const schedule = document.getElementById('repo-schedule').value || null;
        const run_on_startup = document.getElementById('repo-run-on-startup').checked;
        const run_once = document.getElementById('repo-run-once').checked;

        fetch(`${apiBaseUrl}/repo/clone_and_run/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_url, schedule, run_on_startup, run_once })
        }).then(response => response.json())
        .then(data => {
            alert(data.message);
            closeRepoModal();
            fetchRepos();
        })
        .catch(error => console.error('Error submitting repository form:', error)); // Error handling
    }

    function runAutomationOnce(task_id) {
        fetch(`${apiBaseUrl}/automation/${task_id}/get_code/`)
            .then(response => response.json())
            .then(data => {
                const code = data.code;
                const packages = data.packages || [];
                fetch(`${apiBaseUrl}/automation/create_or_update/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ task_id, code, packages, schedule: data.schedule, run_on_startup: data.run_on_startup, run_once: true })
                }).then(response => response.json())
                .then(data => {
                    alert(`Automation ${task_id} run once.`);
                });
            })
            .catch(error => console.error('Error running automation once:', error)); // Error handling
    }

    function deleteAutomation(task_id) {
        if (confirm(`Are you sure you want to delete automation ${task_id}?`)) {
            fetch(`${apiBaseUrl}/automation/${task_id}/delete/`, {
                method: 'DELETE'
            }).then(response => response.json())
            .then(data => {
                alert(data.message);
                fetchAutomations();
            })
            .catch(error => console.error('Error deleting automation:', error)); // Error handling
        }
    }

    function runRepoOnce(repo_name) {
        fetch(`${apiBaseUrl}/repo/${repo_name}/re-pull/`, {
            method: 'POST'
        }).then(response => response.json())
        .then(data => {
            alert(`Repository ${repo_name} run once.`);
        })
        .catch(error => console.error('Error running repository once:', error)); // Error handling
    }

    function deleteRepo(repo_name) {
        if (confirm(`Are you sure you want to delete repository ${repo_name}?`)) {
            fetch(`${apiBaseUrl}/repo/${repo_name}/delete/`, {
                method: 'DELETE'
            }).then(response => response.json())
            .then(data => {
                alert(data.message);
                fetchRepos();
            })
            .catch(error => console.error('Error deleting repository:', error)); // Error handling
        }
    }

    window.onclick = function(event) {
        const automationModal = document.getElementById('automation-modal');
        const repoModal = document.getElementById('repo-modal');
        if (event.target == automationModal) {
            closeAutomationModal();
        }
        if (event.target == repoModal) {
            closeRepoModal();
        }
    }

    // Initial fetch
    fetchAutomations();
    fetchRepos();
</script>

</body>
</html>

```

### repos.json
*Location:* `C:/Users/liamg/PycharmProjects/pythonProject/scheduler_tool\app`

```json
{
    "test": {
        "repo_url": "https://github.com/liamgwallace/test.git",
        "schedule": "* * * * *",
        "run_on_startup": true,
        "run_once": false
    },
    "jen_cool": {
        "repo_url": "https://github.com/liamgwallace/jen_cool.git",
        "schedule": "* * * * *",
        "run_on_startup": false,
        "run_once": true
    }
}
```

### web_server.py
*Location:* `C:/Users/liamg/PycharmProjects/pythonProject/scheduler_tool\app`

```python
from flask import Flask, send_from_directory
import os

app = Flask(__name__)

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    app.run(port=5000, debug=True)

```

