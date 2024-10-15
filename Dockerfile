FROM python:3.9-slim
WORKDIR /

# Install git and necessary packages
RUN apt-get update && apt-get install -y git curl nano \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Expose ports for both API and Web servers
EXPOSE 8000 5000

# Ensure the latest updates are pulled when the container starts
CMD sh -c "\
  if [ ! -d .git ]; then \
    git clone https://github.com/liamgwallace/scheduler_tool.git .; \
  else \
    git pull; \
  fi && \
  pip install --no-cache-dir -r requirements.txt && \
  python app/api_server.py & \
  python app/web_server.py & \
  wait \
"