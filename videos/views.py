import tempfile
from django.core.files import File
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import subprocess
from django.http import JsonResponse
from datetime import timedelta
import json
import ffmpeg
import re
import json
import os
from tts.views import synthesize_description_to_audio
import numpy as np
import shutil
import time
## Mis paquetes

from .silence_detection import extract_audio, detect_silences
from .models import Video, Description

################################################################################################################
## Subir archivo de video

def parse_seconds_to_hhmmss(seconds):
    total_seconds = int(seconds)  # truncar o usar round(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"

def delete_existent(filename):
	record = Video.objects.filter(title=filename)

	if record.exists():

		video = record.first()
		video_file_path = os.path.join(settings.MEDIA_ROOT, str(video.video_file))
		
		if os.path.exists(video_file_path):
			os.remove(video_file_path)

		video_folder = os.path.dirname(video_file_path)
		
		if os.path.exists(video_folder):
			try:
				shutil.rmtree(video_folder)
				print(f"Carpeta eliminada: {video_folder}")
			except Exception as e:
				print(f"Error al borrar la carpeta: {e}")
		
		video.delete()

@csrf_exempt
def upload_file(req):
	try:
		if req.method == 'POST':
			if 'file' in req.FILES:
				start_time = time.time()
				file = req.FILES['file']
				
				delete_existent(file.name)

				option_selected = req.POST.get('optionSelected')
				threshold_selected = req.POST.get('thresholdSelected')
				threshold_value = None
				
				if threshold_selected == 'option5_thresh_manual':
					threshold_value = req.POST.get('thresholdValue')

				voice_id = None

				if option_selected != 'option1_grabar':
					voice_id = req.POST.get('voice_id')
				
				new_video = Video(
					video_file=file,
					title=file.name,
					option_selected=option_selected,
					threshold_selected=threshold_selected,
					threshold_value=threshold_value,
					voice_id=voice_id
				)

				new_video.save()
				end_time = time.time()
				print(f"---------------------------- Video {file.name} uploaded successfully in {parse_seconds_to_hhmmss(end_time - start_time)} seconds")

				return JsonResponse({'message': 'File uploaded successfully', 'video_id': new_video.id}, status=200)
			
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)
	
	return JsonResponse({'error': 'Invalid request'}, status=400)

def get_silences(req, video_id): 
	try:
		start_time = time.time()
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

		end_time = time.time()
		print(f"---------------------------- Silences detected successfully in {parse_seconds_to_hhmmss(end_time - start_time)} seconds")
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

@csrf_exempt
def update_time_description(req, video_id, description_id):
	if req.method == 'PUT':
		all_descriptions = Description.objects.filter(video_id=video_id)

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

			for desc in all_descriptions:
				if desc.id != description.id:
					if (description.start_at < desc.end_at and description.end_at > desc.start_at):
						return JsonResponse({'error': 'Time overlap with another description'}, status=409)

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
		
def estimate_duration_from_text(text, wpm=150):
	words = len(text.split())
	seconds = (words / wpm) * 60
	return round(seconds, 2)

def gen_temp_file(text):
	temp_file = 'temp_description.mp3'
	synthesize_description_to_audio(text, 'es', temp_file)
	file_time_duration = ffmpeg.probe(temp_file)['format']['duration']

	return timedelta(seconds=float(file_time_duration))

def delete_temp_file():
	# Eliminar archivo temporal si existe
	if os.path.exists('temp_description.mp3'):
		os.remove('temp_description.mp3')
		print("Archivo temporal eliminado.")
	else:
		print("No se encontró el archivo temporal para eliminar.")

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
		
			description.real_audio_duration = gen_temp_file(description_text)
			description.save()

			# Eliminar archivo temporal
			delete_temp_file()

			return JsonResponse({'message': 'Description updated successfully', 'real_audio_duration': description.real_audio_duration}, status=200)
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

