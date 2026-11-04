from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, Conversation, Query, Answer, History


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin untuk model User custom."""

    list_display = ["id", "username", "email", "role", "is_active", "is_staff", "created_at"]
    list_filter = ["role", "is_active", "is_staff", "is_superuser"]
    search_fields = ["username", "email"]
    ordering = ["-created_at"]

    fieldsets = (
        (None, {"fields": ("username", "email", "password")}),
        ("Personal info", {"fields": ("role",)}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2", "role"),
            },
        ),
    )

    readonly_fields = ["created_at", "updated_at"]


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    """Admin untuk model Conversation."""

    list_display = ["id", "title", "user", "created_at", "updated_at"]
    list_filter = ["created_at", "updated_at"]
    search_fields = ["title", "user__email"]
    ordering = ["-updated_at"]
    readonly_fields = ["created_at", "updated_at"]

    def user(self, obj):
        return obj.user.email
