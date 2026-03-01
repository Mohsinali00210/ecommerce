from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User
from .utils import send_verification_email

class EmailRegisterSerializer(serializers.ModelSerializer):
    confirmPassword = serializers.CharField(write_only=True)
    acceptTerms = serializers.BooleanField(write_only=True)
    tokens = serializers.SerializerMethodField(read_only=True)

    fullName = serializers.CharField(source='first_name')

    class Meta:
        model = User
        fields = (
            'fullName',
            'email',
            'mobile',
            'password',
            'confirmPassword',
            'acceptTerms',
            'tokens',
        )
        extra_kwargs = {'password': {'write_only': True}}

    def validate(self, data):
        if data['password'] != data['confirmPassword']:
            raise serializers.ValidationError("Passwords do not match")
        if not data['acceptTerms']:
            raise serializers.ValidationError("You must accept terms & conditions")
        validate_password(data['password'])
        return data

    def create(self, validated_data):
        validated_data.pop('confirmPassword')
        validated_data.pop('acceptTerms')

        password = validated_data.pop('password')
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.is_active = True
        user.generate_email_verification()
        user.save()

        send_verification_email(user)
        return user

    def get_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh)
        }
