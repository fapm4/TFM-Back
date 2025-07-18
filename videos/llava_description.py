import av.container
from transformers import LlavaNextVideoProcessor, LlavaNextVideoForConditionalGeneration
import av
import torch
import numpy as np
import cv2
import os
from transformers import LlavaNextVideoProcessor, LlavaNextVideoForConditionalGeneration
from datetime import timedelta

model_id = "llava-hf/LLaVA-NeXT-Video-7B-hf"

model = LlavaNextVideoForConditionalGeneration.from_pretrained(
	model_id, 
	torch_dtype=torch.float16, 
	low_cpu_mem_usage=True, 
).to('mps')

processor = LlavaNextVideoProcessor.from_pretrained(model_id)

def open_container(video_file):
	return av.open(video_file)
	
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


def generate_description(container, indices, start_sec, end_sec):
	print(f'Procesando video con start: {start_sec} - end: {end_sec}')
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

	return text

def generate_description_history(container, indices, start_sec, end_sec, conversation_history=None):
	print(f'Procesando video con start: {start_sec} - end: {end_sec}')
	clip = read_video_pyav(container, indices, size=(336, 336))


	if conversation_history is None:		
		conversation_history = []
	# Crear nuevo mensaje del usuario
	user_message = {
		"role": "user",
		"content": [
			{"type": "text", "text": f"Describe brevemente qué se muestra visualmente en este segmento del video ({start_sec:.1f}s a {end_sec:.1f}s), en español. Usa una sola frase corta."},
			{"type": "video"}
		],
	}

	# Añadir mensaje del usuario al historial
	conversation_history.append(user_message)

	# Preparar prompt
	prompt = processor.apply_chat_template(conversation_history, add_generation_prompt=True)
	inputs = processor(text=prompt, videos=clip, padding=True, return_tensors="pt").to(model.device)

	# Generar respuesta
	output = model.generate(**inputs, max_new_tokens=1000, do_sample=False)

	# Asegurar que sea lista de IDs (batch_size = 1)
	if isinstance(output, (list, tuple)) and isinstance(output[0], (list, torch.Tensor)):
		generated_ids = output[0]
	else:
		generated_ids = output

	# Decodificar
	text = processor.decode(generated_ids, skip_special_tokens=True)

	# Limpiar texto
	if "ASSISTANT:" in text:
		text = text.split("ASSISTANT:")[-1].strip()
	text = text.split("\n")[0].strip()

	# Añadir respuesta al historial
	assistant_message = {
		"role": "assistant",
		"content": text
	}
	conversation_history.append(assistant_message)

	return text, conversation_history



# Hablar de google Trends sobre lo que trabajado
# 30/6/2015

# Icono ayuda
# Tamaño maximo de los videos (subida maxima navegador)
# Seleccionar idioma a través del video


# En la pagina de subida, mostrar la duracion del video

# Ver solapamientos de silencios

# Ordenar silencios

# Mantener conversacion del modelo

# Modularidad

# Tipos de archivos de video

# Es facil de adaptar el codigo

# Probar diferentes tipos de videos -> partido de futobl y pelicula