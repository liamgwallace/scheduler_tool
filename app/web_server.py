from flask import Flask, send_from_directory
import os
import socket

app = Flask(__name__)

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

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