from django.urls import path, include
from . import views

urlpatterns = [
    path('upload_file/', views.upload_file, name='upload_file'),
    path('get_packages/', views.get_packages, name='get_packages'),
    path('get_voices/<str:lang>/<str:tone>/', views.get_voices, name='get_voices'),
    path('text_to_speech/<str:voice_id>/', views.text_to_speech, name='text_to_speech'),
    path('get_silences/<int:video_id>/', views.get_silences, name='get_silences'),
]
