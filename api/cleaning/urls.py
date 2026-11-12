from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("clean/", views.clean_view),
]
