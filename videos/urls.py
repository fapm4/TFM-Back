from django.urls import path
from . import views
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [
    path('upload_file/', views.upload_file, name='upload_file'),
    path('get_silences/<int:video_id>/', views.get_silences, name='get_silences'),
    path('delete_existent/', views.delete_existent, name='delete_existent'),
    path('delete_description/<int:video_id>/<int:description_id>/', views.delete_description, name='delete_description'),
    path('update_time_description/<int:video_id>/<int:description_id>/', views.update_time_description, name='update_time_description'),
    path('update_description/<int:video_id>/<int:description_id>/', views.update_description, name='update_description'),
    path('add_description/<int:video_id>/', views.add_description, name='add_description'),
    path('get_video_stats/<int:video_id>/', views.get_video_stats, name='get_video_stats'),

    path('generate_descriptions/<int:video_id>/', views.generate_descriptions, name='generate_descriptions'),
    path('add_descriptions_to_video/<int:video_id>/', views.add_descriptions_to_video, name='add_descriptions_to_video'),

    path('get_modified_video/<int:video_id>/', views.get_modified_video, name='get_modified_video'),

    path('add_audio_description/<int:video_id>/<int:description_id>/', views.add_audio_description, name='add_audio_description'),
    path('get_audio_description/<int:video_id>/<int:description_id>/', views.get_audio_description, name='get_audio_description'),

    path('upload_vtt/<int:video_id>/', views.upload_vtt, name='upload_vtt')
]