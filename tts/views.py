from django.shortcuts import render
import pyttsx3
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
import time
import os

engine = pyttsx3.init()

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


from gtts import gTTS
def synthesize_description_to_audio(text, voice_id, filename, max_wait=5):
	tts = gTTS(text=text, lang='es')
	tts.save(filename)