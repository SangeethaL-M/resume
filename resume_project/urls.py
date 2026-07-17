from django.contrib import admin
from django.urls import path
from core.views import resume_builder, render_preview

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', resume_builder, name='resume_builder'),
    path('preview/', render_preview, name='resume_preview'),
]