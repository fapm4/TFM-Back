from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
import os
from django.conf import settings
import subprocess
from django.http import JsonResponse
from datetime import timedelta
import ffmpeg
import re
import json
import av
import torch
import numpy as np
import cv2
from transformers import LlavaNextVideoProcessor, LlavaNextVideoForConditionalGeneration

from tts.views import synthesize_description_to_audio

# model_id = "llava-hf/LLaVA-NeXT-Video-7B-hf"

# model = LlavaNextVideoForConditionalGeneration.from_pretrained(
# 	model_id, 
# 	torch_dtype=torch.float16, 
# 	low_cpu_mem_usage=True, 
# ).to('mps')

# print(torch.device('mps'))

# processor = LlavaNextVideoProcessor.from_pretrained(model_id)

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
			'video_id': video.id
		}, status=200)

	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)

################################################################################################################
## Delete description
@csrf_exempt
def delete_description(req, video_id, description_id):
	# Eliminar una descripción específica
	try:
		description = Description.objects.get(id=description_id, video_id=video_id)
		description.delete()
		return JsonResponse({'message': 'Description deleted successfully'}, status=200)
	except Description.DoesNotExist:
		return JsonResponse({'error': 'Description not found'}, status=404)
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from datetime import timedelta
import json

@csrf_exempt
def update_time_description(req, video_id, description_id):
	if req.method == 'PUT':
		try:
			description = Description.objects.get(id=description_id, video_id=video_id)
			body = req.body.decode('utf-8')
			data = json.loads(body)

			key = data['type']
			time = data['value']

			def parse_hhmmss_to_timedelta(hhmmss_str):
				h, m, s = map(int, hhmmss_str.split(":"))
				return timedelta(hours=h, minutes=m, seconds=s)

			if key == 'start_at':
				description.start_at = parse_hhmmss_to_timedelta(time)
			elif key == 'end_at':
				description.end_at = parse_hhmmss_to_timedelta(time)
			
			description.duration = description.end_at - description.start_at
			description.save()
			return JsonResponse({'message': 'Description updated successfully'}, status=200)
		except Description.DoesNotExist:
			return JsonResponse({'error': 'Description not found'}, status=404)
		except json.JSONDecodeError:
			return JsonResponse({'error': 'Invalid JSON data'}, status=400)
		except Exception as e:
			print(f"Error: {e}")
			return JsonResponse({'error': str(e)}, status=500)
		

@csrf_exempt
def update_description(req, video_id, description_id):
	if req.method == 'PUT':
		try:
			description = Description.objects.get(id=description_id, video_id=video_id)
			body = req.body.decode('utf-8')
			data = json.loads(body)

			print(f"Received data: {data} | {data['description']}")
			description_text = data['description']
			description.description = description_text
			description.save()
			return JsonResponse({'message': 'Description updated successfully'}, status=200)
		except Description.DoesNotExist:
			return JsonResponse({'error': 'Description not found'}, status=404)
		except json.JSONDecodeError:
			return JsonResponse({'error': 'Invalid JSON data'}, status=400) 
		except Exception as e:
			print(f"Error: {e}")
			return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def add_description(req, video_id):
	if req.method == 'POST':
		try:
			video = Video.objects.get(id=video_id)
			body = req.body.decode('utf-8')
			data = json.loads(body)

			start_str = data['start_at']
			end_str = data['end_at']

			def parse_hhmmss_to_timedelta(hhmmss_str):
				h, m, s = map(int, hhmmss_str.split(":"))
				return timedelta(hours=h, minutes=m, seconds=s)

			start_at = parse_hhmmss_to_timedelta(start_str)
			end_at = parse_hhmmss_to_timedelta(end_str)
			duration = end_at - start_at

			new_description = Description(
				video=video,
				start_at=start_at,
				end_at=end_at,
				duration=duration,
				description=""
			)

			new_description.save()
			return JsonResponse({'message': 'Description added successfully'}, status=200)
		except Video.DoesNotExist:
			return JsonResponse({'error': 'Video not found'}, status=404)
		except json.JSONDecodeError:
			return JsonResponse({'error': 'Invalid JSON data'}, status=400)
		except Exception as e:
			print(f"Error: {e}")
			return JsonResponse({'error': str(e)}, status=500)
	return JsonResponse({'error': 'Invalid request method'}, status=405)

def get_video_stats(req, video_id):
	video = Video.objects.filter(id=video_id).first()

	video_title = video.title if video else "Unknown Video"
	video_file_path = video.video_file.url if video and video.video_file else None
	option_selected = video.option_selected if video else "Unknown Option"
	threhold_selected = video.threshold_selected if video else "Unknown Threshold"
	threshold_value = video.threshold_value if video else "Unknown Threshold Value"
	lang = video.lang if video else "Unknown Language"
	tone = video.tone if video else "Unknown Tone"
	voice_id = video.voice_id if video else "Unknown Voice ID"
	audio_url = video.audio_file.url if video and video.audio_file else None
	descriptions = Description.objects.filter(video=video) if video else []


	stats = {
		'video_title': video_title,
		'video_file_path': video_file_path,
		'option_selected': option_selected,
		'threshold_selected': threhold_selected,
		'threshold_value': threshold_value,
		'descriptions': [
			{
				'id': desc.id,
				'start_at': str(desc.start_at),
				'end_at': str(desc.end_at),
				'duration': str(desc.duration),
				'description': desc.description
			} for desc in descriptions
		],
		'lang': lang,
		'tone': tone,
		'voice_id': voice_id,
		'audio_url': audio_url
	}

	return JsonResponse(stats, status=200)

