from django.shortcuts import render
import pyttsx3
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
import time
import os
from gtts import gTTS
from playsound import playsound
import tempfile
from gtts.lang import tts_langs

def get_voices(req):
	try:
		langs = tts_langs()

		json_response = {}

		for code, name in langs.items():
			json_response[code] = name

		print(f"Available languages: {json_response}")

	except Exception as e:
			print(f"Error: {e}")
			return JsonResponse({'error': str(e)}, status=500)
	
@csrf_exempt
def text_to_speech(req, voice_id):
	try:
		if req.method == 'POST':
			print(f"Received request with voice_id: {voice_id}")
			text = req.body.decode('utf-8')
			text = json.loads(text).get('text', '')
			
			tts = gTTS(text=text, lang=voice_id, slow=False)

			with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
				tts.save(fp.name)
				playsound(fp.name)
			
			os.unlink(fp.name)
			
			return JsonResponse({'message': 'Text to speech conversion successful', 'voice_id': voice_id}, status=200)
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)
	
	return JsonResponse({'error': 'Invalid request'}, status=400)

def synthesize_description_to_audio(text, voice_id, filename, max_wait=5):
	tts = gTTS(text=text, lang='es')
	tts.save(filename)