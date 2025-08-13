#!/bin/bash

# Create necessary directories
mkdir -p temp
mkdir -p downloaded_files

# Start Streamlit app
streamlit run video_processing.py --server.port $PORT --server.address 0.0.0.0 --server.headless true --server.fileWatcherType none 