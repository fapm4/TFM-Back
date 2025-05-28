from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
import os
from django.conf import settings
from django.http import JsonResponse
from datetime import timedelta
import ffmpeg
import re

# Create your views here.
from .models import Video, Description

def delete_existent(filename):
	record = Video.objects.filter(title=filename)
	if record.exists():
		video = record.first()
		video_file_path = os.path.join(settings.MEDIA_ROOT, str(video.video_file))
		if os.path.exists(video_file_path):
			os.remove(video_file_path)
		video.delete()

@csrf_exempt
def upload_file(req):
	try:
		if req.method == 'POST':
			if 'file' in req.FILES:
				file = req.FILES['file']
				
				delete_existent(file.name)

				option_selected = req.POST.get('optionSelected')
				threshold_selected = req.POST.get('thresholdSelected')
				threshold_value = None
				
				if threshold_selected == 'option5_thresh_manual':
					threshold_value = req.POST.get('thresholdValue')

				lang = None
				tone = None
				voice_id = None

				if option_selected != 'option1_grabar':
					lang = req.POST.get('idiomaSelected')
					tone = req.POST.get('tonoSelected')
					voice_id = req.POST.get('voice_id')
				
				new_video = Video(
					video_file=file,
					title=file.name,
					option_selected=option_selected,
					threshold_selected=threshold_selected,
					threshold_value=threshold_value,
					lang=lang,
					tone=tone,
					voice_id=voice_id
				)
				new_video.save()

				return JsonResponse({'message': 'File uploaded successfully', 'video_id': new_video.id}, status=200)
			
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)
	
	return JsonResponse({'error': 'Invalid request'}, status=400)

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

def detect_silences(audio_path, threshold=None, max_attempts=5):
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


def get_silences(req, video_id): 
	try:
		video = Video.objects.get(id=video_id)
		video_file = video.video_file.path
		video_path = os.path.join(settings.MEDIA_URL, str(video_file))

		new_audio_path = extract_audio(video_path)
		video.audio_file = new_audio_path
		video.save()

		## Umbral inicial
		threshold = video.threshold_value if video.threshold_selected == 'option5_thresh_manual' else None
	
		## Detectar silencio (con reintentos)
		silences, final_threshold = detect_silences(new_audio_path, threshold=threshold, max_attempts=5)

		if not silences:
			return JsonResponse({'error': 'No silences detected'}, status=200)

		# Guardar silencios
		Description.objects.bulk_create([
			Description(
				video=video,
				start_at=timedelta(seconds=s['start']),
				end_at=timedelta(seconds=s['end']),
				duration=timedelta(seconds=s['duration'])
			) for s in silences
		])

		descriptions = [
			{
				'start_at': str(d.start_at),
				'end_at': str(d.end_at),
				'duration': str(d.duration),
				'video_id': d.video.id,
				'description_id': d.id,
				'threshold': final_threshold,
			}
			for d in Description.objects.filter(video=video)
		]

		return JsonResponse({
			'descriptions': descriptions,
			'file_name': video.title,
			'file_url': req.build_absolute_uri(video.video_file.url),
			'video_id': video.id,
		}, status=200)

	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)
