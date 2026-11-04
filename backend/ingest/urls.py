"""
urls.py — URL routing for the ingest app.
"""

from django.urls import path

from .views import IngestUploadView, IngestStatusView, IngestViewSet

urlpatterns = [
    path("ingest/upload/", IngestUploadView.as_view(), name="ingest-upload"),
    path("ingest/status/<int:document_id>/", IngestStatusView.as_view(), name="ingest-status"),
    path("ingest/<int:pk>/re-ingest/", IngestViewSet.as_view({"post": "re_ingest"}), name="ingest-re-ingest"),
]
