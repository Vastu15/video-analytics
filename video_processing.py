import streamlit as st
import os
from google import genai
from google.genai import types
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Set page config
st.set_page_config(
    layout="wide", page_title="Household Issues Analysis", page_icon="🔧"
)

# Initialize Google API client
# Try to get API key from environment variable first (for deployment), then from secrets (for local dev)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    try:
        GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    except:
        st.error(
            "Please set the GOOGLE_API_KEY environment variable or add it to .streamlit/secrets.toml"
        )
        st.stop()

client = genai.Client(api_key=GOOGLE_API_KEY)
# model_name = "gemini-2.0-flash-exp"
model_name = "gemini-2.5-pro"
fallback_model = "gemini-2.5-flash"  # Fallback model for when primary fails


def get_with_retries(url, params=None, retries=3, backoff_factor=0.5):
    """Make HTTP requests with retry logic"""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    resp = session.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp


def fetch_work_order_info(work_order_number):
    """Fetch work order information from the API"""
    url = "https://proposal-backend-uat.onengine.io/commserve/confirm-work-order-number"
    params = {"query": work_order_number}

    try:
        response = get_with_retries(url, params=params)
        data = response.json()

        if data.get("valid"):
            return {
                "success": True,
                "work_order_number": data.get("work_order_number"),
                "client_description": data.get("client_description"),
                "entity_name": data.get("entity_name"),
                "trades": data.get("trades", []),
            }
        else:
            return {"success": False, "error": "Invalid work order number"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def upload_file(file_path):
    """Upload a video or image file to Google AI"""
    uploaded_file = client.files.upload(file=file_path)
    with st.spinner("Uploading file..."):
        while uploaded_file.state == "PROCESSING":
            time.sleep(10)
            uploaded_file = client.files.get(name=uploaded_file.name)
        if uploaded_file.state == "FAILED":
            raise ValueError(uploaded_file.state)
    st.success(f"Uploaded {os.path.basename(file_path)}!")
    return uploaded_file


# BACKUP PROMPTS (Original working prompts)
BACKUP_USER_PROMPT = """Analyze the provided video(s) and/or image(s) to identify any household issues such as broken/leaking faucets, cracked doors, damp walls, damaged tiles, electrical issues, structural problems, etc. 

If multiple files are provided, correlate information across all media to provide a comprehensive assessment. Generate a structured technical report using the following format:

ISSUE TYPE:
[Single line description of the primary issue(s) identified]

LOCATION:
[Specific location details based on visual evidence from videos/images]

DETAILED ASSESSMENT:
[Thorough description of the damage/issue based on analysis of all provided media]

PHYSICAL CHARACTERISTICS:
- [Bullet points describing measurable/observable features from videos and images]
- [Include dimensions, patterns, extent of damage where visible]
- [Note any progression or variation visible across different media]

TECHNICAL IMPLICATIONS:
- [List of structural/functional impacts]
- [Safety concerns]
- [Security implications]
- [Environmental effects]

REPAIR REQUIREMENTS:
1. [Prioritized list of necessary repairs]
2. [Include safety measures required]
3. [Special considerations for repair work]

DOCUMENTATION NOTES:
- [Additional relevant observations from video/image analysis]
- [Areas needing further inspection]
- [Correlation between different media if multiple files provided]
"""

BACKUP_SYSTEM_PROMPT = """You are a professional property inspection assistant specializing in technical documentation. Your role is to analyze video and image content showing household issues and produce structured technical reports. You will receive one or more media files (videos and/or images) and must analyze all provided content comprehensively.

Follow these key principles:

1. MULTI-MEDIA ANALYSIS:
- Analyze all provided videos and images thoroughly
- Correlate information across different media types
- Use static images for detailed visual assessment
- Use video content for understanding motion, flow, or progressive damage
- Synthesize findings from all sources into a unified report

2. DOCUMENTATION STYLE:
- Maintain strictly professional and technical language
- Never use conversational phrases or first-person language
- Exclude greetings, introductions, and concluding remarks
- Avoid hedging words like "seems," "appears," or "might"

3. REPORT STRUCTURE:
- Use consistent hierarchical formatting
- Present information in clearly defined sections
- Employ bullet points for discrete observations
- Use numbered lists only for sequential procedures

4. TECHNICAL DETAILS:
- Prioritize measurable and observable characteristics
- Include specific measurements when visible
- Document patterns and extent of damage precisely
- Note spatial relationships and orientations
- Reference specific media when making observations

5. SAFETY AND COMPLIANCE:
- Always highlight immediate safety concerns
- Include relevant safety procedures for repairs
- Note potential code violations or compliance issues
- Document security implications

6. COMMUNICATION STANDARDS:
- Use industry-standard terminology
- Maintain objective, fact-based descriptions
- Exclude subjective assessments
- Omit speculative content

7. FOCUS AREAS:
- Structural elements
- Mechanical systems
- Electrical components
- Plumbing systems
- Environmental conditions
- Safety hazards
- Security vulnerabilities

FORMAT ALL OBSERVATIONS USING THE PRESCRIBED TEMPLATE STRUCTURE IN THE USER PROMPT."""


def process_media_files(
    uploaded_files, work_order_info=None, retry_count=0, max_retries=5
):
    """Process both video and image files for household issue analysis with retry logic"""

    # Build context from work order if available
    work_order_context = ""
    if work_order_info and work_order_info.get("success"):
        client_desc = work_order_info.get("client_description", "")
        trades = work_order_info.get("trades", [])
        work_order_num = work_order_info.get("work_order_number", "")

        work_order_context = f"""
WORK ORDER CONTEXT:
- Work Order Number: {work_order_num}
- Client Description: {client_desc}
- Relevant Trades: {', '.join(trades[:10])}{'...' if len(trades) > 10 else ''}
"""

    USER_PROMPT = f"""Analyze the provided video(s) and/or image(s) to identify any household issues such as broken/leaking faucets, cracked doors, damp walls, damaged tiles, electrical issues, structural problems, etc. 

{work_order_context}

If multiple files are provided, correlate information across all media to provide a comprehensive assessment. When work order context is provided, validate your findings against the client description and focus on trades relevant to the identified issues.

IMPORTANT: For technical measurements, only provide estimates when you can identify clear scale references in the media (such as standard doors ~80", electrical outlets ~4.5", floor tiles, fixtures, etc.). State your reference method and confidence level. Avoid speculative measurements without visual reference points.

For the General Description section, use terminology that US service providers, contractors, and maintenance professionals would recognize on work orders and service tickets. Examples:
- "Leaking faucet cartridge needs replacement" (not just "water leak")
- "HVAC ductwork has loose joints requiring sealing" (not just "air loss")  
- "Drywall patch and paint needed for wall damage" (not just "wall repair")
- "Tile grout requires cleaning and resealing" (not just "tile maintenance")
- "Electrical outlet replacement required" (not just "electrical issue")
- "Roof shingle replacement needed for weather damage" (not just "roof damage")
- "Caulk and weatherstrip door frame" (not just "door seal repair")
- "Snake drain line to clear blockage" (not just "drainage problem")
- "Replace wax ring and reseat toilet" (not just "toilet issue")

Generate a structured technical report using the following format:

WORK ORDER VALIDATION:
[If work order context provided, assess alignment between visual findings and client description]

ISSUE TYPE:
[Single line description of the primary issue(s) identified]

GENERAL DESCRIPTION:
[Explanation of the issue using common terminology familiar to US service providers, contractors, and maintenance professionals. Use industry-standard language that would appear on work orders, service tickets, or contractor estimates.]

LOCATION:
[Specific location details based on visual evidence from videos/images]

DETAILED ASSESSMENT:
[Thorough description of the damage/issue based on analysis of all provided media]

PHYSICAL CHARACTERISTICS:
- [Bullet points describing measurable/observable features from videos and images]
- [Include dimensions, patterns, extent of damage where visible]
- [Note any progression or variation visible across different media]

TECHNICAL MEASUREMENTS:
- [Estimated dimensions where scale references are available (e.g., relative to standard fixtures, doors, tiles)]
- [Area measurements for damage extent (approximate square footage/meters)]
- [Linear measurements for cracks, gaps, or affected spans]
- [Volume estimates for water damage, mold growth, or material loss]
- [Depth assessments for cracks, holes, or deterioration]
- [Angle measurements for structural misalignment or settling]
- [Count of affected units (tiles, panels, fixtures, etc.)]
- [Spacing measurements between structural elements]
- [Height/clearance measurements where safety is concerned]
- [Only include measurements that can be reasonably estimated from visual evidence with clear reference points]

TECHNICAL IMPLICATIONS:
- [List of structural/functional impacts]
- [Safety concerns]
- [Security implications]
- [Environmental effects]

RECOMMENDED TRADES:
[List specific trades from the available trades list that are most relevant to the identified issues]

REPAIR REQUIREMENTS:
1. [Prioritized list of necessary repairs]
2. [Include safety measures required]
3. [Special considerations for repair work]

DOCUMENTATION NOTES:
- [Additional relevant observations from video/image analysis]
- [Areas needing further inspection]
- [Correlation between different media if multiple files provided]
- [Alignment or discrepancies with client description if provided]
"""

    SYSTEM_PROMPT = f"""You are a professional property inspection assistant specializing in technical documentation. Your role is to analyze video and image content showing household issues and produce structured technical reports. You will receive one or more media files (videos and/or images) and must analyze all provided content comprehensively.

When work order information is provided, use it to enhance your analysis by:
- Validating visual findings against client descriptions
- Focusing on trades most relevant to identified issues
- Providing context-aware recommendations

Follow these key principles:

1. MULTI-MEDIA ANALYSIS:
- Analyze all provided videos and images thoroughly
- Correlate information across different media types
- Use static images for detailed visual assessment
- Use video content for understanding motion, flow, or progressive damage
- Synthesize findings from all sources into a unified report

2. WORK ORDER INTEGRATION:
- When available, reference client description to validate findings
- Prioritize trades relevant to identified issues
- Note any discrepancies between reported and observed issues

3. DOCUMENTATION STYLE:
- Maintain strictly professional and technical language
- Never use conversational phrases or first-person language
- Exclude greetings, introductions, and concluding remarks
- Avoid hedging words like "seems," "appears," or "might"

4. REPORT STRUCTURE:
- Use consistent hierarchical formatting
- Present information in clearly defined sections
- Employ bullet points for discrete observations
- Use numbered lists only for sequential procedures

5. TECHNICAL DETAILS:
- Prioritize measurable and observable characteristics
- Include specific measurements when visible with clear reference points
- Document patterns and extent of damage precisely
- Note spatial relationships and orientations
- Reference specific media when making observations
- Provide technical measurements using scale references (doors ~80", standard tiles, fixtures)
- Estimate dimensions, areas, and volumes only when reasonable references are visible
- Include quantitative assessments: counts, linear measurements, affected areas
- Use standard units (feet/inches for US, meters/cm for metric)
- Clearly state estimation methods and reference points used

6. SAFETY AND COMPLIANCE:
- Always highlight immediate safety concerns
- Include relevant safety procedures for repairs
- Note potential code violations or compliance issues
- Document security implications

7. COMMUNICATION STANDARDS:
- Use industry-standard terminology
- Maintain objective, fact-based descriptions
- Exclude subjective assessments
- Omit speculative content
- For General Description section: Use common US service provider language (HVAC, plumbing, electrical, flooring, roofing, etc.)
- Include terminology from work orders, service tickets, and contractor estimates
- Use trade-specific language familiar to maintenance professionals and contractors

8. FOCUS AREAS:
- Structural elements
- Mechanical systems
- Electrical components
- Plumbing systems
- Environmental conditions
- Safety hazards
- Security vulnerabilities

FORMAT ALL OBSERVATIONS USING THE PRESCRIBED TEMPLATE STRUCTURE IN THE USER PROMPT.{BACKUP_SYSTEM_PROMPT}"""

    # Prepare content parts for all uploaded files
    content_parts = []
    for uploaded_file in uploaded_files:
        content_parts.append(
            types.Part.from_uri(
                file_uri=uploaded_file.uri, mime_type=uploaded_file.mime_type
            )
        )

    try:
        with st.spinner("Analyzing media files..."):
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=content_parts,
                    ),
                    USER_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.0,
                ),
            )
            # Check if response has valid content
        if not response.text or response.text.strip() == "":
            # Handle empty response case - retry with main model first
            if retry_count < max_retries:
                st.warning(
                    f"⚠️ {model_name} returned empty response (attempt {retry_count + 1}/{max_retries + 1}). Retrying..."
                )
                st.write(f"Debug: Response object: {type(response)}")
                st.write(
                    f"Debug: Response candidates: {len(response.candidates) if hasattr(response, 'candidates') else 'None'}"
                )
                if hasattr(response, "candidates") and response.candidates:
                    candidate = response.candidates[0]
                    st.write(
                        f"Debug: Finish reason: {candidate.finish_reason if hasattr(candidate, 'finish_reason') else 'None'}"
                    )
                    st.write(
                        f"Debug: Content parts: {candidate.content.parts if hasattr(candidate, 'content') and candidate.content else 'None'}"
                    )

                st.info(
                    f"🔄 Retrying with {model_name} in {(retry_count + 1) * 2} seconds..."
                )
                time.sleep((retry_count + 1) * 2)  # Exponential backoff
                return process_media_files(
                    uploaded_files, work_order_info, retry_count + 1, max_retries
                )
            else:
                # After max retries with main model, try fallback model
                st.warning(
                    f"⚠️ {model_name} failed after {max_retries + 1} attempts. Trying fallback model ({fallback_model})..."
                )

                # Try with fallback model using the same detailed prompt
                fallback_response = client.models.generate_content(
                    model=fallback_model,
                    contents=[
                        types.Content(
                            role="user",
                            parts=content_parts,
                        ),
                        USER_PROMPT,
                    ],
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.0,
                    ),
                )

                if fallback_response.text and fallback_response.text.strip():
                    st.info(
                        f"✅ Analysis completed using fallback model ({fallback_model})"
                    )
                    return fallback_response.text
                else:
                    raise ValueError(
                        f"Both {model_name} and {fallback_model} returned empty responses after {max_retries + 1} attempts. This may indicate content policy restrictions or file processing issues."
                    )

        return response.text

    except Exception as e:
        error_message = str(e)

        # Check if it's a retryable error (500, rate limit, etc.)
        if any(
            code in error_message
            for code in ["500", "503", "429", "INTERNAL", "RATE_LIMIT"]
        ):
            if retry_count < max_retries:
                st.warning(
                    f"⚠️ API error with {model_name} (attempt {retry_count + 1}/{max_retries + 1}): {error_message}"
                )
                st.info(
                    f"🔄 Retrying with {model_name} in {(retry_count + 1) * 2} seconds..."
                )
                time.sleep((retry_count + 1) * 2)  # Exponential backoff
                return process_media_files(
                    uploaded_files, work_order_info, retry_count + 1, max_retries
                )
            else:
                # Try fallback model as last resort for server errors
                st.warning("🔄 Trying fallback model for server error...")
                try:
                    response = client.models.generate_content(
                        model=fallback_model,
                        contents=[
                            types.Content(
                                role="user",
                                parts=content_parts,
                            ),
                            USER_PROMPT,
                        ],
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            temperature=0.0,
                        ),
                    )

                    if response.text and response.text.strip():
                        st.info(
                            f"✅ Analysis completed using fallback model ({fallback_model})"
                        )
                        return response.text
                    else:
                        raise ValueError(
                            f"Fallback model ({fallback_model}) also returned empty response."
                        )

                except Exception as fallback_error:
                    st.error(
                        f"❌ Analysis failed with both models. Please try again later."
                    )
                    st.info(
                        "💡 This appears to be a widespread issue with Google's AI service:"
                    )
                    st.info("• Wait 10-15 minutes and try again")
                    st.info(
                        "• Check if your files are too large or in unsupported format"
                    )
                    st.info("• Try with fewer files at once")
                    st.info("• Contact support if the issue persists")
                    raise fallback_error
        else:
            # Non-retryable error
            st.error(f"❌ Analysis error: {error_message}")
            raise e


def save_uploaded_file(uploaded_file):
    """Save uploaded file to temp directory"""
    try:
        with open(os.path.join("temp", uploaded_file.name), "wb") as f:
            f.write(uploaded_file.getbuffer())
        return os.path.join("temp", uploaded_file.name)
    except:
        st.error("Error saving file")
        return None


def cleanup_files():
    """Clean up all uploaded files and reset session state"""
    try:
        # Delete local temp files
        temp_dir = "temp"
        if os.path.exists(temp_dir):
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    st.write(f"🗑️ Deleted local file: {filename}")

        # Delete files from Google AI
        if (
            hasattr(st.session_state, "uploaded_files")
            and st.session_state.uploaded_files
        ):
            for uploaded_file in st.session_state.uploaded_files:
                try:
                    client.files.delete(name=uploaded_file.name)
                    st.write(f"🗑️ Deleted from Google AI: {uploaded_file.name}")
                except Exception as e:
                    st.warning(
                        f"Could not delete {uploaded_file.name} from Google AI: {str(e)}"
                    )

        # Clear session state
        if hasattr(st.session_state, "uploaded_files"):
            del st.session_state.uploaded_files
        if hasattr(st.session_state, "analysis_result"):
            del st.session_state.analysis_result
        if hasattr(st.session_state, "files_ready_for_analysis"):
            del st.session_state.files_ready_for_analysis

        # Clear file uploader widgets by updating their keys
        if "file_uploader_key" not in st.session_state:
            st.session_state.file_uploader_key = 0
        st.session_state.file_uploader_key += 1

        st.success("✅ All files have been cleaned up successfully!")
        st.info("📤 Please upload new files to process again.")

    except Exception as e:
        st.error(f"❌ Error during cleanup: {str(e)}")


def show_cleanup_button():
    """Show cleanup button after analysis is complete"""
    if (
        hasattr(st.session_state, "analysis_result")
        and st.session_state.analysis_result
    ):
        st.markdown("---")
        if st.button(
            "🧹 Clear All Files & Reset", type="secondary", use_container_width=True
        ):
            cleanup_files()
            st.rerun()  # Refresh the app to show empty file uploaders


def display_media_files(file_paths):
    """Display uploaded media files in the UI"""
    for file_path in file_paths:
        file_ext = os.path.splitext(file_path)[1].lower()
        st.write(f"**{os.path.basename(file_path)}**")

        if file_ext in [".mp4", ".avi", ".mov", ".mkv"]:
            st.video(file_path)
        elif file_ext in [".jpg", ".jpeg", ".png", ".bmp", ".gif"]:
            st.image(file_path, use_container_width=True)

        st.write("---")


def main():
    # Custom CSS for better styling
    st.markdown(
        """
    <style>
    .main-header {
        text-align: center;
        background: linear-gradient(90deg, #4CAF50, #45a049);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 2rem;
    }
    .section-header {
        background-color: #f0f2f6;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        border-left: 4px solid #4CAF50;
        margin: 1rem 0;
    }
    .work-order-info {
        background-color: #e8f4f8;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #b3d9e6;
        margin: 1rem 0;
    }
    .upload-section {
        background-color: #f9f9f9;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # Main header
    st.markdown(
        '<div class="main-header"><h1>🔧 Property Issues Analysis & Inspection</h1><p>Advanced AI-powered analysis for work orders, videos, and photos</p></div>',
        unsafe_allow_html=True,
    )

    # Work Order Section
    st.markdown(
        '<div class="section-header"><h3>📋 Work Order Information</h3></div>',
        unsafe_allow_html=True,
    )

    col_wo1, col_wo2 = st.columns([1, 2])

    with col_wo1:
        work_order_number = st.text_input(
            "Enter Work Order Number:", placeholder="e.g., 146106-02"
        )
        fetch_button = st.button("🔍 Fetch Work Order", type="secondary")

    work_order_info = None
    if fetch_button and work_order_number:
        with st.spinner("Fetching work order information..."):
            work_order_info = fetch_work_order_info(work_order_number)
            st.session_state.work_order_info = work_order_info

    # Display work order info if available
    if hasattr(
        st.session_state, "work_order_info"
    ) and st.session_state.work_order_info.get("success"):
        work_order_info = st.session_state.work_order_info
        with col_wo2:
            st.markdown('<div class="work-order-info">', unsafe_allow_html=True)
            st.write(f"**Work Order:** {work_order_info.get('work_order_number')}")
            st.write(f"**Entity:** {work_order_info.get('entity_name')}")
            with st.expander("📝 Client Description"):
                st.write(work_order_info.get("client_description"))
            with st.expander(
                f"🔧 Available Trades ({len(work_order_info.get('trades', []))})"
            ):
                trades = work_order_info.get("trades", [])
                # Display trades in columns for better layout
                if trades:
                    for i in range(0, len(trades), 3):
                        trade_cols = st.columns(3)
                        for j, trade in enumerate(trades[i : i + 3]):
                            trade_cols[j].write(f"• {trade}")
            st.markdown("</div>", unsafe_allow_html=True)
    elif hasattr(
        st.session_state, "work_order_info"
    ) and not st.session_state.work_order_info.get("success"):
        with col_wo2:
            st.error(f"❌ {st.session_state.work_order_info.get('error')}")

    # Create main analysis columns
    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown(
            '<div class="section-header"><h3>📁 Media Upload & Analysis</h3></div>',
            unsafe_allow_html=True,
        )

        # Initialize file uploader key for cleanup functionality
        if "file_uploader_key" not in st.session_state:
            st.session_state.file_uploader_key = 0

        # File uploaders in styled sections
        st.markdown('<div class="upload-section">', unsafe_allow_html=True)
        st.write("**🎥 Upload Videos:**")
        uploaded_videos = st.file_uploader(
            "Choose video files",
            type=["mp4", "avi", "mov", "mkv"],
            accept_multiple_files=True,
            key=f"videos_{st.session_state.file_uploader_key}",
            help="Supported formats: MP4, AVI, MOV, MKV",
        )

        st.write("**📸 Upload Photos:**")
        uploaded_images = st.file_uploader(
            "Choose image files",
            type=["jpg", "jpeg", "png", "bmp", "gif"],
            accept_multiple_files=True,
            key=f"images_{st.session_state.file_uploader_key}",
            help="Supported formats: JPG, JPEG, PNG, BMP, GIF",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        # Combine all uploaded files
        all_uploaded_files = []
        if uploaded_videos:
            all_uploaded_files.extend(uploaded_videos)
        if uploaded_images:
            all_uploaded_files.extend(uploaded_images)

        if all_uploaded_files:
            # Create temp directory if it doesn't exist
            os.makedirs("temp", exist_ok=True)

            # Save all files and get their paths
            file_paths = []
            for uploaded_file in all_uploaded_files:
                file_path = save_uploaded_file(uploaded_file)
                if file_path:
                    file_paths.append(file_path)

            if file_paths:
                # Show current status
                files_uploaded = (
                    hasattr(st.session_state, "uploaded_files")
                    and st.session_state.uploaded_files
                    and len(st.session_state.uploaded_files) == len(file_paths)
                )

                if files_uploaded:
                    st.success(
                        f"✅ {len(file_paths)} file(s) uploaded and ready for analysis"
                    )
                else:
                    st.success(f"✅ {len(file_paths)} file(s) ready for upload")

                with st.expander(f"👁️ Preview Files ({len(file_paths)})"):
                    display_media_files(file_paths)

                # Enhanced analyze button
                analyze_button_text = "🚀 Analyze All Media"
                if hasattr(
                    st.session_state, "work_order_info"
                ) and st.session_state.work_order_info.get("success"):
                    analyze_button_text += " with Work Order Context"

                # Check if files are already uploaded and ready for analysis
                files_uploaded = (
                    hasattr(st.session_state, "uploaded_files")
                    and st.session_state.uploaded_files
                    and len(st.session_state.uploaded_files) == len(file_paths)
                )

                # Show different buttons based on upload status
                if not files_uploaded:
                    # Step 1: Upload files
                    if st.button(
                        "📤 Upload Files to AI",
                        type="primary",
                        use_container_width=True,
                    ):
                        try:
                            uploaded_files = []
                            progress_bar = st.progress(0)
                            status_text = st.empty()

                            for i, file_path in enumerate(file_paths):
                                status_text.text(
                                    f"Uploading {os.path.basename(file_path)}..."
                                )
                                uploaded_file = upload_file(file_path)
                                uploaded_files.append(uploaded_file)
                                progress_bar.progress((i + 1) / len(file_paths))

                            st.session_state.uploaded_files = uploaded_files
                            st.session_state.files_ready_for_analysis = True

                            status_text.empty()
                            progress_bar.empty()
                            st.success(
                                f"✅ {len(uploaded_files)} files uploaded successfully!"
                            )
                            st.info(
                                "👆 Now click 'Analyze Files' to generate your report."
                            )
                            st.rerun()

                        except Exception as e:
                            st.error(f"❌ Error uploading files: {str(e)}")
                            # Clear any partial uploads
                            if hasattr(st.session_state, "uploaded_files"):
                                del st.session_state.uploaded_files
                else:
                    # Step 2: Analyze uploaded files
                    st.success(
                        f"✅ {len(st.session_state.uploaded_files)} files ready for analysis"
                    )

                    if st.button(
                        f"🚀 {analyze_button_text}",
                        type="primary",
                        use_container_width=True,
                    ):
                        try:
                            status_text = st.empty()
                            status_text.text(
                                f"🔍 Analyzing files using {model_name}..."
                            )

                            # Get work order info if available
                            work_order_context = None
                            if hasattr(st.session_state, "work_order_info"):
                                work_order_context = st.session_state.work_order_info

                            # Process all files together
                            analysis_result = process_media_files(
                                st.session_state.uploaded_files, work_order_context
                            )

                            st.session_state.analysis_result = analysis_result

                            status_text.empty()
                            st.success(
                                f"🎉 Analysis completed for {len(st.session_state.uploaded_files)} files!"
                            )
                            st.info(
                                "👉 Check the 'Analysis Results' section on the right to view your report!"
                            )

                        except Exception as e:
                            error_message = str(e)
                            st.error(f"❌ Error during analysis: {error_message}")

                            # Provide specific guidance based on error type
                            if "empty response" in error_message.lower():
                                st.info("🤖 **AI Model Response Issue:**")
                                st.info(
                                    "• The AI model processed your request but returned no content"
                                )
                                st.info(
                                    "• This may be due to content policy restrictions"
                                )
                                st.info("• Try with different/smaller video files")
                                st.info(
                                    "• Ensure video content is appropriate for analysis"
                                )
                                st.info(
                                    "• Check if video files are corrupted or unreadable"
                                )
                            elif any(
                                code in error_message
                                for code in ["500", "503", "INTERNAL"]
                            ):
                                st.info("🔧 **Server Error Solutions:**")
                                st.info("• This is a temporary Google AI server issue")
                                st.info(
                                    "• Wait 2-3 minutes and try 'Analyze Files' again"
                                )
                                st.info(
                                    "• Your files are still uploaded - no need to re-upload"
                                )
                            elif (
                                "429" in error_message or "RATE_LIMIT" in error_message
                            ):
                                st.info("⏱️ **Rate Limit Solutions:**")
                                st.info("• Too many requests - wait 5-10 minutes")
                                st.info("• Try analyzing fewer files at once")
                            else:
                                st.info("💡 **General Solutions:**")
                                st.info("• Check your internet connection")
                                st.info("• Ensure files are not corrupted")
                                st.info("• Try with smaller file sizes")
                                st.info(
                                    "• Click 'Analyze Files' again (files remain uploaded)"
                                )
        else:
            st.info(
                "📤 Please upload at least one video or image file to begin analysis."
            )

    with col2:
        st.markdown(
            '<div class="section-header"><h3>📊 Analysis Results</h3></div>',
            unsafe_allow_html=True,
        )

        if (
            hasattr(st.session_state, "analysis_result")
            and st.session_state.analysis_result
        ):
            # Display results in a nice container
            with st.container():
                st.markdown("### 📋 Technical Inspection Report")
                st.markdown(st.session_state.analysis_result)

                # Add download button for the report
                report_filename = f"inspection_report_{work_order_number if work_order_number else 'analysis'}.txt"
                st.download_button(
                    label="💾 Download Report",
                    data=st.session_state.analysis_result,
                    file_name=report_filename,
                    mime="text/plain",
                )

                # Add cleanup functionality after results are shown
                st.markdown("---")
                st.info(
                    "💡 **Pro Tip**: Clean up files after downloading your report to free storage space and reset for new uploads."
                )

                col_cleanup1, col_cleanup2 = st.columns(2)
                with col_cleanup1:
                    if st.button(
                        "🗑️ Clean Up Files Now",
                        type="secondary",
                        use_container_width=True,
                        key="cleanup_results",
                    ):
                        cleanup_files()
                        st.rerun()
                with col_cleanup2:
                    if st.button(
                        "📥 Keep Files for Review",
                        type="tertiary",
                        use_container_width=True,
                        key="keep_files_results",
                    ):
                        st.info("Files retained. Upload new files to process again.")
        else:
            st.info(
                "📊 Upload media files and complete the analysis to see results here."
            )

            # Show sample report format
            with st.expander("📖 Sample Report Format"):
                st.code(
                    """
WORK ORDER VALIDATION:
[Alignment assessment]

ISSUE TYPE:
[Primary issues identified]

GENERAL DESCRIPTION:
[Common service provider terminology]

LOCATION:
[Specific locations]

DETAILED ASSESSMENT:
[Comprehensive description]

PHYSICAL CHARACTERISTICS:
- Observable features
- Measurements and patterns

TECHNICAL MEASUREMENTS:
- Estimated dimensions (using scale references)
- Area/volume calculations
- Linear measurements for damage extent
- Count of affected components

TECHNICAL IMPLICATIONS:
- Structural impacts
- Safety concerns

RECOMMENDED TRADES:
[Relevant trade specialties]

REPAIR REQUIREMENTS:
1. Priority repairs
2. Safety measures

DOCUMENTATION NOTES:
- Additional observations
- Further inspection needs
                """
                )


if __name__ == "__main__":
    main()
