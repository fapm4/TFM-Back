import os
import ffmpeg
import re

def extract_audio(video_path):
	video_folder = os.path.dirname(video_path)
	video_name = os.path.basename(video_path)
	audio_name = os.path.splitext(video_name)[0] + '.mp3'
	audio_path = os.path.join(video_folder, audio_name)

	if os.path.exists(audio_path):
		os.remove(audio_path)

	input_file = ffmpeg.input(video_path)
	input_file.output(audio_path).run(overwrite_output=True, quiet=True)

	return audio_path

def get_mean_volume(audio_path):
	_, err = (
		ffmpeg.input(audio_path)
		.audio
		.filter('volumedetect')
		.output('null', f='null')
		.run(capture_stdout=True, capture_stderr=True)
	)

	for line in err.decode().split('\n'):
		if 'mean_volume:' in line:
			mean_db = float(line.strip().split('mean_volume:')[1].replace(' dB', ''))
			return mean_db
		
	return None

def detect_silences(audio_path, threshold=None, max_attempts=10):
	# Si no hay umbral, lo calculamos como media - 10
	mean_db = get_mean_volume(audio_path)
	if threshold is None:
		threshold = mean_db - 10

	threshold = float(threshold)

	for attempt in range(0, max_attempts):
		print(f"Intento {attempt + 1}: Threshold = {threshold} dB")

		err, out = (
			ffmpeg
			.input(audio_path)
			.filter('silencedetect', n=f'{threshold}dB', d=2)
			.output('null', f='null')
			.run(capture_stdout=True, capture_stderr=True)
		)

		if err:
			print(f"Error: {err.decode()}")
			# return [], threshold
	
		silence_lines = [
			line for line in out.decode().splitlines()
			if re.match(r'^\[silencedetect @', line)
		]

		if silence_lines:
			# Procesar líneas detectadas
			silence_periods = []
			for i in range(0, len(silence_lines) - 1, 2):
				start_match = re.search(r'silence_start: (\d+(?:\.\d+)?)', silence_lines[i])
				end_match = re.search(r'silence_end: (\d+\.\d+)', silence_lines[i + 1])

				if start_match and end_match:
					start = float(start_match.group(1))
					end = float(end_match.group(1))
					duration = end - start
					silence_periods.append({
						"start": start,
						"end": end,
						"duration": duration
					})
			if silence_periods:
				return silence_periods, threshold

		threshold += 2

	return [], threshold