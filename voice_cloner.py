import torch
from TTS.api import TTS

# Select device (GPU if available)
device = "cuda" if torch.cuda.is_available() else "cpu"

if torch.cuda.is_available():
    print("Using GPU for TTS processing.")
else:
    print("Using CPU for TTS processing.")

# Initialize the multi-speaker voice cloning model
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=True).to(device)

# Your new script text to synthesize
script_text = """
This is a sample script for voice cloning using the TTS library.
"""


speaker_wav_path = 'reference_audio.wav'
file_path = script_text[:10] + "_cloned_speech.wav"

# Generate speech with voice cloning
tts.tts_to_file(
    text=script_text,
    speaker_wav=speaker_wav_path,
    language="en",
    file_path= file_path,
)

print("Audio generated: ", file_path)
