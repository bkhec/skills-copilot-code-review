#!/bin/bash

# Install MongoDB
# Remove old GPG key if it exists
sudo rm -f /etc/apt/trusted.gpg.d/mongodb-server-7.0.gpg
sudo rm -f /etc/apt/sources.list.d/mongodb-org-7.0.list

# Add MongoDB GPG key with insecure option
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/mongodb-server-7.0.gpg

# Add repository without signature verification due to SHA1 deprecation
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

# Update and install with options to bypass signature issues
sudo apt-get update --allow-insecure-repositories
sudo apt-get install -y --allow-unauthenticated mongodb-org

# Create necessary directories and set permissions
sudo mkdir -p /data/db
sudo chown -R $(whoami):$(whoami) /data/db
