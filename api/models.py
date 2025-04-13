from django.db import models
from base.settings import MEDIA_URL, MEDIA_ROOT

import os
def video_upload_to(instance, filename):
    file_name_without_extension = os.path.splitext(filename)[0]
    folder_path = file_name_without_extension
    return os.path.join(folder_path, filename)

class Video(models.Model):
    video_file = models.FileField(upload_to=video_upload_to)
    title = models.CharField(max_length=100)
    option_selected = models.CharField(max_length=100, default='option1_grabar')
    threshold_selected = models.CharField(max_length=100, null=True, blank=True)
    threshold_value = models.FloatField(null=True, blank=True)
    lang = models.CharField(max_length=50, null=True, blank=True)
    tone = models.CharField(max_length=50, null=True, blank=True)
    lang_name = models.CharField(max_length=100, null=True, blank=True)
    voice_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Description(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='descriptions')
    description = models.TextField()
    start_at = models.DurationField()  # Usar DurationField para duración
    end_at = models.DurationField()    # Usar DurationField para duración
    created_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=100, default='')


    def __str__(self):
        return f"Description for {self.video.title} from {self.start_at} to {self.end_at}"
 