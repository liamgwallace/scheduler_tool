# Use Python 3.9 slim image as the base
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Install git and any necessary packages
RUN apt-get update && apt-get install -y git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone the repository initially
RUN git clone https://github.com/liamgwallace/scheduler_tool.git .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose ports for both API and Web servers
EXPOSE 8000 5000

# Ensure the latest updates are pulled when the container starts
CMD ["sh", "-c", "git -C /app pull && python app/api_server.py & python app/web_server.py"]
