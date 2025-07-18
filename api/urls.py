from django.urls import path, include
from . import views

urlpatterns = [
    path('api/videos/', include('videos.urls')),
    path('api/tts/', include('tts.urls')),
]
