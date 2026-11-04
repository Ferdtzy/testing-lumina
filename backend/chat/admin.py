from django.contrib import admin

from core.models import Query, Answer, History


@admin.register(Query)
class QueryAdmin(admin.ModelAdmin):
    list_display = ["id", "query_title", "user", "status", "response_time_ms", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["query_text", "query_title", "user__username", "user__email"]
    readonly_fields = ["created_at", "updated_at", "deleted_at"]


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ["id", "query", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["query__query_text", "query__query_title", "answer_text"]
    readonly_fields = ["created_at", "updated_at", "deleted_at"]


@admin.register(History)
class HistoryAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "query", "answer"]
    search_fields = ["user__username", "user__email", "query__query_text", "answer__answer_text"]