@csrf_exempt
def add_audio_description(req, video_id, description_id):
	if req.method != 'POST':
		return JsonResponse({'error': 'Only POST allowed'}, status=405)

	try:
		description = Description.objects.get(id=description_id, video_id=video_id)
		audio_blob = req.FILES.get('audio')

		if not audio_blob:
			return JsonResponse({'error': 'No audio file provided'}, status=400)

		# Guardar el archivo temporalmente
		with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_input:
			for chunk in audio_blob.chunks():
				temp_input.write(chunk)
			temp_input_path = temp_input.name

		# Definir ruta de salida temporal en .mp4
		with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_output:
			temp_output_path = temp_output.name

		# Convertir a .mp4 usando FFmpeg
		ffmpeg_cmd = f'ffmpeg -y -i "{temp_input_path}" -c:a aac -b:a 128k "{temp_output_path}"'
		result = subprocess.run(ffmpeg_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

		if result.returncode != 0:
			return JsonResponse({'error': 'Audio conversion failed', 'details': result.stderr.decode()}, status=500)

		# Eliminar el archivo anterior si existe
		if description.audio_file and os.path.isfile(description.audio_file.path):
			os.remove(description.audio_file.path)

		# Guardar archivo convertido con nombre basado en ID
		final_name = f"desc_{description_id}.mp4"
		with open(temp_output_path, 'rb') as f:
			django_file = File(f)
			description.audio_file.save(final_name, django_file, save=True)
			file_time_duration = ffmpeg.probe(temp_output_path)['format']['duration']
		# Actualizar duración del audio
		description.real_audio_duration = timedelta(seconds=float(file_time_duration))
		description.save()

		return JsonResponse({'message': 'Audio description updated successfully', 'duration': file_time_duration}, status=200)

	except Description.DoesNotExist:
		return JsonResponse({'error': 'Description not found'}, status=404)
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)

		
def get_audio_description(req, video_id, description_id):
	try:
		description = Description.objects.get(id=description_id, video_id=video_id)

		audio_url = description.audio_file.url if description.audio_file else None

		return JsonResponse({
			'description_id': description.id,
			'audio_file': audio_url,
			'text': description.description,
		})

	except Description.DoesNotExist:
		return JsonResponse({'error': 'Description not found'}, status=404)
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)

def get_video_stats(req, video_id):
	video = Video.objects.filter(id=video_id).first()

	video_title = video.title if video else "Unknown Video"
	video_file_path = video.video_file.url if video and video.video_file else None
	option_selected = video.option_selected if video else "Unknown Option"
	threhold_selected = video.threshold_selected if video else "Unknown Threshold"
	threshold_value = video.threshold_value if video else "Unknown Threshold Value"
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
				'description': desc.description,
				'real_audio_duration': str(desc.real_audio_duration) if desc.real_audio_duration else None,
			} for desc in descriptions
		],
		'voice_id': voice_id,
		'audio_url': audio_url
	}

	return JsonResponse(stats, status=200)


from .llava_description import open_container, generate_description

