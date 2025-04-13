from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
import pyttsx3
from django.conf import settings

engine = pyttsx3.init()

from .models import Video, Description

@csrf_exempt
def upload_file(req):
	try:
		if req.method == 'POST':
			if 'file' in req.FILES:
				file = req.FILES['file']
				
				option_selected = req.POST.get('optionSelected')
				threshold_selected = req.POST.get('thresholdSelected')
				threshold_value = None
				
				if threshold_selected == 'option5_thresh_manual':
					threshold_value = req.POST.get('thresholdValue')

				lang = None
				tone = None
				lang_name = None
				voice_id = None

				if option_selected != 'option1_grabar':
					lang = req.POST.get('idiomaSelected')
					tone = req.POST.get('tonoSelected')
					lang_name = req.POST.get('voiceSelected')
					voice_id = get_voice_id(req, lang, tone, lang_name)
				
				new_video = Video(
					video_file=file,
					title=file.name,
					option_selected=option_selected,
					threshold_selected=threshold_selected,
					threshold_value=threshold_value,
					lang=lang,
					tone=tone,
					lang_name=lang_name,
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
def text_to_speech(req, lang, tone, lang_name):
	voice_id = get_voice_id(req, lang, tone, lang_name)

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


def process_video(req, video_id):
	try:
		video = Video.objects.get(id=video_id)
		video_file = video.video_file.path
		option_selected = video.option_selected
		threshold_selected = video.threshold_selected
		threshold_value = video.threshold_value
		lang = video.lang
		tone = video.tone
		lang_name = video.lang_name
		voice_id = video.voice_id

		if option_selected == 'option1_grabar':
			return JsonResponse({'message': 'Processing video with recording option'}, status=200)
		
		elif option_selected == 'option2_analizar':
			return JsonResponse({'message': 'Processing video with analyze option'}, status=200)
		
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)
	
	return JsonResponse({'error': 'Invalid request'}, status=400)
