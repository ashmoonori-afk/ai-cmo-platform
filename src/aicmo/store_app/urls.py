from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from aicmo.store_app import (
    archive,
    delivery,
    editor_views,
    feedback_views,
    onboarding_views,
    outcome_views,
    photos,
    publication,
    report_views,
    rewrites,
    views,
)

handler400 = "aicmo.store_app.uploads.upload_bad_request"

urlpatterns = [
    path("", views.home, name="home"),
    path("archive/", archive.index, name="archive"),
    path("onboarding/", onboarding_views.wizard, name="onboarding"),
    path("onboarding/confirm/", onboarding_views.confirmation, name="onboarding-confirm"),
    path("onboarding/<int:step>/", onboarding_views.wizard, name="onboarding-step"),
    path(
        "login/", auth_views.LoginView.as_view(template_name="store_app/login.html"), name="login"
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("operator/", admin.site.urls),
    path("stores/<int:store_id>/new/", views.create, name="create"),
    path("stores/<int:store_id>/outcomes/", outcome_views.index, name="outcomes"),
    path(
        "stores/<int:store_id>/outcomes/preview/",
        outcome_views.preview,
        name="outcomes-preview",
    ),
    path(
        "stores/<int:store_id>/outcomes/confirm/",
        outcome_views.confirm,
        name="outcomes-confirm",
    ),
    path(
        "stores/<int:store_id>/outcomes/report/",
        report_views.request_report,
        name="report-request",
    ),
    path("jobs/<uuid:job_id>/", views.detail, name="job"),
    path("jobs/<uuid:job_id>/report/", report_views.detail, name="report"),
    path("jobs/<uuid:job_id>/report/download/", report_views.download, name="report-download"),
    path("jobs/<uuid:job_id>/report/action/", report_views.action, name="report-action"),
    path("jobs/<uuid:job_id>/feedback/", feedback_views.detail, name="feedback"),
    path("jobs/<uuid:job_id>/feedback/approve/", feedback_views.approve, name="feedback-approve"),
    path("jobs/<uuid:job_id>/feedback/learn/", feedback_views.learn, name="feedback-learn"),
    path(
        "jobs/<uuid:job_id>/feedback/<str:item_key>/",
        feedback_views.create,
        name="feedback-create",
    ),
    path("jobs/<uuid:job_id>/photo/", photos.preview, name="job-photo"),
    path("jobs/<uuid:job_id>/rewrite/", rewrites.rewrite, name="rewrite"),
    path("jobs/<uuid:job_id>/edit/", editor_views.edit, name="edit"),
    path("jobs/<uuid:job_id>/edit/confirm/", editor_views.confirmation, name="edit-confirm"),
    path("jobs/<uuid:job_id>/edit/restore/", editor_views.restore, name="edit-restore"),
    path("jobs/<uuid:job_id>/approve/", views.approve, name="approve"),
    path("jobs/<uuid:job_id>/cancel/", views.cancel, name="cancel"),
    path("jobs/<uuid:job_id>/download/", views.download, name="download"),
    path("jobs/<uuid:job_id>/delivery/", delivery.detail, name="delivery"),
    path(
        "jobs/<uuid:job_id>/publication/<slug:item_key>/",
        publication.record,
        name="publication",
    ),
]
