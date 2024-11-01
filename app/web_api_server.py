import socket
from flask import Flask, send_from_directory, jsonify, request
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
import types
import threading

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
scheduler = BackgroundScheduler()
scheduler.start()

# Define base directory one level up from the current script working directory
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Define the directories for data, log, and repo
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
REPO_DIR = os.path.join(BASE_DIR, 'repos')
APP_DIR = os.path.join(BASE_DIR, 'app')

# Ensure these directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(REPO_DIR, exist_ok=True)

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # Set the root logger level to DEBUG so all messages are processed

# Create a single handler
file_handler = logging.FileHandler(os.path.join(LOG_DIR, 'logs.log'))
file_handler.setLevel(logging.DEBUG)  # Log all messages

# Create formatter and add it to the handler
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Add handler to the logger
logger.addHandler(file_handler)


# Define the log_print function
def log_print(message, level='INFO'):
    # Log levels: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    # Map the level to the logging module levels
    level_dict = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    # Get the numeric level
    numeric_level = level_dict.get(level.upper(), logging.INFO)
    # Log the message
    logger.log(numeric_level, message)
    # Print the message with the level
    print(f"{level}: {message}")


# Files to store automations and repositories
AUTOMATIONS_FILE = os.path.join(DATA_DIR, "automations.json")
REPOS_FILE = os.path.join(DATA_DIR, "repos.json")

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
            log_print(f"Unhandled exception: {str(e)}", level='ERROR')
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
        log_print(f"Failed to install package: '{package}'. Error: {str(e)}", level='ERROR')
        raise HTTPException(400, f"Failed to install package: '{package}'. Error: {str(e)}")


# Function to run the code (packages already installed)
def run_task(code, task_id):
    def task():
        try:
            # Create a new module to serve as the global namespace
            module = types.ModuleType(f'automation_{task_id}')
            module.__name__ = '__main__'  # Set __name__ to '__main__' for Flask
            module.__file__ = f'automation_{task_id}.py'  # Optional: Set a dummy __file__

            # Execute the automation code within the module's namespace
            exec(code, module.__dict__)

            log_print(f"Automation '{task_id}' successfully ran.", level='INFO')
        except Exception as e:
            log_print(f"Error running automation '{task_id}': {str(e)}", level='ERROR')

    # Create and start a new daemon thread for the automation task
    task_thread = threading.Thread(target=task, name=f'automation_thread_{task_id}', daemon=True)
    task_thread.start()


# Function to run repo task
def run_repo_task(repo_script, repo_name):
    def task():
        try:
            result = subprocess.run(
                [sys.executable, repo_script],
                check=True,
                shell=False
            )
            log_print(f"Executed '{repo_script}' from repository '{repo_name}'", level='INFO')
        except subprocess.CalledProcessError as e:
            log_print(f"Failed to execute '{repo_script}' from repository '{repo_name}': {str(e)}", level='ERROR')

    # Create and start a new daemon thread for the task
    task_thread = threading.Thread(target=task, name=f'repo_task_thread_{repo_name}', daemon=True)
    task_thread.start()


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
    repo_dir = os.path.join(REPO_DIR, repo_name)

    # Clone the repository if it doesn't exist
    if not os.path.exists(repo_dir):
        try:
            repo = git.Repo.clone_from(repo_url, repo_dir)
            log_print(f"Cloned repository '{repo_url}'", level='INFO')
            del repo  # Ensure the Repo object is deleted
        except Exception as e:
            log_print(f"Failed to clone repository '{repo_url}': {str(e)}", level='ERROR')
            raise HTTPException(500, f"Failed to clone repository: {str(e)}")
    else:
        # Pull the latest changes
        try:
            repo = git.Repo(repo_dir)
            origin = repo.remotes.origin
            origin.pull()
            log_print(f"Pulled latest changes for repository '{repo_url}'", level='INFO')
            del repo  # Ensure the Repo object is deleted
        except Exception as e:
            log_print(f"Failed to pull repository {repo_url}: {str(e)}", level='ERROR')
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
            log_print(f"Installed requirements for '{repo_name}'", level='INFO')
        except subprocess.CalledProcessError as e:
            log_print(f"Failed to install requirements for '{repo_name}': {str(e)}", level='ERROR')
            raise HTTPException(500, f"Failed to install requirements: {str(e)}")

    # Run main.py if it exists
    main_py = os.path.join(repo_dir, 'main.py')
    if not os.path.exists(main_py):
        log_print(f"No main.py found in {repo_name}", level='ERROR')
        raise HTTPException(404, f"No main.py found in '{repo_name}'")

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
        log_print(f"Scheduled repository '{repo_name}' with cron schedule: '{schedule}'", level='INFO')

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
@app.route('/')
def index():
    # Serve index.html from the current directory
    return send_from_directory(APP_DIR, 'index.html')


