"""Serializers untuk endpoint autentikasi Lumina (token-based)."""

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Data user publik untuk respons login/register/me."""

    class Meta:
        model = User
        fields = ["id", "email", "username", "role", "is_staff", "created_at"]
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    """Validasi & pembuatan user baru."""

    username = serializers.CharField(max_length=255, trim_whitespace=True)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email sudah terdaftar.")
        return value

    def validate_username(self, value: str) -> str:
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Username sudah digunakan.")
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Konfirmasi password tidak cocok."}
            )
        validate_password(attrs["password"], user=User(username=attrs["username"], email=attrs["email"]))
        return attrs

    def create(self, validated_data: dict) -> User:
        validated_data.pop("password_confirm")
        return User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["username"],
            password=validated_data["password"],
        )


class LoginSerializer(serializers.Serializer):
    """Validasi kredensial login."""

    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs: dict) -> dict:
        email = (attrs.get("email") or "").strip().lower()
        user = authenticate(username=email, password=attrs.get("password") or "")
        if user is None:
            raise serializers.ValidationError("Email atau password salah.")
        if not user.is_active:
            raise serializers.ValidationError("Akun Anda dinonaktifkan.")
        attrs["user"] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    """Validasi ganti password untuk user yang sudah login."""

    old_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(min_length=8)
    confirm_password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs: dict) -> dict:
        user = self.context["request"].user
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError({"old_password": "Password lama salah."})
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Konfirmasi password tidak cocok."}
            )
        if attrs["new_password"] == attrs["old_password"]:
            raise serializers.ValidationError(
                {"new_password": "Password baru harus berbeda dari password lama."}
            )
        validate_password(attrs["new_password"], user=user)
        return attrs
