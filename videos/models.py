# Create your models here.
from django.db import models
from base.settings import MEDIA_URL, MEDIA_ROOT
import os

def video_upload_to(instance, filename):
    file_name_without_extension = os.path.splitext(filename)[0]
    folder_path = file_name_without_extension
    return os.path.join(folder_path, filename)

def description_audio_upload_to(instance, filename):
    video_file_path = instance.video.video_file.name
    video_folder = os.path.dirname(video_file_path)
    return os.path.join(video_folder, 'audio_descriptions', filename)

class Video(models.Model):
    video_file = models.FileField(upload_to=video_upload_to)
    title = models.CharField(max_length=100)
    option_selected = models.CharField(max_length=100, default='option1_grabar')
    threshold_selected = models.CharField(max_length=100, null=True, blank=True)
    threshold_value = models.FloatField(null=True, blank=True)
    voice_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    audio_file = models.FileField(upload_to=video_upload_to, null=True, blank=True)

    modified_video_file = models.FileField(upload_to=video_upload_to, null=True, blank=True)
    modified_audio_file = models.FileField(upload_to=video_upload_to, null=True, blank=True)
    modified = models.BooleanField(default=False)
    modified_at = models.DateTimeField(null=True, blank=True)

    web_vtt_file = models.FileField(upload_to=video_upload_to, null=True, blank=True)

    def __str__(self):
        return self.title

class Description(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='descriptions')
    description = models.TextField()
    start_at = models.DurationField()
    end_at = models.DurationField()
    duration = models.DurationField()
    created_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=100, default='')
    audio_file = models.FileField(upload_to=description_audio_upload_to, blank=True, null=True)
    real_audio_duration = models.DurationField(null=True, blank=True)

    def __str__(self):
        return f"Description for {self.video.title} from {self.start_at} to {self.end_at}"