@app.route("/automation/create_or_update/", methods=["POST"])
@handle_exceptions
def create_or_update_automation():
    log_print(f"Endpoint '/automation/create_or_update/' triggered.", level='INFO')
    data = request.get_json()
    log_print(f"Payload: {data}", level='DEBUG')
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
            log_print(f"Removed existing automation job {task_id}", level='INFO')
        except JobLookupError:
            pass  # Job might not exist

    # Step 3: Schedule job with cron if schedule is provided
    if schedule:
        cron_params = parse_cron(schedule)
        trigger = CronTrigger(**cron_params)
        scheduler.add_job(run_task, trigger, id=task_id, args=[code, task_id])
        log_print(f"Scheduled automation '{task_id}' with cron schedule: '{schedule}'", level='INFO')

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
        "message": f"Automation '{task_id}' added or updated",
        "id": task_id
    }), 200


@app.route("/automation/list_all/", methods=["GET"])
@handle_exceptions
def list_automations():
    log_print(f"Endpoint '/automation/list_all/' triggered.", level='INFO')
    automations = load_automations()
    return jsonify(automations), 200


@app.route("/automation/<task_id>/get_code/", methods=["GET"])
@handle_exceptions
def get_automation_code(task_id):
    log_print(f"Endpoint '/automation/{task_id}/get_code/' triggered.", level='INFO')
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
    log_print(f"Endpoint '/automation/{task_id}/delete/' triggered.", level='INFO')
    automations = load_automations()
    if task_id not in automations:
        raise HTTPException(404, "Automation not found")

    try:
        scheduler.remove_job(task_id)
        log_print(f"Removed automation job '{task_id}'", level='INFO')
    except JobLookupError as e:
        log_print(f"Could not remove job '{task_id}': {str(e)}", level='WARNING')

    del automations[task_id]
    save_automations(automations)

    return jsonify({
        "status": "success",
        "message": f"Automation '{task_id}' removed"
    }), 200


# Routes for Repositories

@app.route("/repo/clone_and_run/", methods=["POST"])
@handle_exceptions
def clone_and_run_repo():
    log_print(f"Endpoint '/repo/clone_and_run/' triggered.", level='INFO')
    data = request.get_json()
    log_print(f"Payload: {data}", level='DEBUG')
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
        "message": f"Cloned and ran repo '{repo_url}'",
        "id": repo_name
    }), 200


@app.route("/repo/list_all/", methods=["GET"])
@handle_exceptions
def list_repos_route():
    log_print(f"Endpoint '/repo/list_all/' triggered.", level='INFO')
    repos = load_repos()
    return jsonify(repos), 200


@app.route("/repo/<repo_name>/delete/", methods=["DELETE"])
@handle_exceptions
def remove_repo(repo_name):
    log_print(f"Endpoint '/repo/{repo_name}/delete/' triggered.", level='INFO')
    repos = load_repos()
    if repo_name not in repos:
        raise HTTPException(404, "Repository not found")

    # Remove scheduled job
    try:
        scheduler.remove_job(repo_name)
        log_print(f"Removed scheduled job for repository '{repo_name}'", level='INFO')
    except JobLookupError:
        pass  # Job might not exist

    del repos[repo_name]
    save_repos(repos)

    # Remove the actual repo directory
    repo_dir = os.path.join(REPO_DIR, repo_name)
    if os.path.exists(repo_dir):
        try:
            shutil.rmtree(repo_dir, onerror=remove_readonly)
            log_print(f"Removed repository directory '{repo_dir}'", level='INFO')
        except Exception as e:
            log_print(f"Failed to remove repository directory '{repo_dir}': {str(e)}", level='ERROR')
            raise HTTPException(500, f"Failed to remove repository directory: {str(e)}")

    return jsonify({
        "status": "success",
        "message": f"Repository '{repo_name}' removed"
    }), 200


