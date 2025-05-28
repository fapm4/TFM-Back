from django.urls import path
from . import views

urlpatterns = [
    path('get_voices/<str:lang>/<str:tone>/', views.get_voices, name='get_voices'),
    path('text_to_speech/<str:voice_id>/', views.text_to_speech, name='text_to_speech'),
]