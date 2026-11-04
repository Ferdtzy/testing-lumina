from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AskView, QueryViewSet, AnswerViewSet, HistoryViewSet, ConversationViewSet

router = DefaultRouter()
router.register(r"conversations", ConversationViewSet, basename="conversation")
router.register(r"queries", QueryViewSet, basename="query")
router.register(r"answers", AnswerViewSet, basename="answer")
router.register(r"history", HistoryViewSet, basename="history")

urlpatterns = [
    path("ask/", AskView.as_view(), name="ask"),
    path("", include(router.urls)),
]
