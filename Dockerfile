FROM python:3.9-slim

WORKDIR /app

# Install git, curl, nano, and necessary packagess
RUN apt-get update && apt-get install -y git curl nano \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone your repository
RUN git clone https://github.com/liamgwallace/scheduler_tool.git .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose ports
EXPOSE 8000 5000

# Start the servers and pull updates from the repo
CMD ["sh", "-c", "while true; do git pull origin master; sleep 60; done & python app/api_server.py & python app/web_server.py & wait"]
