from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
import pyttsx3
import os
from django.conf import settings
from django.core.files.storage import default_storage
import ffmpeg
import re
from datetime import timedelta
import av
import torch
import numpy as np
from transformers import LlavaNextVideoProcessor, LlavaNextVideoForConditionalGeneration

# model_id = "llava-hf/LLaVA-NeXT-Video-7B-hf"

# model = LlavaNextVideoForConditionalGeneration.from_pretrained(
#     model_id, 
#     torch_dtype=torch.float16, 
#     low_cpu_mem_usage=True, 
# ).to('cpu')

# processor = LlavaNextVideoProcessor.from_pretrained(model_id)


engine = pyttsx3.init()

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
					voice_id = req.POST.get('voiceSelected')
				
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

	
def get_packages(req, json_response=True):
	try:
		voices = engine.getProperty('voices')
		list_voices = []
		for voice in voices:
			name = voice.name
			languages = voice.languages
			voice_id = voice.id
			gender = "Neutro" if voice.gender == 'VoiceGenderNeuter' else 'Mujer'

			obj = {
				'name': name,
				'languages': languages,
				'voice_id': voice_id,
				'gender': gender
			}

			list_voices.append(obj)
			
		voices = list_voices

		if json_response:
			return JsonResponse({"voices": voices}, status=200)
		else:
			return voices

	except Exception as e:
			print(f"Error: {e}")
			return JsonResponse({'error': str(e)}, status=500)
	
def get_voices(req, lang, tone, json_response=False):
	try:
		voices = get_packages(req, json_response=False)
		filtered_voices = []

		tone = 'Neutro' if tone == 'Neutro' else 'Mujer'

		for voice in voices:
			if lang in voice['languages'] and tone in voice['gender']:
				filtered_voices.append(voice)

		return JsonResponse({"voices": filtered_voices}, status=200)
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)
	
def get_voice_id(req, lang, tone, lang_name):
	voices = get_packages(req, json_response=False)
	tone = 'Neutro' if tone == 'Neutro' else 'Mujer'
	for voice in voices:
		if lang in voice['languages'] and tone in voice['gender'] and lang_name in voice['name']:
			voice_id = voice['voice_id']
			return voice_id
		
@csrf_exempt
def text_to_speech(req, voice_id):
	try:
		if req.method == 'POST':
			text = req.body.decode('utf-8')
			text = json.loads(text).get('text', '')
			engine.setProperty('voice', voice_id)

			engine.say(text)
			engine.runAndWait()
			engine.endLoop()
			engine.stop()
			
			return JsonResponse({'message': 'Text to speech conversion successful', 'voice_id': voice_id}, status=200)
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

def detect_silences(audio_path, threshold):
	mean_db = get_mean_volume(audio_path)
	
	if threshold:
		threshold = float(threshold)
	else:
		threshold = mean_db - 10

	print(f"Threshold: {threshold}")
	print(audio_path)
	err, out = (
		ffmpeg
		.input(audio_path)
		.filter('silencedetect', n=f'{threshold}dB', d=2)
		.output('null', f='null')
		.run(capture_stdout=True, capture_stderr=True)
	)

	silence_periods = []

	silence_lines = [
		line for line in out.decode().splitlines()
		if re.match(r'^\[silencedetect @', line)
	]

	for i in range(0, len(silence_lines), 2):
		start_line = silence_lines[i]
		end_line = silence_lines[i + 1]

		print('Start', start_line)
		print('End', end_line)

		start_match = re.search(r'silence_start: (\d+(?:\.\d+)?)', start_line)
		end_match = re.search(r'silence_end: (\d+\.\d+)', end_line)

		if start_match and end_match:
			start = float(start_match.group(1))
			end = float(end_match.group(1))

			duration = end - start
			silence_periods.append({
				"start": start,
				"end": end,
				"duration": duration
			})
	
	return silence_periods

def get_silences(req, video_id):
	try:
		video = Video.objects.get(id=video_id)
		video_file = video.video_file.path
		video_path = os.path.join(settings.MEDIA_URL, str(video_file))

		new_audio_path = extract_audio(video_path)
		video.audio_file = new_audio_path
		video.save()

		threshold = video.threshold_selected

		if threshold == 'option5_thresh_manual':
			threshold = video.threshold_value
		else:
			threshold = None
	
		### Detectar silencio
		silences = detect_silences(new_audio_path, threshold=threshold)

		if not silences or len(silences) == 0:
			return JsonResponse({'error': 'No silences detected'}, status=200)
		
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
			}
			for d in Description.objects.filter(video=video)
		]

		return JsonResponse({'silences': silences, 'descriptions': descriptions}, status=200)
	
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)