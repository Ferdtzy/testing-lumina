from django.contrib import admin

from core.models import Document, Chunk, IngestLog


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "document_name", "user", "file_type", "size", "status", "created_at"]
    list_filter = ["status", "file_type", "created_at"]
    search_fields = ["document_name", "user__username", "user__email"]
    readonly_fields = ["created_at", "updated_at", "deleted_at"]


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ["id", "document", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["document__document_name", "chunk_text"]
    readonly_fields = ["created_at", "updated_at", "deleted_at"]


@admin.register(IngestLog)
class IngestLogAdmin(admin.ModelAdmin):
    list_display = ["id", "document", "step", "session_id", "created_at"]
    list_filter = ["step", "created_at"]
    search_fields = ["document__document_name", "message"]
    readonly_fields = ["created_at", "updated_at"]