def generate_descriptions(req, video_id):
	try:
		start_time = time.time()
		video = Video.objects.get(id=video_id)
		descriptions = Description.objects.filter(video=video)
		container = open_container(video.video_file)
		stream = container.streams.video[0]
		fps = float(stream.average_rate)

		for desc in descriptions:
			start_sec = desc.start_at.total_seconds()
			end_sec = desc.end_at.total_seconds()
			start_frame = int(start_sec * fps)
			end_frame = int(end_sec * fps)
			indices = np.linspace(start_frame, end_frame, num=8).astype(int)

			text = generate_description(container, indices, start_sec, end_sec)
			desc.real_audio_duration = gen_temp_file(text)

			delete_temp_file()

			desc.description = text
			desc.save()

		end_time = time.time()
		print(f"---------------------------- Descriptions generated successfully in {parse_seconds_to_hhmmss(end_time - start_time)} seconds")

		return JsonResponse({'message': 'Descriptions generated successfully'}, status=200)

	except Video.DoesNotExist:
		return JsonResponse({'error': 'Video not found'}, status=404)
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def add_descriptions_to_video(req, video_id):
	try:
		start_time = time.time()
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

		input_index = 0  # Contador solo para las entradas reales que se añaden

		for desc in descriptions:
			audio_filename = f"desc_{desc.id}.mp3"
			audio_path = os.path.join(video_folder, audio_filename)
			start_ms = int(desc.start_at.total_seconds() * 1000)

			if video.option_selected != 'option1_grabar':
				# 1. Generar audio con TTS
				synthesize_description_to_audio(desc.description, voice_id, audio_path)

				# 2. Preparar entrada FFmpeg
				audio_paths.append(audio_path)
				input_files += f'-i "{audio_path}" '
				adelay_filters += f"[{input_index}:a]adelay={start_ms}|{start_ms}[a{input_index}];"
				amix_inputs += f"[a{input_index}]"
				input_index += 1

			else:
				if desc.audio_file:
					audio_file_path = desc.audio_file.path

					# 1. Usar archivo de audio existente
					audio_paths.append(audio_file_path)
					input_files += f'-i "{audio_file_path}" '
					adelay_filters += f"[{input_index}:a]adelay={start_ms}|{start_ms}[a{input_index}];"
					amix_inputs += f"[a{input_index}]"
					input_index += 1

		if input_index == 0:
			return JsonResponse({'error': 'No valid audio files or TTS generated'}, status=400)

		# 3. Crear archivo de narración final
		final_audio_filename = f"{video.title}_narration.mp3"
		final_video_filename = f"{video.title}_with_audio.mp4"
		final_audio_path = os.path.join(video_folder, final_audio_filename)
		final_video_path = os.path.join(video_folder, final_video_filename)

		filter_complex = f'{adelay_filters}{amix_inputs}amix=inputs={input_index}:duration=longest[aout]'

		cmd_audio = f'''
		ffmpeg {input_files} -filter_complex "{filter_complex}" -map "[aout]" -y "{final_audio_path}"
		'''

		# Ejecutar FFmpeg para generar la pista de audio final
		audio_result = subprocess.run(cmd_audio, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		if audio_result.returncode != 0:
			print("FFmpeg stdout:", audio_result.stdout.decode())
			print("FFmpeg stderr:", audio_result.stderr.decode())
			return JsonResponse({
				'error': 'Failed to generate audio narration',
				'details': audio_result.stderr.decode()
			}, status=500)

		# 4. Reemplazar el audio del video original por el generado
		# Extraer el audio original
		original_audio_path = os.path.join(video_folder, "original_audio.mp3")
		cmd_extract_audio = f'''
		ffmpeg -i "{video.video_file.path}" -q:a 0 -map a -y "{original_audio_path}"
		'''
		subprocess.run(cmd_extract_audio, shell=True)

		# Mezclar narración + audio original
		mixed_audio_path = os.path.join(video_folder, "final_mix.mp3")
		cmd_mix_audio = f'''
		ffmpeg -i "{original_audio_path}" -i "{final_audio_path}" -filter_complex "[0:a][1:a]amix=inputs=2:duration=longest" -y "{mixed_audio_path}"
		'''
		mix_result = subprocess.run(cmd_mix_audio, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		if mix_result.returncode != 0:
			print("Mixing audio failed")
			print(mix_result.stderr.decode())
			return JsonResponse({'error': 'Failed to mix audio with narration'}, status=500)

		# Reinsertar audio mezclado al video
		# cmd_video = f'''
		# ffmpeg -i "{video.video_file.path}" -i "{mixed_audio_path}" -c:v copy -map 0:v:0 -map 1:a:0 -y "{final_video_path}"
		# '''
		cmd_video = f'''
		ffmpeg -i "{video.video_file.path}" -i "{mixed_audio_path}" -c:v copy -c:a aac -b:a 192k -map 0:v:0 -map 1:a:0 -shortest -y "{final_video_path}"
		'''

		# 6. Ejecutar FFmpeg para generar el video final
		video_result = subprocess.run(cmd_video, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		if video_result.returncode != 0:
			print("FFmpeg stdout:", video_result.stdout.decode())
			print("FFmpeg stderr:", video_result.stderr.decode())
			return JsonResponse({
				'error': 'Failed to generate final video with narration',
				'details': video_result.stderr.decode()
			}, status=500)
		
		# 5. Guardar rutas relativas
		rel_video_path = os.path.relpath(final_video_path, settings.MEDIA_ROOT)
		rel_audio_path = os.path.relpath(final_audio_path, settings.MEDIA_ROOT)

		video.modified_video_file.name = rel_video_path
		video.modified_audio_file.name = rel_audio_path
		video.modified = True
		video.modified_at = video.modified_at or video.created_at
		video.save()

		end_time = time.time()
		print(f"---------------------------- Narration added to video successfully in {parse_seconds_to_hhmmss(end_time - start_time)} seconds")
		print(f'Found {len(descriptions)} descriptions for video {video_id}')

		return JsonResponse({
			'message': 'Narration added to video successfully',
			'final_video': video.modified_video_file.url
		}, status=200)

	except Video.DoesNotExist:
		return JsonResponse({'error': 'Video not found'}, status=404)
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)

	
def format_vtt_timestamp(td):
	total_seconds = int(td.total_seconds())
	milliseconds = int((td.total_seconds() - total_seconds) * 1000)
	hours = total_seconds // 3600
	minutes = (total_seconds % 3600) // 60
	seconds = total_seconds % 60
	return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"

def generate_webvtt_from_descriptions(descriptions, video_id, folder):
	webvtt_content = "WEBVTT\n\n"
	for desc in descriptions:
		start = format_vtt_timestamp(desc.start_at)
		end = format_vtt_timestamp(desc.end_at)
		webvtt_content += f"{start} --> {end}\n{desc.description.strip()}\n\n"

	webvtt_filename = f"video_{video_id}_descriptions.vtt"
	webvtt_path = os.path.join(folder, webvtt_filename)

	with open(webvtt_path, 'w', encoding='utf-8') as f:
		f.write(webvtt_content)

	return webvtt_path

def get_modified_video(req, video_id):
	try:
		video = Video.objects.get(id=video_id)

		if not video.modified or not video.modified_video_file:
			return JsonResponse({'error': 'Video has not been modified yet'}, status=404)

		# Generar WebVTT si no existe
		if not video.web_vtt_file:
			descriptions = Description.objects.filter(video=video)
			if not descriptions.exists():
				return JsonResponse({'error': 'No descriptions to generate WebVTT'}, status=404)

			video_folder = os.path.dirname(video.video_file.path)
			webvtt_path = generate_webvtt_from_descriptions(descriptions, video_id, video_folder)

			# Guardar ruta relativa
			relative_path = os.path.relpath(webvtt_path, settings.MEDIA_ROOT)
			video.web_vtt_file.name = relative_path
			video.save()

		return JsonResponse({
			'video_id': video.id,
			'video_file_url': req.build_absolute_uri(video.modified_video_file.url),
			'audio_file_url': req.build_absolute_uri(video.modified_audio_file.url) if video.modified_audio_file else None,
			'web_vtt_file_url': req.build_absolute_uri(video.web_vtt_file.url) if video.web_vtt_file else None
		}, status=200)

	except Video.DoesNotExist:
		return JsonResponse({'error': 'Video not found'}, status=404)
	except Exception as e:
		print(f"Error: {e}")
		return JsonResponse({'error': str(e)}, status=500)
	
@csrf_exempt
def upload_vtt(req, video_id):
	if req.method == 'POST':
		video = Video.objects.get(id=video_id)
		if not video:
			return JsonResponse({'error': 'Video not found'}, status=404)

		vtt_file = req.FILES.get('vtt_file')
		content = vtt_file.read().decode('utf-8')

		if not content.startswith("WEBVTT"):
			return JsonResponse({'error': 'Invalid VTT file: must start with "WEBVTT"'}, status=400)

		Description.objects.filter(video=video).delete()

		blocks = re.split(r'\n\n+', content)
		for block in blocks:
			lines = block.strip().splitlines()
			if len(lines) >= 2 and "-->" in lines[0]:
				times = lines[0].split(" --> ")
				if len(times) != 2:
					raise ValueError(f'Invalid timestamp format: {lines[0]}')

				start_str, end_str = times[0].strip(), times[1].strip()

				def parse_vtt_time(tstr):
					match = re.match(r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})", tstr)
					if not match:
						raise ValueError(f'Invalid time format: {tstr}')
					h, m, s, ms = map(int, match.groups())
					return timedelta(hours=h, minutes=m, seconds=s, milliseconds=ms)

				start_at = parse_vtt_time(start_str)
				end_at = parse_vtt_time(end_str)
				duration = end_at - start_at
				description_text = "\n".join(lines[1:]).strip()
				real_audio_duration = gen_temp_file(description_text)

				# Crear descripción
				Description.objects.create(
					video=video,
					start_at=start_at,
					end_at=end_at,
					duration=duration,
					description=description_text,
					real_audio_duration=real_audio_duration
				)

				delete_temp_file()

		return JsonResponse({'message': 'VTT file uploaded and descriptions parsed'}, status=200)


	return JsonResponse({'error': 'Invalid request method'}, status=405)