#2
FROM python:3.9-slim

WORKDIR /app

# Install git, curl, nano, and necessary packages
RUN apt-get update && apt-get install -y git curl nano \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone your repository
RUN git clone https://github.com/liamgwallace/scheduler_tool.git .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose ports
EXPOSE 8000 5000

# Start the servers and pull updates from the repo
CMD ["sh", "-c", "rm -rf /app/* && while true; do git -C /app pull origin master; sleep 60; done & python app/api_server.py & python app/web_server.py & wait"]
