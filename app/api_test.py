import requests
import time

# Base URL of the API
BASE_URL = "http://localhost:8000"
BASE_URL = "http://192.168.8.146:8000"

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
