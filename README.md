# Video Processing Streamlit App

A Streamlit application for analyzing household issues in videos using Google's Gemini AI.

## Features

- Upload and analyze video files
- AI-powered identification of household issues
- Work order integration
- Detailed technical reports

## Deployment on Render.com

### Prerequisites

1. A GitHub repository containing this code
2. A Render.com account
3. Google AI API key

### Steps

1. **Push to GitHub**: Ensure your code is in a GitHub repository

2. **Create a new Web Service on Render**:
   - Go to your Render dashboard
   - Click "New" → "Web Service"
   - Connect your GitHub repository
   - Select this repository

3. **Configure the service**:
   - **Name**: `video-processing-app` (or your preferred name)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `streamlit run video_processing.py --server.port $PORT --server.address 0.0.0.0 --server.headless true --server.fileWatcherType none`

4. **Set Environment Variables**:
   - Add `GOOGLE_API_KEY` with your Google AI API key value

5. **Deploy**: Click "Create Web Service"

### Environment Variables

- `GOOGLE_API_KEY`: Your Google AI Studio API key

### Local Development

```bash
pip install -r requirements.txt
streamlit run video_processing.py
```

## Usage

1. Enter a work order number (optional)
2. Upload a video file
3. Wait for AI analysis
4. Review the generated technical report 