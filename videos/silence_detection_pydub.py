import os
from pydub import AudioSegment, silence

def extract_audio(video_path):
    """
    Extrae el audio de un video y lo guarda como .wav para análisis más rápido.
    """
    video_folder = os.path.dirname(video_path)
    video_name = os.path.basename(video_path)
    audio_name = os.path.splitext(video_name)[0] + '.wav'
    audio_path = os.path.join(video_folder, audio_name)

    if os.path.exists(audio_path):
        os.remove(audio_path)

    # Extraer audio como WAV (mejor para análisis)
    audio = AudioSegment.from_file(video_path)
    audio.export(audio_path, format="wav")

    return audio_path

def get_mean_volume(audio_segment):
    """
    Retorna el volumen medio en dBFS de un objeto AudioSegment.
    """
    return audio_segment.dBFS  # dB Full Scale

def detect_silences(audio_segment, threshold=None, min_silence_len=2000, max_attempts=10):
    """
    Detecta silencios en el audio, aumentando progresivamente el umbral si no encuentra nada.
    """
    mean_db = audio_segment.dBFS

    if threshold is None:
        threshold = mean_db - 10  # Umbral inicial si no se pasa

    for attempt in range(max_attempts):
        print(f"Intento {attempt + 1}: Threshold = {threshold:.2f} dB")

        silent_ranges = silence.detect_silence(
            audio_segment,
            min_silence_len=min_silence_len,
            silence_thresh=threshold
        )

        if silent_ranges:
            silence_periods = []
            for start_ms, end_ms in silent_ranges:
                silence_periods.append({
                    "start": start_ms / 1000,
                    "end": end_ms / 1000,
                    "duration": (end_ms - start_ms) / 1000
                })
            return silence_periods, threshold

        threshold += 2  # Más sensible en cada intento

    return [], threshold
