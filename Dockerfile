# Use a slim version of Python 3.9 as the base image
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Install required packages (git, curl, nano)
RUN apt-get update && \
    apt-get install -y git curl nano && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Clone the GitHub repository
RUN git clone https://github.com/liamgwallace/scheduler_tool.git .

# Copy requirements.txt to the working directory
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the necessary ports
EXPOSE 8000 5000

# Copy the entire application code from the cloned repository
COPY app/ ./app/

# Start the application servers
CMD ["sh", "-c", "echo 'Running version 0.01' && python -u app/web_api_server.py & wait"]


