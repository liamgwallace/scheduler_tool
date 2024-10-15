from flask import Flask, send_from_directory
import os
import socket

app = Flask(__name__)


@app.route('/')
def index():
    # Get the directory of the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Script working directory: {current_dir}")

    # Construct the full path to index.html
    index_file = os.path.join(current_dir, 'index.html')
    print(f"Index.html path: {index_file}")

    # Check if index.html exists
    if not os.path.exists(index_file):
        print("index.html not found")
        return "index.html not found", 404

    # Serve index.html from the current directory
    return send_from_directory(current_dir, 'index.html')


if __name__ == "__main__":
    # Get the machine's local IP address
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    port = "5000"

    # Print informative message
    print(f"##############################")
    print(f"Local address: http://{local_ip}:{port}")
    print(f"Machine hostname: {hostname}")

    # Run the Flask server
    app.run(host="0.0.0.0", port=port, debug=False)
