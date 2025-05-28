from django.urls import path, include
from . import views

urlpatterns = [
    path('api/videos/', include('videos.urls')),
    path('api/tts/', include('tts.urls')),
    # path('get_packages/', views.get_packages, name='get_packages'),
    # path('get_voices/<str:lang>/<str:tone>/', views.get_voices, name='get_voices'),
    # path('text_to_speech/<str:voice_id>/', views.text_to_speech, name='text_to_speech'),
]
