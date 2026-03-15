from django import forms
from .models import User, Address

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['full_name', 'email', 'mobile', 'dob', 'gender', 'avatar']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control profile-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-control profile-input'}),
            'mobile': forms.TextInput(attrs={'class': 'form-control profile-input'}),
            'dob': forms.DateInput(attrs={'type': 'date', 'class': 'form-control profile-input'}),
            'gender': forms.Select(attrs={'class': 'form-select profile-input'}, choices=[('Male','Male'),('Female','Female'),('Other','Other')]),
            'avatar': forms.FileInput(attrs={'class': 'form-control profile-input'}),
        }

class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ['full_name', 'phone', 'street_address', 'city', 'state', 'country', 'postal_code', 'address_type', 'is_default']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'street_address': forms.Textarea(attrs={'class': 'form-control', 'rows':2}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'address_type': forms.Select(attrs={'class': 'form-select'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }