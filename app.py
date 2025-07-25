import torch.cuda
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from TTS.api import TTS
import os
import hashlib
import threading
import uuid

app = Flask(__name__)
CORS(app)

# 1. Rate Limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# In-memory job store for async tasks
jobs = {}

device = "cpu"

if torch.cuda.is_available():
    print("Using GPU for TTS processing.")
    device = "cuda"
else:
    print("Using CPU for TTS processing.")

# Init TTS
print("Initializing TTS...")
tts = TTS(model_name="tts_models/en/vctk/vits", progress_bar=False).to(device=device)
# If you have a GPU, you can uncomment the following line:
# tts.to('cuda')
print("TTS initialized.")

def get_request_hash(text, speaker, speed, use_ssml):
    """Create a unique hash for the request parameters."""
    params = f"{text}{speaker}{speed}{use_ssml}"
    return hashlib.md5(params.encode('utf-8')).hexdigest()

@app.route("/api/synthesize", methods=["POST"])
@limiter.limit("15 per minute")
def api_synthesize():
    data = request.json
    text = data.get("text", "")
    speaker = data.get('speaker', tts.speakers[0])
    speed = data.get('speed', 1.0)
    use_ssml = data.get('ssml', False)

    if not text:
        return "No text provided", 400

    # 2. Audio Caching
    request_hash = get_request_hash(text, speaker, speed, use_ssml)
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    file_path = os.path.join(output_dir, f"{request_hash}.wav")

    if os.path.exists(file_path):
        print(f"Serving cached audio for hash: {request_hash}")
        return send_file(file_path, mimetype="audio/wav")

    print(f"Synthesizing text: '{text}' at speed: {speed}")
    tts.tts_to_file(text=text, file_path=file_path, speaker=speaker, speed=speed, ssml=use_ssml)
    print(f"Audio saved to {file_path}")

    return send_file(file_path, mimetype="audio/wav")

@app.route("/api/speakers", methods=["GET"])
def api_speakers():
    """Endpoint to list available speakers"""
    return jsonify(tts.speakers)

# 3. Async Processing
def tts_task(job_id, file_path, text, speaker, speed, use_ssml):
    """The background task for TTS synthesis."""
    try:
        jobs[job_id]['status'] = 'processing'
        print(f"Starting async job {job_id}")
        tts.tts_to_file(text=text, file_path=file_path, speaker=speaker, speed=speed, ssml=use_ssml)
        jobs[job_id]['status'] = 'complete'
        print(f"Async job {job_id} complete. File at {file_path}")
    except Exception as e:
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)
        print(f"Async job {job_id} failed: {e}")

@app.route("/api/synthesize-async", methods=["POST"])
def api_synthesize_async():
    data = request.json
    text = data.get("text", "")
    speaker = data.get('speaker', tts.speakers[0])
    speed = data.get('speed', 1.0)
    use_ssml = data.get('ssml', False)

    if not text:
        return "No text provided", 400

    request_hash = get_request_hash(text, speaker, speed, use_ssml)
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    file_path = os.path.join(output_dir, f"{request_hash}.wav")

    if os.path.exists(file_path):
        print(f"Serving cached audio for async request: {request_hash}")
        job_id = str(uuid.uuid4())
        jobs[job_id] = {'status': 'complete', 'file_path': file_path}
        return jsonify({"job_id": job_id, "status": "complete", "cached": True})

    job_id = str(uuid.uuid4())
    jobs[job_id] = {'status': 'pending', 'file_path': file_path}
    
    thread = threading.Thread(target=tts_task, args=(job_id, file_path, text, speaker, speed, use_ssml))
    thread.start()

    return jsonify({"job_id": job_id, "status": "pending"}), 202

@app.route("/api/status/<job_id>", methods=["GET"])
def api_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    response = {"job_id": job_id, "status": job['status']}
    if job['status'] == 'complete':
        response['url'] = f'/api/audio/{job_id}'
    elif job['status'] == 'failed':
        response['error'] = job.get('error')
    return jsonify(response)

@app.route("/api/audio/<job_id>", methods=["GET"])
def api_audio(job_id):
    job = jobs.get(job_id)
    if not job or job['status'] != 'complete':
        return jsonify({"error": "Job not found or not complete"}), 404
    
    file_path = job.get('file_path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "Audio file not found"}), 404

    return send_file(file_path, mimetype="audio/wav")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002) 