@app.route("/repo/<repo_name>/re-pull/", methods=["POST"])
@handle_exceptions
def re_pull_repo(repo_name):
    log_print(f"Endpoint '/repo/{repo_name}/re-pull/' triggered.", level='INFO')
    repos = load_repos()
    if repo_name not in repos:
        raise HTTPException(404, "Repository not found")

    repo_data = repos[repo_name]
    repo_url = repo_data["repo_url"]
    schedule = repo_data.get("schedule")
    run_on_startup = repo_data.get("run_on_startup", False)
    run_once = repo_data.get("run_once", False)

    # Re-clone or pull the repository
    repo_dir = os.path.join(REPO_DIR, repo_name)
    if os.path.exists(repo_dir):
        try:
            repo = git.Repo(repo_dir)
            origin = repo.remotes.origin
            origin.pull()
            log_print(f"Re-pulled repository '{repo_url}'", level='INFO')
            del repo  # Ensure the Repo object is deleted
        except Exception as e:
            log_print(f"Failed to re-pull repository '{repo_url}': {str(e)}", level='ERROR')
            raise HTTPException(500, f"Failed to re-pull repository: {str(e)}")
    else:
        # If repo directory doesn't exist, clone it
        clone_and_run(repo_url, schedule, run_on_startup, run_once)
        return jsonify({
            "status": "success",
            "message": f"Cloned and ran repo '{repo_url}'",
            "id": repo_name
        }), 200

    # Schedule with cron if schedule is provided
    main_py = os.path.join(repo_dir, 'main.py')
    if not os.path.exists(main_py):
        log_print(f"No main.py found in '{repo_name}' after re-pull", level='ERROR')
        raise HTTPException(404, f"No main.py found in '{repo_name}' after re-pull")

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
        log_print(f"Rescheduled repository '{repo_name}' with cron schedule: '{schedule}'", level='INFO')

    # Run immediately if run_once is True
    if run_once:
        run_repo_task(main_py, repo_name)

    return jsonify({
        "status": "success",
        "message": f"Re-pulled and executed repo '{repo_name}'"
    }), 200

@app.route("/logs", methods=["GET"])
def get_logs():
    log_file_path = os.path.join(LOG_DIR, 'logs.log')
    if os.path.exists(log_file_path):
        with open(log_file_path, 'r') as f:
            logs_content = f.read()
        return jsonify({"logs": logs_content}), 200
    return jsonify({"logs": "Log file not found"}), 404

# Load and run repositories and automations on startup
def startup_event():
    # Load and run repositories
    repos = load_repos()
    for repo_name, repo_data in repos.items():
        repo_url = repo_data["repo_url"]
        schedule = repo_data.get("schedule")
        run_on_startup = repo_data.get("run_on_startup", False)
        run_once = False  # Avoid running twice on startup
        log_print(
            f"Cloning and loading repo '{repo_name}' - '{repo_url}', schedule: '{schedule}', run_on_startup: '{run_on_startup}'",
            level='INFO')
        try:
            clone_and_run(
                repo_url,
                schedule,
                run_on_startup,
                run_once
            )
            # Run immediately if run_on_startup is True
            if run_on_startup:
                main_py = os.path.join(REPO_DIR, repo_name, 'main.py')
                if os.path.exists(main_py):
                    run_repo_task(main_py, repo_name)
        except Exception as e:
            log_print(f"Failed to run repository '{repo_name}' on startup: {str(e)}", level='ERROR')
    # Load and run automations
    automations = load_automations()
    for task_id, automation_data in automations.items():
        code = automation_data.get("code")
        packages = automation_data.get("packages", [])
        schedule = automation_data.get("schedule")
        run_on_startup = automation_data.get("run_on_startup", False)
        run_once = False  # Avoid running twice on startup
        log_print(f"Loading code '{task_id}', schedule: '{schedule}', run_on_startup: '{run_on_startup}'", level='INFO')

        # Install packages
        install_packages(packages)

        # Schedule job with cron if schedule is provided
        if schedule:
            cron_params = parse_cron(schedule)
            trigger = CronTrigger(**cron_params)
            scheduler.add_job(run_task, trigger, id=task_id, args=[code, task_id])

        # Run immediately if run_on_startup is True
        if run_on_startup:
            run_task(code, task_id)


if __name__ == "__main__":
    # Get the machine's local IP address
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    port = "8000"

    # Print informative message
    log_print(f"##############################", level='INFO')
    log_print(f"Local address: http://{local_ip}:{port}", level='INFO')
    log_print(f"Machine hostname: '{hostname}'", level='INFO')

    startup_event()

    # Run the Flask server
    app.run(host="0.0.0.0", port=port, debug=False)