def read_video_pyav(container, indices, size=(336, 336)):
	frames = []
	container.seek(0)
	start_index = indices[0]
	end_index = indices[-1]
	for i, frame in enumerate(container.decode(video=0)):
		if i > end_index:
			break
		if i >= start_index and i in indices:
			img = frame.to_ndarray(format="rgb24")
			img = cv2.resize(img, size)
			frames.append(img)
	return np.stack(frames)

def generate_descriptions(req, video_id):
	try:
		video = Video.objects.get(id=video_id)
		descriptions = Description.objects.filter(video=video)
		container = av.open(video.video_file)
		stream = container.streams.video[0]
		fps = float(stream.average_rate)

		for desc in descriptions:
			start_sec = desc.start_at.total_seconds()
			end_sec = desc.end_at.total_seconds()
			start_frame = int(start_sec * fps)
			end_frame = int(end_sec * fps)
			indices = np.linspace(start_frame, end_frame, num=8).astype(int)

			clip = read_video_pyav(container, indices, size=(336, 336))  # resized
			conversation = [{
				"role": "user",
				"content": [
					{"type": "text", "text": f"Describe brevemente qué se muestra visualmente en este segmento del video ({start_sec:.1f}s a {end_sec:.1f}s), en español. Usa una sola frase corta."},
					{"type": "video"}
				],
			}]

			prompt = processor.apply_chat_template(conversation, add_generation_prompt=True)
			inputs = processor(text=prompt, videos=clip, padding=True, return_tensors="pt").to(model.device)

			output = model.generate(**inputs, max_new_tokens=1000, do_sample=False)
			text = processor.decode(output[0], skip_special_tokens=True)
			
			if "ASSISTANT:" in text:
				text = text.split("ASSISTANT:")[-1].strip()

			text = text.split("\n")[0].strip()

			desc.description = text
			desc.save()

		return JsonResponse({'message': 'Descriptions generated successfully'}, status=200)

	except Video.DoesNotExist:
		return JsonResponse({'error': 'Video not found'}, status=404)
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def add_descriptions_to_video(req, video_id):
    try:
        video = Video.objects.get(id=video_id)
        voice_id = video.voice_id
        descriptions = Description.objects.filter(video=video)

        if not descriptions.exists():
            return JsonResponse({'error': 'No descriptions found for this video'}, status=404)

        video_folder = os.path.dirname(video.video_file.path)
        audio_paths = []
        input_files = ""
        adelay_filters = ""
        amix_inputs = ""

        # 1. Síntesis de cada descripción
        for i, desc in enumerate(descriptions):
            audio_filename = f"desc_{desc.id}.mp3"
            audio_path = os.path.join(video_folder, audio_filename)
            start_ms = int(desc.start_at.total_seconds() * 1000)

            synthesize_description_to_audio(desc.description, voice_id, audio_path)

            audio_paths.append(audio_path)
            input_files += f'-i "{audio_path}" '
            adelay_filters += f"[{i}:a]adelay={start_ms}|{start_ms}[a{i}];"
            amix_inputs += f"[a{i}]"

        # 2. Generar narración final
        final_audio_path = os.path.join(video_folder, f"{video.title}_narration.mp3")
        final_video_path = os.path.join(video_folder, f"{video.title}_with_audio.mp4")

        filter_complex = f'{adelay_filters} {amix_inputs}amix=inputs={len(descriptions)}[aout]'

        cmd_audio = f'''
        ffmpeg {input_files} -filter_complex "{filter_complex}" -map "[aout]" -y "{final_audio_path}"
        '''

        audio_result = subprocess.run(cmd_audio, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if audio_result.returncode != 0:
            return JsonResponse({'error': 'Failed to generate audio narration', 'details': audio_result.stderr.decode()}, status=500)

        # 3. Reemplazar audio original por narración
        cmd_video = f'''
        ffmpeg -i "{video.video_file.path}" -i "{final_audio_path}" -c:v copy -map 0:v:0 -map 1:a:0 -shortest -y "{final_video_path}"
        '''

        video_result = subprocess.run(cmd_video, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if video_result.returncode != 0:
            return JsonResponse({'error': 'Failed to combine video with audio', 'details': video_result.stderr.decode()}, status=500)

        # 4. Limpieza
        for path in audio_paths:
            os.remove(path)

        return JsonResponse({
            'message': 'Narration added to video successfully',
            'final_video': final_video_path
        }, status=200)

    except Video.DoesNotExist:
        return JsonResponse({'error': 'Video not found'}, status=404)
    except Exception as e:
        print(f"Error: {e}")
        return JsonResponse({'error': str(e)}, status=500)