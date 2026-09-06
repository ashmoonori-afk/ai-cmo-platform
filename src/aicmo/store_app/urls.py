from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from aicmo.store_app import views

urlpatterns = [
    path("", views.home, name="home"),
    path(
        "login/", auth_views.LoginView.as_view(template_name="store_app/login.html"), name="login"
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("operator/", admin.site.urls),
    path("stores/<int:store_id>/new/", views.create, name="create"),
    path("jobs/<uuid:job_id>/", views.detail, name="job"),
    path("jobs/<uuid:job_id>/approve/", views.approve, name="approve"),
    path("jobs/<uuid:job_id>/cancel/", views.cancel, name="cancel"),
    path("jobs/<uuid:job_id>/download/", views.download, name="download"),
]
