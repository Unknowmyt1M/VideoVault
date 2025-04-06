#!/bin/bash

# This script is used by Vercel to setup the Python environment during build

echo "Setting up application for Vercel deployment..."
echo "Current directory: $(pwd)"
echo "Python version: $(python --version)"

# Make this file executable
chmod +x build_vercel.sh

# Create necessary directories if they don't exist
mkdir -p data
mkdir -p instance

# Create an empty .env file as Vercel will use environment variables
touch .env

echo "Setup complete!"
