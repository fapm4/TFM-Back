from django.urls import path
from . import views
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [
    path('upload_file/', views.upload_file, name='upload_file'),
    path('get_silences/<int:video_id>/', views.get_silences, name='get_silences'),
    path('delete_existent/', views.delete_existent, name='delete_existent'),
]