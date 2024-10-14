FROM python:3.9-slim

WORKDIR /app

# Install git and necessary packages
RUN apt-get update && apt-get install -y git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone the repository
RUN git clone https://github.com/liamgwallace/scheduler_tool .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose ports for both API and Web servers
EXPOSE 8000 5000

# Start both servers on container start
CMD ["sh", "-c", "python app/api_server.py & python app/web_server.py"]